# 🔍 THIẾT KẾ HYBRID SEARCH + RERANKING

## Tổng quan

Document này mô tả thiết kế và implementation cho **Hybrid Search** kết hợp với **Reranking** để nâng cao chất lượng retrieval trong hệ thống RAG.

---

## 📊 Phân tích Hiện trạng

### Kiến trúc hiện tại (Basic RAG)

```
User Query → Embedding → Vector Search (Top 3) → LLM Generation
```

**Hạn chế:**

- Chỉ sử dụng Dense Vector Search (semantic similarity)
- Không bắt được exact keyword matches (tên ngành, mã ngành, số điểm cụ thể)
- Top K cố định (k=3), có thể miss relevant chunks
- Không có re-ranking để chọn lọc kết quả tốt nhất

### Kiến trúc đề xuất (Advanced RAG)

```
User Query
    ↓
┌───────────────────────────────────────┐
│         HYBRID RETRIEVAL              │
│  ┌─────────────┐   ┌─────────────┐   │
│  │ Dense Vector│   │ Sparse BM25 │   │
│  │   Search    │   │   Search    │   │
│  └──────┬──────┘   └──────┬──────┘   │
│         └────────┬────────┘          │
│                  ↓                    │
│         Reciprocal Rank Fusion       │
│              (Top 10)                 │
└───────────────────────────────────────┘
                   ↓
┌───────────────────────────────────────┐
│           RERANKING                   │
│    Cross-Encoder Scoring (Top 5)     │
└───────────────────────────────────────┘
                   ↓
┌───────────────────────────────────────┐
│        METADATA FILTERING             │
│    (Year, Category - Optional)        │
└───────────────────────────────────────┘
                   ↓
           LLM Generation
```

---

## 🛠️ Chi tiết Implementation

### 1. Dependencies mới cần thêm

```txt
# requirements.txt - Thêm vào
llama-index-retrievers-bm25
rank-bm25
```

### 2. Cấu trúc file mới

```
Backend/
├── app/
│   └── service/
│       ├── chat_service.py      # Cập nhật
│       ├── retrieval/           # 📁 THƯ MỤC MỚI
│       │   ├── __init__.py
│       │   ├── hybrid_retriever.py    # Hybrid Search logic
│       │   ├── reranker.py            # Cross-Encoder Reranker
│       │   └── metadata_filter.py     # Dynamic filtering
│       └── ingestion_service.py  # Cập nhật - thêm BM25 index
```

---

## 📝 Chi tiết từng Component

### Component 1: Hybrid Retriever (`hybrid_retriever.py`)

**Mục đích:** Kết hợp Dense Vector Search + Sparse BM25 Search

**Thuật toán:**

1. **Dense Search**: Sử dụng OpenAI embeddings + Qdrant vector search
2. **Sparse Search**: Sử dụng BM25 cho keyword matching
3. **Fusion**: Reciprocal Rank Fusion (RRF) để merge kết quả

```python
# Pseudo-code
class HybridRetriever:
    def __init__(self, vector_index, bm25_retriever, alpha=0.5):
        """
        alpha: Trọng số cho dense search (0.5 = cân bằng)
        - alpha = 1.0: Chỉ dùng dense (semantic)
        - alpha = 0.0: Chỉ dùng sparse (keyword)
        - alpha = 0.5: Cân bằng cả hai (recommended)
        """
        self.vector_retriever = vector_index.as_retriever(similarity_top_k=10)
        self.bm25_retriever = bm25_retriever
        self.alpha = alpha

    def retrieve(self, query: str, top_k: int = 10):
        # 1. Dense retrieval
        dense_nodes = self.vector_retriever.retrieve(query)

        # 2. Sparse retrieval (BM25)
        sparse_nodes = self.bm25_retriever.retrieve(query)

        # 3. Reciprocal Rank Fusion
        fused_nodes = self._reciprocal_rank_fusion(
            dense_nodes, sparse_nodes, top_k
        )

        return fused_nodes

    def _reciprocal_rank_fusion(self, dense, sparse, top_k, k=60):
        """
        RRF Score = Σ 1/(k + rank)
        k = 60 (constant to prevent high ranks from dominating)
        """
        scores = {}

        # Score from dense results
        for rank, node in enumerate(dense):
            node_id = node.node.node_id
            scores[node_id] = scores.get(node_id, 0) + self.alpha / (k + rank + 1)

        # Score from sparse results
        for rank, node in enumerate(sparse):
            node_id = node.node.node_id
            scores[node_id] = scores.get(node_id, 0) + (1 - self.alpha) / (k + rank + 1)

        # Sort by combined score and return top_k
        sorted_nodes = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_nodes[:top_k]
```

