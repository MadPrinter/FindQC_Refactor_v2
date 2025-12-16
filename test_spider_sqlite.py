#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
使用 SQLite 的爬虫测试脚本

无需 MySQL，使用 SQLite 数据库进行测试。
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置使用 SQLite 数据库（测试用）
os.environ.setdefault("MAX_PRODUCTS", "10")
os.environ.setdefault("LOG_LEVEL", "INFO")

from loguru import logger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# 导入模型和工具
from shared_lib.models import Base, Product, TaskProduct
from service_spider.api_client import FindQCAPIClient
from service_spider.db_service import ProductDBService
from service_spider.spider import SpiderService

# 尝试导入 aiosqlite（SQLite 异步驱动）
try:
    import aiosqlite
    AIOSQLITE_AVAILABLE = True
except ImportError:
    AIOSQLITE_AVAILABLE = False
    logger.warning("aiosqlite 未安装，无法使用 SQLite 测试")


async def test_spider_with_sqlite():
    """使用 SQLite 测试爬虫功能"""
    if not AIOSQLITE_AVAILABLE:
        logger.error("需要安装 aiosqlite: pip install aiosqlite")
        return
    
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )
    
    logger.info("=" * 60)
    logger.info("开始测试爬虫服务（使用 SQLite 数据库）")
    logger.info("=" * 60)
    
    # 创建 SQLite 数据库引擎
    db_path = "test_findqc.db"
    database_url = f"sqlite+aiosqlite:///{db_path}"
    
    logger.info(f"数据库文件: {db_path}")
    
    engine = create_async_engine(
        database_url,
        echo=False,
    )
    
    # 创建表结构
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✓ 数据库表创建成功")
    
    # 创建会话工厂
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    # 初始化 API 客户端
    api_client = FindQCAPIClient(
        base_url="https://findqc.com/api",
    )
    
    # 创建爬虫服务（需要修改以支持自定义数据库会话）
    # 由于 spider.py 使用了 get_database()，我们需要一个不同的方法
    # 这里我们直接调用 API 和数据库服务
    
    try:
        # 获取分类商品列表
        category_id = 4113
        logger.info(f"\n开始爬取分类ID: {category_id}")
        
        response = await api_client.get_category_products(
            catalogue_id=category_id,
            page=1,
            size=10,
        )
        
        items = api_client.extract_product_list(response)
        logger.info(f"获取到 {len(items)} 个商品")
        
        if not items:
            logger.warning("该分类没有商品")
            return
        
        # 处理前10个商品
        max_products = 10
        db_service = ProductDBService()
        update_task_id = int(datetime.now().strftime("%Y%m%d%H"))
        
        processed = 0
        for item_summary in items[:max_products]:
            if processed >= max_products:
                break
            
            findqc_id = item_summary.get("id")
            item_id = item_summary.get("itemId")
            mall_type = item_summary.get("mallType")
            
            if not findqc_id or not item_id or not mall_type:
                logger.warning(f"商品信息不完整，跳过: {item_summary}")
                continue
            
            logger.info(f"\n处理商品 {processed + 1}/{max_products}: findqc_id={findqc_id}")
            
            try:
                # 获取商品详情
                detail_response = await api_client.get_product_detail(
                    item_id=item_id,
                    mall_type=mall_type,
                )
                
                # 获取商品图集（只获取第一页）
                atlas_responses = []
                try:
                    atlas_response = await api_client.get_product_atlas(
                        goods_id=str(findqc_id),
                        item_id=item_id,
                        mall_type=mall_type,
                        page=1,
                        size=10,
                    )
                    atlas_responses.append(atlas_response)
                except Exception as e:
                    logger.debug(f"获取图集失败（可能没有图集）: {e}")
                
                # 整理商品数据
                product_data = db_service.prepare_product_data(
                    findqc_id=findqc_id,
                    item_id=item_id,
                    mall_type=mall_type,
                    category_id=category_id,
                    detail_response=detail_response,
                    atlas_responses=atlas_responses,
                )
                
                # 保存到数据库
                async with async_session_maker() as session:
                    product = await db_service.save_or_update_product(
                        session=session,
                        product_data=product_data,
                        update_task_id=update_task_id,
                    )
                    
                    await db_service.create_task_record(
                        session=session,
                        findqc_id=findqc_id,
                        update_task_id=update_task_id,
                        status=0,
                    )
                    
                    await session.commit()
                    
                    logger.info(f"✓ 商品保存成功: id={product.id}, findqc_id={findqc_id}")
                    processed += 1
                
                await asyncio.sleep(0.5)  # 延迟
                
            except Exception as e:
                logger.error(f"处理商品失败: findqc_id={findqc_id}, error={e}")
                import traceback
                traceback.print_exc()
                continue
        
        logger.info("\n" + "=" * 60)
        logger.info(f"测试完成！成功处理 {processed} 个商品")
        logger.info(f"数据库文件: {db_path}")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api_client.close()
        await engine.dispose()


if __name__ == "__main__":
    try:
        asyncio.run(test_spider_with_sqlite())
    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
    except Exception as e:
        logger.error(f"测试异常: {e}")
        sys.exit(1)

