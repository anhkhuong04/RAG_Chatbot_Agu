import re
import logging
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
            "tiền học", "học bổng", "miễn giảm",
        ],
        "Tuyển sinh": [
            "tuyển sinh", "xét tuyển", "đăng ký", "nộp hồ sơ",
            "phương thức", "chỉ tiêu", "nguyện vọng", "hồ sơ",
        ],
        "Khác": [
            "giới thiệu", "thông tin", "ngành", "chương trình",
            "cơ sở vật chất", "đội ngũ", "liên hệ",
        ],
    }
    
    # Categories stored as CSV only (not in Qdrant) — skip these in post-filtering
    CSV_ONLY_CATEGORIES = {"Điểm chuẩn", "Học phí"}
    
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
        
        # Extract category (skip CSV-only categories — they're not in Qdrant)
        category = self._extract_category(query_lower)
        if category and category not in self.CSV_ONLY_CATEGORIES:
            filters["category"] = category
        
        if filters:
            logger.debug(f"Extracted filters: {filters}")
        
        return filters
    
    def _extract_year(self, query: str) -> Optional[int]:
        for pattern in self.YEAR_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                if self.MIN_YEAR <= year <= self.MAX_YEAR:
                    return year
        return None
    
    def _extract_category(self, query_lower: str) -> Optional[str]:
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in query_lower:
                    return category
        return None
    
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
                    # Node has no year metadata - don't filter it out
                    # This allows documents without year to still be included
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
        
        # Fallback behavior
        if not filtered and not strict:
            logger.warning(
                f"No nodes matched filters {filters}. "
                f"Returning all {len(nodes)} nodes."
            )
            return nodes
        
        logger.debug(f"Post-filter: {len(nodes)} → {len(filtered)} nodes")
        return filtered
    
    def get_filter_summary(self, filters: Dict[str, Any]) -> str:
        if not filters:
            return "No filters applied"
        
        parts = []
        if "year" in filters:
            parts.append(f"Năm {filters['year']}")
        if "category" in filters:
            parts.append(f"Danh mục: {filters['category']}")
        
        return ", ".join(parts)


# Singleton instance
_filter_service: Optional[MetadataFilterService] = None


def get_metadata_filter_service(
    default_year: Optional[int] = None,
) -> MetadataFilterService:
    global _filter_service
    
    if _filter_service is None:
        _filter_service = MetadataFilterService(default_year=default_year)
    
    return _filter_service