**Lợi ích:**

- **Dense Search** tốt cho: Câu hỏi semantic, paraphrase, context understanding
- **BM25 Search** tốt cho: Exact matches (mã ngành "7480201", điểm "25.5")

---

### Component 2: Cross-Encoder Reranker (`reranker.py`)

**Mục đích:** Sắp xếp lại top 10 kết quả từ Hybrid Search, chọn top 5 relevant nhất

**Lựa chọn Model:**

| Model                                  | Size  | Speed  | Quality | Recommendation      |
| -------------------------------------- | ----- | ------ | ------- | ------------------- |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | 80MB  | Fast   | Good    | ✅ **Recommended**  |
| `BAAI/bge-reranker-base`               | 1.1GB | Medium | Better  | For high accuracy   |
| `BAAI/bge-reranker-large`              | 2.2GB | Slow   | Best    | Production with GPU |

**Implementation:**

```python
# Pseudo-code
class CrossEncoderReranker:
    def __init__(self, model_name="cross-encoder/ms-marco-MiniLM-L-6-v2", top_n=5):
        self.model = CrossEncoder(model_name)
        self.top_n = top_n

    def rerank(self, query: str, nodes: List[NodeWithScore]) -> List[NodeWithScore]:
        """
        Re-rank nodes using cross-encoder scoring
        """
        if not nodes:
            return []

        # Prepare query-document pairs
        pairs = [[query, node.node.text] for node in nodes]

        # Get cross-encoder scores
        scores = self.model.predict(pairs)

        # Sort by score and return top_n
        scored_nodes = list(zip(nodes, scores))
        scored_nodes.sort(key=lambda x: x[1], reverse=True)

        # Update node scores and return
        result = []
        for node, score in scored_nodes[:self.top_n]:
            node.score = float(score)
            result.append(node)

        return result
```

**Tại sao Cross-Encoder tốt hơn Bi-Encoder?**

| Aspect      | Bi-Encoder (Embedding)          | Cross-Encoder        |
| ----------- | ------------------------------- | -------------------- |
| Input       | Query & Doc embedded separately | Query + Doc together |
| Interaction | Cosine similarity               | Full attention       |
| Speed       | Fast (precomputed)              | Slower (real-time)   |
| Quality     | Good                            | **Better**           |
| Use case    | Initial retrieval               | Re-ranking           |

---

### Component 3: Metadata Filter (`metadata_filter.py`)

**Mục đích:** Filter kết quả theo năm, category trước hoặc sau retrieval

