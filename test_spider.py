#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试爬虫服务

只爬取前10个商品进行测试，不依赖数据库和RabbitMQ。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置环境变量（测试模式，不使用数据库和RabbitMQ）
import os
os.environ.setdefault("MAX_PRODUCTS", "10")
os.environ.setdefault("LOG_LEVEL", "INFO")

# 如果没有配置数据库，使用内存SQLite（仅用于测试）
if "DB_HOST" not in os.environ:
    os.environ.setdefault("DB_HOST", "localhost")
    os.environ.setdefault("DB_PORT", "3306")
    os.environ.setdefault("DB_USER", "test")
    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("DB_NAME", "test_findqc")

from loguru import logger
from service_spider.api_client import FindQCAPIClient
from service_spider.spider import SpiderService


async def test_spider():
    """测试爬虫功能（不依赖数据库）"""
    logger.info("=" * 60)
    logger.info("开始测试爬虫服务（仅测试API调用，不保存数据）")
    logger.info("=" * 60)
    
    # 初始化 API 客户端
    api_client = FindQCAPIClient(
        base_url="https://findqc.com/api",
    )
    
    try:
        # 测试：获取分类商品列表
        logger.info("测试：获取分类商品列表...")
        category_id = 4113  # 使用旧项目中存在的分类ID
        response = await api_client.get_category_products(
            catalogue_id=category_id,
            page=1,
            size=10,
        )
        
        items = api_client.extract_product_list(response)
        has_more = api_client.has_more_products(response)
        
        logger.info(f"成功获取商品列表：{len(items)} 个商品")
        logger.info(f"是否还有更多：{has_more}")
        
        if items:
            # 测试：获取第一个商品的详情
            first_item = items[0]
            findqc_id = first_item.get("id")
            item_id = first_item.get("itemId")
            mall_type = first_item.get("mallType")
            
            logger.info(f"测试：获取商品详情 (findqc_id={findqc_id}, itemId={item_id}, mallType={mall_type})...")
            
            try:
                detail_response = await api_client.get_product_detail(
                    item_id=item_id,
                    mall_type=mall_type,
                )
                logger.info("成功获取商品详情")
                
                # 测试：获取商品图集
                logger.info("测试：获取商品图集...")
                atlas_response = await api_client.get_product_atlas(
                    goods_id=str(findqc_id),
                    item_id=item_id,
                    mall_type=mall_type,
                    page=1,
                    size=10,
                )
                logger.info("成功获取商品图集")
                
            except Exception as e:
                logger.error(f"获取商品详情失败: {e}")
        
        logger.info("=" * 60)
        logger.info("API 测试完成")
        logger.info("=" * 60)
        
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        await api_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(test_spider())
    except KeyboardInterrupt:
        logger.info("测试被用户中断")
    except Exception as e:
        logger.error(f"测试异常: {e}")
        sys.exit(1)

