# FindQC 商品重构与 AI 聚类系统

## 项目简介

将分散的爬虫脚本重构为基于微服务的系统，用于：
- 爬取 FindQC 平台的商品数据
- 通过 Qwen 大模型进行商品图片分析和标签生成
- 使用 Google Lens API 识别相似商品
- 通过阿里云图搜服务进行商品聚类
- 基于聚类结果构建商品推荐系统

## 技术栈

- **语言**: Python 3.9
- **数据库**: MySQL（生产）/ SQLite（开发/测试）
- **ORM**: SQLAlchemy (Async)
- **消息队列**: RabbitMQ（可选）
- **日志**: Loguru
- **HTTP 客户端**: httpx
- **容器化**: Docker & Docker Compose

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 数据库配置

#### 方式1：使用 Docker（推荐）

```bash
# 启动 MySQL 容器
docker-compose up -d

# 查看运行状态
docker-compose ps
```

然后创建 `.env` 文件：

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=findqc_root_password
DB_NAME=findqc_db
MAX_PRODUCTS=10
LOG_LEVEL=INFO
```

**详细文档**：`docs/docker_mysql_setup.md`

#### 方式2：使用本地 MySQL

参考：`docs/mysql_setup.md`

#### 方式3：使用 SQLite（开发/测试）

```env
USE_SQLITE=true
DB_NAME=findqc_db
```

### 3. 运行爬虫服务

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行爬虫服务
python3 -m service_spider.main
```

## 项目结构

```
FindQC_Refactor_v2/
├── shared_lib/              # 共享库
│   ├── models.py           # 数据库模型
│   ├── database.py         # 数据库连接
│   └── config.py           # 配置管理
├── service_spider/         # 爬虫服务
│   ├── main.py            # 主程序入口
│   ├── spider.py          # 爬虫核心逻辑
│   ├── api_client.py      # FindQC API 客户端
│   ├── db_service.py      # 数据库操作服务
│   └── mq_service.py      # 消息队列服务
├── scripts/                # 脚本文件
│   ├── init_mysql_db.sql  # MySQL 初始化脚本
│   └── setup_mysql.sh     # MySQL 设置脚本
├── docs/                   # 文档
│   ├── architecture.md    # 架构设计
│   ├── service_flow.md    # 服务流程
│   ├── db_structure.dbml  # 数据库设计
│   ├── docker_mysql_setup.md  # Docker MySQL 设置
│   └── mysql_setup.md     # MySQL 设置指南
├── docker-compose.yml     # Docker Compose 配置
├── test_spider_sqlite.py  # SQLite 测试脚本
└── requirements.txt       # 依赖包列表
```

## Docker 使用

### 启动 MySQL

```bash
# 启动 MySQL 容器
docker-compose up -d

# 查看日志
docker-compose logs -f mysql

# 停止容器
docker-compose stop

# 停止并删除容器（数据保留）
docker-compose down

# 停止并删除所有数据
docker-compose down -v
```

### 进入 MySQL

```bash
# 进入容器
docker-compose exec mysql bash

# 连接 MySQL
docker-compose exec mysql mysql -u root -p
```

**详细文档**：`docs/docker_mysql_setup.md`

## 数据库配置说明

### Docker MySQL（推荐）

优点：
- 无需本地安装 MySQL
- 易于管理和部署
- 数据持久化在 Docker volume 中

使用方法：
```bash
docker-compose up -d
```

### SQLite（开发/测试）

优点：
- 无需安装数据库服务
- 数据存储在单个文件中
- 适合开发和测试

使用方法：
```env
USE_SQLITE=true
```

### 本地 MySQL（生产）

优点：
- 性能更好
- 支持高并发
- 适合生产环境

详细设置：`docs/mysql_setup.md`

## 开发指南

### 数据库初始化

数据库表会在首次运行时自动创建（通过 SQLAlchemy 的 `create_all`）。

### 测试

```bash
# 运行 API 测试（不依赖数据库）
python3 test_spider_simple.py

# 运行完整测试（使用 SQLite）
python3 test_spider_sqlite.py

# 运行主程序（使用 Docker MySQL，限制10个商品）
MAX_PRODUCTS=10 python3 -m service_spider.main
```

## 微服务说明

### service_spider（爬虫服务）

负责从 FindQC API 爬取商品数据。

功能：
- 遍历分类获取商品列表
- 获取商品详情和图集
- 保存商品数据到数据库
- 发送消息到 RabbitMQ（通知 AI 处理管道）

详细文档：`service_spider/README.md`

## 注意事项

1. **请求频率控制**：代码中已添加请求延迟，避免被 API 限流
2. **数据库选择**：
   - 开发/测试推荐使用 Docker MySQL 或 SQLite
   - 生产使用本地 MySQL 或 Docker MySQL
3. **消息队列**：RabbitMQ 是可选的，未安装时爬虫仍可正常运行（只是不发送消息）

## 维护者

MadPrinter

## 许可证

[待定]
