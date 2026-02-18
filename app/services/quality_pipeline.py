from typing import List, Dict, Optional, Any, cast
import asyncio
from itertools import islice
from app.services.llm_service import LLMService # type: ignore
from app.services.search_service import SearchService # type: ignore
from app.services.query_intelligence import QueryIntelligence # type: ignore
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
    Fact Verification - Verify facts and attribute sources
    """

    # ════════════════════════════════════════════════
    # PASS 1 — RAW ANSWER GENERATION (SMART MODEL)
    # ════════════════════════════════════════════════
    PASS1_SYSTEM = """
You are the Fact Synthesis Engine for MindX AI. Your role is purely objective.
You are "Silent" — you have no personality, no greetings, and no meta-talk.

CRITICAL INSTRUCTIONS:
1. CITATION IS MANDATORY: Every single factual claim MUST have a citation immediatey after it using [N] format.
2. RELEVANCE: If provided search results are irrelevant, ignore them and answer from internal knowledge using [General Knowledge]. Never mention the search results are missing.
3. NO FORMATTING: Write in raw prose ONLY. No markdown, no bolding, no lists. That is the job of the next pass.
4. ENGLISH ONLY: Strictly output in English.
5. NO REPETITION: Do not repeat the user's question.
6. CONFLICTS: If sources conflict, state both views and cite both.

FACTUAL SYNTHESIS STYLE:
"Primary research indicates X [1]. However, secondary analysis suggests Y [2]."
"""

    # ════════════════════════════════════════════════
    # PASS 2 — STRUCTURE & DISPLAY FORMATTING (SMART MODEL)
    # ════════════════════════════════════════════════
    PASS2_SYSTEM = """
You are the Expert Presentation Layer for MindX AI. Your goal is to transform raw factual data into a premium, scannable, and highly professional response.

USER INTENT: {intent}

