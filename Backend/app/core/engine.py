from typing import Optional
from llama_index.core import VectorStoreIndex
from llama_index.core.chat_engine import CondensePlusContextChatEngine
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.query_engine import RetrieverQueryEngine
from app.core.vector_store import get_vector_store
from app.core.llm import setup_llm_settings
from app.core.query_transformation import QueryTransformer
from app.core.reranker import create_reranker
from app.core.session import get_session_manager, Session
from app.core.exceptions import EngineError, LLMError, RetrievalError
from app.config import settings
from app.core.logger import get_logger, LogContext
from app.core.metrics import track_rag_operation, get_metrics_collector
from app.core.cache import get_cache_manager
import time

logger = get_logger(__name__)
cache = get_cache_manager()

# --- 1. SYSTEM PROMPT (QUAN TRỌNG NHẤT) ---
# Đây là nơi bạn dạy AI cách cư xử và trả lời.
SYSTEM_PROMPT = """
Bạn là Trợ lý Tuyển sinh ảo (Virtual Admissions Assistant) của trường Đại học An Giang-DHQG TPHCM.
Nhiệm vụ của bạn là giải đáp thắc mắc cho thí sinh dựa trên thông tin được cung cấp.

QUY TẮC TRẢ LỜI:
1. TRUNG THỰC TUYỆT ĐỐI: Chỉ trả lời dựa trên ngữ cảnh (context) được cung cấp. 
   Nếu thông tin không có trong tài liệu, hãy nói: "Xin lỗi, tôi chưa tìm thấy thông tin này trong văn bản chính thức. Bạn vui lòng liên hệ phòng đào tạo."
2. KHÔNG BỊA ĐẶT: Tuyệt đối không tự đoán điểm chuẩn hay học phí nếu không thấy số liệu.
3. NGÔN NGỮ: Tiếng Việt trang trọng, thân thiện, xưng hô là "mình" và gọi người dùng là "bạn".
4. ĐỊNH DẠNG: Sử dụng Markdown (in đậm **...**, gạch đầu dòng) để trình bày rõ ràng.
5. NGẮN GỌN: Trả lời súc tích, tránh dài dòng để tiết kiệm chi phí.
   - Câu hỏi đơn giản: 2-3 câu
   - Câu hỏi phức tạp: 5-7 câu, dùng bullet points
   - Chỉ cung cấp thông tin được hỏi, không mở rộng không cần thiết
"""

def get_chat_engine(
    use_query_transformation: bool = None, 
    transform_strategy: str = None,
    use_reranking: bool = None,
    reranker_type: str = None
):
    """
    Khởi tạo Chat Engine với Query Transformation Pipeline và Re-ranking
    
    Args:
        use_query_transformation: Bật/tắt query transformation (None = dùng config)
        transform_strategy: Chiến lược (None = dùng config) ["rewrite", "decompose", "multi_query", "hyde", "full"]
        use_reranking: Bật/tắt re-ranking (None = dùng config)
        reranker_type: Loại reranker (None = dùng config) ["cross-encoder", "llm", "cohere", "none"]
    """
    # Sử dụng config nếu không truyền tham số
    if use_query_transformation is None:
        use_query_transformation = settings.USE_QUERY_TRANSFORMATION
    
    if transform_strategy is None:
        transform_strategy = settings.QUERY_TRANSFORM_STRATEGY
    
    if use_reranking is None:
        use_reranking = settings.USE_RERANKING
    
    if reranker_type is None:
        reranker_type = settings.RERANKER_TYPE
    
    # Setup LLM & Embedding (nếu chưa chạy)
    setup_llm_settings()
    
    # Kết nối Qdrant
    storage_context = get_vector_store()
    
    # Tải Index từ đĩa lên (không tốn tiền embedding lại)
    index = VectorStoreIndex.from_vector_store(
        vector_store=storage_context.vector_store
    )
    
    # Cấu hình bộ nhớ (Nhớ được 5 cặp câu hỏi-trả lời gần nhất)
    memory = ChatMemoryBuffer.from_defaults(token_limit=3000)

    # Tạo Chat Engine chế độ "Condense Plus Context"
    # Chế độ này rất hay: Nó tóm tắt lịch sử chat + câu hỏi mới -> Tạo câu truy vấn vector chuẩn xác
    chat_engine = index.as_chat_engine(
        chat_mode="condense_plus_context",
        memory=memory,
        system_prompt=SYSTEM_PROMPT,
        similarity_top_k=settings.SIMILARITY_TOP_K,
        verbose=True
    )
    
    # Wrap chat engine với Query Transformation và Re-ranking nếu được bật
    if use_query_transformation:
        print(f"✅ Query Transformation enabled with strategy: {transform_strategy}")
        chat_engine = QueryTransformChatEngine(
            chat_engine=chat_engine,
            index=index,
            transform_strategy=transform_strategy,
            use_reranking=use_reranking,
            reranker_type=reranker_type
        )
    
    return chat_engine


