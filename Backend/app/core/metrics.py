"""
Metrics Tracking System
Track và aggregate performance metrics
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import statistics
from app.core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Metric:
    """Single metric data point"""
    name: str
    value: float
    timestamp: datetime
    unit: str = ""
    tags: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """
    Collect và aggregate metrics
    """
    
    def __init__(self):
        self.metrics: Dict[str, List[Metric]] = {}
        self.counters: Dict[str, int] = {}
    
    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "",
        tags: Optional[Dict[str, str]] = None
    ):
        """
        Record a metric value
        
        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
            tags: Additional tags
        """
        metric = Metric(
            name=name,
            value=value,
            timestamp=datetime.utcnow(),
            unit=unit,
            tags=tags or {}
        )
        
        if name not in self.metrics:
            self.metrics[name] = []
        
        self.metrics[name].append(metric)
        
        logger.debug(
            f"Metric recorded: {name}",
            context={
                "metric": name,
                "value": value,
                "unit": unit,
                "tags": tags
            }
        )
    
    def increment_counter(self, name: str, delta: int = 1):
        """
        Increment a counter
        
        Args:
            name: Counter name
            delta: Increment amount
        """
        if name not in self.counters:
            self.counters[name] = 0
        
        self.counters[name] += delta
    
    def get_stats(self, metric_name: str) -> Dict:
        """
        Get statistics for a metric
        
        Args:
            metric_name: Name of metric
            
        Returns:
            Dict with stats (count, mean, median, min, max, etc.)
        """
        if metric_name not in self.metrics:
            return {}
        
        values = [m.value for m in self.metrics[metric_name]]
        
        if not values:
            return {}
        
        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0
        }
    
    def get_counter(self, name: str) -> int:
        """Get counter value"""
        return self.counters.get(name, 0)
    
    def get_summary(self) -> Dict:
        """
        Get summary của tất cả metrics
        
        Returns:
            Dict with all metrics summary
        """
        summary = {
            "metrics": {},
            "counters": self.counters.copy()
        }
        
        for metric_name in self.metrics:
            summary["metrics"][metric_name] = self.get_stats(metric_name)
        
        return summary
    
    def reset(self):
        """Reset all metrics"""
        self.metrics.clear()
        self.counters.clear()
        logger.info("Metrics reset")


# Global metrics collector
_metrics_collector = MetricsCollector()


def get_metrics_collector() -> MetricsCollector:
    """Get global metrics collector instance"""
    return _metrics_collector


# ==========================================
# PREDEFINED METRICS
# ==========================================

class RAGMetrics:
    """
    Predefined metrics cho RAG system
    """
    
    # Query Transformation
    QUERY_TRANSFORM_DURATION = "query_transform_duration_ms"
    QUERY_TRANSFORM_COUNT = "query_transform_count"
    
    # Retrieval
    RETRIEVAL_DURATION = "retrieval_duration_ms"
    RETRIEVAL_COUNT = "retrieval_count"
    RETRIEVAL_DOCS_COUNT = "retrieval_docs_count"
    
    # Re-ranking
    RERANK_DURATION = "rerank_duration_ms"
    RERANK_COUNT = "rerank_count"
    RERANK_INPUT_DOCS = "rerank_input_docs"
    RERANK_OUTPUT_DOCS = "rerank_output_docs"
    
    # LLM
    LLM_DURATION = "llm_duration_ms"
    LLM_TOKEN_COUNT = "llm_token_count"
    LLM_CALL_COUNT = "llm_call_count"
    
    # End-to-End
    E2E_DURATION = "e2e_duration_ms"
    E2E_SUCCESS_COUNT = "e2e_success_count"
    E2E_ERROR_COUNT = "e2e_error_count"
    
    # API
    API_REQUEST_COUNT = "api_request_count"
    API_RESPONSE_TIME = "api_response_time_ms"
    API_ERROR_COUNT = "api_error_count"


def track_rag_operation(
    operation_type: str,
    duration_ms: float,
    **kwargs
):
    """
    Helper function để track RAG operations
    
    Args:
        operation_type: Type of operation
        duration_ms: Duration in milliseconds
        **kwargs: Additional metadata
    """
    collector = get_metrics_collector()
    
    # Record duration
    metric_name = f"{operation_type}_duration_ms"
    collector.record_metric(metric_name, duration_ms, unit="ms")
    
    # Increment counter
    counter_name = f"{operation_type}_count"
    collector.increment_counter(counter_name)
    
    # Record additional metrics
    for key, value in kwargs.items():
        if isinstance(value, (int, float)):
            collector.record_metric(f"{operation_type}_{key}", value)
