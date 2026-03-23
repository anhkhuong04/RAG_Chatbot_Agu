import re
import logging
import unicodedata
from typing import List, Dict, Optional, Any
from datetime import datetime

from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import (
    MetadataFilters,
    MetadataFilter,
    FilterOperator,
    FilterCondition,
)

logger = logging.getLogger(__name__)


class MetadataFilterService:
    # Patterns to extract year from Vietnamese queries
    YEAR_PATTERNS = [
        r'năm\s*(\d{4})',           # "năm 2025"
        r'(\d{4})\s*[-–]\s*\d{4}',  # "2024-2025" → first year
        r'niên\s*khóa\s*(\d{4})',   # "niên khóa 2025"
        r'khóa\s*(\d{4})',          # "khóa 2025"
        r'kỳ\s*tuyển\s*sinh\s*(\d{4})',  # "kỳ tuyển sinh 2025"
        r'\b(20[2-3]\d)\b',         # Standalone year 2020-2039
    ]
    
    # Category keywords mapping - Values match DB categories (Vietnamese with diacritics)
    CATEGORY_KEYWORDS = {
        "Điểm chuẩn": [
            "điểm chuẩn", "điểm trúng tuyển", "điểm đỗ", "điểm đậu",
            "điểm xét tuyển", "điểm thi", "điểm sàn",
        ],
        "Học phí": [
            "học phí", "chi phí", "đóng tiền", "phí", "lệ phí",
            "tiền học", "miễn giảm",
        ],
        "Tuyển sinh": [
            "tuyển sinh", "xét tuyển", "đăng ký", "nộp hồ sơ", "thông tin",
            "phương thức", "chỉ tiêu", "nguyện vọng", "hồ sơ", "thủ tục", "quy đổi", "ưu tiên xét tuyển"
        ],
        "Khác": [
            "giới thiệu",  "ngành", "chương trình",
            "cơ sở vật chất", "đội ngũ", "liên hệ",
        ],
    }
    
    CSV_ONLY_CATEGORIES: set[str] = set()
    
    # Valid year range
    MIN_YEAR = 2020
    MAX_YEAR = 2035
    
    def __init__(self, default_year: Optional[int] = None):
        self.default_year = default_year or datetime.now().year
        logger.info(f"MetadataFilterService initialized (default_year={self.default_year})")
    
    def extract_filters(self, query: str) -> Dict[str, Any]:
        filters = {}
        query_lower = query.lower()
        
        # Extract year
        year = self._extract_year(query)
        if year:
            filters["year"] = year
        
        # Extract category
        category = self._extract_category(query_lower)

        if category and category != "Khác":
            filters["category"] = category
        
        if filters:
            logger.debug(f"Extracted filters: {filters}")
        
        return filters
    
    def _extract_year(self, query: str) -> Optional[int]:
        query_lower = query.lower()

        # Relative-year phrases frequently used by users.
        now_year = datetime.now().year
        if any(token in query_lower for token in ["năm trước", "năm vừa rồi", "nam truoc"]):
            relative = now_year - 1
            if self.MIN_YEAR <= relative <= self.MAX_YEAR:
                return relative

        if any(token in query_lower for token in ["năm nay", "nam nay"]):
            if self.MIN_YEAR <= now_year <= self.MAX_YEAR:
                return now_year

        for pattern in self.YEAR_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                if self.MIN_YEAR <= year <= self.MAX_YEAR:
                    return year
        return None
    
    def _extract_category(self, query_lower: str) -> Optional[str]:
        query_norm = self._normalize_for_match(query_lower)
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                keyword_norm = self._normalize_for_match(keyword)
                if keyword_norm in query_norm:
                    return category
        return None

    @staticmethod
    def _normalize_for_match(text: str) -> str:
        """Normalize Vietnamese text for robust diacritic-insensitive matching."""
        text = unicodedata.normalize("NFKD", text)
        text = "".join(ch for ch in text if not unicodedata.combining(ch))
        text = text.replace("đ", "d").replace("Đ", "D")
        return text.lower().replace("_", " ")
    
    def build_qdrant_filters(self, filters: Dict[str, Any]) -> Optional[MetadataFilters]:
        if not filters:
            return None
        
        filter_list = []
        
        if "year" in filters:
            filter_list.append(
                MetadataFilter(
                    key="year",
                    value=filters["year"],
                    operator=FilterOperator.EQ,
                )
            )
        
        if "category" in filters:
            filter_list.append(
                MetadataFilter(
                    key="category",
                    value=filters["category"],
                    operator=FilterOperator.EQ,
                )
            )
        
        if filter_list:
            return MetadataFilters(
                filters=filter_list,
                condition=FilterCondition.AND,
            )
        
        return None
    
    def apply_post_filters(
        self,
        nodes: List[NodeWithScore],
        filters: Dict[str, Any],
        strict: bool = False,
    ) -> List[NodeWithScore]:
        if not filters or not nodes:
            return nodes
        
        filtered = []
        
        for node in nodes:
            metadata = node.node.metadata or {}
            match = True
            
            # Check year filter
            if "year" in filters:
                node_year = metadata.get("year")
                if node_year is not None:
                    # Handle both int and string years
                    try:
                        if int(node_year) != int(filters["year"]):
                            match = False
                    except (ValueError, TypeError):
                        # Year doesn't match or can't be converted
                        match = False
                else:
                    pass
            
            # Check category filter - use fuzzy matching
            if "category" in filters and match:
                node_category = metadata.get("category", "")
                filter_category = filters["category"]
                
                if node_category:
                    # Normalize for comparison (remove spaces, lowercase)
                    node_cat_norm = node_category.lower().replace(" ", "").replace("_", "")
                    filter_cat_norm = filter_category.lower().replace(" ", "").replace("_", "")
                    
                    # Check if they match or one contains the other
                    if node_cat_norm != filter_cat_norm and filter_cat_norm not in node_cat_norm and node_cat_norm not in filter_cat_norm:
                        match = False
            
            if match:
                filtered.append(node)
        
        if not filtered and "category" in filters:
            logger.warning(
                f"No nodes matched category filter {filters}. Returning empty list."
            )
            return []

        if not filtered and ("year" in filters):
            logger.warning(
                f"No nodes matched year filter {filters}. Returning empty list."
            )
            return []

        if not filtered and not strict:
            logger.warning(
                f"No nodes matched filters {filters}. "
                f"Returning all {len(nodes)} nodes."
            )
            return nodes
        
        logger.debug(f"Post-filter: {len(nodes)} → {len(filtered)} nodes")
        return filtered
