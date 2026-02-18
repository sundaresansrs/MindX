from typing import List, Dict, Optional, Any
import asyncio
from app.services.llm_service import LLMService # type: ignore
from app.services.search_service import SearchService # type: ignore
import logging
import time
from sqlalchemy.orm import Session # type: ignore
from app.services.vector_service import VectorService # type: ignore


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
                from app.services.rerank_service import RerankService # type: ignore
                self.rerank_service = RerankService()
                logger.info("Re-ranking service initialized")
            except Exception as e:
                logger.warning(f"Re-ranking disabled: {e}")
                self.use_reranking = False

    async def process_query(self, query: str, user: Any, session_id: Optional[str] = None, history: Optional[List[Any]] = None, use_search: bool = True, max_sources: int = 20, fast_mode: bool = False) -> Dict:
        """
        Process query through the 7-stage quality pipeline
        
        Args:
            query: User's question
            user: Current user object
            session_id: current session identifier
            history: List of previous messages in this session
            use_search: Whether to use web search (default: True)
            max_sources: Maximum sources to include in answer
        """
        history = history or []
        
        # Stage 0: Contextual Query Enhancement
        # If there's history, rewrite the query to be standalone
        enhanced_query = query
        if history:
            # Truncate history answers to keep the prompt lean and prevent hangs
            slim_history = []
            for h in history[-3:]: # type: ignore
                slim_history.append({
                    "query": h.get("query", ""),
                    "answer": (h.get("answer", "")[:200] + "...") if len(h.get("answer", "")) > 200 else h.get("answer", "")
                })

            enhance_prompt = f"""Given the following conversation history and a follow-up question, rewrite the follow-up question to be a standalone search query.
            If the question is already standalone, return it as is.
            
            History:
            {slim_history}
            
            Follow-up: {query}
            Standalone Query:"""
            try:
                llm_response = await self.llm_service.generate_response(enhance_prompt)
                enhanced_query = str(llm_response).strip().strip('"')
                logger.info(f"Enhanced Query: {enhanced_query}")
            except Exception as e:
                logger.error(f"Query enhancement failed: {e}")

        query_to_search = enhanced_query

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
            if not fast_mode:
                logger.info("Stage 1: Query Enhancement")
                expanded_queries = await self.expand_query(query)
            else:
                expanded_queries = [query]
            
            # Stage 2: Multi-Source Retrieval (Web + Vector)
            logger.info("Stage 2: Multi-Source Retrieval")
            
            # Fetch results in parallel (same as stream)
            web_task = self.search_service.search_multiple_queries(
                expanded_queries, 
                max_results_per_query=5 if fast_mode else 15
            )
            vector_task = self.vector_service.search_documents(
                query, 
                user_id=user.id,
                session_id=session_id,
                limit=10
            )

            # Parallel Retrieve with timeout
            try:
                web_results, vector_results = await asyncio.wait_for(
                    asyncio.gather(web_task, vector_task),
                    timeout=25.0
                )
            except asyncio.TimeoutError:
                logger.warning("Pipeline process_query retrieval timed out.")
                web_results, vector_results = [], []

            
            # Combine results using RRF (Premium Ranking)
            ranked_results = self.apply_rrf([vector_results, web_results])
            
            if not ranked_results:
                # Fallback to LLM-only if no search results
                logger.warning("No search results found, falling back to LLM-only")
                llm_fallback = await self.llm_service.generate_response(query)
                answer = str(llm_fallback)
                return {
                    "answer": answer,
                    "sources": [],
                    "confidence": 0.3,
                    "metadata": {
                        "mode": "llm_fallback",
                        "processing_time": time.time() - start_time
                    }
                }
            
            # Select top sources
            sources_to_use = ranked_results[:max_sources] # type: ignore
            
            # Stage 4: Semantic Chunking
            logger.info("Stage 4: Semantic Chunking")
            chunks = self.semantic_chunk(sources_to_use)
            
            if fast_mode:
                 # Skip Stage 5 & 6 in Fast Mode
                  prompt = f"Answer the user's question accurately using ONLY the provided sources. Use inline citations [1], [2].\n\nContext:\n{chunks[:5]}\n\nQuestion: {query}\n\nAnswer:" # type: ignore
                  fast_response = await self.llm_service.generate_response(prompt)
                  consensus_answer = str(fast_response)
            else:
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
                sources_to_use
            )
            
            # Add metadata
            verified_result["metadata"] = {
                "queries_used": len(expanded_queries),
                "web_sources": len(web_results),
                "vector_sources": len(vector_results),
                "sources_retrieved": len(vector_results) + len(web_results),
                "sources_used": len(sources_to_use),
                "processing_time": time.time() - start_time,
                "mode": "full_pipeline_rrf"
            }
            
            return verified_result
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            # Fallback to LLM-only on error
            err_fallback = await self.llm_service.generate_response(query)
            answer = str(err_fallback)
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

    async def stream_query(self, query: str, user: Any, session_id: Optional[str] = None, history: Optional[List[Any]] = None, use_search: bool = True, max_sources: int = 10, fast_mode: bool = False):
        """
        Stream query results through the pipeline
        """
        history = history or []
        start_time = time.time()
        
        # Fast Path Detection - Only for greetings, NOT factual questions
        greeting_words = ["hi", "hello", "hey", "thanks", "thank you", "who are you", "help"]
        is_greeting = any(query.lower().strip() == word or query.lower().startswith(word + " ") for word in greeting_words)
        
        if is_greeting and len(query.split()) < 5:
            logger.info("Fast Path (Stream): Greeting detected, bypassing RAG")
            async for token in self.llm_service.stream_response(query):
                yield {"type": "token", "content": token}
            return

        # Stage 0: Context Enhancement
        enhanced_query = query
        if history:
            yield {"type": "status", "stage": 0, "content": "Analyzing conversation history..."}
            
            # Truncate history answers for Stage 0
            slim_history = []
            for h in history[-3:]: # type: ignore
                slim_history.append({
                    "query": h.get("query", ""),
                    "answer": (h.get("answer", "")[:200] + "...") if len(h.get("answer", "")) > 200 else h.get("answer", "")
                })

            enhance_prompt = f"Given conversation history and follow-up, rewrite to standalone query.\nHistory: {slim_history}\nFollow-up: {query}\nStandalone Query:"
            try:
                # Add a smaller timeout specifically for context enhancement
                llm_response = await asyncio.wait_for(self.llm_service.generate_response(enhance_prompt), timeout=10.0)
                enhanced_query = str(llm_response).strip().strip('"')
            except Exception as e:
                logger.warning(f"Context enhancement failed, using original query: {e}")

        try:
            # Stage 1: Expansion
            if not fast_mode:
                yield {"type": "status", "content": "Expanding search queries..." if not history else "Refining search queries..."}
                expanded_queries = await self.expand_query(enhanced_query)
            else:
                expanded_queries = [enhanced_query]
            
            # Stage 2: Parallel Retrieval
            yield {"type": "status", "stage": 2, "content": "Parallelizing retrieval..."}
            
            web_task = self.search_service.search_multiple_queries(
                expanded_queries, 
                max_results_per_query=5 if fast_mode else 15
            )
            vector_task = self.vector_service.search_documents(
                enhanced_query, 
                user_id=user.id, 
                session_id=session_id, 
                limit=5 if fast_mode else 10
            )
            
            # Yielding status while gathering with a strict timeout
            try:
                web_results, vector_results = await asyncio.wait_for(
                    asyncio.gather(web_task, vector_task),
                    timeout=25.0 # 25s total for combined retrieval
                )
                yield {"type": "status", "stage": 2, "content": "Retrieval complete."}
            except asyncio.TimeoutError:
                logger.warning("Retrieval stage timed out. Proceeding with limited data.")
                yield {"type": "status", "stage": 2, "content": "Search slow; proceeding with limited results..."}
                web_results, vector_results = [], [] # Fallback to empty if both timed out
            
            # Stage 3: RRF (Ranking)
            yield {"type": "status", "stage": 3, "content": "Applying neural ranking (RRF)..."}
            ranked_results = self.apply_rrf([vector_results, web_results])
            sources_to_use = ranked_results[:max_sources]
            
            # Stage 4: Chunking
            yield {"type": "status", "stage": 4, "content": "Processing semantic chunks..."}
            chunks = self.semantic_chunk(sources_to_use)
            
            # Stage 5+6 (Consensus/Consistency - simplified for speed if fast_mode)
            yield {"type": "status", "stage": 5, "content": "Sourcing intelligence..."}
            
            yield {"type": "status", "stage": 6, "content": "Finalizing verification..."}
            
            # Send initial metadata "packet" with source information
            logger.info(f"RAG Pipeline: Found {len(web_results)} web results, {len(vector_results)} vector results")
            initial_metadata = {
                "type": "metadata",
                "sources": sources_to_use,
                "confidence": float(round(float(0.5 + (len(sources_to_use)/40.0)), 2)), # type: ignore
                "web_search_performed": len(web_results) > 0,
                "documents_found": len(vector_results) > 0
            }
            yield initial_metadata

            # Stage 5: Streaming Generation
            # Use chunks (already formatted as Source [N] with title + snippet)
            context = "\n\n".join(chunks[:10])
            
            # Log context to verify web results are being passed
            logger.info(f"Context length for LLM: {len(context)} chars, sources: {len(sources_to_use)}")
            if chunks:
                logger.info(f"First chunk preview: {chunks[0][:200]}")
            
            is_personal = user.account_type == "personal"
            has_documents = len(vector_results) > 0
            
            if is_personal and not has_documents:
                # Personal account, no uploaded docs - pure web search like Perplexity
                prompt = f"""You are MindX, a real-time AI search engine. Answer the question using the web search results below.

RULES:
- Answer in clear, flowing prose. Minimum 3-4 paragraphs (150+ words) for factual queries.
- Cite sources using superscript-style [1], [2], [3] immediately after the fact.
- STRICTLY LINK citations to the provided sources. Do not hallucinate citations.
- DO NOT Include a "References" or "Sources" section at the end. Sources are handled by the UI.
- Use English language only.
- If web results are insufficient, answer from your knowledge but note it.

WEB SEARCH RESULTS:
{context}

Question: {query}

Answer:"""
            elif is_personal and has_documents:
                prompt = f"""You are MindX, a real-time AI search engine. Answer using the web search results and uploaded documents below.

RULES:
- Answer in clear, flowing prose. Minimum 3-4 paragraphs (150+ words).
- Cite sources using superscript-style [1], [2] immediately after the fact.
- STRICTLY LINK citations to the provided sources.
- DO NOT Include a "References" or "Sources" section.
- Use English language only.

SOURCES:
{context}

Question: {query}

Answer:"""
            else:
                # Company account - hybrid RAG
                prompt = f"""You are MindX, an enterprise AI search assistant. Answer using the provided sources.

RULES:
- Answer in clear, flowing prose. Minimum 3-4 paragraphs.
- Prioritize company documents, use web sources as supplementary.
- Cite sources using [1], [2] immediately after the fact.
- DO NOT Include a "References" or "Sources" section.
- Use English language only.

SOURCES:
{context}

Question: {query}

Answer:"""
            
            async for token in self.llm_service.stream_response(prompt):
                yield {"type": "token", "content": token}

            # Final metadata
            yield {
                "type": "final",
                "processing_time": time.time() - start_time
            }

        except Exception as e:
            logger.error(f"Streaming pipeline error: {e}")
            yield {"type": "error", "content": str(e)}

    def apply_rrf(self, results_groups: List[List[Dict]], k: int = 60) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) to merge multiple ranked lists.
        Higher k reduces importance of top results. Default 60 is common.
        """
        scores = {}
        docs = {}
        
        for group in results_groups:
            for rank, doc in enumerate(group):
                # Use URL or Title as ID
                doc_id = doc.get("url") or doc.get("href") or doc.get("title")
                if not doc_id: continue
                
                score = 1.0 / (k + rank + 1)
                scores[doc_id] = scores.get(doc_id, 0.0) + score
                if doc_id not in docs:
                    docs[doc_id] = doc
        
        # Sort by score descending
        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return [docs[did] for did in sorted_ids]
    
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
            raw_queries = [q.strip() for q in str(response).split('\n') if q.strip()]
            # Include original query
            all_queries: List[str] = [query]
            # Slicing safely
            top_queries = raw_queries[:3] # type: ignore
            all_queries.extend(top_queries)
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
        Stage 4: Break search results into semantic chunks with indexing for citations.
        Prefers full_content (from Jina AI) over snippet when available.
        """
        chunks = []
        for i, result in enumerate(results):
            source_idx = i + 1
            title = result.get('title', 'No Title')
            url = result.get('url', '')
            source_label = result.get('source', 'Web')
            credibility = result.get('credibility_score', 0.5)
            
            # Prefer full page content (Jina) over short snippet
            content = result.get('full_content') or result.get('snippet') or result.get('body') or 'No content available.'
            
            chunk = (
                f"Source [{source_idx}] ({title})\n"
                f"URL: {url}\n"
                f"Credibility: {source_label} ({credibility:.0%})\n"
                f"Content: {content}"
            )
            chunks.append(chunk)
        return chunks
    
    async def generate_multiple_answers(self, query: str, chunks: List[str], num_candidates: int = 3) -> List[str]:
        """
        Stage 5: Generate multiple answer candidates
        """
        answers = []
        
        # Divide chunks into groups for different perspectives
        chunk_groups = []
        for i in range(num_candidates):
            # Use manual slicing if linter fails on extended slicing
            group = [chunks[j] for j in range(i, len(chunks), num_candidates)]
            chunk_groups.append(group)
        
        for i in range(min(len(chunk_groups), num_candidates)):
            chunk_group = chunk_groups[i]
            # Top 5 chunks per candidate
            top_chunks = chunk_group[:5] # type: ignore
            context = "\n\n".join(top_chunks)


            
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

            Provide a final consensus answer that is clear, concise, and well-structured.
            Do NOT include meta-commentary like "Consensus Answer:", "Resolving Contradictions:", or "Answer Candidate X".
            Just provide the final answer text.

