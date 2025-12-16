"""
配置管理

从环境变量加载配置信息。
"""

import os
from typing import Optional, Any
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    """应用配置"""
    
    # 数据库配置
    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "")
    db_name: str = os.getenv("DB_NAME", "findqc_db")
    
    # RabbitMQ 配置
    rabbitmq_host: str = os.getenv("RABBITMQ_HOST", "localhost")
    rabbitmq_port: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    rabbitmq_user: str = os.getenv("RABBITMQ_USER", "guest")
    rabbitmq_password: str = os.getenv("RABBITMQ_PASSWORD", "guest")
    rabbitmq_vhost: str = os.getenv("RABBITMQ_VHOST", "/")
    
    # FindQC API 配置
    findqc_api_base_url: str = os.getenv("FINDQC_API_BASE_URL", "https://findqc.com/api")
    findqc_api_key: Optional[str] = os.getenv("FINDQC_API_KEY", None)
    
    # Qwen API 配置
    qwen_api_base_url: str = os.getenv("QWEN_API_BASE_URL", "")
    qwen_api_key: Optional[str] = os.getenv("QWEN_API_KEY", None)
    
    # Google Lens API 配置
    google_lens_api_key: Optional[str] = os.getenv("GOOGLE_LENS_API_KEY", None)
    
    # 阿里云图搜配置
    aliyun_image_search_endpoint: Optional[str] = os.getenv("ALIYUN_IMAGE_SEARCH_ENDPOINT", None)
    aliyun_image_search_access_key_id: Optional[str] = os.getenv("ALIYUN_IMAGE_SEARCH_ACCESS_KEY_ID", None)
    aliyun_image_search_access_key_secret: Optional[str] = os.getenv("ALIYUN_IMAGE_SEARCH_ACCESS_KEY_SECRET", None)
    
    # 日志配置
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    # 测试/调试配置
    max_products: Optional[int] = None  # 最大爬取商品数量（None表示不限制，用于测试）
    
    @field_validator("max_products", mode="before")
    @classmethod
    def parse_max_products(cls, v: Any) -> Optional[int]:
        """解析 max_products 环境变量"""
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            if not v or v.lower() in ("none", "null", ""):
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        return None
    
    @property
    def database_url(self) -> str:
        """
        构建数据库连接URL
        
        默认使用 SQLite（开发/测试）
        如果需要使用 MySQL，设置环境变量 USE_MYSQL=true
        
        Returns:
            str: 数据库连接URL（SQLite 或 MySQL）
        """
        use_mysql = os.getenv("USE_MYSQL", "").lower() in ("true", "1", "yes")
        
        if use_mysql:
            # 使用 MySQL（生产）
            return f"mysql+aiomysql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        else:
            # 使用 SQLite（开发/测试，默认）
            db_file = self.db_name if self.db_name.endswith(".db") else f"{self.db_name}.db"
            return f"sqlite+aiosqlite:///{db_file}"
    
    @property
    def rabbitmq_url(self) -> str:
        """
        构建 RabbitMQ 连接URL
        
        Returns:
            str: RabbitMQ 连接URL
        """
        return f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
    
    class Config:
        """Pydantic 配置"""
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # 允许从环境变量读取额外字段（但需要先定义字段）
        extra = "ignore"  # 忽略未定义的字段，而不是报错


# 全局配置实例
settings = Settings()

