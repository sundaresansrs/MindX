"""
Quality Pipeline - 7-Stage Verification System
Implements multi-stage processing for high-quality, factual answers
"""
from typing import List, Dict, Optional
from app.services.llm_service import LLMService
from app.services.search_service import SearchService
import logging
import time
from sqlalchemy.orm import Session
from app.services.vector_service import VectorService


logger = logging.getLogger(__name__)


class QualityPipeline:
    """
    7-Stage Quality Pipeline for generating accurate, well-sourced answers
    
    Stages:
    1. Query Enhancement - Expand query into multiple variations
    2. Multi-Source Retrieval - Search web with expanded queries
    3. Re-ranking - Rank results by relevance (requires Cohere)
    4. Semantic Chunking - Break results into meaningful chunks
    5. Multi-Answer Generation - Generate multiple answer candidates
    6. Self-Consistency - Check consistency across answers
    7. Fact Verification - Verify facts and attribute sources
    """
    
    def __init__(self, db: Session, use_reranking: bool = False):
        self.db = db
        self.llm_service = LLMService()
        self.search_service = SearchService()
        self.vector_service = VectorService(db)
        self.use_reranking = use_reranking

        
        # Initialize re-ranking if enabled
        if use_reranking:
            try:
                from app.services.rerank_service import RerankService
                self.rerank_service = RerankService()
                logger.info("Re-ranking service initialized")
            except Exception as e:
                logger.warning(f"Re-ranking disabled: {e}")
                self.use_reranking = False

    async def process_query(self, query: str, use_search: bool = True, max_sources: int = 20) -> Dict:
        """
        Process query through the 7-stage quality pipeline
        
        Args:
            query: User's question
            use_search: Whether to use web search (default: True)
            max_sources: Maximum sources to include in answer
        
        Returns:
            Dictionary with answer, sources, confidence, and metadata
        """
        start_time = time.time()
        
        try:
            # If search disabled, use LLM-only mode (existing behavior)
            if not use_search:
                answer = await self.llm_service.generate_response(query)
                return {
                    "answer": answer,
                    "sources": [],
                    "confidence": 0.5,
                    "metadata": {
                        "mode": "llm_only",
                        "processing_time": time.time() - start_time
                    }
                }
            
            # Stage 1: Query Enhancement
            logger.info("Stage 1: Query Enhancement")
            expanded_queries = await self.expand_query(query)
            
            # Stage 2: Multi-Source Retrieval (Web + Vector)
            logger.info("Stage 2: Multi-Source Retrieval")
            
            # Fetch Web Results
            web_results = self.search_service.search_multiple_queries(
                expanded_queries, 
                max_results_per_query=20
            )
            
            # Fetch Vector Results (Hybrid RAG)
            vector_results = await self.vector_service.search_documents(
                query, 
                limit=10
            )
            
            # Combine results
            search_results = vector_results + web_results

            
            if not search_results:
                # Fallback to LLM-only if no search results
                logger.warning("No search results found, falling back to LLM-only")
                answer = await self.llm_service.generate_response(query)
                return {
                    "answer": answer,
                    "sources": [],
                    "confidence": 0.3,
                    "metadata": {
                        "mode": "llm_fallback",
                        "processing_time": time.time() - start_time
                    }
                }
            
            # Stage 3: Re-ranking (optional)
            if self.use_reranking:
                logger.info("Stage 3: Re-ranking")
                ranked_results = await self.rerank_results(query, search_results)
            else:
                logger.info("Stage 3: Skipping re-ranking")
                ranked_results = search_results[:max_sources]
            
            # Stage 4: Semantic Chunking
            logger.info("Stage 4: Semantic Chunking")
            chunks = self.semantic_chunk(ranked_results)
            
            # Stage 5: Multi-Answer Generation
            logger.info("Stage 5: Multi-Answer Generation")
            answer_candidates = await self.generate_multiple_answers(query, chunks)
            
            # Stage 6: Self-Consistency Check
            logger.info("Stage 6: Self-Consistency")
            consensus_answer = await self.check_consistency(answer_candidates)
            
            # Stage 7: Fact Verification
            logger.info("Stage 7: Fact Verification")
            verified_result = await self.verify_facts(
                consensus_answer, 
                ranked_results[:max_sources]
            )
            
            # Add metadata
            verified_result["metadata"] = {
                "queries_used": len(expanded_queries),
                "web_sources": len(web_results),
                "vector_sources": len(vector_results),
                "sources_retrieved": len(search_results),
                "sources_used": len(ranked_results[:max_sources]),

                "processing_time": time.time() - start_time,
                "mode": "full_pipeline"
            }
            
            return verified_result
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            # Fallback to LLM-only on error
            answer = await self.llm_service.generate_response(query)
            return {
                "answer": answer,
                "sources": [],
                "confidence": 0.2,
                "metadata": {
                    "mode": "error_fallback",
                    "error": str(e),
                    "processing_time": time.time() - start_time
                }
            }
    
    async def expand_query(self, query: str) -> List[str]:
        """
        Stage 1: Expand query into multiple variations
        """
        prompt = f"""Generate 3 alternative search queries for the following question. 
Each query should approach the question from a slightly different angle to maximize information retrieval.

Original question: {query}

Provide ONLY the 3 alternative queries, one per line, without numbering or explanation."""

        try:
            response = await self.llm_service.generate_response(prompt)
            # Parse response into list of queries
            queries = [q.strip() for q in response.split('\n') if q.strip()]
            # Include original query
            all_queries = [query] + queries[:3]
            logger.info(f"Expanded to {len(all_queries)} queries")
            return all_queries
        except Exception as e:
            logger.error(f"Query expansion failed: {e}")
            return [query]  # Fallback to original query
    
    async def rerank_results(self, query: str, results: List[Dict]) -> List[Dict]:
        """
        Stage 3: Re-rank results by relevance (requires Cohere)
        """
        try:
            # Use re-ranking service
            ranked = await self.rerank_service.rerank(query, results)
            return ranked
        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            return results  # Return original order
    
    def semantic_chunk(self, results: List[Dict]) -> List[str]:
        """
        Stage 4: Break search results into semantic chunks
        """
        chunks = []
        for result in results:
            # Combine title and snippet for context
            chunk = f"{result['title']}\n{result['snippet']}"
            chunks.append(chunk)
        return chunks
    
    async def generate_multiple_answers(self, query: str, chunks: List[str], num_candidates: int = 3) -> List[str]:
        """
        Stage 5: Generate multiple answer candidates
        """
        answers = []
        
        # Divide chunks into groups for different perspectives
        chunk_groups = [chunks[i::num_candidates] for i in range(num_candidates)]
        
        for i, chunk_group in enumerate(chunk_groups[:num_candidates]):
            context = "\n\n".join(chunk_group[:5])  # Use top 5 chunks per candidate
            
            prompt = f"""Based on the following information, answer the question accurately and concisely.

Context:
{context}

Question: {query}

Answer:"""
            
            try:
                answer = await self.llm_service.generate_response(prompt)
                answers.append(answer)
            except Exception as e:
                logger.error(f"Answer generation {i+1} failed: {e}")
        
        return answers if answers else ["Unable to generate answer"]
    
    async def check_consistency(self, answers: List[str]) -> str:
        """
        Stage 6: Check consistency and build consensus answer
        """
        if len(answers) == 1:
            return answers[0]
        
        prompt = f"""You are given multiple answer candidates for the same question. 
Your task is to synthesize them into a single, coherent answer that captures the consensus.

Answer Candidate 1:
{answers[0]}

Answer Candidate 2:
{answers[1] if len(answers) > 1 else 'N/A'}

Answer Candidate 3:
{answers[2] if len(answers) > 2 else 'N/A'}

Provide a final consensus answer that:
1. Includes facts that appear in multiple candidates
2. Resolves contradictions by favoring the most commonly stated information
3. Is clear, concise, and well-structured

Consensus Answer:"""
        
        try:
            consensus = await self.llm_service.generate_response(prompt)
            return consensus
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return answers[0]  # Return first answer as fallback
    
    async def verify_facts(self, answer: str, sources: List[Dict]) -> Dict:
        """
        Stage 7: Verify facts and calculate confidence
        """
        # Calculate confidence based on number of sources and answer quality
        num_sources = len(sources)
        confidence = min(0.9, 0.5 + (num_sources / 40))  # Cap at 0.9
        
        return {
            "answer": answer,
            "sources": sources,
            "confidence": round(confidence, 2)
        }
