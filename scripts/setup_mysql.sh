#!/bin/bash
# MySQL 数据库设置脚本

set -e

echo "=========================================="
echo "FindQC 项目 MySQL 数据库设置"
echo "=========================================="

# 检查 MySQL 是否安装
if ! command -v mysql &> /dev/null; then
    echo "❌ MySQL 未安装"
    echo ""
    echo "请先安装 MySQL："
    echo "  macOS (使用 Homebrew):"
    echo "    brew install mysql"
    echo "    brew services start mysql"
    echo ""
    echo "  macOS (使用 MySQL 官方安装包):"
    echo "    下载并安装: https://dev.mysql.com/downloads/mysql/"
    echo ""
    exit 1
fi

echo "✓ MySQL 已安装"

# 检查 MySQL 服务是否运行
if ! pgrep -x mysqld > /dev/null; then
    echo "⚠️  MySQL 服务未运行"
    echo ""
    echo "请启动 MySQL 服务："
    echo "  macOS (Homebrew):"
    echo "    brew services start mysql"
    echo ""
    echo "  或者："
    echo "    sudo /usr/local/mysql/support-files/mysql.server start"
    echo ""
    exit 1
fi

echo "✓ MySQL 服务正在运行"

# 提示输入 MySQL root 密码
echo ""
read -sp "请输入 MySQL root 密码: " MYSQL_PASSWORD
echo ""

# 执行数据库初始化
echo ""
echo "正在创建数据库..."
mysql -u root -p"$MYSQL_PASSWORD" < "$(dirname "$0")/init_mysql_db.sql"

if [ $? -eq 0 ]; then
    echo "✓ 数据库创建成功"
    echo ""
    echo "下一步："
    echo "1. 更新 .env 文件中的 DB_PASSWORD 为你的 MySQL root 密码"
    echo "2. 运行: python3 -m service_spider.main"
else
    echo "❌ 数据库创建失败，请检查 MySQL 密码和权限"
    exit 1
fi

