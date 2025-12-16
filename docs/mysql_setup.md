# MySQL 数据库设置指南

## 1. 安装 MySQL

### macOS (推荐使用 Homebrew)

```bash
# 安装 MySQL
brew install mysql

# 启动 MySQL 服务
brew services start mysql

# 或者手动启动（一次性）
mysql.server start
```

### macOS (使用官方安装包)

1. 下载 MySQL：https://dev.mysql.com/downloads/mysql/
2. 安装 MySQL 安装包
3. 按照安装向导完成设置
4. 启动 MySQL 服务（通常在系统设置中）

### 验证安装

```bash
# 检查 MySQL 是否运行
ps aux | grep mysql

# 或尝试连接
mysql -u root -p
```

## 2. 创建数据库

### 方法1：使用提供的脚本（推荐）

```bash
# 运行设置脚本
./scripts/setup_mysql.sh
```

脚本会自动：
- 检查 MySQL 是否安装和运行
- 创建 `findqc_db` 数据库
- 提示下一步操作

### 方法2：手动创建

```bash
# 连接到 MySQL
mysql -u root -p

# 在 MySQL 命令行中执行
CREATE DATABASE IF NOT EXISTS findqc_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;
```

或者使用 SQL 文件：

```bash
mysql -u root -p < scripts/init_mysql_db.sql
```

## 3. 配置 .env 文件

编辑项目根目录的 `.env` 文件：

```env
# 数据库配置
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的MySQL密码  # 修改这里！
DB_NAME=findqc_db

# 爬虫配置
MAX_PRODUCTS=10

# 日志级别
LOG_LEVEL=INFO
```

**重要**：将 `DB_PASSWORD=your_password` 修改为你的实际 MySQL root 密码。

## 4. 测试连接

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行爬虫服务（会测试数据库连接）
python3 -m service_spider.main
```

如果连接成功，你会看到：
```
数据库初始化成功
```

如果失败，检查：
1. MySQL 服务是否运行
2. `.env` 文件中的密码是否正确
3. MySQL root 用户是否有权限创建数据库

## 5. 数据库表自动创建

当第一次运行 `service_spider.main` 时，SQLAlchemy 会自动创建所有需要的表：
- `t_products` - 商品主表
- `t_tasks_products` - 任务表
- `t_product_tags` - AI 标签表
- `t_cluster` - 聚类中心表
- `t_cluster_members` - 聚类成员表

## 常见问题

### Q: 连接失败 "Can't connect to MySQL server"

**解决方案**：
1. 确保 MySQL 服务正在运行
   ```bash
   # 检查服务状态
   brew services list | grep mysql
   
   # 启动服务
   brew services start mysql
   ```

2. 检查端口是否正确（默认 3306）

### Q: 访问被拒绝 "Access denied"

**解决方案**：
1. 检查 `.env` 文件中的用户名和密码是否正确
2. 尝试使用 MySQL 客户端连接测试：
   ```bash
   mysql -u root -p
   ```
3. 如果忘记密码，需要重置 MySQL root 密码

### Q: 数据库不存在

**解决方案**：
1. 运行数据库初始化脚本：
   ```bash
   ./scripts/setup_mysql.sh
   ```
2. 或手动创建数据库（见步骤2）

## 安全建议

1. **生产环境**：不要使用 root 用户，创建专用数据库用户：
   ```sql
   CREATE USER 'findqc_user'@'localhost' IDENTIFIED BY '强密码';
   GRANT ALL PRIVILEGES ON findqc_db.* TO 'findqc_user'@'localhost';
   FLUSH PRIVILEGES;
   ```
   然后更新 `.env` 文件使用新用户。

2. **密码安全**：使用强密码，不要提交 `.env` 文件到 Git

3. **备份**：定期备份数据库

---

**维护者**: MadPrinter  
**最后更新**: 2025-12-16

