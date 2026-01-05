all:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml down
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml up --build

up:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml up -d

down:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml down

logs:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml logs -f

restart:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml restart

ps:
  docker compose -f docker-compose.yml -f docker-compose.milvus.yml -f docker-compose.ai.yml -f docker-compose.ui.yml ps
