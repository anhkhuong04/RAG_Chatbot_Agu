# 🚀 REDIS CACHING LAYER

## 📋 Tổng quan

Redis Caching Layer giúp tối ưu hiệu suất và giảm chi phí API calls bằng cách cache các kết quả đã xử lý.

### ✨ Lợi ích

- ⚡ **Giảm latency**: Cache hits trả về ngay lập tức (~1-5ms)
- 💰 **Tiết kiệm chi phí**: Giảm API calls đến Gemini LLM
- 🔄 **Tái sử dụng**: Cache transformations và responses
- 📊 **Monitoring**: Track cache hit rate và performance
- ⏱️ **TTL flexible**: Cấu hình TTL riêng cho từng loại cache

---

## 🏗️ Cache Hierarchy

```
┌─────────────────────────────────────────┐
│ Level 1: Response Cache (2 hours TTL)   │
│ → Full LLM responses                     │
│ → Fastest return                         │
└─────────────────────────────────────────┘
                 ↓ miss
┌─────────────────────────────────────────┐
│ Level 2: Transform Cache (1 hour TTL)   │
│ → Query transformations                  │
│ → Rewrite, decompose, multi-query       │
└─────────────────────────────────────────┘
                 ↓ miss
┌─────────────────────────────────────────┐
│ Level 3: Retrieval Cache (30 min TTL)   │
│ → Retrieved document nodes               │
│ → Vector search results                  │
└─────────────────────────────────────────┘
                 ↓ miss
         Execute full pipeline
```

---

## 📦 Installation

### 1. Install Redis Server

**Windows:**

```bash
# Download from: https://github.com/microsoftarchive/redis/releases
# Or use Chocolatey:
choco install redis-64

# Start server:
redis-server
```

**Linux:**

```bash
sudo apt-get install redis-server
sudo systemctl start redis
```

**Mac:**

```bash
brew install redis
brew services start redis
```

### 2. Install Python Package

```bash
pip install redis
```

### 3. Configure Environment

```bash
# .env
REDIS_ENABLED=true
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# TTL settings (in seconds)
REDIS_TTL=3600
REDIS_TRANSFORM_TTL=3600
REDIS_RETRIEVAL_TTL=1800
REDIS_RESPONSE_TTL=7200
```

---

## 🔧 Usage

### Basic Cache Operations

```python
from app.core.cache import get_cache_manager

# Get cache manager
cache = get_cache_manager()

# Set value
cache.set("my_key", {"data": "value"}, ttl=300)

# Get value
value = cache.get("my_key")

# Delete value
cache.delete("my_key")

# Clear all keys
count = cache.clear("rag:*")
```

### RAG-Specific Caching

```python
# Cache query transformation
cache.cache_query_transform(
    query="điểm chuẩn CNTT",
    strategy="rewrite",
    transformed=["Điểm chuẩn ngành Công nghệ Thông tin"],
    ttl=3600
)

# Get cached transformation
result = cache.get_cached_transform(
    query="điểm chuẩn CNTT",
    strategy="rewrite"
)

# Cache LLM response
cache.cache_response(
    query="điểm chuẩn CNTT",
    response="Điểm chuẩn CNTT là 25.5",
    ttl=7200
)

# Get cached response
response = cache.get_cached_response("điểm chuẩn CNTT")
```

### Cache Decorator

```python
from app.core.cache import cached

@cached(cache_type="custom", ttl=300)
def expensive_function(arg1, arg2):
    # Expensive operation
    return result

# First call: executes function
result1 = expensive_function("a", "b")

# Second call: returns from cache
result2 = expensive_function("a", "b")
```

---

## 🌐 API Endpoints

### 1. Cache Health

```bash
GET /api/v1/cache/health
```

Response:

```json
{
  "status": "healthy",
  "message": "Redis cache is connected and operational",
  "keys_count": 125
}
```

### 2. Cache Statistics

```bash
GET /api/v1/cache/stats
```

Response:

```json
{
  "enabled": true,
  "stats": {
    "enabled": true,
    "connected": true,
    "keys_count": 125,
    "hits": 450,
    "misses": 50,
    "hit_rate": 90.0
  }
}
```

### 3. Clear Cache

```bash
POST /api/v1/cache/clear?pattern=rag:*
```

Response:

```json
{
  "success": true,
  "keys_deleted": 125,
  "message": "Successfully deleted 125 keys matching pattern 'rag:*'"
}
```

**Patterns:**

- `rag:*` - Clear all RAG cache
- `rag:transform:*` - Clear transformation cache only
- `rag:response:*` - Clear response cache only
- `rag:retrieval:*` - Clear retrieval cache only

---

## 📊 Integration trong RAG Pipeline

### Cache Flow

```python
def chat(self, message: str):
    # 1. Check response cache first
    cached_response = cache.get_cached_response(message)
    if cached_response:
        return cached_response  # ⚡ Instant return

    # 2. Check transformation cache
    cached_transform = cache.get_cached_transform(message, strategy)
    if cached_transform:
        transformed_queries = cached_transform
    else:
        # Transform and cache
        transformed_queries = transformer.transform(message)
        cache.cache_query_transform(message, strategy, transformed_queries)

    # 3. Retrieve documents
    nodes = retrieve(transformed_queries)

    # 4. Generate response
    response = llm.generate(nodes)

    # 5. Cache response
    cache.cache_response(message, response)

    return response
```

### Performance Impact

**Without Cache:**

```
Query → Transform (200ms) → Retrieve (250ms) → Rerank (150ms) → LLM (800ms) → Response
Total: ~1400ms
```

**With Cache (hit):**

```
Query → Cache Hit → Response
Total: ~2ms (700x faster!)
```

