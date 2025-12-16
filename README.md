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

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

创建 `.env` 文件：

```env
# 数据库配置（选择一种方式）

# 方式1：使用 SQLite（推荐用于开发/测试，无需安装 MySQL）
USE_SQLITE=true
DB_NAME=findqc_db

# 方式2：使用 MySQL（生产环境）
# DB_HOST=localhost
# DB_PORT=3306
# DB_USER=root
# DB_PASSWORD=your_password
# DB_NAME=findqc_db

# 爬虫配置
MAX_PRODUCTS=10  # 测试模式：限制爬取商品数量

# 日志级别
LOG_LEVEL=INFO
```

### 3. 运行爬虫服务

#### 使用 SQLite（开发/测试）

```bash
# 方法1：设置环境变量
USE_SQLITE=true python3 -m service_spider.main

# 方法2：修改 .env 文件，设置 USE_SQLITE=true 或 DB_HOST=sqlite
python3 -m service_spider.main
```

#### 使用 MySQL（生产）

```bash
# 确保 MySQL 服务已启动，并配置 .env 文件
python3 -m service_spider.main
```

#### 使用测试脚本（推荐用于快速测试）

```bash
# 使用 SQLite 测试脚本（无需配置，直接运行）
python3 test_spider_sqlite.py
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
├── docs/                   # 文档
│   ├── architecture.md    # 架构设计
│   ├── service_flow.md    # 服务流程
│   └── db_structure.dbml  # 数据库设计
├── test_spider_sqlite.py  # SQLite 测试脚本
└── requirements.txt       # 依赖包列表
```

## 数据库配置说明

### SQLite（开发/测试）

优点：
- 无需安装数据库服务
- 数据存储在单个文件中
- 适合开发和测试

使用方法：
```bash
# 设置环境变量
USE_SQLITE=true python3 -m service_spider.main

# 或修改 .env 文件
echo "USE_SQLITE=true" >> .env
```

数据库文件：`findqc_db.db`（项目根目录）

### MySQL（生产）

优点：
- 性能更好
- 支持并发
- 适合生产环境

使用方法：
```bash
# 配置 .env 文件
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=findqc_db

# 运行服务
python3 -m service_spider.main
```

## 开发指南

### 数据库初始化

数据库表会在首次运行时自动创建（通过 SQLAlchemy 的 `create_all`）。

### 测试

```bash
# 运行 API 测试（不依赖数据库）
python3 test_spider_simple.py

# 运行完整测试（使用 SQLite）
python3 test_spider_sqlite.py

# 运行主程序（使用 SQLite，限制10个商品）
USE_SQLITE=true MAX_PRODUCTS=10 python3 -m service_spider.main
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
2. **数据库选择**：开发/测试推荐使用 SQLite，生产使用 MySQL
3. **消息队列**：RabbitMQ 是可选的，未安装时爬虫仍可正常运行（只是不发送消息）

## 维护者

MadPrinter

## 许可证

[待定]
