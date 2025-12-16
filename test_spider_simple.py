#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版爬虫测试脚本

只测试API调用，不依赖数据库和RabbitMQ。
用于验证FindQC API是否可以正常访问。
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from loguru import logger
from service_spider.api_client import FindQCAPIClient


async def test_api():
    """测试API调用"""
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )
    
    logger.info("=" * 60)
    logger.info("开始测试 FindQC API 调用")
    logger.info("=" * 60)
    
    # 初始化 API 客户端
    api_client = FindQCAPIClient(
        base_url="https://findqc.com/api",
    )
    
    try:
        # 测试1：获取分类商品列表
        logger.info("\n[测试1] 获取分类商品列表...")
        category_id = 4113  # 使用旧项目中存在的分类ID
        logger.info(f"分类ID: {category_id}, 页码: 1, 每页数量: 10")
        
        response = await api_client.get_category_products(
            catalogue_id=category_id,
            page=1,
            size=10,
        )
        
        items = api_client.extract_product_list(response)
        has_more = api_client.has_more_products(response)
        
        logger.info(f"✓ 成功获取商品列表：{len(items)} 个商品")
        logger.info(f"  是否还有更多：{has_more}")
        
        if not items:
            logger.warning("⚠ 该分类没有商品，尝试其他分类ID...")
            # 尝试其他分类ID
            for test_cat_id in [4114, 4115, 4116, 4117]:
                try:
                    response = await api_client.get_category_products(
                        catalogue_id=test_cat_id,
                        page=1,
                        size=10,
                    )
                    items = api_client.extract_product_list(response)
                    if items:
                        logger.info(f"✓ 分类ID {test_cat_id} 有 {len(items)} 个商品")
                        category_id = test_cat_id
                        break
                except Exception as e:
                    logger.debug(f"分类ID {test_cat_id} 测试失败: {e}")
                    continue
        
        if not items:
            logger.error("❌ 所有测试分类都没有商品")
            return
        
        # 显示前几个商品的基本信息
        logger.info(f"\n前 {min(3, len(items))} 个商品信息：")
        for i, item in enumerate(items[:3], 1):
            findqc_id = item.get("id")
            item_id = item.get("itemId")
            mall_type = item.get("mallType")
            title = item.get("title", "")[:50]  # 标题前50个字符
            logger.info(f"  {i}. findqc_id={findqc_id}, itemId={item_id}, mallType={mall_type}")
            logger.info(f"     标题: {title}...")
        
        # 测试2：获取第一个商品的详情
        if items:
            first_item = items[0]
            findqc_id = first_item.get("id")
            item_id = first_item.get("itemId")
            mall_type = first_item.get("mallType")
            
            logger.info(f"\n[测试2] 获取商品详情...")
            logger.info(f"findqc_id={findqc_id}, itemId={item_id}, mallType={mall_type}")
            
            try:
                detail_response = await api_client.get_product_detail(
                    item_id=item_id,
                    mall_type=mall_type,
                )
                logger.info("✓ 成功获取商品详情")
                
                # 提取详情数据
                detail_data = api_client.extract_product_detail(detail_response)
                pic_list = detail_data.get("picList", [])
                qc_list = detail_data.get("qcList", [])
                props_list = detail_data.get("propsList", [])
                
                logger.info(f"  主图数量: {len(pic_list)}")
                logger.info(f"  QC图数量: {len(qc_list)}")
                logger.info(f"  SKU规格数量: {len(props_list)}")
                
            except Exception as e:
                logger.error(f"❌ 获取商品详情失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 测试3：获取商品图集
            logger.info(f"\n[测试3] 获取商品图集...")
            try:
                atlas_response = await api_client.get_product_atlas(
                    goods_id=str(findqc_id),
                    item_id=item_id,
                    mall_type=mall_type,
                    page=1,
                    size=10,
                )
                logger.info("✓ 成功获取商品图集")
                
                atlas_data = atlas_response.get("data", {})
                atlas_list = atlas_data.get("atlasList", [])
                has_more_atlas = atlas_data.get("hasMore", False)
                
                logger.info(f"  图集数量: {len(atlas_list)}")
                logger.info(f"  是否还有更多: {has_more_atlas}")
                
            except Exception as e:
                logger.warning(f"⚠ 获取商品图集失败（可能该商品没有图集）: {e}")
        
        logger.info("\n" + "=" * 60)
        logger.info("API 测试完成 ✓")
        logger.info("=" * 60)
        
        # 如果测试成功，提示可以运行完整爬虫
        logger.info("\n提示：如果API测试成功，可以运行完整爬虫：")
        logger.info("  python3 -m service_spider.main")
        logger.info("（需要先配置数据库和安装依赖）")
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await api_client.close()


if __name__ == "__main__":
    try:
        asyncio.run(test_api())
    except KeyboardInterrupt:
        logger.info("\n测试被用户中断")
    except Exception as e:
        logger.error(f"测试异常: {e}")
        sys.exit(1)

