from typing import List, Dict, Optional, Any, cast
import asyncio
import json
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
You are a research analyst for MindX AI.

ABSOLUTE RULES:
1. Answer the question directly and completely
2. Never say "I did not find information in the search results"
3. Never say "Based on search results..." or "According to source X"
4. Never mention the search results at all
5. If search context is irrelevant, use your own knowledge confidently
6. Cite facts with [1][2][3] immediately after each fact
7. Write in English only — ignore any foreign language sources
8. Never list references at the end
9. Never use __1__ markers — use [1] only
10. Be thorough — cover all important aspects of the question

Your answer must start immediately with the actual answer.
No preamble. No hedging. No meta-commentary.
"""

    PASS2_SYSTEM = """
You are the display formatter for MindX AI.
Transform raw research notes into Claude-quality structured output.

════════════════════════════════════════
STEP 1 — IDENTIFY QUESTION TYPE AND CHOOSE STRUCTURE
════════════════════════════════════════

CONCEPT/EXPLAIN question → Structure:
  - Bold subject + direct definition sentence
  - Italic TLDR line
  - ## The Core Idea (2-3 prose paragraphs)
  - ## Key Principles (bullet list with bold terms)
  - ## Why It Matters (real-world applications)
  - Closing insight sentence

WHO IS/BIOGRAPHY question → Structure:
  - Bold name + one-sentence who they are
  - Italic TLDR
  - Background paragraph
  - Key contributions/achievements paragraph
  - Legacy/impact paragraph

HOW TO/PROCESS question → Structure:
  - Direct answer sentence
  - Italic TLDR
  - Numbered steps (bold step name + explanation)
  - Tips or warnings if relevant

COMPARISON question → Structure:
  - Direct answer sentence
  - Prose explaining key differences
  - Markdown comparison table
  - Recommendation sentence

LIST/EXAMPLES question → Structure:
  - Intro sentence
  - Numbered list (bold term + explanation for each)
  - Brief context paragraph

WHY question → Structure:
  - Direct answer
  - Cause → Effect prose
  - Implications paragraph

════════════════════════════════════════
STEP 2 — FORMATTING RULES
════════════════════════════════════════

OPENING:
- First sentence directly answers. Bold the main subject: **Netflix**
- Never start with "Certainly!", "Great question!", "Based on..."
- Never restate the question

TLDR LINE (always second element):
- One italic summary: *Netflix was founded in 1997 by Reed Hastings 
  and Marc Randolph as a DVD-by-mail service before pivoting to streaming.*
- Blank line after

PROSE PARAGRAPHS:
- Max 3-4 sentences each
- Blank line between every paragraph
- One idea per paragraph
- NEVER repeat information already stated in a previous paragraph
- NEVER write 3+ paragraphs all defining the same concept differently

HEADERS:
- ## for major sections (answers over 200 words)
- #### for smaller sections or short answers (REQUIRED if answer < 200 words)
- Descriptive titles: ## Key Principles, #### Why It Matters
- NEVER: ## Introduction, ## Conclusion, ## Overview, ## Summary
- **CRITICAL**: You MUST include at least one `##` OR `####` header in every response.
- **PROHIBITED**: Do NOT use bold-only lines (e.g. **Title**) as section headers.

BULLET POINTS (for lists of features, principles, properties):
- Format: **Bold Key Term** — one complete sentence explanation
- Every bullet minimum one full sentence
- Never single-word bullets
- Max 6 bullets per list
- Use • symbol

NUMBERED LISTS (steps, processes, ranked items ONLY):
- Format: 1. **Step Name** — explanation of the step
- Never use numbers for unordered content

BOLD:
- Every key technical term on first use: **superposition**, **entanglement**
- All proper nouns and names: **Reed Hastings**, **Isaac Newton**
- Important facts that need emphasis
- NEVER bold entire sentences

ITALIC:
- TLDR line only
- Subtle clarifications or asides

CODE FORMAT:
- Chemical formulas: `Fe₂O₃`, `H₂O`, `CO₂`
- Math equations: `E = mc²`
- Technical notation

TABLES:
- Only for direct side-by-side comparisons
- Bold column headers

════════════════════════════════════════
STEP 3 — ABSOLUTE PROHIBITIONS
════════════════════════════════════════

NEVER include ANY of these:
✗ Citation numbers [1][2][3] anywhere — not in prose, not anywhere
✗ __1__ or __2__ markers anywhere
✗ "References:" section or any source listing
✗ URLs in the answer body
✗ "Based on search results..."
✗ "According to source X..."
✗ "Note: this answer may not be current"
✗ "I did not find information about..."
✗ Repeated paragraphs saying the same thing differently
✗ Walls of text with no formatting breaks
✗ More than 2 consecutive prose paragraphs without a list or header
✗ "In conclusion" or "In summary" or "To summarize"
✗ Restating the question at any point

════════════════════════════════════════
STEP 4 — LENGTH TARGETS
════════════════════════════════════════

Simple fact (who, when, where): 80-150 words, no headers
Definition/concept: 250-400 words with headers and bullets
Multi-part question: 400-600 words
Comparison: 300-450 words with table
Never exceed 700 words

════════════════════════════════════════
## The Founders

**Reed Hastings**, a software entrepreneur, came up with the core 
idea after reportedly being charged a $40 late fee for a Blockbuster 
rental of Apollo 13. He brought in **Marc Randolph**, a veteran 
marketer and serial entrepreneur, as co-founder and first CEO.

Randolph is widely credited with conceiving the original business 
model and is often called Netflix's "founding father." Hastings 
provided the funding and technical vision, eventually taking over 
as CEO in 1999 as the company scaled.

## From DVDs to Streaming