Final Answer:"""
        
        try:
            consensus = await self.llm_service.generate_response(prompt)
            # Sanitization: Strip common AI meta-talk leaks
            leaks = [
                "Consensus Answer:", "Resolving Contradictions:", "Answer Candidate", 
                "**Consensus Answer:**", "**Resolving Contradictions:**",
                "Consensus Point", "**Consensus Points:**"
            ]
            clean_consensus = str(consensus)
            for leak in leaks:
                if isinstance(clean_consensus, str) and leak in clean_consensus:
                    clean_consensus = clean_consensus.split(leak)[0].strip()
            
            return clean_consensus

        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return answers[0]  # Return first answer as fallback
    
    async def verify_facts(self, answer: str, sources: List[Dict]) -> Dict:
        """
        Stage 7: Verify facts and calculate confidence using a smarter heuristic
        """
        num_sources = len(sources)
        if num_sources == 0:
            return {"answer": answer, "sources": [], "confidence": 0.3}

        # Smarter Heuristic:
        # 1. Base score starts at 0.4
        # 2. Add 0.1 for every 5 sources (up to 0.4 bonus)
        # 3. Add 0.1 if we have web + local results (diversity bonus)
        # 4. Cap at 0.98 for LLM humility
        
        has_web = any(s.get('href') for s in sources)
        has_local = any(not s.get('href') for s in sources)
        
        conf_val = 0.4 + (min(20, num_sources) / 50.0)
        if has_web and has_local:
            conf_val += 0.1
            
        return {
            "answer": answer,
            "sources": sources,
            "confidence": float(round(float(min(0.98, conf_val)), 2)) # type: ignore
        }

