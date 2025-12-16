"""
爬虫核心逻辑

实现商品数据的爬取流程，包括分类遍历、分页处理、商品详情获取等。
参考 getdata伪代码 和白板设计。
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared_lib.database import get_database, init_database
from shared_lib.config import settings
from service_spider.api_client import FindQCAPIClient
from service_spider.db_service import ProductDBService
from service_spider.mq_service import mq_service


class SpiderService:
    """爬虫服务"""
    
    def __init__(
        self,
        api_client: FindQCAPIClient,
        page_size: int = 20,
        delay_between_requests: float = 0.5,
    ):
        """
        初始化爬虫服务
        
        Args:
            api_client: FindQC API 客户端
            page_size: 每页商品数量
            delay_between_requests: 请求之间的延迟（秒），防止被封
        """
        self.api_client = api_client
        self.page_size = page_size
        self.delay = delay_between_requests
        self.db_service = ProductDBService()
    
    async def get_target_categories(self) -> List[Dict[str, Any]]:
        """
        获取需要爬取的分类列表
        
        这里返回一个示例列表，实际应该从配置文件或数据库读取。
        
        Returns:
            List[Dict]: 分类列表，每个元素包含 id 和 name
        """
        # TODO: 从配置文件或数据库读取分类列表
        return [
            {"id": 101, "name": "户外服装"},
            {"id": 102, "name": "露营装备"},
        ]
    
    async def process_single_product(
        self,
        session,
        item_summary: Dict[str, Any],
        category: Dict[str, Any],
        update_task_id: int,
    ) -> None:
        """
        处理单个商品详情
        
        对应白板右侧的: detail { QC images, main images, sku images }
        以及写入数据库 t_products 的逻辑
        
        Args:
            session: 数据库会话
            item_summary: 商品摘要信息（来自列表接口）
            category: 分类信息
            update_task_id: 任务批次ID
        """
        findqc_id = item_summary.get("id")
        item_id = item_summary.get("itemId", "")
        mall_type = item_summary.get("mallType", "")
        category_id = category.get("id")
        
        if not findqc_id or not item_id or not mall_type:
            logger.warning(f"商品信息不完整，跳过: {item_summary}")
            return
        
        try:
            # 1. 获取商品详情
            detail_response = await self.api_client.get_product_detail(
                item_id=item_id,
                mall_type=mall_type,
            )
            
            # 2. 获取商品图集（分页获取所有 QC 图）
            atlas_responses = []
            atlas_page = 1
            while True:
                try:
                    atlas_response = await self.api_client.get_product_atlas(
                        goods_id=str(findqc_id),
                        item_id=item_id,
                        mall_type=mall_type,
                        page=atlas_page,
                        size=10,
                    )
                    atlas_data = atlas_response.get("data", {})
                    atlas_list = atlas_data.get("atlasList", [])
                    
                    if not atlas_list:
                        break
                    
                    atlas_responses.append(atlas_response)
                    
                    if not atlas_data.get("hasMore", False):
                        break
                    
                    atlas_page += 1
                    await asyncio.sleep(self.delay)  # 延迟
                except Exception as e:
                    logger.error(f"获取图集失败: findqc_id={findqc_id}, page={atlas_page}, error={e}")
                    break
            
            # 3. 整理图片结构（这是后续AI图搜的基础）
            product_data = self.db_service.prepare_product_data(
                findqc_id=findqc_id,
                item_id=item_id,
                mall_type=mall_type,
                category_id=category_id,
                detail_response=detail_response,
                atlas_responses=atlas_responses,
            )
            
            # 4. 写入数据库（Upsert: 存在则更新，不存在则插入）
            product = await self.db_service.save_or_update_product(
                session=session,
                product_data=product_data,
                update_task_id=update_task_id,
            )
            
            # 5. 记录任务状态（t_tasks_products）
            await self.db_service.create_task_record(
                session=session,
                findqc_id=findqc_id,
                update_task_id=update_task_id,
                status=0,  # 0: 待执行（等待 AI 处理）
            )
            
            # 6. 提交事务
            await session.commit()
            
            # 7. 发送消息到消息队列（通知 AI 处理管道）
            try:
                await mq_service.send_product_new_message(
                    task_id=update_task_id,
                    findqc_id=findqc_id,
                    product_id=product.id,
                    item_id=item_id,
                    mall_type=mall_type,
                )
            except Exception as e:
                logger.error(f"发送消息失败: findqc_id={findqc_id}, error={e}")
                # 消息发送失败不影响主流程
            
            logger.info(f"商品处理完成: findqc_id={findqc_id}, item_id={item_id}")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"处理商品失败: findqc_id={findqc_id}, error={e}")
            raise
    
    async def fetch_category_products(
        self,
        category: Dict[str, Any],
        update_task_id: int,
    ) -> None:
        """
        抓取单个分类的所有商品
        
        对应白板上的双层循环结构：
        1. 遍历 Category
        2. 遍历 Page (While True)
        
        Args:
            category: 分类信息
            update_task_id: 任务批次ID
        """
        category_id = category.get("id")
        category_name = category.get("name", str(category_id))
        logger.info(f"开始爬取分类: {category_name} (ID: {category_id})")
        
        current_page = 1
        total_products = 0
        
        db = get_database()
        
        while True:
            try:
                # 获取商品列表
                response = await self.api_client.get_category_products(
                    catalogue_id=category_id,
                    page=current_page,
                    size=self.page_size,
                )
                
                # 提取商品列表
                items = self.api_client.extract_product_list(response)
                
                # 核心判断逻辑：如果当前页获取的数量小于页大小，说明是最后一页
                # 对应白板: if len(items) < page-size ... all_finish = True
                is_last_page = len(items) < self.page_size
                
                if not items:
                    logger.info(f"分类 {category_name} 第 {current_page} 页无数据")
                    break
                
                # 遍历并处理单个商品
                # 对应白板: else for item in items
                async with db.async_session_maker() as session:
                    for item_summary in items:
                        try:
                            await self.process_single_product(
                                session=session,
                                item_summary=item_summary,
                                category=category,
                                update_task_id=update_task_id,
                            )
                            total_products += 1
                            await asyncio.sleep(self.delay)  # 延迟，防止被封
                        except Exception as e:
                            logger.error(f"处理商品失败，继续下一个: {item_summary}, error={e}")
                            continue
                
                # 循环控制
                # 对应白板: if all_finish: break
                if is_last_page:
                    logger.info(f"分类 {category_name} 爬取结束，共 {total_products} 个商品")
                    break
                
                # 翻页逻辑
                current_page += 1
                await asyncio.sleep(self.delay)  # 翻页延迟
                
            except Exception as e:
                logger.error(f"获取分类商品列表失败: category_id={category_id}, page={current_page}, error={e}")
                break
    
    async def spider_main_process(self, update_task_id: int) -> None:
        """
        主爬虫流程
        
        对应白板上的双层循环结构：
        1. 遍历 Category
        2. 遍历 Page (While True)
        
        Args:
            update_task_id: 任务批次ID
        """
        logger.info(f"开始爬虫任务，update_task_id={update_task_id}")
        
        # 获取需要爬取的分类列表
        # 对应白板: for c in categories
        category_list = await self.get_target_categories()
        
        for category in category_list:
            try:
                await self.fetch_category_products(
                    category=category,
                    update_task_id=update_task_id,
                )
            except Exception as e:
                logger.error(f"分类爬取失败，继续下一个: category={category}, error={e}")
                continue
        
        logger.info(f"爬虫任务完成，update_task_id={update_task_id}")

