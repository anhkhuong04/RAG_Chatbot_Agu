"""
Hybrid Retriever - Combines Dense Vector Search + Sparse BM25 Search
Uses Reciprocal Rank Fusion (RRF) to merge results
"""
import asyncio
import logging
from typing import List, Optional, Dict, Any
from collections import defaultdict

from llama_index.core import VectorStoreIndex
from llama_index.core.schema import NodeWithScore, QueryBundle
from llama_index.core.retrievers import BaseRetriever
from llama_index.retrievers.bm25 import BM25Retriever

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """
    Hybrid Retriever combining Dense (Vector) and Sparse (BM25) search.
    
    Uses Reciprocal Rank Fusion (RRF) to combine results from both retrievers.
    
    Attributes:
        vector_retriever: Dense vector retriever (semantic search)
        bm25_retriever: Sparse BM25 retriever (keyword matching)
        alpha: Weight for dense search (1-alpha for sparse)
        top_k: Number of final results to return
    """
    
    def __init__(
        self,
        vector_index: VectorStoreIndex,
        nodes: List[Any],
        alpha: float = 0.5,
        dense_top_k: int = 20,
        sparse_top_k: int = 20,
        final_top_k: int = 20,
    ):
        """
        Initialize Hybrid Retriever.
        
        Args:
            vector_index: LlamaIndex VectorStoreIndex for dense retrieval
            nodes: List of nodes for BM25 index (from documents)
            alpha: Balance between dense (1.0) and sparse (0.0). Default 0.5
            dense_top_k: Number of results from dense retriever
            sparse_top_k: Number of results from sparse retriever
            final_top_k: Number of final fused results
        """
        super().__init__()
        
        self.alpha = alpha
        self.dense_top_k = dense_top_k
        self.sparse_top_k = sparse_top_k
        self.final_top_k = final_top_k
        
        # Initialize Dense (Vector) Retriever
        self.vector_retriever = vector_index.as_retriever(
            similarity_top_k=dense_top_k
        )
        
        # Initialize Sparse (BM25) Retriever
        if nodes:
            self.bm25_retriever = BM25Retriever.from_defaults(
                nodes=nodes,
                similarity_top_k=sparse_top_k,
            )
            logger.info(f"✅ BM25 Retriever initialized with {len(nodes)} nodes")
        else:
            self.bm25_retriever = None
            logger.warning("⚠️ No nodes provided for BM25. Using dense-only retrieval.")
        
        logger.info(
            f"✅ HybridRetriever initialized (alpha={alpha}, "
            f"dense_k={dense_top_k}, sparse_k={sparse_top_k})"
        )
    
    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        Retrieve nodes using hybrid search.
        
        Args:
            query_bundle: Query bundle containing the query string
            
        Returns:
            List of NodeWithScore objects sorted by RRF score
        """
        query = query_bundle.query_str
        
        # 1. Dense Retrieval (Semantic Search)
        logger.debug(f"🔍 Dense retrieval for: {query[:50]}...")
        dense_nodes = self.vector_retriever.retrieve(query)
        logger.debug(f"   Found {len(dense_nodes)} dense results")
        
        # 2. Sparse Retrieval (BM25 Keyword Search)
        sparse_nodes = []
        if self.bm25_retriever:
            logger.debug(f"🔍 Sparse (BM25) retrieval for: {query[:50]}...")
            try:
                sparse_nodes = self.bm25_retriever.retrieve(query)
                logger.debug(f"   Found {len(sparse_nodes)} sparse results")
            except Exception as e:
                logger.warning(f"⚠️ BM25 retrieval failed: {e}")
        
        # 3. Reciprocal Rank Fusion
        fused_nodes = self._reciprocal_rank_fusion(dense_nodes, sparse_nodes)
        
        logger.info(
            f"✅ Hybrid retrieval complete: {len(dense_nodes)} dense + "
            f"{len(sparse_nodes)} sparse → {len(fused_nodes)} fused"
        )
        
        return fused_nodes
    
    def _reciprocal_rank_fusion(
        self,
        dense_nodes: List[NodeWithScore],
        sparse_nodes: List[NodeWithScore],
        k: int = 60,
    ) -> List[NodeWithScore]:
        """
        Combine results using Reciprocal Rank Fusion (RRF).
        
        RRF Score = Σ 1/(k + rank)
        
        Args:
            dense_nodes: Results from dense retriever
            sparse_nodes: Results from sparse retriever
            k: Constant to prevent high ranks from dominating (default 60)
            
        Returns:
            Fused and sorted list of NodeWithScore
        """
        # Store scores and node references
        node_scores: Dict[str, float] = defaultdict(float)
        node_map: Dict[str, NodeWithScore] = {}
        
        # Score from dense results (weighted by alpha)
        for rank, node in enumerate(dense_nodes):
            node_id = node.node.node_id
            rrf_score = self.alpha / (k + rank + 1)
            node_scores[node_id] += rrf_score
            node_map[node_id] = node
        
        # Score from sparse results (weighted by 1-alpha)
        for rank, node in enumerate(sparse_nodes):
            node_id = node.node.node_id
            rrf_score = (1 - self.alpha) / (k + rank + 1)
            node_scores[node_id] += rrf_score
            if node_id not in node_map:
                node_map[node_id] = node
        
        # Sort by combined RRF score
        sorted_node_ids = sorted(
            node_scores.keys(),
            key=lambda x: node_scores[x],
            reverse=True
        )
        
        # Build final result list with updated scores
        result = []
        for node_id in sorted_node_ids[:self.final_top_k]:
            node = node_map[node_id]
            # Update score to RRF score for transparency
            node.score = node_scores[node_id]
            result.append(node)
        
        return result
    
    # Lock to prevent concurrent BM25 rebuilds
    _bm25_rebuild_lock = asyncio.Lock()

    async def update_bm25_index(self, nodes: List[Any]) -> None:
        """
        Update the BM25 index with new nodes.
        Call this after ingesting new documents.

        The rebuild runs in a thread-pool executor so it does not block the
        FastAPI event loop.  An asyncio.Lock prevents concurrent rebuilds.

        Note: The current version of llama-index BM25Retriever does NOT expose
        an ``insert_nodes()`` method, so the index must be rebuilt from scratch.
        Once upstream support is added, this can be changed to an incremental
        append.

        Args:
            nodes: Complete list of nodes to index
        """
        if not nodes:
            logger.warning("⚠️ No nodes provided for BM25 update")
            return

        async with self._bm25_rebuild_lock:
            logger.info(f"🔄 Rebuilding BM25 index with {len(nodes)} nodes (background)...")

            loop = asyncio.get_event_loop()
            sparse_top_k = self.sparse_top_k

            # Heavy tokenisation + indexing happens off the event loop
            new_retriever = await loop.run_in_executor(
                None,
                lambda: BM25Retriever.from_defaults(
                    nodes=nodes,
                    similarity_top_k=sparse_top_k,
                ),
            )

            # Atomic swap — readers already in-flight keep the old instance
            self.bm25_retriever = new_retriever
            logger.info(f"✅ BM25 index updated with {len(nodes)} nodes")
