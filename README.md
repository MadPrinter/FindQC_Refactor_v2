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
- **数据库**: SQLite（开发/测试，默认）/ MySQL（生产，需设置 `USE_MYSQL=true`）
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

### 2. 数据库配置

**默认使用 SQLite**（无需额外配置），数据库文件会自动创建在项目根目录：`findqc_db.db`

如果需要使用 MySQL，创建 `.env` 文件：

```env
USE_MYSQL=true
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=findqc_db
```

### 3. 运行爬虫服务

```bash
# 激活虚拟环境
source venv/bin/activate

# 测试模式：只爬取 10 个商品
MAX_PRODUCTS=10 python3 -m service_spider.main

# 全量模式：不限制爬取数量
MAX_PRODUCTS=0 python3 -m service_spider.main
# 或者不设置 MAX_PRODUCTS（默认全量模式）
python3 -m service_spider.main

# 也可以通过 .env 文件设置
# MAX_PRODUCTS=10  # 测试模式
# MAX_PRODUCTS=0   # 全量模式（或不设置）
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
├── docs/                   # 文档
│   ├── architecture.md    # 架构设计
│   ├── service_flow.md    # 服务流程
│   ├── db_structure.dbml  # 数据库设计
│   └── git_guide.md       # Git 使用指南
├── test_spider_simple.py  # 简单测试脚本（不依赖数据库）
├── test_spider_sqlite.py  # SQLite 测试脚本
└── requirements.txt       # 依赖包列表
```

## 数据库说明

### SQLite（默认，开发/测试）

- **优点**：
  - 无需安装数据库服务
  - 数据存储在单个文件中（`findqc_db.db`）
  - 适合开发和测试
  - 可以直接查看数据库文件

- **使用**：无需配置，直接运行即可

- **查看数据库**：
  ```bash
  # 使用 sqlite3 命令行工具
  sqlite3 findqc_db.db
  
  # 查看表
  .tables
  
  # 查询数据
  SELECT * FROM t_products;
  ```

### MySQL（生产环境）

如果需要使用 MySQL，需要：

1. 安装并启动 MySQL 服务
2. 创建 `.env` 文件，设置：
   ```env
   USE_MYSQL=true
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=your_password
   DB_NAME=findqc_db
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
MAX_PRODUCTS=10 python3 -m service_spider.main
```

### 配置文件

项目使用 `.env` 文件进行配置管理，所有配置都有合理的默认值，**不创建 `.env` 文件也能正常运行**。

如果需要自定义配置，可以：

1. **复制配置模板**：
   ```bash
   cp .env.example .env
   ```

2. **编辑 `.env` 文件**，根据实际需求修改配置

3. **主要配置项说明**：
   - `START_CAT_ID` / `END_CAT_ID`: 分类ID范围（默认 3000-10000）
   - `MAX_PRODUCTS`: 爬取模式（不设置或 0=全量模式，数字=测试模式）
   - `USE_MYSQL`: 是否使用 MySQL（默认 false，使用 SQLite）

### 环境变量配置（可选）

如果需要通过环境变量覆盖配置：

```env
# 数据库配置（默认使用 SQLite）
# USE_MYSQL=true  # 取消注释以使用 MySQL
# DB_HOST=localhost
# DB_PORT=3306
# DB_USER=root
# DB_PASSWORD=your_password
DB_NAME=findqc_db

# 爬取模式配置
MAX_PRODUCTS=10  # 测试模式：爬取指定数量（如 10）
# MAX_PRODUCTS=0   # 全量模式：不限制爬取数量（或不设置此项）

# 分类ID范围配置（用于遍历分类）
START_CAT_ID=3000  # 起始分类ID
END_CAT_ID=10000   # 结束分类ID

# 日志配置
LOG_LEVEL=INFO

# FindQC API 配置（可选）
# FINDQC_API_BASE_URL=https://findqc.com/api
# FINDQC_API_KEY=your_api_key

# RabbitMQ 配置（可选）
# RABBITMQ_HOST=localhost
# RABBITMQ_PORT=5672
# RABBITMQ_USER=guest
# RABBITMQ_PASSWORD=guest
```

## 微服务说明

### service_spider（爬虫服务）

负责从 FindQC API 爬取商品数据。

功能：
- 遍历分类获取商品列表
- 获取商品详情和图集
- 过滤不符合条件的商品（无 QC 图或 QC 图不在近 30 天内）
- 保存商品数据到数据库
- 发送消息到 RabbitMQ（通知 AI 处理管道，可选）

详细文档：`service_spider/README.md`

## 注意事项

1. **请求频率控制**：代码中已添加请求延迟，避免被 API 限流
2. **数据库选择**：
   - 开发/测试：使用 SQLite（默认）
   - 生产：使用 MySQL（设置 `USE_MYSQL=true`）
3. **消息队列**：RabbitMQ 是可选的，未安装时爬虫仍可正常运行（只是不发送消息）
4. **数据过滤**：爬虫会自动跳过没有 QC 图或 QC 图最晚时间不在近 30 天内的商品

## 维护者

MadPrinter

## 许可证

[待定]