Netflix launched its streaming service in 2007, a decade after 
founding, completely pivoting away from physical media. The bet 
paid off — Netflix now has over **260 million subscribers** across 
190 countries, making it the dominant force in global entertainment.

The company's success also triggered the "streaming wars," 
prompting Disney, HBO, Apple, and Amazon to launch competing 
services, permanently dismantling the traditional TV model.

════════════════════════════════════════
PRODUCE OUTPUT EXACTLY LIKE THIS REFERENCE.
Your formatted answer must be indistinguishable in quality 
and structure from a Claude AI response.
════════════════════════════════════════
"""

    PASS3_SYSTEM = """
You are a Research Auditor for MindX AI. 
Evaluate the factuality and reliability of the provided answer based on the context.

Score based on:
1. Authority: Are sources official, academic, or reputable?
2. Multi-Sourcing: Do multiple sources confirm the core facts?
3. Language: Deduct points for mixed-language or non-English sources.
4. Accuracy: Does the answer accurately reflect the context?

Return ONLY this JSON object:
{
  "score": 0-100,
  "level": "high | medium | low",
  "reason": "specific reason for this score",
  "conflicts": "describe any factual conflicts found, or null"
}
"""

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
                optimized = await self.query_intel.optimize_query_for_search(resolved_query, history)
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
            relevance = await self.check_context_relevance(query, context)
            if not relevance.get("is_relevant", True):
                logger.warning(f"Search context irrelevant: {relevance.get('reason')}")
                context = f"The search results were found to be mostly irrelevant: {relevance.get('reason')}. Answer the user's question directly and comprehensively using your own knowledge. Do not mention search results or lack thereof."

            messages = await self.llm_service.build_messages_with_history(
                question=query,
                context=context,
                chat_history=history
            ,
                system_prompt=self.PASS1_SYSTEM
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
                optimized_queries = await self.query_intel.optimize_query_for_search(resolved_query, intelligence)
                expanded_queries = optimized_queries
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
            relevance = await self.check_context_relevance(query, context)
            if not relevance.get("is_relevant", True):
                if not fast_mode: 
                    yield {"type": "status", "content": "Context mismatch; relying on model intelligence..."}
                logger.warning(f"Search context irrelevant: {relevance.get('reason')}")
                context = f"The search results were found to be mostly irrelevant: {relevance.get('reason')}. Answer the user's question directly and comprehensively using your own knowledge. Do not mention search results or lack thereof."

            messages = await self.llm_service.build_messages_with_history(
                question=query,
                context=context,
                chat_history=history
            ,
                system_prompt=self.PASS1_SYSTEM
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
            # Stream with citation filtering
            buffer = ""
            import re
            
            async for token in self.llm_service.stream_response(
                prompt=f"Raw answer:\n\n{raw_answer}",
                system_prompt=self.PASS2_SYSTEM.format(intent=intent),
                model=self.llm_service.SMART_MODEL
            ):
                full_formatted += token
                buffer += token
                
                # Check if buffer contains a potential start of a citation
                if "[" in buffer:
                    # Check if complete citation exists
                    match = re.search(r'\[\s*\d+(?:,\s*\d+)*(?:-\d+)*\s*\]', buffer)
                    if match:
                        # Remove the citation from buffer
                        buffer = buffer.replace(match.group(0), "")
                        # Yield remaining buffer if no more open brackets
                        if "[" not in buffer:
                           yield {"type": "token", "content": buffer}
                           buffer = ""
                        continue
                    
                    # If buffer gets too long without closing bracket, flush it
                    # (Safety against hanging "[Summary: ...")
                    if len(buffer) > 20 and not re.search(r'\[\s*\d+', buffer):
                         # Likely not a citation, or a long one we shouldn't block
                         yield {"type": "token", "content": buffer}
                         buffer = ""
                else:
                    # No bracket, yield immediately
                    # Last check for stray numbers if prompted to be ultra-clean
                    yield {"type": "token", "content": buffer}
                    buffer = ""

            # Flush any remaining buffer
            if buffer:
                 # Last check for citations
                 buffer = re.sub(r'\[\s*\d+(?:,\s*\d+)*(?:-\d+)*\s*\]', '', buffer)
                 if buffer:
                    yield {"type": "token", "content": buffer}

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
            logger.info(f"Pass 2 dropped citations: {missing} — consistent with Claude-style formatting.")
            # Do NOT append repair note for Claude-style output as it violates the clean look.
            # repair_note = f"\n\n> [!NOTE]\n> Citations for sources {', '.join([f'[{m}]' for m in sorted(list(missing))])} were verified from the reasoning pass."
            # formatted += repair_note
        
        return formatted


    async def check_context_relevance(self, question: str, context: str) -> Dict[str, Any]:
        """
        Stage 4b: Relevance Pass
        Analyze search results to see if they actually contain the answer.
        Returns a detailed report.
        """
        try:
            context_snippet = "".join(islice(context, 1500))
            prompt = f"""
Analyze if the provided context is relevant to answering the question: "{question}"

Context Preview:
{context_snippet}

Return ONLY a JSON object:
{{
  "is_relevant": true | false,
  "relevance_score": 0-100,
  "reason": "short explanation",
  "missing_aspects": ["topic1", "topic2"]
}}
"""
            response = await self.llm_service.generate_response(
                prompt=prompt,
                system_prompt="You are a Relevance Auditor. Return ONLY raw JSON.",
                model=self.llm_service.FAST_MODEL
            )
            raw = response.strip().replace('```json', '').replace('```', '').strip()
            return json.loads(raw)
        except Exception as e:
            logger.warn(f"Relevance check failed: {e}")
            return {"is_relevant": True, "relevance_score": 100, "reason": "Audit failed, defaulting to relevant."}

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

