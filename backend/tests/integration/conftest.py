"""Фикстуры для integration/API-тестов.

Реальный Postgres и реальный Redis в контейнерах (отдельные тестовые
инстансы, но настоящие движки), реальный Celery-воркер отдельным
процессом. get_uow переопределён на тестовый UnitOfWork(test_session_maker) —
это не мок бизнес-логики (БД настоящая), а обязательный шаг: штатный DI
берёт engine из app.core.database, созданный один раз при импорте на
основе .env.dev (реальная dev-БД), и monkeypatch.setenv после этого
момента на него уже не действует — без override тесты били бы по dev-БД.
Тестовый engine создаётся с NullPool — без пулинга, каждая сессия своё
соединение, чтобы не делить соединение между разными event loop'ами
pytest-asyncio (иначе asyncpg падает с "another operation is in progress").
"""

import os
import subprocess
import time
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer


@pytest.fixture(scope="session")
def postgres_container():
    """Поднимает Postgres-контейнер (отдельный от прод-инстанса) на всю тестовую сессию.

    Returns:
        PostgresContainer: Запущенный контейнер.
    """
    with PostgresContainer("postgres:16-alpine") as container:
        yield container


@pytest.fixture(scope="session")
def redis_container():
    """Поднимает Redis-контейнер (отдельный от прод-инстанса) на всю тестовую сессию.

    Returns:
        RedisContainer: Запущенный контейнер.
    """
    with RedisContainer() as container:
        yield container


@pytest.fixture(scope="session")
def test_env(postgres_container, redis_container) -> dict[str, str]:
    """Собирает env для тестовой БД/брокера — тот же формат переменных, что читает Settings в проде.

    Args:
        postgres_container (PostgresContainer): Контейнер с поднятым Postgres.
        redis_container (RedisContainer): Контейнер с поднятым Redis.

    Returns:
        dict[str, str]: POSTGRES_*/REDIS_URL для тестового воркера (реальный процесс Celery).
    """
    return {
        "POSTGRES_USER": postgres_container.username,
        "POSTGRES_PASSWORD": postgres_container.password,
        "POSTGRES_HOST": postgres_container.get_container_host_ip(),
        "PGPORT": str(postgres_container.get_exposed_port(5432)),
        "POSTGRES_DB": postgres_container.dbname,
        "REDIS_URL": (
            f"redis://{redis_container.get_container_host_ip()}"
            f":{redis_container.get_exposed_port(6379)}/0"
        ),
    }


def _build_database_url(test_env: dict[str, str]) -> str:
    """Собирает asyncpg-строку подключения из test_env (тот же формат, что Settings.database_url).

    Args:
        test_env (dict[str, str]): Env с параметрами подключения к тестовому Postgres.

    Returns:
        str: Строка подключения SQLAlchemy (async, asyncpg-драйвер).
    """
    return (
        f"postgresql+asyncpg://{test_env['POSTGRES_USER']}:{test_env['POSTGRES_PASSWORD']}"
        f"@{test_env['POSTGRES_HOST']}:{test_env['PGPORT']}/{test_env['POSTGRES_DB']}"
    )


@pytest.fixture
async def test_session_maker(test_env) -> AsyncGenerator[async_sessionmaker, None]:
    """Создаёт схему моделей в тестовом Postgres перед тестом, отдаёт sessionmaker, дропает схему после.

    Args:
        test_env (dict[str, str]): Env с параметрами подключения к тестовому Postgres.

    Returns:
        AsyncGenerator[async_sessionmaker, None]: Фабрика сессий на изолированную схему (NullPool).
    """
    from app.models import Base

    engine = create_async_engine(_build_database_url(test_env), poolclass=NullPool)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def celery_worker_process(test_env, shared_storage_dir):
    """Поднимает реальный Celery-воркер отдельным процессом (как в проде), с env тестового Redis/Postgres.

    Args:
        test_env (dict[str, str]): Env с параметрами подключения к тестовым Postgres/Redis.

    Returns:
        None: Процесс воркера живёт до конца тестовой сессии, затем завершается.
    """
    env = os.environ.copy()
    env.update(test_env)
    env["STORAGE_DIR"] = str(shared_storage_dir)

    process = subprocess.Popen(
        ["celery", "-A", "app.core.celery_app", "worker", "--pool=solo", "--loglevel=info", "-I", "app.tasks"],
        env=env,
        cwd=".",
    )
    time.sleep(3)  # ждём подключения воркера к брокеру

    yield

    process.terminate()
    process.wait(timeout=10)


@pytest.fixture
async def client(
    test_session_maker, celery_worker_process, shared_storage_dir, monkeypatch
) -> AsyncGenerator[AsyncClient, None]:
    """httpx-клиент поверх FastAPI app, с get_uow, переопределённым на тестовый Postgres.

    Args:
        test_session_maker: Фабрика сессий тестовой (изолированной) БД.
        celery_worker_process: Гарантирует, что реальный воркер запущен (fixture-зависимость).
        tmp_path: Временная директория для хранения файлов на время теста.
        monkeypatch: Стандартная фикстура pytest для подмены атрибутов.

    Returns:
        AsyncGenerator[AsyncClient, None]: Клиент для отправки запросов в приложение.
    """
    import app.services as services_module
    from app.core.dependencies import get_uow
    from app.core.uow import UnitOfWork
    from app.main import app

    monkeypatch.setattr(services_module.settings, "storage_dir", shared_storage_dir)
    monkeypatch.setattr(services_module.settings, "max_upload_size", 10 * 1024 * 1024)

    async def override_get_uow():
        async with UnitOfWork(test_session_maker) as uow:
            yield uow

    app.dependency_overrides[get_uow] = override_get_uow

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def session_maker(test_session_maker) -> async_sessionmaker:
    """Даёт тестам прямой доступ к БД (в обход HTTP) — например, для wait_for_processing.

    Args:
        test_session_maker: Фабрика сессий тестовой БД, уже открытая для этого теста.

    Returns:
        async_sessionmaker: Та же фабрика сессий, что использует client.
    """
    return test_session_maker


@pytest.fixture(scope="session")
def shared_storage_dir(tmp_path_factory):
    """Общая директория хранения файлов на всю тестовую сессию — её видят и FastAPI-процесс, и воркер.

    Args:
        tmp_path_factory: Стандартная фикстура pytest для сессионных временных директорий.

    Returns:
        Path: Путь к общей директории.
    """
    return tmp_path_factory.mktemp("storage")
