"""
Re-ranking Module for Advanced RAG
Sử dụng Cross-Encoder để re-rank retrieved documents
"""
from typing import List, Tuple, Optional
import torch
from sentence_transformers import CrossEncoder
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
from llama_index.core.postprocessor.types import BaseNodePostprocessor

from .logger import get_logger, LogContext

logger = get_logger(__name__)

# ==========================================
# CROSS-ENCODER MODELS
# ==========================================

# Các models có sẵn cho Cross-Encoder
AVAILABLE_MODELS = {
    # Multilingual models (hỗ trợ tiếng Việt)
    "multilingual-large": "cross-encoder/ms-marco-MiniLM-L-12-v2",  # Best balance
    "multilingual-small": "cross-encoder/ms-marco-TinyBERT-L-2-v2",  # Fast
    
    # Vietnamese-specific (nếu có)
    "vietnamese": "bkai-foundation-models/vietnamese-bi-encoder",  # Nếu có
    
    # English models (backup)
    "english-large": "cross-encoder/ms-marco-electra-base",
}

DEFAULT_MODEL = "multilingual-large"


class CrossEncoderReranker(BaseNodePostprocessor):
    """
    Re-rank nodes sử dụng Cross-Encoder
    
    Cross-Encoder khác với Bi-Encoder (embedding model):
    - Bi-Encoder: Encode query và doc riêng rẽ -> tính similarity
    - Cross-Encoder: Encode [query, doc] cùng nhau -> predict relevance trực tiếp
    
    Cross-Encoder chính xác hơn nhưng chậm hơn, nên dùng sau khi đã retrieve
    """
    
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        top_n: Optional[int] = None,
        device: Optional[str] = None
    ):
        """
        Args:
            model_name: Tên model hoặc key trong AVAILABLE_MODELS
            top_n: Số nodes giữ lại sau rerank (None = giữ tất cả)
            device: 'cuda', 'cpu', hoặc None (auto detect)
        """
        super().__init__()
        
        # Resolve model name
        if model_name in AVAILABLE_MODELS:
            model_path = AVAILABLE_MODELS[model_name]
        else:
            model_path = model_name
        
        # Auto detect device
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        
        logger.info(f"Loading Cross-Encoder: {model_path} on {device}")
        
        try:
            self.model = CrossEncoder(model_path, max_length=512, device=device)
            self.top_n = top_n
            self.device = device
            logger.info("✅ Cross-Encoder loaded successfully")
        except Exception as e:
            logger.error(f"❌ Failed to load Cross-Encoder: {str(e)}")
            logger.info("Falling back to no reranking...")
            self.model = None
    
    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        """
        Re-rank nodes based on query
        
        Args:
            nodes: List of nodes with scores from retriever
            query_bundle: Query information
            
        Returns:
            Re-ranked nodes with updated scores
        """
        if self.model is None:
            logger.warning("Cross-Encoder not available, returning original nodes")
            return nodes
        
        if not nodes or not query_bundle:
            return nodes
        
        query_text = query_bundle.query_str
        
        with LogContext(logger, "cross_encoder_rerank", 
                       query=query_text, num_nodes=len(nodes)):
            # Chuẩn bị pairs [query, document] cho Cross-Encoder
            pairs = []
            for node in nodes:
                doc_text = node.node.get_content()
                pairs.append([query_text, doc_text])
            
            logger.debug(f"Prepared {len(pairs)} query-document pairs for re-ranking")
            
            # Predict relevance scores
            try:
                scores = self.model.predict(pairs)
                
                # Update node scores
                for i, node in enumerate(nodes):
                    node.score = float(scores[i])
                
                # Sort by new scores (descending)
                nodes = sorted(nodes, key=lambda x: x.score, reverse=True)
                
                # Trim to top_n if specified
                output_count = len(nodes)
                if self.top_n is not None:
                    nodes = nodes[:self.top_n]
                    output_count = len(nodes)
                
                logger.info(f"Re-ranked from {len(pairs)} to {output_count} nodes",
                           top_score=nodes[0].score if nodes else 0.0,
                           top_n=self.top_n)
                
                return nodes
                
            except Exception as e:
                logger.error(f"Re-ranking failed: {str(e)}", error=str(e))
                return nodes


