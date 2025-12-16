# FindQC 商品重构与 AI 聚类系统

## 项目简介

将分散的爬虫脚本重构为基于微服务的系统，实现商品数据爬取、AI 智能打标、图搜聚类和推荐系统的完整流程。

## 技术栈

- **语言**: Python 3.9
- **数据库**: MySQL
- **ORM**: SQLAlchemy (Async) 或 Tortoise-ORM
- **消息队列**: RabbitMQ
- **API 框架**: FastAPI (推荐)

## 项目结构

```
FindQC_Refactor_v2/
├── docs/                    # 文档目录
│   ├── db_structure.dbml   # 数据库设计（DBML格式）
│   ├── architecture.md      # 系统架构文档
│   └── git_guide.md         # Git 使用指南
├── shared_lib/              # 共享库
│   └── models.py            # 数据库模型定义
├── service_spider/          # 爬虫服务
├── service_ai_pipe/         # AI 处理管道服务
├── service_cluster/         # 聚类服务
├── old_projects/            # 旧项目代码（参考用）
├── .gitignore              # Git 忽略文件配置
└── README.md               # 项目说明文档
```

## 业务流程

1. **爬虫阶段** (`service_spider`)
   - 从 FindQC API 爬取商品数据
   - 保存商品基本信息和图片 URLs

2. **AI 处理阶段** (`service_ai_pipe`)
   - 调用 Qwen 大模型选择商品正面图（1-3张）并生成初始标签
   - 调用 Google Lens API 识别相似商品（前10条）
   - 调用 Qwen 大模型综合生成最终标签

3. **聚类阶段** (`service_cluster`)
   - 调用阿里云图搜 API 进行图片相似度搜索
   - 根据相似度分值进行商品聚类

4. **推荐系统**（未来扩展）
   - 基于聚类结果进行销量分析
   - 生成商品推荐

## 数据库设计

数据库设计文档位于 `docs/db_structure.dbml`，包含以下表：

- `t_products` - 商品主表
- `t_tasks_products` - 任务关联表
- `t_product_tags` - AI 标签表
- `t_cluster` - 聚类中心表
- `t_cluster_members` - 聚类成员表

## 快速开始

### 环境要求

- Python 3.9+
- MySQL 5.7+
- RabbitMQ 3.8+

### 安装依赖

```bash
# 创建虚拟环境
python3.9 -m venv venv

# 激活虚拟环境
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置数据库

1. 创建 MySQL 数据库
2. 配置数据库连接信息（在配置文件中设置）
3. 运行数据库迁移脚本（待实现）

## 开发规范

1. **代码风格**: 遵循 PEP8，必须有 Type Hints
2. **数据库模型**: 所有模型定义在 `shared_lib/models.py`
3. **数据库设计**: 必须遵循 `docs/db_structure.dbml`
4. **开发方式**: 每次只专注一个模块，逐步完善

## 文档

- [系统架构文档](docs/architecture.md) - 详细的架构设计和流程图
- [数据库设计](docs/db_structure.dbml) - 数据库表结构设计
- [Git 使用指南](docs/git_guide.md) - Git 版本控制使用说明

## 开发计划

- [x] 数据库设计
- [x] 架构文档
- [ ] 数据库模型实现 (shared_lib/models.py)
- [ ] 爬虫服务 (service_spider)
- [ ] AI 处理管道 (service_ai_pipe)
- [ ] 聚类服务 (service_cluster)
- [ ] 消息队列集成
- [ ] API 文档
- [ ] 部署和测试

## 作者

开发团队

## 许可证

[待定]

