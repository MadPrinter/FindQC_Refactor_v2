# 使用 Docker 运行 MySQL

## 快速开始

### 1. 启动 MySQL 容器

```bash
# 启动 MySQL（在后台运行）
docker-compose up -d

# 查看运行状态
docker-compose ps

# 查看日志
docker-compose logs -f mysql
```

### 2. 配置 .env 文件

复制示例配置文件：

```bash
cp .env.example .env
```

编辑 `.env` 文件，使用 Docker Compose 中配置的密码：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=findqc_root_password  # 与 docker-compose.yml 中的 MYSQL_ROOT_PASSWORD 一致
DB_NAME=findqc_db
```

**或者使用专用用户**（推荐，更安全）：

```env
DB_USER=findqc_user
DB_PASSWORD=findqc_password  # 与 docker-compose.yml 中的 MYSQL_PASSWORD 一致
```

### 3. 测试连接

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行爬虫服务（会自动创建数据库表）
python3 -m service_spider.main
```

## Docker 命令参考

### 启动和停止

```bash
# 启动 MySQL 容器
docker-compose up -d

# 停止 MySQL 容器（数据会保留）
docker-compose stop

# 停止并删除容器（数据会保留在 volume 中）
docker-compose down

# 停止并删除容器和所有数据（包括 volume）
docker-compose down -v
```

### 查看日志

```bash
# 查看实时日志
docker-compose logs -f mysql

# 查看最近 100 行日志
docker-compose logs --tail=100 mysql
```

### 进入 MySQL 容器

```bash
# 进入 MySQL 容器
docker-compose exec mysql bash

# 连接到 MySQL（在容器内）
mysql -u root -p
# 密码：findqc_root_password（或你在 docker-compose.yml 中设置的）
```

### 从宿主机连接 MySQL

```bash
# 使用 MySQL 客户端（如果已安装）
mysql -h 127.0.0.1 -P 3306 -u root -p
# 密码：findqc_root_password

# 或者使用 Docker 执行
docker-compose exec mysql mysql -u root -p
```

## 自定义配置

### 修改密码

编辑 `docker-compose.yml`：

```yaml
environment:
  MYSQL_ROOT_PASSWORD: 你的新密码
  MYSQL_PASSWORD: 你的新密码
```

然后重新创建容器：

```bash
docker-compose down -v  # 删除旧数据
docker-compose up -d    # 创建新容器
```

**注意**：修改密码后需要同步更新 `.env` 文件。

### 修改端口

如果 3306 端口已被占用，可以修改 `docker-compose.yml`：

```yaml
ports:
  - "3307:3306"  # 宿主机端口:容器端口
```

然后在 `.env` 文件中修改：

```env
DB_PORT=3307
```

### 数据持久化

数据存储在 Docker volume `mysql_data` 中，即使删除容器数据也不会丢失。

查看 volume：

```bash
docker volume ls | grep findqc
```

备份数据：

```bash
docker-compose exec mysql mysqldump -u root -p findqc_db > backup.sql
```

恢复数据：

```bash
docker-compose exec -T mysql mysql -u root -p findqc_db < backup.sql
```

## 数据库初始化

数据库 `findqc_db` 会在容器首次启动时自动创建（由 `MYSQL_DATABASE` 环境变量）。

如果 `scripts/init_mysql_db.sql` 文件存在，它也会在首次启动时自动执行。

数据库表会在首次运行 `service_spider.main` 时自动创建（通过 SQLAlchemy）。

## 常见问题

### Q: 容器启动失败

**检查日志**：
```bash
docker-compose logs mysql
```

**常见原因**：
1. 端口被占用：修改 `docker-compose.yml` 中的端口映射
2. 权限问题：确保 Docker 有足够权限

### Q: 连接被拒绝

**检查容器状态**：
```bash
docker-compose ps
```

**确保容器正在运行**：
```bash
docker-compose up -d
```

**检查端口是否正确**：
```bash
docker-compose port mysql 3306
```

### Q: 忘记密码

**重置密码**（需要停止容器并重新创建）：

1. 停止容器：
   ```bash
   docker-compose down -v
   ```

2. 修改 `docker-compose.yml` 中的密码

3. 重新启动：
   ```bash
   docker-compose up -d
   ```

### Q: 数据丢失

数据存储在 Docker volume 中，不会因为容器重启而丢失。

如果数据丢失，可能是：
1. 使用了 `docker-compose down -v` 删除了 volume
2. volume 被意外删除

**预防措施**：定期备份数据库（见"数据持久化"部分）

## 性能优化

### 内存限制

如果服务器资源有限，可以限制 MySQL 内存使用。编辑 `docker-compose.yml`：

```yaml
services:
  mysql:
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M
```

### 字符集

已在配置中设置 `utf8mb4` 字符集，支持完整的 Unicode（包括 emoji）。

---

**维护者**: MadPrinter  
**最后更新**: 2025-12-16