```python
# Pseudo-code
class MetadataFilterService:
    YEAR_PATTERNS = [
        r'năm\s*(\d{4})',
        r'(\d{4})',
        r'khóa\s*(\d{4})',
    ]

    CATEGORY_KEYWORDS = {
        "Điểm Chuẩn": ["điểm chuẩn", "điểm trúng tuyển", "điểm đỗ"],
        "Học Phí": ["học phí", "chi phí", "đóng tiền"],
        "Tuyển Sinh": ["tuyển sinh", "xét tuyển", "đăng ký"],
        "Quy Chế": ["quy chế", "quy định", "điều kiện"],
    }

    def extract_filters(self, query: str) -> dict:
        """Extract year and category from query"""
        filters = {}

        # Extract year
        for pattern in self.YEAR_PATTERNS:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                year = int(match.group(1))
                if 2020 <= year <= 2030:  # Valid range
                    filters["year"] = year
                    break

        # Extract category
        query_lower = query.lower()
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                filters["category"] = category
                break

        return filters

    def apply_filters(self, nodes: List, filters: dict) -> List:
        """Filter nodes by metadata"""
        if not filters:
            return nodes

        filtered = []
        for node in nodes:
            metadata = node.node.metadata

            # Check year filter
            if "year" in filters:
                if metadata.get("year") != filters["year"]:
                    continue

            # Check category filter
            if "category" in filters:
                if metadata.get("category") != filters["category"]:
                    continue

            filtered.append(node)

        return filtered if filtered else nodes  # Fallback to all if no matches
```

---

## 🔄 Cập nhật ChatService

### Trước (Basic RAG)

```python
def _get_query_engine(self):
    if self._query_engine is None:
        index = self._get_index()
        if index:
            self._query_engine = index.as_query_engine(
                similarity_top_k=3,
                response_mode="compact",
                system_prompt=self.RAG_SYSTEM_PROMPT
            )
    return self._query_engine
```

### Sau (Advanced RAG)

```python
def _get_advanced_retriever(self):
    """Initialize Hybrid Retriever with Reranking"""
    if self._advanced_retriever is None:
        index = self._get_index()
        if index:
            # 1. Initialize Hybrid Retriever
            self._hybrid_retriever = HybridRetriever(
                vector_index=index,
                bm25_corpus=self._load_bm25_corpus(),
                alpha=0.5  # Balance between semantic and keyword
            )

            # 2. Initialize Reranker
            self._reranker = CrossEncoderReranker(
                model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
                top_n=5
            )

            # 3. Initialize Metadata Filter
            self._metadata_filter = MetadataFilterService()

    return self._hybrid_retriever

async def _handle_rag_query(self, message: str) -> tuple[str, List[str]]:
    """Handle knowledge-base queries using Advanced RAG"""
    try:
        # 1. Extract metadata filters from query
        filters = self._metadata_filter.extract_filters(message)

        # 2. Hybrid Retrieval (Dense + Sparse)
        hybrid_nodes = self._hybrid_retriever.retrieve(
            query=message,
            top_k=10,
            filters=filters  # Pre-filtering in Qdrant
        )

        # 3. Rerank with Cross-Encoder
        reranked_nodes = self._reranker.rerank(
            query=message,
            nodes=hybrid_nodes
        )

        # 4. Post-filter if needed
        final_nodes = self._metadata_filter.apply_filters(
            reranked_nodes,
            filters
        )

        # 5. Generate response with context
        response = await self._generate_response(message, final_nodes)

        # 6. Extract sources
        sources = self._extract_sources(final_nodes)

        return response, sources

    except Exception as e:
        logger.error(f"Advanced RAG error: {e}")
        # Fallback to basic retrieval
        return await self._handle_basic_rag_query(message)
```

---

## 📊 So sánh Performance

### Test Cases

| Query                             | Basic RAG                 | Hybrid + Rerank        |
| --------------------------------- | ------------------------- | ---------------------- |
| "Điểm chuẩn ngành CNTT năm 2025?" | ⚠️ Có thể miss exact year | ✅ Filter + BM25 match |
| "Học phí bao nhiêu?"              | ✅ OK                     | ✅ Better context      |
| "Mã ngành 7480201 là gì?"         | ❌ Semantic miss          | ✅ BM25 exact match    |
| "Điều kiện xét tuyển thẳng?"      | ✅ OK                     | ✅ Better ranking      |

### Expected Improvements

| Metric      | Basic RAG | Advanced RAG | Improvement |
| ----------- | --------- | ------------ | ----------- |
| Recall@10   | ~70%      | ~85%         | +15%        |
| Precision@5 | ~60%      | ~80%         | +20%        |
| MRR         | ~0.65     | ~0.82        | +26%        |
| Latency     | ~1.5s     | ~2.2s        | +0.7s       |

