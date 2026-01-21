# 📊 STRUCTURED LOGGING SYSTEM

## 📋 Tổng quan

Structured Logging System cung cấp khả năng theo dõi, giám sát và phân tích hiệu suất của hệ thống RAG một cách chi tiết và có cấu trúc.

### ✨ Tính năng chính

1. **JSON-based Logging**: Logs có cấu trúc, dễ parse và phân tích
2. **Context Tracking**: Theo dõi operations với context và timing
3. **Performance Metrics**: Thu thập và tổng hợp metrics
4. **HTTP Request Logging**: Tự động log tất cả HTTP requests/responses
5. **Multi-level Logging**: DEBUG, INFO, WARNING, ERROR
6. **Automatic Rotation**: Log rotation tự động
7. **Metrics API**: RESTful API để xem metrics

---

## 🏗️ Kiến trúc

```
Backend/
├── app/
│   ├── core/
│   │   ├── logger.py           # Core logging module
│   │   └── metrics.py          # Metrics collection
│   ├── middleware/
│   │   └── logging_middleware.py  # HTTP logging
│   └── api/
│       └── endpoints/
│           └── metrics.py      # Metrics API
├── logs/                       # Log files
│   └── app.log                # JSON logs
└── test/
    └── test_logging.py        # Tests
```

---

## 📦 Core Components

### 1. StructuredLogger

Logger chính với JSON formatting và context support.

```python
from app.core.logger import get_logger

logger = get_logger("my_module")

# Basic logging
logger.info("User logged in", user_id="user123")
logger.error("Failed to process", error="Connection timeout")

# With context
logger.debug("Processing query",
    query="điểm chuẩn",
    context={"user": "test", "session": "abc123"}
)
```

**Features:**

- Automatic JSON formatting
- Thread-safe logging
- Console + file output
- Structured context data

### 2. LogContext

Context manager để track operations với timing.

```python
from app.core.logger import LogContext

with LogContext(logger, "query_processing", user_id="user123"):
    # Your code here
    result = process_query(query)
    # Automatically logs start, completion, and duration
```

**Output:**

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "logger": "my_module",
  "message": "Starting operation: query_processing",
  "operation": "query_processing",
  "user_id": "user123"
}
{
  "timestamp": "2024-01-15T10:30:45.678Z",
  "level": "INFO",
  "message": "Completed operation: query_processing",
  "operation": "query_processing",
  "duration_ms": 555.0,
  "status": "success"
}
```

### 3. PerformanceLogger

Decorator và utility để track performance metrics.

```python
from app.core.logger import PerformanceLogger

perf_logger = PerformanceLogger(logger)

# As decorator
@perf_logger.track_time("slow_function")
def process_data():
    # Your code
    return result

# Manual logging
perf_logger.log_metric("api_latency", 234.5, unit="ms", tags={"endpoint": "/chat"})
```

### 4. RequestLogger

Logger cho HTTP requests/responses.

```python
from app.core.logger import RequestLogger

req_logger = RequestLogger(logger)

# Log request
req_logger.log_request(
    method="POST",
    path="/api/v1/chat",
    query_params={"debug": "true"},
    body={"message": "hello"},
    request_id="req-123"
)

# Log response
req_logger.log_response(
    status_code=200,
    duration_ms=234.5,
    request_id="req-123"
)
```

---

## 📈 Metrics Collection

### MetricsCollector

Thu thập và tổng hợp performance metrics.

```python
from app.core.metrics import get_metrics_collector, track_rag_operation

# Track operations
track_rag_operation("query_transform", 125.5, strategy="rewrite")
track_rag_operation("retrieval", 234.8, num_docs=10)
track_rag_operation("rerank", 189.3, input_docs=10, output_docs=5)

# Get statistics
collector = get_metrics_collector()
stats = collector.get_stats("query_transform_duration_ms")
print(f"Mean: {stats['mean']:.2f}ms")
print(f"P95: {stats['p95']:.2f}ms")
```

### RAG Metrics Constants

```python
from app.core.metrics import RAGMetrics

# Available metrics
RAGMetrics.QUERY_TRANSFORM_DURATION
RAGMetrics.RETRIEVAL_DURATION
RAGMetrics.RERANK_DURATION
RAGMetrics.LLM_DURATION
RAGMetrics.E2E_DURATION
RAGMetrics.NUM_RETRIEVED_DOCS
RAGMetrics.NUM_RERANKED_DOCS
```

---

## 🌐 HTTP Middleware

LoggingMiddleware tự động log tất cả HTTP requests.

### Features:

1. **Request Tracking**

   - Unique request_id cho mỗi request
   - Log method, path, query params
   - Optional body logging

2. **Response Tracking**

   - Status code
   - Response time
   - Error tracking

3. **Integration**

```python
from app.middleware.logging_middleware import LoggingMiddleware