---

## ⚙️ Configuration

### TTL Strategy

| Cache Type | Default TTL | Reasoning                        |
| ---------- | ----------- | -------------------------------- |
| Response   | 2 hours     | Most valuable, full answer       |
| Transform  | 1 hour      | Reusable across similar queries  |
| Retrieval  | 30 minutes  | More volatile, context-dependent |

### Memory Management

Redis automatically handles memory with LRU eviction:

```bash
# redis.conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

### Monitoring

```python
# Get cache statistics
stats = cache.get_stats()

print(f"Hit rate: {stats['hit_rate']}%")
print(f"Keys count: {stats['keys_count']}")
print(f"Hits: {stats['hits']}")
print(f"Misses: {stats['misses']}")
```

---

## 🧪 Testing

### Run Tests

```bash
cd Backend
python test/test_cache.py
```

### Run Demo

```bash
python demo_cache.py
```

### Manual Testing

```bash
# Start Redis
redis-server

# Test connection
redis-cli ping
# Should return: PONG

# View all keys
redis-cli keys "rag:*"

# Get key value
redis-cli get "rag:response:abc123"

# Clear all RAG keys
redis-cli --scan --pattern "rag:*" | xargs redis-cli del
```

---

## 📈 Performance Metrics

### Cache Hit Scenarios

1. **Identical Query**

   - User: "điểm chuẩn CNTT"
   - Cache: Full response hit
   - Latency: ~2ms
   - Savings: ~1400ms

2. **Similar Query (different words)**

   - User: "điểm chuẩn công nghệ thông tin"
   - Cache: Transform hit, continue pipeline
   - Latency: ~1200ms
   - Savings: ~200ms

3. **Different Query**
   - Cache miss, full pipeline
   - Latency: ~1400ms
   - Savings: 0ms

### Expected Hit Rates

| Scenario       | Expected Hit Rate |
| -------------- | ----------------- |
| Chatbot (live) | 30-50%            |
| FAQ queries    | 60-80%            |
| Test/dev       | 10-20%            |

---

## 🎯 Best Practices

### 1. Cache Invalidation

```python
# Clear specific query cache
cache.delete(cache._generate_key("response", query=query))

# Clear all transformations
cache.clear("rag:transform:*")

# Clear all cache (use sparingly)
cache.clear("rag:*")
```

### 2. Error Handling

```python
try:
    result = cache.get(key)
    if result:
        return result
except Exception as e:
    logger.warning(f"Cache error: {e}")
    # Continue without cache
    result = expensive_operation()
```

### 3. Cache Warming

```python
# Pre-populate cache with common queries
common_queries = [
    "điểm chuẩn CNTT",
    "học phí một học kỳ",
    "quy chế thi"
]

for query in common_queries:
    response = engine.chat(query)
    cache.cache_response(query, response)
```

### 4. Monitoring

```python
# Track cache performance
from app.core.metrics import track_rag_operation

if cached_result:
    track_rag_operation("cache_hit", 0, cache_type="response")
else:
    track_rag_operation("cache_miss", 0, cache_type="response")
```

---

## 🐛 Troubleshooting

### Issue: Cache not working

**Check:**

```bash
# 1. Redis running?
redis-cli ping

# 2. Configuration correct?
cat .env | grep REDIS

# 3. Python package installed?
pip list | grep redis
```

**Fix:**

```bash
# Install package
pip install redis

# Start Redis
redis-server

# Enable in .env
REDIS_ENABLED=true
```

### Issue: Cache hit rate low

**Solutions:**

1. **Increase TTL** for frequently accessed data
2. **Warm cache** with common queries
3. **Normalize queries** before caching (lowercase, trim)
4. **Use semantic hashing** for similar queries

### Issue: Memory full

**Solutions:**

```bash
# 1. Increase Redis memory limit
# redis.conf:
maxmemory 512mb

# 2. Reduce TTL
REDIS_RESPONSE_TTL=3600  # 1 hour instead of 2

# 3. Manual cleanup
redis-cli --scan --pattern "rag:*" | xargs redis-cli del
```

---

## 📊 Cost Savings Analysis

### API Call Costs

- Gemini API: ~$0.0001 per request
- Average requests: 1000/day
- Without cache: $0.10/day = $36.5/year
- With 40% hit rate: $0.06/day = $21.9/year
- **Savings: $14.6/year**

### Latency Improvement

- Average query time: 1400ms → 560ms (with 40% cache hit)
- **60% faster** on average
- Better user experience
- Higher satisfaction

---

## 🎓 Summary

**Redis Caching Layer** provides:

✅ **Performance**: 700x faster for cache hits  
✅ **Cost savings**: 40-60% reduction in API calls  
✅ **Flexible TTL**: Configure per cache type  
✅ **Easy integration**: Drop-in with existing pipeline  
✅ **Monitoring**: Track hit rates and stats  
✅ **Production-ready**: Robust error handling

**Trade-offs:**

- ➕ Much faster responses
- ➕ Lower API costs
- ➕ Better scalability
- ➖ Requires Redis server
- ➖ Slight complexity
- ➖ Stale data (TTL-based)

---

## 📚 Related Documentation

- [Advanced RAG Complete](../ADVANCED_RAG_COMPLETE.md)
- [Query Transformation](QUERY_TRANSFORMATION.md)
- [Re-ranking](RERANKING.md)
- [Logging System](LOGGING.md)

---

**Next Steps:**

1. ✅ Install Redis server
2. ✅ Configure .env
3. ✅ Run tests: `python test/test_cache.py`
4. ✅ Monitor hit rates: `curl /api/v1/cache/stats`
5. ✅ Deploy to production

🎯 **Production-ready caching with Redis!**
