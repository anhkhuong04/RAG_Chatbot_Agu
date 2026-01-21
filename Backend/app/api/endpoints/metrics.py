"""
Metrics API Endpoint
Expose metrics và health check
"""
from fastapi import APIRouter
from app.core.metrics import get_metrics_collector
from app.core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "Server is running"
    }


@router.get("/metrics")
def get_metrics():
    """
    Get current metrics summary
    """
    try:
        collector = get_metrics_collector()
        summary = collector.get_summary()
        
        logger.info("Metrics retrieved", context={"metrics_count": len(summary["metrics"])})
        
        return {
            "status": "success",
            "data": summary
        }
    except Exception as e:
        logger.error(f"Failed to get metrics: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }


@router.post("/metrics/reset")
def reset_metrics():
    """
    Reset all metrics
    """
    try:
        collector = get_metrics_collector()
        collector.reset()
        
        logger.info("Metrics reset")
        
        return {
            "status": "success",
            "message": "Metrics reset successfully"
        }
    except Exception as e:
        logger.error(f"Failed to reset metrics: {str(e)}")
        return {
            "status": "error",
            "message": str(e)
        }
