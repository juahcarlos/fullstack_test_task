docker compose -f /opt/tz/fullstack_test_task/docker-compose.dev.yml stop backend-worker
docker compose -f /opt/tz/fullstack_test_task/docker-compose.dev.yml exec -e UV_NO_DEV=0 backend uv run pytest /backend/tests -v --cache-clear
docker compose -f /opt/tz/fullstack_test_task/docker-compose.dev.yml start backend-worker