---

## ⚙️ Configuration

### Environment Variables mới

```env
# .env additions

# Reranking Model
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_TOP_N=5

# Hybrid Search
HYBRID_ALPHA=0.5
DENSE_TOP_K=10
SPARSE_TOP_K=10

# Feature Flags
ENABLE_HYBRID_SEARCH=true
ENABLE_RERANKING=true
ENABLE_METADATA_FILTER=true
ENABLE_QUERY_REWRITE=true
ENABLE_QUERY_EXPANSION=false
```

### Config Class

```python
# app/core/config.py
from pydantic_settings import BaseSettings

class RetrievalSettings(BaseSettings):
    # Hybrid Search
    enable_hybrid_search: bool = True
    hybrid_alpha: float = 0.5
    dense_top_k: int = 10
    sparse_top_k: int = 10

    # Reranking
    enable_reranking: bool = True
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rerank_top_n: int = 5

    # Metadata Filtering
    enable_metadata_filter: bool = True
    default_year: int = 2026

    # Query Rewriting (NEW)
    enable_query_rewrite: bool = True
    enable_query_expansion: bool = False
    enable_keyword_extraction: bool = True
    max_expanded_queries: int = 3

    class Config:
        env_prefix = "RAG_"
```

---

## 🚀 Migration Plan

### Phase 1: Preparation (Day 1)

- [ ] Thêm dependencies vào requirements.txt
- [ ] Tạo folder structure mới
- [ ] Download và cache reranker model

### Phase 2: Implementation (Day 2-3)

- [ ] Implement `HybridRetriever`
- [ ] Implement `CrossEncoderReranker`
- [ ] Implement `MetadataFilterService`
- [ ] Update `ChatService`

### Phase 3: Testing (Day 4)

- [ ] Unit tests cho từng component
- [ ] Integration tests
- [ ] Performance benchmarking

### Phase 4: Deployment (Day 5)

- [ ] Feature flag rollout (gradual)
- [ ] Monitor latency và accuracy
- [ ] A/B testing if possible

---

## 📁 Files sẽ được tạo/cập nhật

### Files MỚI:

1. `Backend/app/service/retrieval/__init__.py`
2. `Backend/app/service/retrieval/hybrid_retriever.py`
3. `Backend/app/service/retrieval/reranker.py`
4. `Backend/app/service/retrieval/metadata_filter.py`
5. `Backend/app/core/config.py`

### Files CẬP NHẬT:

1. `Backend/requirements.txt` - Thêm dependencies
2. `Backend/app/service/chat_service.py` - Integrate advanced retrieval
3. `Backend/.env` - Thêm config variables

---

## 🔧 Troubleshooting

### Issue 1: Reranker model download chậm

```python
# Pre-download model trong startup
from sentence_transformers import CrossEncoder
model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
```

### Issue 2: BM25 index chưa sync với Qdrant

```python
# Rebuild BM25 index khi ingest new documents
def rebuild_bm25_index():
    # Fetch all documents from Qdrant
    # Rebuild BM25 corpus
    pass
```

### Issue 3: Memory issues với large corpus

```python
# Use disk-based BM25 hoặc limit corpus size
bm25_retriever = BM25Retriever.from_defaults(
    nodes=nodes,
    similarity_top_k=10,
    stemmer=None,  # Skip stemming for Vietnamese
)
```

---

## 📚 References

1. [LlamaIndex Hybrid Search](https://docs.llamaindex.ai/en/stable/examples/retrievers/bm25_retriever/)
2. [Cross-Encoder Reranking](https://www.sbert.net/examples/applications/cross-encoder/README.html)
3. [Reciprocal Rank Fusion Paper](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
4. [Qdrant Hybrid Search](https://qdrant.tech/documentation/concepts/hybrid-queries/)

---

_Document Version: 1.0_
_Last Updated: January 26, 2026_
_Author: AI Assistant_
