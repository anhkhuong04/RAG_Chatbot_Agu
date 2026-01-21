"""
Logging Middleware for FastAPI
Track requests, responses, và performance metrics
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.logger import get_logger, RequestLogger

logger = get_logger(__name__)
request_logger = RequestLogger(logger)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware để log tất cả HTTP requests và responses
    """
    
    async def dispatch(
        self, 
        request: Request, 
        call_next: Callable
    ) -> Response:
        """
        Process request và log
        """
        # Generate request ID
        request_id = str(uuid.uuid4())
        
        # Add request_id to request state
        request.state.request_id = request_id
        
        # Start timer
        start_time = time.time()
        
        # Log incoming request
        try:
            body = None
            if request.method in ["POST", "PUT", "PATCH"]:
                # Try to read body (might fail for large bodies)
                try:
                    body_bytes = await request.body()
                    # Reset body for actual handler
                    async def receive():
                        return {"type": "http.request", "body": body_bytes}
                    request._receive = receive
                    
                    # Try to parse as JSON
                    import json
                    try:
                        body = json.loads(body_bytes.decode())
                    except:
                        body = {"_raw": body_bytes.decode()[:200]}
                except:
                    body = {"_error": "Could not read body"}
            
            request_logger.log_request(
                method=request.method,
                path=request.url.path,
                query_params=dict(request.query_params) if request.query_params else None,
                body=body,
                request_id=request_id
            )
        except Exception as e:
            logger.warning(f"Failed to log request: {str(e)}")
        
        # Process request
        try:
            response = await call_next(request)
            duration = (time.time() - start_time) * 1000
            
            # Log response
            request_logger.log_response(
                status_code=response.status_code,
                duration_ms=round(duration, 2),
                request_id=request_id
            )
            
            # Add request_id to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
            
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            
            # Log error response
            request_logger.log_response(
                status_code=500,
                duration_ms=round(duration, 2),
                request_id=request_id,
                error=str(e)
            )
            
            raise
