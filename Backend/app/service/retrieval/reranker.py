import asyncio
import logging
from typing import List, Optional

from llama_index.core.schema import NodeWithScore
from sentence_transformers import CrossEncoder
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    # Available models (smaller → larger, faster → more accurate)
    MODELS = {
        "fast": "cross-encoder/ms-marco-MiniLM-L-6-v2",      # 80MB, fast
        "balanced": "cross-encoder/ms-marco-MiniLM-L-12-v2", # 120MB, balanced
        "accurate": "BAAI/bge-reranker-base",                # 1.1GB, accurate
        "best": "BAAI/bge-reranker-large",                   # 2.2GB, best quality
    }
    
    def __init__(
        self,
        model_name: Optional[str] = None,
        top_n: int = 3,
        device: Optional[str] = None,
    ):
        if model_name is None:
            model_name = get_settings().retrieval.rerank_model or "fast"
        
        if model_name in self.MODELS:
            model_name = self.MODELS[model_name]
        
        self.model_name = model_name
        self.top_n = top_n
        
        # Initialize cross-encoder
        logger.info(f"Loading reranker model: {model_name}")
        try:
            self.model = CrossEncoder(
                model_name,
                max_length=512,
                device=device,
            )
            logger.info(f"Reranker initialized: {model_name}")
        except Exception as e:
            logger.error(f"Failed to load reranker: {e}")
            raise
    
    async def rerank(
        self,
        query: str,
        nodes: List[NodeWithScore],
        top_n: Optional[int] = None,
    ) -> List[NodeWithScore]:
        if not nodes:
            return []
        
        top_n = top_n or self.top_n
        
        logger.debug(f"Reranking {len(nodes)} nodes...")
        
        # Prepare query-document pairs
        pairs = []
        for node in nodes:
            text = node.node.get_content()
            # Truncate long texts to avoid exceeding max_length
            if len(text) > 1500:
                text = text[:1500] + "..."
            pairs.append([query, text])
        
        # Get cross-encoder scores — run in executor to avoid blocking event loop
        try:
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None,
                lambda: self.model.predict(
                    pairs,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                ),
            )
        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Return original nodes if reranking fails
            return nodes[:top_n]
        
        # Combine nodes with scores and sort
        scored_nodes = list(zip(nodes, scores))
        scored_nodes.sort(key=lambda x: x[1], reverse=True)
        
        # Build result with updated scores
        result = []
        for node, score in scored_nodes[:top_n]:
            # Create new NodeWithScore with reranker score
            reranked_node = NodeWithScore(
                node=node.node,
                score=float(score),
            )
            result.append(reranked_node)
        
        logger.info(
            f"Reranked {len(nodes)} → {len(result)} nodes "
            f"(scores: {result[0].score:.3f} to {result[-1].score:.3f})"
        )
        
        return result
