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
    
    async def get_target_categories(
        self, 
        start_cat_id: Optional[int] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取需要爬取的分类列表
        
        遍历指定范围的分类ID（从 start_cat_id 到 END_CAT_ID）
        实际是否有商品会在 fetch_category_products 中检查并跳过
        
        Args:
            start_cat_id: 起始分类ID（如果为 None，则使用配置的 START_CAT_ID）
            limit: 限制分类数量（用于测试）
        
        Returns:
            List[Dict]: 分类列表，每个元素包含 id 和 name
        """
        # 从配置中获取分类ID范围
        if start_cat_id is None:
            start_cat_id = settings.start_cat_id
        end_cat_id = settings.end_cat_id
        
        # 生成分类ID列表
        cat_ids = list(range(start_cat_id, end_cat_id + 1))
        
        # 如果设置了限制，只取前N个（用于测试）
        if limit:
            cat_ids = cat_ids[:limit]
        
        # 转换为分类字典列表
        categories = [{"id": cat_id, "name": f"分类_{cat_id}"} for cat_id in cat_ids]
        
        logger.info(f"将遍历分类ID范围: {start_cat_id} - {end_cat_id} (共 {len(categories)} 个分类)")
        
        return categories
    
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
            
            # 3. 整理图片结构并提取 QC 相关信息
            product_data, should_save = self.db_service.prepare_product_data(
                findqc_id=findqc_id,
                item_id=item_id,
                mall_type=mall_type,
                category_id=category_id,
                detail_response=detail_response,
                atlas_responses=atlas_responses,
            )
            
            # 检查是否应该保存（必须有 QC 图且最晚时间在30天内）
            if not should_save or product_data is None:
                logger.info(f"跳过商品 findqc_id={findqc_id}, item_id={item_id}: 不符合保存条件（无 QC 图或 QC 图不在30天内）")
                return
            
            # 提取 QC 相关数据
            last_qc_time = product_data.get("last_qc_time")
            qc_count_30days = product_data.get("qc_count_30days", 0)
            
            # 4. 检查数据库是否存在该商品
            product, operation_type = await self.db_service.check_and_update_existing_product(
                session=session,
                findqc_id=findqc_id,
                last_qc_time=last_qc_time,
                qc_count_30days=qc_count_30days,
            )
            
            # 5. 根据操作类型处理
            if operation_type == "exists_deleted":
                # 已存在的商品，但 QC 图不在30天内，已软删除，直接提交并返回
                await session.commit()
                logger.info(f"商品 findqc_id={findqc_id} 已软删除，跳过后续处理")
                return
            
            elif operation_type == "exists_updated":
                # 已存在的商品，QC 图在30天内，只更新了 QC 相关字段，直接提交并返回
                await session.commit()
                logger.info(f"商品 findqc_id={findqc_id} 已更新 QC 相关字段，跳过后续处理")
                return
            
            elif operation_type == "not_exists":
                # 不存在，保存新商品
                product = await self.db_service.save_or_update_product(
                    session=session,
                    product_data=product_data,
                    update_task_id=update_task_id,
                )
                
                # 6. 记录任务状态（t_tasks_products）
                await self.db_service.create_task_record(
                    session=session,
                    findqc_id=findqc_id,
                    update_task_id=update_task_id,
                    status=0,  # 0: 待执行（等待 AI 处理）
                )
                
                # 7. 提交事务
                await session.commit()
                
                # 8. 发送消息到消息队列（通知 AI 处理管道）
                try:
                    await mq_service.send_product_new_message(
                        task_id=update_task_id,
                        findqc_id=findqc_id,
                        product_id=product.id,
                        item_id=item_id,
                        mall_type=mall_type,
                    )
                except Exception as e:
                    logger.warning(f"发送消息失败（不影响主流程）: findqc_id={findqc_id}, error={e}")
                    # 消息发送失败不影响主流程
                
                logger.info(f"新商品保存完成: findqc_id={findqc_id}, item_id={item_id}")
            
        except Exception as e:
            await session.rollback()
            logger.error(f"处理商品失败: findqc_id={findqc_id}, error={e}")
            raise
    
    async def fetch_category_products(
        self,
        category: Dict[str, Any],
        update_task_id: int,
        max_products: Optional[int] = None,
    ) -> None:
        """
        抓取单个分类的所有商品
        
        对应白板上的双层循环结构：
        1. 遍历 Category
        2. 遍历 Page (While True)
        
        Args:
            category: 分类信息
            update_task_id: 任务批次ID
            max_products: 最大爬取商品数量（None表示不限制，用于测试）
        """
        category_id = category.get("id")
        category_name = category.get("name", str(category_id))
        logger.info(f"开始爬取分类: {category_name} (ID: {category_id})")
        if max_products:
            logger.info(f"测试模式：最多爬取 {max_products} 个商品")
        
        current_page = 1
        total_products = 0
        
        db = get_database()
        
        while True:
            # 检查是否达到最大数量限制
            if max_products and total_products >= max_products:
                logger.info(f"达到最大爬取数量限制 ({max_products})，停止爬取")
                break
            try:
                # 获取商品列表
                response = await self.api_client.get_category_products(
                    catalogue_id=category_id,
                    page=current_page,
                    size=self.page_size,
                )
                
                # 检查是否有更多商品（用于判断分类是否有商品）
                has_more = self.api_client.has_more_products(response)
                
                # 如果是第一页且 hasMore=False，说明该分类没有商品，直接跳过
                if current_page == 1 and not has_more:
                    # 提取商品列表，检查是否为空
                    items = self.api_client.extract_product_list(response)
                    if not items:
                        logger.info(f"分类 {category_name} (ID: {category_id}) 无商品，跳过")
                        return  # 直接返回，跳过该分类
                
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
                        # 检查是否达到最大数量限制
                        if max_products and total_products >= max_products:
                            logger.info(f"达到最大爬取数量限制 ({max_products})，停止处理")
                            break
                        
                        try:
                            await self.process_single_product(
                                session=session,
                                item_summary=item_summary,
                                category=category,
                                update_task_id=update_task_id,
                            )
                            total_products += 1
                            logger.info(f"已爬取商品数量: {total_products}/{max_products if max_products else '∞'}")
                            await asyncio.sleep(self.delay)  # 延迟，防止被封
                        except Exception as e:
                            logger.error(f"处理商品失败，继续下一个: {item_summary}, error={e}")
                            continue
                    
                    # 如果达到限制，跳出外层循环
                    if max_products and total_products >= max_products:
                        break
                
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
    
    async def spider_main_process(
        self, 
        update_task_id: int, 
        max_products: Optional[int] = None,
        start_cat_id: Optional[int] = None,
    ) -> None:
        """
        主爬虫流程
        
        对应白板上的双层循环结构：
        1. 遍历 Category
        2. 遍历 Page (While True)
        
        Args:
            update_task_id: 任务批次ID
            max_products: 最大爬取商品数量（None表示不限制，用于测试）
            start_cat_id: 起始分类ID（如果为 None，则使用配置的 START_CAT_ID 或断点续传）
        """
        logger.info(f"开始爬虫任务，update_task_id={update_task_id}")
        if max_products:
            logger.info(f"测试模式：最多爬取 {max_products} 个商品")
        if start_cat_id:
            logger.info(f"断点续传模式：从分类ID {start_cat_id} 开始")
        
        # 获取需要爬取的分类列表
        # 对应白板: for c in categories
        category_list = await self.get_target_categories(start_cat_id=start_cat_id)
        
        # 并发处理多个分类（类似旧项目的多线程并发）
        max_concurrent = settings.max_concurrent_categories
        logger.info(f"并发处理分类数量: {max_concurrent}")
        
        # 使用信号量控制并发数量
        semaphore = asyncio.Semaphore(max_concurrent)
        total_processed = 0
        should_stop = False  # 用于控制是否停止处理（达到商品数量限制时）
        
        async def process_category_with_semaphore(category: Dict[str, Any]) -> None:
            """带信号量控制的分类处理函数"""
            nonlocal should_stop
            if should_stop:
                return
                
            async with semaphore:
                if should_stop:
                    return
                    
                try:
                    await self.fetch_category_products(
                        category=category,
                        update_task_id=update_task_id,
                        max_products=max_products,
                    )
                except Exception as e:
                    logger.error(f"分类爬取失败: category={category.get('id')}, error={e}")
        
        # 创建所有任务
        tasks = [asyncio.create_task(process_category_with_semaphore(category)) for category in category_list]
        
        # 并发执行所有任务
        for task in asyncio.as_completed(tasks):
            try:
                await task
                total_processed += 1
                    
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
        
        logger.info(f"爬虫任务完成，update_task_id={update_task_id}，共处理 {total_processed} 个分类")

