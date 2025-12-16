# FindQC 商品重构与 AI 聚类系统 - 架构设计文档

## 一、系统架构总览

### 1.1 微服务架构图

```mermaid
graph TB
    subgraph "外部服务"
        FindQC[FindQC API<br/>商品数据源]
        QwenAPI[Qwen 大模型 API<br/>图片分析/标签生成]
        GoogleLens[Google Lens API<br/>相似商品识别]
        AliyunImageSearch[阿里云图搜服务<br/>图片相似度搜索]
    end

    subgraph "微服务层"
        Spider[service_spider<br/>爬虫服务]
        AIPipe[service_ai_pipe<br/>AI 处理管道]
        Cluster[service_cluster<br/>聚类服务]
    end

    subgraph "共享层"
        SharedLib[shared_lib<br/>共享库<br/>- 数据库模型<br/>- 公共工具<br/>- API 客户端]
    end

    subgraph "基础设施层"
        RabbitMQ[(RabbitMQ<br/>消息队列)]
        MySQL[(MySQL 数据库)]
    end

    subgraph "数据表"
        Products[t_products<br/>商品主表]
        Tasks[t_tasks_products<br/>任务表]
        Tags[t_product_tags<br/>AI标签表]
        ClusterHead[t_cluster<br/>聚类中心表]
        ClusterMember[t_cluster_members<br/>聚类成员表]
    end

    FindQC -->|爬取商品数据| Spider
    Spider -->|商品数据| RabbitMQ
    RabbitMQ -->|消费任务| AIPipe
    
    AIPipe -->|选图+初打标签| QwenAPI
    QwenAPI -->|返回结果| AIPipe
    AIPipe -->|识别相似商品| GoogleLens
    GoogleLens -->|返回前10条| AIPipe
    AIPipe -->|综合标签| QwenAPI
    QwenAPI -->|最终标签| AIPipe
    
    AIPipe -->|带标签的商品| RabbitMQ
    RabbitMQ -->|消费任务| Cluster
    Cluster -->|图片搜索| AliyunImageSearch
    AliyunImageSearch -->|相似度结果| Cluster
    
    Spider --> SharedLib
    AIPipe --> SharedLib
    Cluster --> SharedLib
    
    SharedLib --> Products
    SharedLib --> Tasks
    SharedLib --> Tags
    SharedLib --> ClusterHead
    SharedLib --> ClusterMember
    
    Spider -.->|读写| MySQL
    AIPipe -.->|读写| MySQL
    Cluster -.->|读写| MySQL
```

### 1.2 业务流程时序图

```mermaid
sequenceDiagram
    participant Spider as service_spider
    participant MQ as RabbitMQ
    participant AI as service_ai_pipe
    participant Qwen as Qwen API
    participant GL as Google Lens
    participant Cluster as service_cluster
    participant AliSearch as 阿里云图搜
    participant DB as MySQL

    Note over Spider: 1. 爬取阶段
    Spider->>FindQC: 获取商品列表
    FindQC-->>Spider: 返回商品ID列表
    Spider->>FindQC: 获取商品详情
    FindQC-->>Spider: 返回商品数据+图片URLs
    Spider->>DB: 保存到 t_products
    Spider->>MQ: 发送商品处理任务

    Note over AI: 2. AI 处理阶段
    MQ->>AI: 消费商品任务
    AI->>Qwen: 请求选图(1-3张正面图) + 初打标签
    Qwen-->>AI: 返回选中的图片 + 初始标签
    AI->>GL: 请求相似商品识别(前10条)
    GL-->>AI: 返回相似商品简介列表
    AI->>Qwen: 综合标签(初标签 + Google Lens结果)
    Qwen-->>AI: 返回最终标签
    AI->>DB: 保存到 t_product_tags
    AI->>DB: 更新 t_products (pic_url, introduce)
    AI->>MQ: 发送聚类任务

    Note over Cluster: 3. 聚类阶段
    MQ->>Cluster: 消费聚类任务
    Cluster->>DB: 查询待聚类商品
    Cluster->>AliSearch: 图片相似度搜索
    AliSearch-->>Cluster: 返回相似度分值
    Cluster->>Cluster: 按分值阈值聚类
    Cluster->>DB: 保存到 t_cluster
    Cluster->>DB: 保存到 t_cluster_members
    Cluster->>DB: 更新 t_products (关联cluster_code)

    Note over Cluster: 4. 后续分析(未来扩展)
    Cluster->>DB: 销量分析
    Cluster->>Cluster: 生成推荐结果
```

### 1.3 数据流图

```mermaid
flowchart LR
    subgraph "数据输入"
        A[FindQC 商品数据]
    end
    
    subgraph "数据处理管道"
        B[原始商品数据<br/>- findqc_id<br/>- itemId<br/>- mallType<br/>- image_urls]
        C[AI 增强数据<br/>- pic_url 1-3张<br/>- 初始标签]
        D[综合标签数据<br/>- 品牌/型号<br/>- 类目/关键词]
        E[聚类结果<br/>- cluster_code<br/>- 相似度分值]
    end
    
    subgraph "数据存储"
        F[t_products]
        G[t_product_tags]
        H[t_cluster]
        I[t_cluster_members]
        J[t_tasks_products]
    end
    
    A --> B
    B --> C
    C --> D
    D --> E
    
    B --> F
    B --> J
    D --> G
    E --> H
    E --> I
    E --> F
```

### 1.4 数据库关系图

