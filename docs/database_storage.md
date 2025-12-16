# 数据库存储说明

## Docker MySQL 数据存储位置

当使用 Docker Compose 运行 MySQL 时，数据库文件**不会**出现在项目根目录下。

### 数据存储方式

数据存储在 **Docker Volume** 中，而不是项目目录下的文件。

#### 查看 Volume 信息

```bash
# 查看所有 Docker volumes
docker volume ls

# 查看 MySQL volume 的详细信息
docker volume inspect findqc_refactor_v2_mysql_data
```

#### Volume 位置（macOS/Windows）

Docker Desktop 将 volumes 存储在虚拟机中，不在本地文件系统直接可见：

- **macOS**: `/var/lib/docker/volumes/` (在 Docker Desktop VM 中)
- **Windows**: Docker Desktop WSL2 后端中

### 为什么看不到数据库文件？

- ✅ **Docker MySQL**: 数据存储在 Docker volume 中（不可见）
- ✅ **SQLite**: 数据存储在项目目录下的 `.db` 文件中（可见）

### 查看数据库内容

虽然看不到数据库文件，但可以通过以下方式访问数据：

#### 1. 通过 MySQL 命令行

```bash
# 连接 MySQL
docker-compose exec mysql mysql -u root -pfindqc_root_password

# 在 MySQL 中执行查询
USE findqc_db;
SHOW TABLES;
SELECT * FROM t_products;
```

#### 2. 通过 SQL 脚本

```bash
# 执行 SQL 查询
docker-compose exec -T mysql mysql -u root -pfindqc_root_password -e "USE findqc_db; SELECT COUNT(*) FROM t_products;"
```

#### 3. 导出数据库（备份）

```bash
# 导出整个数据库
docker-compose exec mysql mysqldump -u root -pfindqc_root_password findqc_db > backup.sql

# 导出单个表
docker-compose exec mysql mysqldump -u root -pfindqc_root_password findqc_db t_products > products_backup.sql
```

### 数据持久化

**数据不会丢失**！即使：
- 停止容器：`docker-compose stop`
- 删除容器：`docker-compose down`

数据仍然保留在 Docker volume 中。

**只有在以下情况数据才会丢失**：
```bash
# 删除容器和 volume（数据会丢失！）
docker-compose down -v
```

### 如果想在项目目录看到数据库文件

如果你希望数据库文件出现在项目目录中，有两个选择：

#### 方案1：使用 SQLite（开发/测试）

修改 `.env` 文件：
```env
USE_SQLITE=true
```

这样会在项目根目录生成 `findqc_db.db` 文件。

#### 方案2：将 MySQL 数据映射到本地目录

修改 `docker-compose.yml`，将 volume 改为 bind mount：

```yaml
services:
  mysql:
    volumes:
      # 将数据存储到项目目录的 data/mysql 文件夹
      - ./data/mysql:/var/lib/mysql  # 改为 bind mount
      # 移除原来的 volume 引用
```

**注意**：修改后需要重新初始化数据库。

### 查看当前数据库大小

```bash
# 查看 volume 大小
docker system df -v | grep mysql_data
```

### 总结

- ✅ Docker MySQL 数据存储在 Docker volume 中（不可见，但持久化）
- ✅ 数据不会因为容器重启而丢失
- ✅ 可以通过 MySQL 命令访问数据
- ✅ 如果需要可见的数据库文件，使用 SQLite 或修改 docker-compose.yml 使用 bind mount

---

**维护者**: MadPrinter  
**最后更新**: 2025-12-16

