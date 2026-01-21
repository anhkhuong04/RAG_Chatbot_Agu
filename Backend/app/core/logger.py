"""
Structured Logging System for Advanced RAG
JSON-based logging với context tracking và metrics
"""
import logging
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional
from pathlib import Path
import traceback
import sys

# ==========================================
# CUSTOM JSON FORMATTER
# ==========================================

class JSONFormatter(logging.Formatter):
    """
    Format log records thành JSON để dễ parse và analyze
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Convert log record sang JSON format
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Thêm context nếu có
        if hasattr(record, 'context'):
            log_data['context'] = record.context
        
        # Thêm extra fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        # Thêm exception info nếu có
        if record.exc_info:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        return json.dumps(log_data, ensure_ascii=False)


# ==========================================
# STRUCTURED LOGGER
# ==========================================

class StructuredLogger:
    """
    Wrapper cho logging với structured format và context tracking
    """
    
    def __init__(self, name: str, log_level: str = "INFO"):
        """
        Args:
            name: Logger name (thường là __name__ của module)
            log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        
        # Prevent duplicate handlers
        if not self.logger.handlers:
            self._setup_handlers()
    
    def _setup_handlers(self):
        """Setup console và file handlers"""
        # Console handler (human-readable)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        
        # File handler (JSON format)
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        file_handler = logging.FileHandler(
            logs_dir / "app.log",
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JSONFormatter())
        
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
    
    def _log(
        self, 
        level: str, 
        message: str, 
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """
        Internal log method
        
        Args:
            level: Log level
            message: Log message
            context: Additional context dict
            **kwargs: Extra fields
        """
        extra = {}
        if context:
            extra['context'] = context
        if kwargs:
            extra['extra_fields'] = kwargs
        
        log_func = getattr(self.logger, level.lower())
        log_func(message, extra=extra)
    
    def debug(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log debug message"""
        self._log("DEBUG", message, context, **kwargs)
    
    def info(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log info message"""
        self._log("INFO", message, context, **kwargs)
    
    def warning(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log warning message"""
        self._log("WARNING", message, context, **kwargs)
    
    def error(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log error message"""
        self._log("ERROR", message, context, **kwargs)
    
    def critical(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log critical message"""
        self._log("CRITICAL", message, context, **kwargs)
    
    def exception(self, message: str, context: Optional[Dict] = None, **kwargs):
        """Log exception with traceback"""
        extra = {}
        if context:
            extra['context'] = context
        if kwargs:
            extra['extra_fields'] = kwargs
        
        self.logger.exception(message, extra=extra)


# ==========================================
# CONTEXT LOGGER
# ==========================================

class LogContext:
    """
    Context manager để track context trong logs
    """
    
    def __init__(
        self,
        logger: StructuredLogger,
        operation: str,
        **context_data
    ):
        """
        Args:
            logger: StructuredLogger instance
            operation: Operation name (e.g., "query_transformation", "retrieval")
            **context_data: Additional context data
        """
        self.logger = logger
        self.operation = operation
        self.context_data = context_data
        self.start_time = None
    
    def __enter__(self):
        """Start operation"""
        self.start_time = time.time()
        self.logger.info(
            f"Starting {self.operation}",
            context={
                "operation": self.operation,
                "phase": "start",
                **self.context_data
            }
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """End operation"""
        duration = time.time() - self.start_time
        
        if exc_type is None:
            # Success
            self.logger.info(
                f"Completed {self.operation}",
                context={
                    "operation": self.operation,
                    "phase": "complete",
                    "duration_ms": round(duration * 1000, 2),
                    "status": "success",
                    **self.context_data
                }
            )
        else:
            # Error
            self.logger.error(
                f"Failed {self.operation}: {exc_val}",
                context={
                    "operation": self.operation,
                    "phase": "error",
                    "duration_ms": round(duration * 1000, 2),
                    "status": "failed",
                    "error_type": exc_type.__name__,
                    **self.context_data
                }
            )
        
        return False  # Don't suppress exception


# ==========================================
# PERFORMANCE LOGGER
# ==========================================

class PerformanceLogger:
    """
    Track và log performance metrics
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
        self.metrics = {}
    
    def track_time(self, operation: str):
        """
        Decorator để track execution time
        """
        def decorator(func):
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    duration = time.time() - start_time
                    
                    self.logger.info(
                        f"Performance: {operation}",
                        context={
                            "operation": operation,
                            "duration_ms": round(duration * 1000, 2),
                            "status": "success"
                        }
                    )
                    
                    return result
                    
                except Exception as e:
                    duration = time.time() - start_time
                    
                    self.logger.error(
                        f"Performance: {operation} failed",
                        context={
                            "operation": operation,
                            "duration_ms": round(duration * 1000, 2),
                            "status": "failed",
                            "error": str(e)
                        }
                    )
                    raise
            
            return wrapper
        return decorator
    
    def log_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        tags: Optional[Dict] = None
    ):
        """
        Log a metric value
        
        Args:
            metric_name: Name of metric
            value: Metric value
            unit: Unit of measurement
            tags: Additional tags
        """
        self.logger.info(
            f"Metric: {metric_name}",
            context={
                "metric": metric_name,
                "value": value,
                "unit": unit,
                "tags": tags or {}
            }
        )


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def get_logger(name: str, log_level: str = "INFO") -> StructuredLogger:
    """
    Factory function để tạo StructuredLogger
    
    Args:
        name: Logger name
        log_level: Log level
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name, log_level)


def setup_logging(log_level: str = "INFO"):
    """
    Setup global logging configuration
    
    Args:
        log_level: Global log level
    """
    # Create logs directory
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)
    
    # File handler
    file_handler = logging.FileHandler(
        logs_dir / "app.log",
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(JSONFormatter())
    root_logger.addHandler(file_handler)
    
    # Disable verbose logging from third-party libs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    print(f"✅ Logging configured: level={log_level}, output=logs/app.log")


# ==========================================
# REQUEST/RESPONSE LOGGER
# ==========================================

class RequestLogger:
    """
    Log HTTP requests và responses
    """
    
    def __init__(self, logger: StructuredLogger):
        self.logger = logger
    
    def log_request(
        self,
        method: str,
        path: str,
        query_params: Optional[Dict] = None,
        body: Optional[Dict] = None,
        headers: Optional[Dict] = None,
        request_id: Optional[str] = None
    ):
        """Log incoming request"""
        self.logger.info(
            f"Incoming request: {method} {path}",
            context={
                "type": "request",
                "method": method,
                "path": path,
                "query_params": query_params,
                "body": body,
                "request_id": request_id
            }
        )
    
    def log_response(
        self,
        status_code: int,
        duration_ms: float,
        request_id: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log outgoing response"""
        level = "info" if status_code < 400 else "error"
        
        log_func = getattr(self.logger, level)
        log_func(
            f"Response: {status_code}",
            context={
                "type": "response",
                "status_code": status_code,
                "duration_ms": duration_ms,
                "request_id": request_id,
                "error": error
            }
        )
