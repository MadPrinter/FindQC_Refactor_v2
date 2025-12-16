"""
数据库连接和会话管理

提供 SQLAlchemy 异步数据库连接的配置和管理。
"""

from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from .models import Base


class Database:
    """数据库连接管理器"""
    
    def __init__(self, database_url: str):
        """
        初始化数据库连接
        
        Args:
            database_url: 数据库连接URL，格式：mysql+aiomysql://user:password@host:port/dbname
        """
        # 创建异步引擎
        self.engine = create_async_engine(
            database_url,
            echo=False,  # 设置为 True 可以看到 SQL 日志
            poolclass=NullPool,  # 使用 NullPool 适合异步场景
            pool_pre_ping=True,  # 连接前ping，确保连接有效
        )
        
        # 创建异步会话工厂
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    
    async def init_db(self) -> None:
        """
        初始化数据库表结构
        
        创建所有定义的表（如果不存在）。
        """
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    
    async def close(self) -> None:
        """关闭数据库连接"""
        await self.engine.dispose()
    
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        获取数据库会话（用于依赖注入）
        
        Yields:
            AsyncSession: 数据库会话对象
            
        Example:
            async with db.get_session() as session:
                result = await session.execute(select(Product))
        """
        async with self.async_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# 全局数据库实例（需要在应用启动时初始化）
db: Optional[Database] = None


def init_database(database_url: str) -> Database:
    """
    初始化全局数据库实例
    
    Args:
        database_url: 数据库连接URL
        
    Returns:
        Database: 数据库实例
    """
    global db
    db = Database(database_url)
    return db


def get_database() -> Database:
    """
    获取全局数据库实例
    
    Returns:
        Database: 数据库实例
        
    Raises:
        RuntimeError: 如果数据库未初始化
    """
    if db is None:
        raise RuntimeError("数据库未初始化，请先调用 init_database()")
    return db

