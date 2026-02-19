import json
import re
import logging
from typing import List, Dict, Optional, Any
from groq import AsyncGroq
import os
from itertools import islice

logger = logging.getLogger(__name__)

QUERY_ANALYSIS_PROMPT = """
You are a search query optimizer for MindX AI.

Analyze the user's question and return ONLY a JSON object with this structure:
{
  "intent": "factual | comparison | howto | opinion | news | definition | person",
  "optimized_queries": ["query1", "query2", "query3"],
  "key_entities": ["entity1", "entity2"],
  "time_sensitive": true | false,
  "language": "en",
  "context_used": true | false
}

Rules:
- optimized_queries: 3 search-engine-optimized versions of the question. These should be short, keyword-focused, English only.
  Example: "who is father of physics" -> ["father of physics biography", "physics founder history", "first physicist scientist"]
- key_entities: named people, places, things in the query.
- time_sensitive: true if query needs latest information (e.g., news, sports, current events).

Return ONLY the JSON. No explanation.
"""

OPTIMIZE_QUERY_PROMPT = """
Convert the following question into a single, highly dense search query. 
Focus on:
1. Identifying the core entity.
2. Adding keywords for grounding (e.g., "official site", "definition", "documentation").
3. Removing all conversational filler.

Example: "Can you tell me more about how photosynthesis works in deep sea plants?" 
Output: photosynthesis mechanism deep sea flora official research
"""

NEEDS_SEARCH_PROMPT = """
Analyze if this query requires external information (RAG/Web Search) or can be answered by the LLM directly.

NEEDS SEARCH (true):
- Factual questions ("Who is CEO of Google?", "Latest news on AI")
- Comparison ("Claude vs GPT-4")
- Technical documentation ("How to use React useEffect")
- Unknown entities ("What is MindX?")

NO SEARCH (false):
- Greetings ("Hi", "Hello", "Thanks")
- Creative writing ("Write a poem", "Draft an email")
- General knowledge logic ("What is 2+2?", "Explain the concept of love")
- Code generation specific to known algorithms ("Write a fibonacci function")
- Follow-up conversation not requiring new facts ("Start over", "Clear context")

Return ONLY JSON:
{
  "needs_search": true,
  "reason": "short explanation"
}
"""

class QueryIntelligence:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.client = AsyncGroq(api_key=api_key)
        self.FAST_MODEL = "llama-3.1-8b-instant"

    async def analyze_query(self, question: str, chat_history: List[Dict] = []) -> Dict:
        """
        Semantically understand the user query before searching.
        Also resolves context references from chat history.
        """
        context_block = ""
        if chat_history:
            recent = list(islice(chat_history, max(0, len(chat_history)-6), len(chat_history)))
            context_block = "\n\nRecent conversation:\n"
            for msg in recent:
                role = "User" if msg.get('role') == 'user' else "MindX"
                content_val = str(msg.get('content') or "")
                context_block += f"{role}: {content_val[0:200]}\n"

        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.1,
                max_tokens=300,
                messages=[
                    {"role": "system", "content": QUERY_ANALYSIS_PROMPT},
                    {"role": "user", "content": f"Question: {question}{context_block}"}
                ]
            )

            raw = response.choices[0].message.content.strip()
            raw = raw.replace('```json', '').replace('```', '').strip()
            
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Query analysis failed: {e}")
            return {
                "intent": "factual",
                "optimized_queries": [question],
                "key_entities": [],
                "time_sensitive": False,
                "language": "en",
                "context_used": False
            }

    async def resolve_context_references(self, question: str, chat_history: List[Dict]) -> str:
        """
        Resolves pronouns and references in follow-up questions.
        Enhanced for multi-turn nested references.
        """
        if not chat_history:
            return question

        context_words = [
            'he', 'she', 'it', 'they', 'his', 'her', 'their', 'this', 'that', 'these', 'those', 
            'the same', 'also', 'too', 'more about', 'who is he', 'what is it', 'tell me more',
            'why', 'how', 'when', 'where', 'him', 'them'
        ]
        
        # Check if query is a clear follow-up or contains pronouns
        is_short = len(question.split()) < 5
        has_reference = any(word in question.lower().split() for word in context_words)
        
        if not has_reference and not is_short:
            return question

        # Provide a deeper window of context for resolution
        recent_context_list = []
        # Take up to 6 turns (user + ai pairs)
        for m in list(islice(chat_history, max(0, len(chat_history)-6), len(chat_history))):
            role = "User" if str(m.get('role', '')).lower() == 'user' else "MindX"
            content_val = str(m.get('content') or "")
            recent_context_list.append(f"{role}: {content_val[0:300]}")
        recent_context = "\n".join(recent_context_list)

        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.1,
                max_tokens=150,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a Context Resolver for MindX AI. 
