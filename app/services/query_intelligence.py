import json
import logging
from typing import List, Dict, Optional
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
                role = "User" if msg['role'] == 'user' else "MindX"
                context_block += f"{role}: {msg['content'][:200]}\n"

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
        """
        if not chat_history:
            return question

        context_words = ['he', 'she', 'it', 'they', 'his', 'her', 'their', 'this', 'that', 'these', 'those', 'the same', 'also', 'too', 'more about']
        has_reference = any(word in question.lower().split() for word in context_words)

        if not has_reference:
            return question

        recent_context_list = []
        for m in list(islice(chat_history, max(0, len(chat_history)-4), len(chat_history))):
            role = "User" if str(m.get('role', '')).lower() == 'user' else "AI"
            content = str(m.get('content', ''))
            recent_context_list.append(f"{role}: {content[:300]}")
        recent_context = "\n".join(recent_context_list)

        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.1,
                max_tokens=100,
                messages=[
                    {
                        "role": "system",
                        "content": "Rewrite the follow-up question as a fully self-contained question by resolving any pronouns or references using the conversation context. Return ONLY the rewritten question. Nothing else."
                    },
                    {
                        "role": "user",
                        "content": f"Context:\n{recent_context}\n\nFollow-up question: {question}"
                    }
                ]
            )
            resolved = response.choices[0].message.content.strip()
            logger.info(f"🔄 Query resolved: '{question}' -> '{resolved}'")
            return resolved
        except Exception as e:
            logger.error(f"Context resolution failed: {e}")
            return question

    async def optimize_query_for_search(self, query: str) -> str:
        """
        Further refines a query to be search-engine optimized.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.FAST_MODEL,
                temperature=0.1,
                max_tokens=50,
                messages=[
                    {"role": "system", "content": OPTIMIZE_QUERY_PROMPT},
                    {"role": "user", "content": query}
                ]
            )
            optimized = response.choices[0].message.content.strip()
            return optimized
        except Exception as e:
            logger.error(f"Query optimization failed: {e}")
            return query
