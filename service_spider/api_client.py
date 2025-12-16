"""
FindQC API 客户端

封装 FindQC API 的调用，提供商品列表和详情获取功能。
"""

import asyncio
from functools import wraps
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
import httpx
from loguru import logger

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from shared_lib.config import settings


def async_retry(
    max_attempts: int = None,
    delay: float = None,
    backoff: float = None,
    retryable_errors: Tuple[Type[Exception], ...] = None,
):
    """
    异步重试装饰器
    
    Args:
        max_attempts: 最大重试次数（默认从配置读取）
        delay: 初始延迟秒数（默认从配置读取）
        backoff: 退避倍数（默认从配置读取）
        retryable_errors: 可重试的异常类型（默认：网络错误和5xx错误）
    """
    # 使用配置的默认值
    if max_attempts is None:
        max_attempts = settings.api_retry_max_attempts
    if delay is None:
        delay = settings.api_retry_delay
    if backoff is None:
        backoff = settings.api_retry_backoff
    if retryable_errors is None:
        retryable_errors = (
            httpx.RequestError,
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
        )
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPStatusError as e:
                    status_code = e.response.status_code
                    # 5xx 错误（服务器错误）可以重试
                    if status_code >= 500:
                        if attempt < max_attempts:
                            logger.warning(
                                f"API 请求失败（{status_code}），{current_delay:.1f}秒后重试 "
                                f"({attempt}/{max_attempts}): {func.__name__}"
                            )
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                            last_exception = e
                            continue
                        else:
                            logger.error(
                                f"API 请求失败（{status_code}），已达最大重试次数 "
                                f"({max_attempts}): {func.__name__}"
                            )
                            raise
                    # 429 Too Many Requests 可以重试
                    elif status_code == 429:
                        if attempt < max_attempts:
                            logger.warning(
                                f"API 请求被限流（429），{current_delay:.1f}秒后重试 "
                                f"({attempt}/{max_attempts}): {func.__name__}"
                            )
                            await asyncio.sleep(current_delay)
                            current_delay *= backoff
                            last_exception = e
                            continue
                        else:
                            logger.error(
                                f"API 请求被限流（429），已达最大重试次数 "
                                f"({max_attempts}): {func.__name__}"
                            )
                            raise
                    else:
                        # 4xx 错误（客户端错误）不重试，直接抛出
                        logger.error(
                            f"API 请求失败（{status_code}，客户端错误），不重试: {func.__name__}"
                        )
                        raise
                except retryable_errors as e:
                    # 网络错误可以重试
                    if attempt < max_attempts:
                        logger.warning(
                            f"API 请求失败（网络错误），{current_delay:.1f}秒后重试 "
                            f"({attempt}/{max_attempts}): {func.__name__}, error={type(e).__name__}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                        last_exception = e
                        continue
                    else:
                        logger.error(
                            f"API 请求失败（网络错误），已达最大重试次数 "
                            f"({max_attempts}): {func.__name__}, error={type(e).__name__}"
                        )
                        raise
                except Exception as e:
                    # 其他异常直接抛出，不重试
                    logger.error(f"API 请求发生未知异常，不重试: {func.__name__}, error={type(e).__name__}: {e}")
                    raise
            
            # 所有重试都失败（理论上不会执行到这里）
            if last_exception:
                raise last_exception
        
        return wrapper
    return decorator


class FindQCAPIClient:
    """FindQC API 客户端"""
    
    def __init__(self, base_url: str = "https://findqc.com/api", api_key: Optional[str] = None):
        """
        初始化 API 客户端
        
        Args:
            base_url: API 基础URL
            api_key: API 密钥（如果需要）
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
        }
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
        # 创建 HTTP 客户端（支持连接池）
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=30.0,
            follow_redirects=True,
        )
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.client.aclose()
    
    @async_retry()
    async def _get_category_products_internal(
        self,
        catalogue_id: int,
        page: int = 1,
        size: int = 20,
        currency_type: str = "USD",
        lang_type: str = "en",
    ) -> Dict[str, Any]:
        """
        获取分类下的商品列表（内部方法，带重试）
        """
        url = "/goods/getCategoryProducts"
        params = {
            "catalogueId": catalogue_id,
            "page": page,
            "size": size,
            "currencyType": currency_type,
            "langType": lang_type,
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_category_products(
        self,
        catalogue_id: int,
        page: int = 1,
        size: int = 20,
        currency_type: str = "USD",
        lang_type: str = "en",
    ) -> Dict[str, Any]:
        """
        获取分类下的商品列表（分页）
        
        Args:
            catalogue_id: 分类ID
            page: 页码（从1开始）
            size: 每页数量
            currency_type: 货币类型
            lang_type: 语言类型
            
        Returns:
            Dict: API 响应数据，包含商品列表和 hasMore 标志
            
        Raises:
            httpx.HTTPStatusError: 当 API 请求失败且重试次数用尽时
            httpx.RequestError: 当网络错误且重试次数用尽时
        """
        try:
            return await self._get_category_products_internal(
                catalogue_id=catalogue_id,
                page=page,
                size=size,
                currency_type=currency_type,
                lang_type=lang_type,
            )
        except Exception as e:
            logger.error(f"获取分类商品列表最终失败: catalogue_id={catalogue_id}, page={page}, error={type(e).__name__}")
            raise
    
    @async_retry()
    async def _get_product_detail_internal(
        self,
        item_id: str,
        mall_type: str,
        currency_type: str = "USD",
        lang_type: str = "en",
        not_need_qc: bool = False,
    ) -> Dict[str, Any]:
        """
        获取商品详情（内部方法，带重试）
        """
        url = "/goods/detail"
        params = {
            "itemId": item_id,
            "mallType": mall_type,
            "currencyType": currency_type,
            "langType": lang_type,
            "notNeedQc": str(not_need_qc).lower(),
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_product_detail(
        self,
        item_id: str,
        mall_type: str,
        currency_type: str = "USD",
        lang_type: str = "en",
        not_need_qc: bool = False,
    ) -> Dict[str, Any]:
        """
        获取商品详情
        
        Args:
            item_id: 商品外部ID
            mall_type: 商城类型
            currency_type: 货币类型
            lang_type: 语言类型
            not_need_qc: 是否需要 QC 数据（False 表示需要）
            
        Returns:
            Dict: 商品详情数据
            
        Raises:
            httpx.HTTPStatusError: 当 API 请求失败且重试次数用尽时
            httpx.RequestError: 当网络错误且重试次数用尽时
        """
        try:
            return await self._get_product_detail_internal(
                item_id=item_id,
                mall_type=mall_type,
                currency_type=currency_type,
                lang_type=lang_type,
                not_need_qc=not_need_qc,
            )
        except Exception as e:
            logger.error(f"获取商品详情最终失败: item_id={item_id}, mall_type={mall_type}, error={type(e).__name__}")
            raise
    
    @async_retry()
    async def _get_product_atlas_internal(
        self,
        goods_id: str,
        item_id: str,
        mall_type: str,
        page: int = 1,
        size: int = 10,
    ) -> Dict[str, Any]:
        """
        获取商品图集（内部方法，带重试）
        """
        url = "/goods/atlas"
        params = {
            "goodsId": goods_id,
            "itemId": item_id,
            "mallType": mall_type,
            "page": page,
            "size": size,
        }
        
        response = await self.client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    
    async def get_product_atlas(
        self,
        goods_id: str,
        item_id: str,
        mall_type: str,
        page: int = 1,
        size: int = 10,
    ) -> Dict[str, Any]:
        """
        获取商品图集（QC图、视频等）
        
        Args:
            goods_id: FindQC 商品ID
            item_id: 商品外部ID
            mall_type: 商城类型
            page: 页码
            size: 每页数量
            
        Returns:
            Dict: 图集数据，包含 atlasList 和 hasMore
            
        Raises:
            httpx.HTTPStatusError: 当 API 请求失败且重试次数用尽时
            httpx.RequestError: 当网络错误且重试次数用尽时
        """
        try:
            return await self._get_product_atlas_internal(
                goods_id=goods_id,
                item_id=item_id,
                mall_type=mall_type,
                page=page,
                size=size,
            )
        except Exception as e:
            logger.error(f"获取商品图集最终失败: goods_id={goods_id}, page={page}, error={type(e).__name__}")
            raise
    
    def extract_product_list(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        从 API 响应中提取商品列表
        
        Args:
            response: getCategoryProducts 的响应
            
        Returns:
            List[Dict]: 商品列表
        """
        data = response.get("data", {})
        return data.get("data", [])
    
    def has_more_products(self, response: Dict[str, Any]) -> bool:
        """
        判断是否还有更多商品（是否还有下一页）
        
        Args:
            response: getCategoryProducts 的响应
            
        Returns:
            bool: True 表示还有更多，False 表示已经是最后一页
        """
        data = response.get("data", {})
        return data.get("hasMore", False)
    
    def extract_product_detail(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        从 API 响应中提取商品详情
        
        Args:
            response: get_product_detail 的响应
            
        Returns:
            Dict: 商品详情数据
        """
        data = response.get("data", {})
        return data.get("data", {})