```mermaid
erDiagram
    t_products ||--o{ t_tasks_products : "一对多"
    t_products ||--|| t_product_tags : "一对一"
    t_products ||--o{ t_cluster_members : "一对多"
    t_cluster ||--o{ t_cluster_members : "一对多"
    
    t_products {
        int id PK
        int findqc_id UK
        text itemId
        text mallType
        int categoryId
        text price
        float weight
        json image_urls
        datetime last_qc_time
        int qc_count_30days
        text introduce
        text pic_url
        int update_task_id
        datetime last_update
        int status
    }
    
    t_tasks_products {
        int id PK
        int findqc_id FK
        int update_task_id
        int status
        datetime created_at
    }
    
    t_product_tags {
        int id PK
        int product_id FK
        text category
        text brand
        text model
        text target_audience
        text season
        text environment
        text keywords
        float ai_confidence
        datetime updated_at
    }
    
    t_cluster {
        int id PK
        text cluster_code UK
        text center_itemId
        text center_mallType
        int total_sales_count
        int member_count
        datetime created_at
    }
    
    t_cluster_members {
        int id PK
        text cluster_code FK
        text member_itemId
        text member_mallType
    }
```

## 二、技术栈说明

### 2.1 核心技术

- **语言**: Python 3.9
- **数据库**: MySQL
- **ORM**: SQLAlchemy (Async) 或 Tortoise-ORM
- **消息队列**: RabbitMQ
- **API 框架**: FastAPI (推荐) 或 Flask

### 2.2 外部 API 服务

- **FindQC API**: 商品数据源
- **Qwen API**: 大模型服务（图片分析、标签生成）
- **Google Lens API**: 相似商品识别
- **阿里云图搜 API**: 图片相似度搜索

## 三、微服务职责划分

### 3.1 service_spider（爬虫服务）

**职责**:
- 从 FindQC API 爬取商品数据
- 处理分类列表、商品详情、图片 URL
- 数据清洗和格式化
- 写入数据库并发送任务到消息队列

**输入**: FindQC API
**输出**: 商品数据 → MySQL + RabbitMQ

### 3.2 service_ai_pipe（AI 处理管道）

**职责**:
- 调用 Qwen API 选择商品正面图（1-3张）并生成初始标签
- 调用 Google Lens API 识别相似商品（前10条）
- 调用 Qwen API 综合生成最终标签
- 更新商品数据（pic_url, introduce）

**输入**: RabbitMQ 消息（商品ID）
**输出**: AI 标签 → MySQL + RabbitMQ

### 3.3 service_cluster（聚类服务）

**职责**:
- 调用阿里云图搜 API 进行图片相似度搜索
- 根据相似度分值进行商品聚类
- 管理聚类中心（cluster）和成员关系（members）
- 计算聚类统计数据（销量总和、成员数量）

**输入**: RabbitMQ 消息（待聚类商品）
**输出**: 聚类结果 → MySQL

### 3.4 shared_lib（共享库）

**职责**:
- 定义所有数据库模型（SQLAlchemy/Tortoise ORM）
- 提供公共工具函数
- API 客户端封装（FindQC、Qwen、Google Lens、阿里云图搜）
- 消息队列连接和消息格式定义

**使用者**: 所有微服务

## 四、消息队列设计

### 4.1 队列定义

```
Exchange: findqc_tasks
├── Queue: spider.products         # 爬虫服务 → AI 处理
│   └── Routing Key: product.new
├── Queue: ai.products             # AI 处理 → 聚类服务
│   └── Routing Key: product.labeled
└── Queue: cluster.products        # 聚类任务
    └── Routing Key: product.cluster
```

### 4.2 消息格式示例

**商品爬取完成消息**:
```json
{
  "task_id": "2024052001",
  "findqc_id": 12345,
  "product_id": 1001,
  "action": "product.new",
  "timestamp": "2024-05-20T10:00:00Z"
}
```

**AI 处理完成消息**:
```json
{
  "product_id": 1001,
  "findqc_id": 12345,
  "pic_url": "https://...",
  "tags": {...},
  "action": "product.labeled",
  "timestamp": "2024-05-20T10:05:00Z"
}
```

## 五、部署架构（未来规划）

```mermaid
graph TB
    subgraph "独立站前端"
        Web[Web Frontend]
    end
    
    subgraph "API Gateway"
        Gateway[Nginx/API Gateway]
    end
    
    subgraph "微服务集群"
        Spider1[service_spider:8001]
        Spider2[service_spider:8002]
        AI1[service_ai_pipe:8011]
        AI2[service_ai_pipe:8012]
        Cluster1[service_cluster:8021]
    end
    
    subgraph "中间件"
        RabbitMQ[(RabbitMQ)]
        Redis[(Redis<br/>缓存)]
    end
    
    subgraph "数据库"
        MySQL[(MySQL<br/>主从)]
    end
    
    Web --> Gateway
    Gateway --> Spider1
    Gateway --> AI1
    Gateway --> Cluster1
    
    Spider1 --> RabbitMQ
    Spider2 --> RabbitMQ
    AI1 --> RabbitMQ
    AI2 --> RabbitMQ
    Cluster1 --> RabbitMQ
    
    Spider1 --> MySQL
    AI1 --> MySQL
    Cluster1 --> MySQL
    
    AI1 --> Redis
    Cluster1 --> Redis
```

## 六、下一步开发计划

1. ✅ 数据库设计完成（db_structure.dbml）
2. ⏳ 创建架构文档（本文档）
3. ⬜ 实现 shared_lib/models.py（数据库模型）
4. ⬜ 实现 service_spider（爬虫服务）
5. ⬜ 实现 service_ai_pipe（AI 处理管道）
6. ⬜ 实现 service_cluster（聚类服务）
7. ⬜ 集成 RabbitMQ 消息队列
8. ⬜ 编写 API 文档
9. ⬜ 部署和测试

---

**文档版本**: v1.0  
**最后更新**: 2024-05-20  
**维护者**: 开发团队