class LLMReranker(BaseNodePostprocessor):
    """
    Re-rank sử dụng LLM (Gemini) để đánh giá relevance
    
    Cách này chậm hơn Cross-Encoder nhưng có thể hiểu ngữ nghĩa sâu hơn
    """
    
    def __init__(
        self,
        llm=None,
        top_n: Optional[int] = None,
        use_async: bool = False
    ):
        """
        Args:
            llm: LLM instance (nếu None sẽ dùng Settings.llm)
            top_n: Số nodes giữ lại
            use_async: Sử dụng async calls (nhanh hơn)
        """
        super().__init__()
        from llama_index.core import Settings
        
        self.llm = llm or Settings.llm
        self.top_n = top_n
        self.use_async = use_async
        
        # Prompt để LLM đánh giá relevance
        self.relevance_prompt_template = """Bạn là chuyên gia đánh giá độ liên quan của tài liệu.

NHIỆM VỤ: Đánh giá độ liên quan của đoạn văn dưới đây với câu hỏi.

CÂU HỎI: {query}

ĐOẠN VĂN: {document}

HÃY CHO ĐIỂM từ 0-10:
- 0-2: Hoàn toàn không liên quan
- 3-5: Có liên quan một phần
- 6-8: Khá liên quan
- 9-10: Rất liên quan, trả lời trực tiếp câu hỏi

CHỈ TRẢ VỀ MỘT SỐ TỪ 0-10:"""
    
    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        """Re-rank nodes using LLM"""
        if not nodes or not query_bundle:
            return nodes
        
        query_text = query_bundle.query_str
        
        logger.info(f"🔄 Re-ranking {len(nodes)} nodes with LLM...")
        
        # Score each node
        scored_nodes = []
        for node in nodes:
            doc_text = node.node.get_content()[:500]  # Limit length
            
            prompt = self.relevance_prompt_template.format(
                query=query_text,
                document=doc_text
            )
            
            try:
                response = self.llm.complete(prompt)
                score_text = response.text.strip()
                
                # Parse score
                try:
                    score = float(score_text)
                    score = max(0.0, min(10.0, score)) / 10.0  # Normalize to 0-1
                except:
                    score = node.score  # Keep original if parsing fails
                
                node.score = score
                scored_nodes.append(node)
                
            except Exception as e:
                logger.warning(f"LLM scoring failed: {str(e)}")
                scored_nodes.append(node)
        
        # Sort by new scores
        scored_nodes = sorted(scored_nodes, key=lambda x: x.score, reverse=True)
        
        # Trim to top_n
        if self.top_n is not None:
            scored_nodes = scored_nodes[:self.top_n]
        
        logger.info(f"✅ Re-ranked to {len(scored_nodes)} top nodes")
        
        return scored_nodes


class CohereReranker(BaseNodePostprocessor):
    """
    Re-rank sử dụng Cohere Rerank API
    
    Cohere có model chuyên cho reranking, rất chính xác
    Nhưng cần API key riêng
    """
    
    def __init__(
        self,
        api_key: str,
        model: str = "rerank-multilingual-v2.0",
        top_n: Optional[int] = None
    ):
        """
        Args:
            api_key: Cohere API key
            model: Model name (rerank-english-v2.0, rerank-multilingual-v2.0)
            top_n: Số nodes giữ lại
        """
        super().__init__()
        
        try:
            import cohere
            self.client = cohere.Client(api_key)
            self.model = model
            self.top_n = top_n
            logger.info(f"✅ Cohere Reranker initialized with {model}")
        except ImportError:
            logger.error("❌ Cohere package not installed. Run: pip install cohere")
            self.client = None
        except Exception as e:
            logger.error(f"❌ Failed to initialize Cohere: {str(e)}")
            self.client = None
    
    def _postprocess_nodes(
        self,
        nodes: List[NodeWithScore],
        query_bundle: Optional[QueryBundle] = None,
    ) -> List[NodeWithScore]:
        """Re-rank using Cohere API"""
        if self.client is None or not nodes or not query_bundle:
            return nodes
        
        query_text = query_bundle.query_str
        documents = [node.node.get_content() for node in nodes]
        
        logger.info(f"🔄 Re-ranking {len(documents)} nodes with Cohere...")
        
        try:
            results = self.client.rerank(
                query=query_text,
                documents=documents,
                model=self.model,
                top_n=self.top_n or len(documents)
            )
            
            # Map results back to nodes
            reranked_nodes = []
            for result in results.results:
                idx = result.index
                score = result.relevance_score
                
                node = nodes[idx]
                node.score = score
                reranked_nodes.append(node)
            
            logger.info(f"✅ Re-ranked to {len(reranked_nodes)} nodes")
            return reranked_nodes
            
        except Exception as e:
            logger.error(f"❌ Cohere reranking failed: {str(e)}")
            return nodes


# ==========================================
# FACTORY FUNCTION
# ==========================================

def create_reranker(
    reranker_type: str = "cross-encoder",
    model_name: str = DEFAULT_MODEL,
    top_n: Optional[int] = None,
    api_key: Optional[str] = None,
    **kwargs
) -> BaseNodePostprocessor:
    """
    Factory function để tạo reranker
    
    Args:
        reranker_type: "cross-encoder", "llm", "cohere", hoặc "none"
        model_name: Model name (cho cross-encoder)
        top_n: Số nodes giữ lại sau rerank
        api_key: API key (cho cohere)
        **kwargs: Additional arguments
        
    Returns:
        Reranker instance
    """
    if reranker_type == "cross-encoder":
        return CrossEncoderReranker(
            model_name=model_name,
            top_n=top_n,
            **kwargs
        )
    
    elif reranker_type == "llm":
        return LLMReranker(
            top_n=top_n,
            **kwargs
        )
    
    elif reranker_type == "cohere":
        if not api_key:
            raise ValueError("Cohere reranker requires api_key")
        return CohereReranker(
            api_key=api_key,
            top_n=top_n,
            **kwargs
        )
    
    elif reranker_type == "none":
        logger.info("No reranking applied")
        return None
    
    else:
        raise ValueError(f"Unknown reranker type: {reranker_type}")


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def rerank_nodes(
    nodes: List[NodeWithScore],
    query: str,
    reranker_type: str = "cross-encoder",
    top_n: Optional[int] = None,
    **kwargs
) -> List[NodeWithScore]:
    """
    Helper function để rerank nodes
    
    Args:
        nodes: List of nodes to rerank
        query: Query string
        reranker_type: Type of reranker
        top_n: Number of top nodes to keep
        **kwargs: Additional arguments for reranker
        
    Returns:
        Re-ranked nodes
    """
    reranker = create_reranker(
        reranker_type=reranker_type,
        top_n=top_n,
        **kwargs
    )
    
    if reranker is None:
        return nodes
    
    query_bundle = QueryBundle(query_str=query)
    return reranker._postprocess_nodes(nodes, query_bundle)