Rewrite the user's follow-up question into a fully self-contained, descriptive search query.
Resolve ALL pronouns (it, they, he, she, this, that) using the conversation history.
If the question is very short (e.g., "Why?"), expand it to include the subject being discussed.

Rules:
- Return ONLY the rewritten question.
- Do not add "Search for:" or any prefix.
- Ensure the result is a complete, grammatically correct question or a dense keyword set.
"""
                    },
                    {
                        "role": "user",
                        "content": f"Conversation Context:\n{recent_context}\n\nUser Follow-up: {question}"
                    }
                ]
            )
            resolved = response.choices[0].message.content.strip()
            # Clean up potential markdown or quotes
            resolved = resolved.replace('"', '').replace("'", "").strip()
            logger.info(f"🔄 Context Resolved: '{question}' -> '{resolved}'")
            return resolved
        except Exception as e:
            logger.error(f"Context resolution failed: {e}")
            return question

    async def optimize_query_for_search(self, question: str, intelligence: Optional[Dict] = None) -> List[str]:
        """
        Rewrite the query into 3 search-optimized variations.
        ENFORCES STRICT TOPIC PRESERVATION.
        """
        intent = "factual"
        if intelligence:
            intent = intelligence.get("intent", "factual")

        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.1,
                max_tokens=200,
                messages=[
                    {
                        "role": "system",
                        "content": """Convert this question into 3 search engine queries.

CRITICAL RULES:
- STRICT TOPIC PRESERVATION: NEVER replace the actual topic words with synonyms. 
- Example: "making tea" -> MUST use "making tea". (Do NOT use "preparing beverages", "brewing", etc.)
- Example: "key principles" -> MUST use "key principles".
- No conversational filler (how to, tell me, etc. in optimizations).
- If the topic is technical, add domain-specific keywords (e.g. "documentation", "API").
- Queries must be 3-6 words, English only.
- Return ONLY a JSON array of 3 strings.
"""
                    },
                    {
                        "role": "user",
                        "content": f"Question: {question} (Intent: {intent})"
                    }
                ]
            )
            
            raw = response.choices[0].message.content.strip()
            # Clean potential markdown
            raw = re.sub(r'```json|```', '', raw).strip()
            
            try:
                optimized_list = json.loads(raw)
                if isinstance(optimized_list, list) and len(optimized_list) > 0:
                    logger.info(f"🔍 Search Optimized ({intent}): '{question}' → {optimized_list}")
                    return [q.replace('"', '').replace("'", "").strip() for q in optimized_list]
            except:
                pass

            # Fallback - extract key nouns or just return the original + 2 basic variants
            logger.warning(f"Query optimization parsing failed for: {raw}. Using fallback.")
            return [question, f"{question} explained", f"{question} guide"]
            
        except Exception as e:
            logger.error(f"Query optimization failed: {e}")
            return [question]

    async def needs_search(self, question: str) -> Dict[str, Any]:
        """
        Determine if the user query requires external info (RAG).
        Returns { "needs_search": bool, "reason": str }
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.0,
                max_tokens=100,
                messages=[
                    {"role": "system", "content": NEEDS_SEARCH_PROMPT},
                    {"role": "user", "content": f"Query: {question}"}
                ]
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r'```json|```', '', raw).strip()
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Needs search check failed: {e}")
            return {"needs_search": True, "reason": "Error fallback"}