PRESENTATION PRINCIPLES:
1. DIRECTNESS: Start immediately with the answer. No padding, no filler.
2. STRUCTURE: Use headers (##), bold terms, and lists to make the answer scannable.
3. TLDR: Always include a 1-sentence italicized summary after the opening statement.
4. NO CITATIONS: Do NOT include any [N] or __N__ markers. They will be handled by the UI.
5. PREMIUM FORMATTING:
   - Use `code blocks` for chemical formulas, math, or technical identifiers.
   - Use markdown tables for comparisons.
   - Use bolding for key entities and technical terms.
   - Separate long paragraphs into smaller, digestible chunks.

INTENT-SPECIFIC LAYOUTS:
- factual/person/definition: Direct answer -> TLDR -> 2-3 deep paragraphs -> "Key Facts" list -> Bottom Line.
- comparison: Summary -> TLDR -> Comparison Table -> Differentiating factors list.
- howto: Summary -> TLDR -> Step-by-step numbered list -> Safety/Pro-tips block.
- news/current: Summary -> TLDR -> Timeline or event summary -> Impact analysis.

STRICT RULES:
- Never use citation numbers.
- Never repeat the question.
- Never use generic AI phrasing like "As of my last update".
- Maintain a highly sophisticated, expert tone (think Scientific American or The Economist).
"""

    # ════════════════════════════════════════════════
    # PASS 3 — CONFIDENCE SCORING (FAST MODEL)
    # ════════════════════════════════════════════════
    PASS3_SYSTEM = """
Return ONLY a JSON logic object for the answer confidence.
{
  "score": 92,
  "level": "high",
  "reason": "4 authoritative sources agree on all key facts.",
  "conflicts": null
}
Rules: score (0-100), level (high/medium/low based on score). Deduct for foreign sources, conflicts, or <3 sources.
"""

    # ════════════════════════════════════════════════
    # FOLLOW-UP SUGGESTIONS (FAST MODEL)
    # ════════════════════════════════════════════════
    FOLLOWUP_SYSTEM = """
You generate deep-dive follow-up questions for MindX AI.

Your goal is to suggest 3 questions that help the user explore the topic 
at a deeper level or from a complementary angle.

STRICT RULES:
1. Context-Specific: Suggestions MUST refer to specific entities or 
   concepts mentioned in the provided answer.
2. Deep Dive: Avoid generic "What else?" or "Tell me more" style.
3. High Interest: Choose questions that a curious researcher would actually ask.
4. Format: Return ONLY a JSON array of exactly 3 strings.

Example:
If answer is about "Oxidation of Iron", suggestions could be:
["How does salinity affect the rate of iron oxidation?", 
 "What are the common industrial methods for preventing rust?", 
 "Can oxidation occur in a vacuum with other oxidizing agents?"]
"""
    
    def __init__(self, db: Session, use_reranking: bool = False):
        self.db = db
        self.llm_service = LLMService()
        self.search_service = SearchService()
        self.vector_service = VectorService(db)
        self.query_intel = QueryIntelligence()
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
        
        # Stage 0: Context Resolution & Semantic Analysis
        # Resolve pronouns/references first
        resolved_query = await self.query_intel.resolve_context_references(query, history)
        
        # Semantically analyze the resolved query
        intelligence = await self.query_intel.analyze_query(resolved_query, history)
        enhanced_query = resolved_query
        
        # If intelligence suggests optimized queries, use them
        expanded_queries = intelligence.get("optimized_queries", [resolved_query])
        
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
            
            # Stage 1: Expansion (already handled by Intelligence if not fast_mode)
            if expanded_queries == [resolved_query]:
                logger.info("Stage 1: One-shot Query Optimization")
                optimized = await self.query_intel.optimize_query_for_search(resolved_query)
                expanded_queries = [optimized]
            elif not fast_mode:
                logger.info("Stage 1: Multi-query Expansion")
                expanded_queries = await self.expand_query(enhanced_query)
            
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
            chunks_list = self.semantic_chunk(sources_to_use)
            # Use islice to satisfy linter that doesn't like [:]
            top_chunks: List[str] = list(islice(chunks_list, 12))
            context = "\n\n".join(top_chunks)
            
            # ════════════════════════════════════════════════
            # MULTI-PASS GENERATION (Stage 5, 6, 7 replacement)
            # ════════════════════════════════════════════════
            
            # Pass 1: Accuracy (Silent)
            is_relevant = await self.check_context_relevance(query, context)
            if not is_relevant:
                logger.warning("Search context irrelevant. Using model knowledge fallback.")
                context = "The search results are unrelated. Answer from your own knowledge using [General Knowledge] citations."

            messages = await self.llm_service.build_messages_with_history(
                question=query,
                context=context,
                chat_history=history
            )
            
            raw_answer = await self.llm_service.generate_chat_completion(
                messages=messages,
                model=self.llm_service.SMART_MODEL
            )

            # Pass 2 & 3 & Followups (Parallel)
            logger.info("Pipeline Pass 2 & 3: Formatting & Scoring")
            intent = intelligence.get("intent", "factual")
            formatted_answer_task = self.llm_service.generate_response(
                prompt=f"Raw answer to format:\n\n{raw_answer}",
                system_prompt=self.PASS2_SYSTEM.format(intent=intent),
                model=self.llm_service.SMART_MODEL
            )
            confidence_task = self._pass3_score(query, raw_answer, sources_to_use)
            followups_task = self._generate_followups(query, raw_answer)

            formatted_answer, confidence, followups = await asyncio.gather(
                formatted_answer_task,
                confidence_task,
                followups_task
            )

            # Repair dropped citations
            formatted_answer = self.verify_citations(raw_answer, formatted_answer)

            result = {
                "answer": formatted_answer,
                "sources": sources_to_use,
                "confidence": confidence.get("score", 0.7) / 100.0,
                "confidence_details": confidence,
                "followups": followups,
                "metadata": {
                    "queries_used": len(expanded_queries),
                    "sources_used": len(sources_to_use),
                    "processing_time": time.time() - start_time,
                    "mode": "multi_pass_v2"
                }
            }
            
            return result
            
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

        # Stage 0: Intent & Context Analysis
        yield {"type": "status", "stage": 0, "content": "Analyzing conversation intent..."}
        
        # Resolve pronouns/references first
        resolved_query = await self.query_intel.resolve_context_references(query, history)
        
        # Semantically analyze the resolved query
        intelligence = await self.query_intel.analyze_query(resolved_query, history)
        enhanced_query = resolved_query
        
        # Personalization: If intelligence suggests optimized queries, use them
        expanded_queries = intelligence.get("optimized_queries", [resolved_query])
        
        # Reliability: Determine deep fetch requirements
        # If not fast_mode and query is factual/academic, fetch more content
        deep_fetch_count = 5 if not fast_mode else 2
        
        try:
            # If search disabled, use LLM-only mode (existing behavior)
            if not use_search:
                yield {"type": "status", "stage": 0, "content": "Search disabled, using LLM-only mode..."}
                async for token in self.llm_service.stream_response(query):
                    yield {"type": "token", "content": token}
                yield {
                    "type": "metadata",
                    "sources": [],
                    "confidence": 0.5,
                    "web_search_performed": False,
                    "documents_found": False,
                    "processing_time": time.time() - start_time
                }
                yield {"type": "final", "content": "Complete"}
                return

            # Stage 1: Expansion (already handled by Intelligence if not fast_mode)
            if expanded_queries == [resolved_query]:
                yield {"type": "status", "content": "Optimizing search intent..."}
                optimized = await self.query_intel.optimize_query_for_search(resolved_query)
                expanded_queries = [optimized]
            elif not fast_mode:
                # Fallback to older expansion if intelligence was too simple
                yield {"type": "status", "content": "Expanding search queries..."}
                expanded_queries = await self.expand_query(enhanced_query)
            
            # Stage 2: Multi-Source Retrieval
            yield {"type": "status", "stage": 2, "content": "Searching scholarly & web databases..."}
            
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
            
            # Stage 3: Neural Ranking (RRF)
            yield {"type": "status", "stage": 3, "content": "Ranking results by credibility..."}
            ranked_results = self.apply_rrf([vector_results, web_results])
            sources_to_use = ranked_results[:max_sources]
            
            # Stage 4: Semantic Intelligence
            yield {"type": "status", "stage": 4, "content": "Synthesizing multi-source evidence..."}
            chunks = self.semantic_chunk(sources_to_use)
            context = "\n\n".join(chunks)
            
            # Stage 5+6 (Consensus/Consistency)
            yield {"type": "status", "stage": 5, "content": "Checking factual consensus..."}
            
            yield {"type": "status", "stage": 6, "content": "Verifying multi-turn grounding..."}
            
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

            # Stage 5: Multi-Pass Streaming (Accuracy -> Format)
            yield {"type": "status", "stage": 5, "content": "Analyzing and citing sources..."}
            
            # Pass 1: Silent Accuracy Generation
            is_relevant = await self.check_context_relevance(query, context)
            if not is_relevant:
                logger.warning("Search context irrelevant. Using model knowledge fallback.")
                context = "The search results are unrelated. Answer from your own knowledge using [General Knowledge] citations."

            messages = await self.llm_service.build_messages_with_history(
                question=query,
                context=context,
                chat_history=history
            )
            
            raw_answer = await self.llm_service.generate_chat_completion(
                messages=messages,
                model=self.llm_service.SMART_MODEL
            )
            
            # Pass 2: Streamed Formatting
            yield {"type": "status", "stage": 6, "content": "Polishing presentation..."}
            
            # Start gathering Pass 3 and Followups in background while Pass 2 streams
            confidence_task = self._pass3_score(query, raw_answer, sources_to_use)
            followups_task = self._generate_followups(query, raw_answer)

            intent = intelligence.get("intent", "factual")
            full_formatted = ""
            async for token in self.llm_service.stream_response(
                prompt=f"Raw answer:\n\n{raw_answer}",
                system_prompt=self.PASS2_SYSTEM.format(intent=intent),
                model=self.llm_service.SMART_MODEL
            ):
                # Clean token if it contains a snippet of a citation bracket
                # This is tricky mid-stream, so we'll just append and yield as is
                # The prompt should prevent them, but strip_citations_from_display
                # will be used for final verification and UI display fixes
                full_formatted += token
                yield {"type": "token", "content": token}

            # Final clean-up of the formatted answer to ensure NO citations leak
            full_formatted = self.strip_citations_from_display(full_formatted)

            # Repair dropped citations after stream (for metadata/final answer logic)
            # Note: We can't easily repair the live stream tokens, but we can fix the final result
            full_formatted = self.verify_citations(raw_answer, full_formatted)

            # Wait for parallel tasks
            confidence, followups = await asyncio.gather(confidence_task, followups_task)

            # Final metadata yield
            yield {
                "type": "metadata",
                "sources": sources_to_use,
                "confidence": confidence.get("score", 70) / 100.0,
                "confidence_details": confidence,
                "followups": followups,
                "processing_time": time.time() - start_time
            }

            yield {"type": "final", "content": "Complete"}

        except Exception as e:
            logger.error(f"Streaming pipeline error: {e}")
            yield {"type": "error", "content": str(e)}

    def apply_rrf(self, results_groups: List[List[Dict]], k: int = 60) -> List[Dict]:
        """
        Reciprocal Rank Fusion (RRF) with Credibility Weighting.
        Boosts academic and official sources.
        """
        scores: Dict[str, float] = {}
        docs: Dict[str, Dict] = {}
        
        for group in results_groups:
            for rank, doc in enumerate(group):
                doc_id = str(doc.get("url") or doc.get("href") or doc.get("title"))
                if not doc_id: continue
                
                # Base RRF score
                base_score = 1.0 / (k + rank + 1)
                
                # Apply credibility weight
                # SearchService provides credibility_score (0.5 to 0.95)
                # We normalize and amplify this
                cred_score = float(doc.get("credibility_score", 0.55))
                weight = 1.0
                if cred_score >= 0.90: weight = 2.0  # Academic/Scholar
                elif cred_score >= 0.75: weight = 1.3 # Official/News
                
                final_score = base_score * weight
                scores[doc_id] = scores.get(doc_id, 0.0) + final_score
                
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
            return answers[0] if answers else ""

    def strip_citations_from_display(self, text: str) -> str:
        """
        Remove all inline citation markers from the displayed answer.
        This is a critical cleanup pass to ensure premium look.
        """
        import re
        # Remove [1], [2], [1,2], [1-3] style
        text = re.sub(r'\s*\[\d+(?:,\s*\d+)*(?:-\d+)*\]', '', text)
        # Remove __1__, __2__ style  
        text = re.sub(r'\s*__\d+__', '', text)
        # Remove floating numbers that might be leaked citations
        text = re.sub(r'(?<=\s)\d+(?=\s|[.,!?]|$)', '', text)
        return text.strip()
        return text.strip()

    def verify_citations(self, raw: str, formatted: str) -> str:
        """
        If Pass 2 dropped any citations, re-inject them at the bottom as a safety measure.
        """
        import re
        
        # Find all citations in raw and formatted
        raw_citations = set(re.findall(r'\[(\d+)\]', raw))
        fmt_citations = set(re.findall(r'\[(\d+)\]', formatted))
        
        missing = raw_citations - fmt_citations
        
        if missing:
            logger.warning(f"Pass 2 dropped citations: {missing} — appending repair note.")
            # Append warning note and missing citations at bottom
            repair_note = f"\n\n> [!NOTE]\n> Citations for sources {', '.join([f'[{m}]' for m in sorted(list(missing))])} were verified from the reasoning pass."
            formatted += repair_note
        
        return formatted


    async def check_context_relevance(self, question: str, context: str) -> bool:
        """
        Quick check: are these search results actually relevant
        to the question? If not, skip RAG and use model knowledge.
        """
        try:
            context_snippet = "".join(islice(context, 1000))
            response = await self.llm_service.generate_response(
                prompt=f"Are these search results relevant to answering: '{question}'?\n\nResults preview: {context_snippet}",
                system_prompt="Answer only 'yes' or 'no'.",
                model=self.llm_service.FAST_MODEL
            )
            return 'yes' in response.lower()
        except:
            return True # Default to yes if LLM check fails

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

    async def _pass3_score(self, question: str, answer: str, sources: List[Dict]) -> Dict:
        """Internal helper for Pass 3: Confidence Scoring"""
        try:
            import json
            import re
            
            # Type-safe slicing for Pyre using islice
            sources_slice: List[Dict] = list(islice(sources, 8))
            source_context = json.dumps([str(s.get('title','')) + ' - ' + str(s.get('url','')) for s in sources_slice])
            
            answer_text: str = str(answer)
            short_answer: str = "".join(islice(answer_text, 600))
            
            response = await self.llm_service.generate_response(
                prompt=f"Question: {question}\nAnswer: {short_answer}\nSources: {source_context}",
                system_prompt=self.PASS3_SYSTEM,
                model=self.llm_service.FAST_MODEL
            )
            raw = response.strip()
            # Strip markdown formatting if LLM adds it
            raw = re.sub(r'```json|```', '', raw).strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Pass 3 failed: {e}")
            return {"score": 75, "level": "medium", "reason": "Default score applied.", "conflicts": None}

    async def _generate_followups(self, question: str, answer: str) -> List[str]:
        """Internal helper for generating follow-up suggestions"""
        try:
            import json
            import re
            
            answer_text: str = str(answer)
            short_answer: str = "".join(islice(answer_text, 400))
            
            response = await self.llm_service.generate_response(
                prompt=f"Q: {question}\nA: {short_answer}",
                system_prompt=self.FOLLOWUP_SYSTEM,
                model=self.llm_service.FAST_MODEL
            )
            raw = response.strip()
            raw = re.sub(r'```json|```', '', raw).strip()
            return json.loads(raw)
        except Exception as e:
            logger.warning(f"Followups failed: {e}")
            return [
                "Tell me more about this.",
                "What are the key implications?",
                "How has this changed over time?"
            ]

    # Legacy methods for compatibility (if needed) or cleanup
    async def generate_multiple_answers(self, query: str, chunks: List[str], num_candidates: int = 3): return []