class QueryTransformChatEngine:
    """
    Wrapper cho Chat Engine với Query Transformation và Re-ranking
    """
    
    def __init__(
        self, 
        chat_engine, 
        index, 
        transform_strategy: str = "rewrite",
        use_reranking: bool = True,
        reranker_type: str = "cross-encoder"
    ):
        self.chat_engine = chat_engine
        self.index = index
        self.transformer = QueryTransformer()
        self.transform_strategy = transform_strategy
        self.use_reranking = use_reranking
        self.reranker_type = reranker_type
        
        # Khởi tạo reranker nếu được bật
        if self.use_reranking and self.reranker_type != "none":
            try:
                self.reranker = create_reranker(
                    reranker_type=reranker_type,
                    top_n=settings.RERANKER_TOP_N,
                    model_name=settings.RERANKER_MODEL if hasattr(settings, 'RERANKER_MODEL') else "multilingual-large"
                )
                print(f"✅ Re-ranking enabled with type: {reranker_type}")
            except Exception as e:
                print(f"⚠️ Failed to initialize reranker: {str(e)}")
                print(f"   Continuing without re-ranking...")
                self.reranker = None
        else:
            self.reranker = None
        
    def chat(self, message: str, chat_history=None):
        """
        Override chat method để áp dụng query transformation và re-ranking
        """
        with LogContext(logger, "chat_request", message=message):
            start_time = time.time()
            
            try:
                # Check response cache first
                if cache.enabled:
                    cached_response = cache.get_cached_response(message)
                    if cached_response:
                        logger.info("Response cache hit", query=message)
                        track_rag_operation("cache_hit", 0, cache_type="response")
                        print("✅ Response retrieved from cache")
                        return cached_response
                
                print(f"\n{'='*60}")
                print(f"🚀 QUERY TRANSFORMATION PIPELINE")
                print(f"{'='*60}")
                
                # Bước 1: Transform query (with cache)
                transform_start = time.time()
                
                # Check transformation cache
                if cache.enabled:
                    cached_transform = cache.get_cached_transform(message, self.transform_strategy)
                    if cached_transform:
                        transformed_queries = cached_transform
                        logger.info("Transform cache hit", query=message, strategy=self.transform_strategy)
                        track_rag_operation("cache_hit", 0, cache_type="transform")
                        print(f"✅ Transformation retrieved from cache ({len(transformed_queries)} queries)")
                    else:
                        transform_result = self.transformer.transform_query(
                            query=message,
                            strategy=self.transform_strategy
                        )
                        transformed_queries = transform_result["transformed_queries"]
                        # Cache the transformation
                        cache.cache_query_transform(
                            message,
                            self.transform_strategy,
                            transformed_queries,
                            ttl=settings.REDIS_TRANSFORM_TTL
                        )
                else:
                    transform_result = self.transformer.transform_query(
                        query=message,
                        strategy=self.transform_strategy
                    )
                    transformed_queries = transform_result["transformed_queries"]
                
                transform_duration = (time.time() - transform_start) * 1000
                track_rag_operation("query_transform", transform_duration)
        
                # Bước 2: Retrieve với tất cả transformed queries
                retrieval_start = time.time()
                all_nodes = []
                retriever = VectorIndexRetriever(
                    index=self.index,
                    similarity_top_k=settings.SIMILARITY_TOP_K
                )
                
                print(f"\n🔍 RETRIEVING with {len(transformed_queries)} queries...")
                for i, query in enumerate(transformed_queries, 1):
                    print(f"   Query {i}: {query[:80]}...")
                    nodes = retriever.retrieve(query)
                    all_nodes.extend(nodes)
                
                retrieval_duration = (time.time() - retrieval_start) * 1000
                track_rag_operation(
                    "retrieval",
                    retrieval_duration,
                    num_queries=len(transformed_queries),
                    total_docs=len(all_nodes)
                )
                
                logger.info(
                    "Retrieval completed",
                    context={
                        "num_queries": len(transformed_queries),
                        "total_docs_retrieved": len(all_nodes),
                        "duration_ms": round(retrieval_duration, 2)
                    }
                )
                
                # Bước 3: Deduplicate và sort by score
                seen_ids = set()
                unique_nodes = []
                for node in all_nodes:
                    if node.node_id not in seen_ids:
                        seen_ids.add(node.node_id)
                        unique_nodes.append(node)
                
                # Sort by score (descending)
                unique_nodes.sort(key=lambda x: x.score if hasattr(x, 'score') else 0, reverse=True)
                
                # Lấy top nodes trước khi rerank
                top_nodes = unique_nodes[:settings.RETRIEVAL_TOP_K]  # Configurable
                
                print(f"\n✨ Retrieved {len(top_nodes)} unique relevant chunks")
                
                # Bước 4: Re-ranking (nếu được bật)
                if self.reranker is not None:
                    rerank_start = time.time()
                    print(f"\n🎯 RE-RANKING with {self.reranker_type}...")
                    from llama_index.core.schema import QueryBundle
                    query_bundle = QueryBundle(query_str=message)
                    
                    try:
                        input_count = len(top_nodes)
                        top_nodes = self.reranker._postprocess_nodes(top_nodes, query_bundle)
                        output_count = len(top_nodes)
                        
                        rerank_duration = (time.time() - rerank_start) * 1000
                        track_rag_operation(
                            "rerank",
                            rerank_duration,
                            input_docs=input_count,
                            output_docs=output_count
                        )
                        
                        print(f"✅ Re-ranked to {len(top_nodes)} nodes")
                        if top_nodes:
                            print(f"   Top score after rerank: {top_nodes[0].score:.4f}")
                        
                        logger.info(
                            "Re-ranking completed",
                            context={
                                "input_docs": input_count,
                                "output_docs": output_count,
                                "duration_ms": round(rerank_duration, 2)
                            }
                        )
                    except Exception as e:
                        print(f"⚠️ Re-ranking failed: {str(e)}")
                        print(f"   Using original retrieval scores...")
                        logger.error(f"Re-ranking failed: {str(e)}")
                
                print(f"{'='*60}\n")
                
                # Bước 5: Inject nodes vào chat engine và trả lời
                llm_start = time.time()
                response = self.chat_engine.chat(message, chat_history=chat_history)
                llm_duration = (time.time() - llm_start) * 1000
                track_rag_operation("llm_generation", llm_duration)
                
                # Cache the response
                if cache.enabled:
                    cache.cache_response(
                        message,
                        response,
                        ttl=settings.REDIS_RESPONSE_TTL
                    )
                    logger.debug("Response cached", query=message)
                
                # Track tổng end-to-end
                total_duration = (time.time() - start_time) * 1000
                track_rag_operation("e2e", total_duration)
                
                logger.info(
                    "Chat completed successfully",
                    context={
                        "total_duration_ms": round(total_duration, 2),
                        "transform_ms": round(transform_duration, 2),
                        "retrieval_ms": round(retrieval_duration, 2),
                        "llm_ms": round(llm_duration, 2)
                    }
                )
                
                return response
                
            except Exception as e:
                duration = (time.time() - start_time) * 1000
                track_rag_operation("e2e_error", duration)
                logger.exception(
                    "Chat failed",
                    context={
                        "message": message,
                        "duration_ms": round(duration, 2),
                        "error": str(e)
                    }
                )
                raise
    
    def reset(self):
        """Reset chat history"""
        if hasattr(self.chat_engine, 'reset'):
            self.chat_engine.reset()
            logger.info("Chat engine memory reset")
    
    def stream_chat(self, message: str, chat_history=None):
        """Support streaming nếu cần"""
        # Tương tự chat() nhưng return streaming response
        # TODO: Implement nếu cần streaming
        return self.chat(message, chat_history)


