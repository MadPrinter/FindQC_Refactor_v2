#!/bin/bash
# 更新 .env 文件中的 MySQL 密码以匹配 docker-compose.yml

ENV_FILE=".env"
COMPOSE_FILE="docker-compose.yml"

# 从 docker-compose.yml 中提取密码
ROOT_PASSWORD=$(grep "MYSQL_ROOT_PASSWORD:" "$COMPOSE_FILE" | sed 's/.*MYSQL_ROOT_PASSWORD: *\(.*\)/\1/' | sed 's/#.*//' | xargs)
USER_PASSWORD=$(grep "MYSQL_PASSWORD:" "$COMPOSE_FILE" | sed 's/.*MYSQL_PASSWORD: *\(.*\)/\1/' | sed 's/#.*//' | xargs)

if [ -z "$ROOT_PASSWORD" ]; then
    echo "❌ 无法从 docker-compose.yml 中提取 MYSQL_ROOT_PASSWORD"
    exit 1
fi

echo "从 docker-compose.yml 提取的密码:"
echo "  ROOT_PASSWORD: $ROOT_PASSWORD"
echo "  USER_PASSWORD: $USER_PASSWORD"
echo ""

# 更新 .env 文件
if [ -f "$ENV_FILE" ]; then
    # 使用 sed 更新密码（macOS 兼容）
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^DB_PASSWORD=.*/DB_PASSWORD=$ROOT_PASSWORD/" "$ENV_FILE"
    else
        sed -i "s/^DB_PASSWORD=.*/DB_PASSWORD=$ROOT_PASSWORD/" "$ENV_FILE"
    fi
    echo "✓ 已更新 $ENV_FILE 中的 DB_PASSWORD"
else
    echo "⚠️  .env 文件不存在，创建新文件..."
    cat > "$ENV_FILE" << ENVEOF
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=$ROOT_PASSWORD
DB_NAME=findqc_db
MAX_PRODUCTS=10
LOG_LEVEL=INFO
ENVEOF
    echo "✓ 已创建 $ENV_FILE"
fi

echo ""
echo "现在可以运行: python3 -m service_spider.main"