app = FastAPI()
app.add_middleware(LoggingMiddleware)
```

---

## 🔌 Metrics API

RESTful API để monitor metrics realtime.

### Endpoints:

#### 1. Health Check

```bash
GET /api/v1/metrics/health
```

Response:

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:45.123Z",
  "uptime_seconds": 3600.5,
  "version": "1.0.0"
}
```

#### 2. Get Metrics

```bash
GET /api/v1/metrics
```

Response:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "metrics": {
    "query_transform_duration_ms": {
      "count": 100,
      "mean": 125.5,
      "median": 120.0,
      "p95": 180.0,
      "min": 80.0,
      "max": 250.0
    },
    "e2e_duration_ms": {
      "count": 100,
      "mean": 1234.5,
      "median": 1200.0,
      "p95": 1800.0
    }
  },
  "counters": {
    "api_requests": 100,
    "errors": 2
  }
}
```

#### 3. Reset Metrics

```bash
POST /api/v1/metrics/reset
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Logging Configuration
LOG_LEVEL=INFO              # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/app.log      # Log file path
LOG_MAX_BYTES=10485760     # 10MB
LOG_BACKUP_COUNT=5         # Keep 5 backup files

# Metrics
METRICS_ENABLED=true
METRICS_RETENTION_HOURS=24
```

### Setup in Code

```python
from app.core.logger import setup_logging

# Basic setup
setup_logging()

# Custom configuration
setup_logging(
    log_level="DEBUG",
    log_file="custom.log",
    log_to_console=True
)
```

---

## 📊 Integration Examples

### 1. Query Transformation với Logging

```python
from app.core.logger import get_logger, LogContext
from app.core.metrics import track_rag_operation

logger = get_logger("query_transform")

def rewrite_query(query: str):
    with LogContext(logger, "rewrite_query", query=query):
        # Transform query
        start_time = time.time()
        result = llm.complete(prompt)
        duration = (time.time() - start_time) * 1000

        # Track metrics
        track_rag_operation("query_transform", duration, strategy="rewrite")

        logger.info("Query rewritten",
            original=query,
            rewritten=result,
            duration_ms=duration
        )

        return result
```

### 2. RAG Engine với Full Logging

```python
def chat(self, message: str) -> dict:
    with LogContext(self.logger, "chat", message=message):
        try:
            # 1. Query Transformation
            start_time = time.time()
            transformed = self.query_transformer.transform(message)
            transform_duration = (time.time() - start_time) * 1000
            track_rag_operation("query_transform", transform_duration)

            # 2. Retrieval
            start_time = time.time()
            nodes = self.index.as_retriever(similarity_top_k=10).retrieve(transformed)
            retrieval_duration = (time.time() - start_time) * 1000
            track_rag_operation("retrieval", retrieval_duration, num_docs=len(nodes))

            # 3. Re-ranking
            start_time = time.time()
            reranked = self.reranker.postprocess_nodes(nodes, query_str=transformed)
            rerank_duration = (time.time() - start_time) * 1000
            track_rag_operation("rerank", rerank_duration,
                input_docs=len(nodes), output_docs=len(reranked))

            # 4. LLM Generation
            start_time = time.time()
            response = self.query_engine.query(transformed)
            llm_duration = (time.time() - start_time) * 1000
            track_rag_operation("llm", llm_duration)

            # Track total duration
            total_duration = transform_duration + retrieval_duration + rerank_duration + llm_duration
            track_rag_operation("e2e", total_duration)

            self.logger.info("Chat completed successfully",
                transform_ms=transform_duration,
                retrieval_ms=retrieval_duration,
                rerank_ms=rerank_duration,
                llm_ms=llm_duration,
                total_ms=total_duration
            )

            return {"response": str(response), "duration": total_duration}

        except Exception as e:
            self.logger.error("Chat failed", error=str(e), traceback=traceback.format_exc())
            raise
```

---

## 🧪 Testing

### Run Tests

```bash
cd Backend
python test/test_logging.py
```

### Run Demo

```bash
cd Backend
python demo_logging.py
```

---

## 📖 Log Analysis

### 1. View Logs

```bash
# View all logs
cat logs/app.log

# View last 100 lines
tail -n 100 logs/app.log

# Follow logs in real-time
tail -f logs/app.log
```

### 2. Parse JSON Logs với jq

```bash
# Pretty print
cat logs/app.log | jq '.'

# Filter by level
cat logs/app.log | jq 'select(.level == "ERROR")'

# Filter by operation
cat logs/app.log | jq 'select(.operation == "chat")'

# Get durations
cat logs/app.log | jq 'select(.duration_ms != null) | {operation, duration_ms}'

# Calculate average duration
cat logs/app.log | jq -s 'map(select(.duration_ms != null)) | add / length'
```

### 3. Extract Metrics

```bash
# Get all query transform durations
cat logs/app.log | jq 'select(.operation == "query_transform") | .duration_ms'

# Count errors
cat logs/app.log | jq 'select(.level == "ERROR")' | wc -l

# Get requests by status code
cat logs/app.log | jq 'select(.status_code != null) | .status_code' | sort | uniq -c
```

---

## 🔍 Monitoring Dashboard

### Using Metrics API

```python
import requests