# ==========================================
# SESSION-AWARE ENGINE FACTORY
# ==========================================

class ChatEngineFactory:
    """
    Factory để tạo và quản lý chat engines theo session
    
    Mỗi session có memory riêng, đảm bảo không lẫn context giữa users
    """
    
    _instance = None
    _index = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialize_index()
        self._initialized = True
    
    def _initialize_index(self):
        """Initialize vector store index (one-time)"""
        logger.info("Initializing ChatEngineFactory...")
        
        # Setup LLM & Embedding
        setup_llm_settings()
        
        # Connect to vector store
        storage_context = get_vector_store()
        
        # Load index from disk
        self._index = VectorStoreIndex.from_vector_store(
            vector_store=storage_context.vector_store
        )
        
        logger.info("ChatEngineFactory initialized successfully")
    
    def create_engine_for_session(
        self,
        session: Session,
        use_query_transformation: bool = None,
        transform_strategy: str = None,
        use_reranking: bool = None,
        reranker_type: str = None
    ):
        """
        Tạo chat engine với memory từ session
        
        Args:
            session: Session object chứa memory
            use_query_transformation: Bật/tắt query transformation
            transform_strategy: Chiến lược transformation
            use_reranking: Bật/tắt re-ranking
            reranker_type: Loại reranker
            
        Returns:
            Chat engine với session memory
        """
        # Use config defaults if not specified
        if use_query_transformation is None:
            use_query_transformation = settings.USE_QUERY_TRANSFORMATION
        if transform_strategy is None:
            transform_strategy = settings.QUERY_TRANSFORM_STRATEGY
        if use_reranking is None:
            use_reranking = settings.USE_RERANKING
        if reranker_type is None:
            reranker_type = settings.RERANKER_TYPE
        
        # Create chat engine with session's memory
        chat_engine = self._index.as_chat_engine(
            chat_mode="condense_plus_context",
            memory=session.memory,  # Use session's isolated memory
            system_prompt=SYSTEM_PROMPT,
            similarity_top_k=settings.SIMILARITY_TOP_K,
            verbose=True
        )
        
        # Wrap with query transformation if enabled
        if use_query_transformation:
            logger.info(
                "Creating engine with query transformation",
                context={
                    "session_id": session.session_id,
                    "strategy": transform_strategy,
                    "use_reranking": use_reranking
                }
            )
            chat_engine = QueryTransformChatEngine(
                chat_engine=chat_engine,
                index=self._index,
                transform_strategy=transform_strategy,
                use_reranking=use_reranking,
                reranker_type=reranker_type
            )
        
        return chat_engine
    
    @property
    def index(self):
        """Get the vector store index"""
        return self._index


