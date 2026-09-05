"""HTTP-роуты для работы с файлами.

Роуты намеренно тонкие: только принимают запрос, вызывают соответствующий
метод FileService (полученный через DI) и возвращают результат. Никакой
бизнес-логики (работа с БД, диском, валидация) здесь не содержится —
она вынесена в services.py.
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse

from app.core.dependencies import FileServiceDep
from app.schemas import FileItem, FileUpdate

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=list[FileItem])
async def list_files_view(
    service: FileServiceDep,
    # Пагинация — файлов может быть много, отдавать весь список разом
    # не масштабируется. Ограничение limit <= 200 защищает от чрезмерных
    # выборок по ошибке клиента.
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    """Возвращает список файлов, отсортированный по дате создания (новые первыми)."""
    return await service.list_files(skip=skip, limit=limit)


@router.post("", response_model=FileItem, status_code=201)
async def create_file_view(
    service: FileServiceDep,
    title: str = Form(...),
    file: UploadFile = File(...),
):
    """Загружает файл, сохраняет его и ставит в очередь на проверку/обработку."""
    return await service.create_file(title=title, upload_file=file)


@router.get("/{file_id}", response_model=FileItem)
async def get_file_view(file_id: str, service: FileServiceDep):
    """Возвращает метаданные одного файла по id (404, если не найден)."""
    return await service.get_file(file_id)


@router.patch("/{file_id}", response_model=FileItem)
async def update_file_view(
    file_id: str,
    payload: FileUpdate,
    service: FileServiceDep,
):
    """Обновляет название файла."""
    return await service.update_file(file_id=file_id, title=payload.title)


@router.get("/{file_id}/download")
async def download_file_view(file_id: str, service: FileServiceDep):
    """Отдаёт бинарное содержимое файла клиенту для скачивания."""
    file_item, stored_path = await service.get_file_with_path(file_id)
    return FileResponse(
        path=stored_path,
        media_type=file_item.mime_type,
        filename=file_item.original_name,
    )


@router.delete("/{file_id}", status_code=204)
async def delete_file_view(file_id: str, service: FileServiceDep):
    """Удаляет файл с диска и запись из БД."""
    await service.delete_file(file_id)