"""
FindQC API 客户端

封装 FindQC API 的调用，提供商品列表和详情获取功能。
"""

import asyncio
from typing import Dict, List, Optional, Any
import httpx
from loguru import logger


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
            httpx.HTTPStatusError: 当 API 请求失败时
        """
        url = "/goods/getCategoryProducts"
        params = {
            "catalogueId": catalogue_id,
            "page": page,
            "size": size,
            "currencyType": currency_type,
            "langType": lang_type,
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"获取分类商品列表失败: catalogue_id={catalogue_id}, page={page}, status={e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"获取分类商品列表异常: catalogue_id={catalogue_id}, page={page}, error={e}")
            raise
    
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
            httpx.HTTPStatusError: 当 API 请求失败时
        """
        url = "/goods/detail"
        params = {
            "itemId": item_id,
            "mallType": mall_type,
            "currencyType": currency_type,
            "langType": lang_type,
            "notNeedQc": str(not_need_qc).lower(),
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"获取商品详情失败: item_id={item_id}, mall_type={mall_type}, status={e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"获取商品详情异常: item_id={item_id}, mall_type={mall_type}, error={e}")
            raise
    
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
            httpx.HTTPStatusError: 当 API 请求失败时
        """
        url = "/goods/atlas"
        params = {
            "goodsId": goods_id,
            "itemId": item_id,
            "mallType": mall_type,
            "page": page,
            "size": size,
        }
        
        try:
            response = await self.client.get(url, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"获取商品图集失败: goods_id={goods_id}, page={page}, status={e.response.status_code}")
            raise
        except Exception as e:
            logger.error(f"获取商品图集异常: goods_id={goods_id}, page={page}, error={e}")
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

