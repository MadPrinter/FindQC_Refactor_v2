#!/bin/bash
# 迁移 MySQL 数据到项目目录的脚本

set -e

echo "=========================================="
echo "迁移 MySQL 数据到项目目录"
echo "=========================================="

DATA_DIR="./data/mysql"

# 检查是否有现有数据需要备份
if docker-compose exec -T mysql mysql -u root -pfindqc_root_password -e "USE findqc_db;" 2>/dev/null | grep -q "t_products"; then
    echo ""
    echo "⚠️  检测到数据库中有数据，是否备份？"
    echo "备份文件将保存为: ./backup_$(date +%Y%m%d_%H%M%S).sql"
    read -p "是否备份现有数据？(y/n): " backup_choice
    
    if [ "$backup_choice" = "y" ] || [ "$backup_choice" = "Y" ]; then
        BACKUP_FILE="./backup_$(date +%Y%m%d_%H%M%S).sql"
        echo "正在备份数据到: $BACKUP_FILE"
        docker-compose exec -T mysql mysqldump -u root -pfindqc_root_password findqc_db > "$BACKUP_FILE"
        echo "✓ 备份完成: $BACKUP_FILE"
    fi
fi

echo ""
echo "步骤 1: 停止 MySQL 容器"
docker-compose stop mysql

echo ""
echo "步骤 2: 创建数据目录（如果不存在）"
mkdir -p "$DATA_DIR"
chmod 755 "$DATA_DIR"

echo ""
echo "步骤 3: 从 Docker volume 复制数据（如果存在）"
if docker volume inspect findqc_refactor_v2_mysql_data >/dev/null 2>&1; then
    echo "找到 Docker volume，正在复制数据..."
    docker run --rm \
        -v findqc_refactor_v2_mysql_data:/source \
        -v "$(pwd)/$DATA_DIR:/target" \
        alpine sh -c "cp -a /source/. /target/ && chown -R 999:999 /target"
    echo "✓ 数据复制完成"
else
    echo "未找到 Docker volume，将创建新的数据库"
fi

echo ""
echo "步骤 4: 删除旧的 Docker volume（可选）"
read -p "是否删除旧的 Docker volume？(y/n): " delete_volume
if [ "$delete_volume" = "y" ] || [ "$delete_volume" = "Y" ]; then
    docker volume rm findqc_refactor_v2_mysql_data 2>/dev/null || echo "Volume 不存在或已被删除"
fi

echo ""
echo "步骤 5: 启动 MySQL 容器"
docker-compose up -d mysql

echo ""
echo "=========================================="
echo "迁移完成！"
echo "=========================================="
echo "数据现在存储在: $DATA_DIR"
echo "可以查看: ls -lh $DATA_DIR"
echo ""