# Global factory instance
_engine_factory: Optional[ChatEngineFactory] = None


def get_engine_factory() -> ChatEngineFactory:
    """Get global engine factory instance"""
    global _engine_factory
    if _engine_factory is None:
        _engine_factory = ChatEngineFactory()
    return _engine_factory


def chat_with_session(
    message: str,
    conversation_id: Optional[str] = None,
    use_query_transformation: bool = None,
    transform_strategy: str = None,
    use_reranking: bool = None,
    reranker_type: str = None
) -> tuple:
    """
    High-level function để chat với session management
    
    Args:
        message: User message
        conversation_id: Optional conversation ID (tạo mới nếu None)
        use_query_transformation: Override config
        transform_strategy: Override config
        use_reranking: Override config
        reranker_type: Override config
        
    Returns:
        Tuple of (response, conversation_id, source_nodes)
    """
    # Get or create session
    session_manager = get_session_manager()
    session = session_manager.get_or_create_session(conversation_id)
    
    # Get engine factory and create engine for this session
    factory = get_engine_factory()
    engine = factory.create_engine_for_session(
        session=session,
        use_query_transformation=use_query_transformation,
        transform_strategy=transform_strategy,
        use_reranking=use_reranking,
        reranker_type=reranker_type
    )
    
    # Chat
    response = engine.chat(message)
    
    return response, session.session_id, getattr(response, 'source_nodes', [])