# Check health
response = requests.get("http://localhost:8000/api/v1/metrics/health")
print(response.json())

# Get metrics
response = requests.get("http://localhost:8000/api/v1/metrics")
metrics = response.json()

# Display key metrics
print(f"Average E2E Duration: {metrics['metrics']['e2e_duration_ms']['mean']:.2f}ms")
print(f"P95 Latency: {metrics['metrics']['e2e_duration_ms']['p95']:.2f}ms")
print(f"Total Requests: {metrics['counters']['api_requests']}")
print(f"Error Rate: {metrics['counters']['errors'] / metrics['counters']['api_requests'] * 100:.2f}%")
```

---

## 🎯 Best Practices

### 1. Logging Levels

```python
# DEBUG: Detailed information for debugging
logger.debug("Query transformed", original=query, transformed=result)

# INFO: General information about flow
logger.info("User session started", user_id=user_id)

# WARNING: Something unexpected but recoverable
logger.warning("Slow retrieval detected", duration_ms=5000, threshold_ms=1000)

# ERROR: Error occurred
logger.error("Failed to connect to database", error=str(e))
```

### 2. Context Data

```python
# Good: Structured context
logger.info("Query processed",
    query=query,
    num_results=len(results),
    duration_ms=duration,
    user_id=user_id
)

# Bad: String concatenation
logger.info(f"Query {query} processed with {len(results)} results in {duration}ms")
```

### 3. Error Handling

```python
try:
    result = risky_operation()
except Exception as e:
    logger.error("Operation failed",
        error=str(e),
        traceback=traceback.format_exc(),
        context={"operation": "risky_operation"}
    )
    raise
```

### 4. Performance Tracking

```python
# Use LogContext for automatic timing
with LogContext(logger, "expensive_operation"):
    result = expensive_operation()

# Track custom metrics
track_rag_operation("custom_metric", value, custom_field="data")
```

---

## 📊 Performance Impact

### Overhead

- **Console logging**: ~0.1-0.5ms per log
- **File logging**: ~0.5-2ms per log (with JSON serialization)
- **Metrics tracking**: ~0.05-0.2ms per metric

### Recommendations

1. Use **INFO** level in production
2. Use **DEBUG** level only when debugging
3. Batch metrics updates when possible
4. Use log rotation to manage disk space

---

## 🚀 Advanced Features

### 1. Custom Formatters

```python
from app.core.logger import JSONFormatter

class CustomFormatter(JSONFormatter):
    def format(self, record):
        log_dict = super().format_dict(record)
        log_dict['custom_field'] = 'custom_value'
        return json.dumps(log_dict)
```

### 2. Custom Metrics

```python
from app.core.metrics import get_metrics_collector

collector = get_metrics_collector()
collector.record_metric("custom_metric", value, metadata={"tag": "value"})
```

### 3. Distributed Tracing

```python
# Add trace_id to LogContext
with LogContext(logger, "operation", trace_id=request.headers.get("X-Trace-ID")):
    # Operation
    pass
```

---

## 🐛 Troubleshooting

### Issue: Logs không xuất hiện

**Solution:**

```python
# Ensure logging is setup
from app.core.logger import setup_logging
setup_logging(log_level="DEBUG")
```

### Issue: Log file quá lớn

**Solution:**

```bash
# Update .env
LOG_MAX_BYTES=5242880  # 5MB
LOG_BACKUP_COUNT=10
```

### Issue: Metrics không chính xác

**Solution:**

```python
# Reset metrics
from app.core.metrics import get_metrics_collector
get_metrics_collector().reset()
```

---

## 📚 Related Documentation

- [Advanced RAG Complete Guide](ADVANCED_RAG_COMPLETE.md)
- [Query Transformation](QUERY_TRANSFORMATION.md)
- [Re-ranking](RERANKING.md)
- [Installation Guide](../INSTALLATION.md)

---

## 🎓 Summary

**Structured Logging System** cung cấp:

✅ **JSON-based logs** dễ parse và phân tích  
✅ **Context tracking** với automatic timing  
✅ **Performance metrics** collection và aggregation  
✅ **HTTP request logging** tự động  
✅ **RESTful API** để monitor realtime  
✅ **Production-ready** với rotation và best practices

**Kết quả:**

- 🔍 **Visibility**: Full visibility vào system behavior
- 📊 **Metrics**: Real-time performance metrics
- 🐛 **Debugging**: Dễ dàng debug issues
- 📈 **Monitoring**: Production monitoring capabilities
- 🚀 **Production-ready**: Ready for production deployment

---

**Next Steps:**

1. ✅ Chạy tests: `python test/test_logging.py`
2. ✅ Chạy demo: `python demo_logging.py`
3. ✅ Xem logs: `cat logs/app.log | jq '.'`
4. ✅ Check metrics: `curl http://localhost:8000/api/v1/metrics`
5. ✅ Deploy to production

🎯 **Production-ready Advanced RAG với full observability!**
