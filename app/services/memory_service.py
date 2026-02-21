import json
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session  # type: ignore
from app.models.user_memory import UserMemory  # type: ignore
from app.services.llm_service import LLMService  # type: ignore

logger = logging.getLogger(__name__)

class MemoryService:
    def __init__(self, db: Session, llm_service: LLMService):
        self.db = db
        self.llm = llm_service

    EXTRACTION_PROMPT = """Extract core personal facts, preferences, or explicit custom instructions about the user from the following exchange.
CRITICAL RULES:
1. ONLY extract information that is strictly personal to the user (e.g., "I prefer dark mode", "My name is John", "I am a software engineer").
2. DO NOT extract general knowledge, facts about the world, topic summaries, trivia, or coding concepts (e.g., DO NOT extract what ZigBee is, DO NOT extract facts about Hawaii).
3. If no new PERSONAL facts are found, you MUST return {{"facts": []}}.

Return a valid JSON object with a "facts" list. Each fact must have "key", "value", and "category" (pref, fact, work, bio).

Exchange:
User: {query}
AI: {answer}

JSON:"""

    async def extract_and_store_facts(self, user_id: int, query: str, answer: str):
        """Analyze a Q&A pair and save new memory items."""
        prompt = self.EXTRACTION_PROMPT.format(query=query, answer=answer)
        
        try:
            raw = await self.llm.generate_response(
                prompt=prompt,
                model=self.llm.FAST_MODEL,
                system_prompt="You are a data extraction engine. Output ONLY JSON."
            )
            
            # Clean JSON string (remove backticks if any)
            clean_json = raw.strip()
            if clean_json.startswith("```json"):
                clean_json = clean_json[7:-3].strip()
            elif clean_json.startswith("```"):
                clean_json = clean_json[3:-3].strip()

            # Check storage limit
            count = self.db.query(UserMemory).filter(UserMemory.user_id == user_id).count()
            if count >= 100:
                logger.warning(f"MemoryService: Storage limit reached for user {user_id}. Skipping extraction.")
                return

            data = json.loads(clean_json)
            facts = data.get("facts", [])
            
            for f in facts:
                key = f.get("key")
                value = f.get("value")
                if not key or not value: continue
                
                # Update if exists, else create
                existing = self.db.query(UserMemory).filter(
                    UserMemory.user_id == user_id,
                    UserMemory.key == key
                ).first()
                
                if existing:
                    existing.value = value
                    existing.category = f.get("category", existing.category)
                else:
                    new_mem = UserMemory(
                        user_id=user_id,
                        key=key,
                        value=value,
                        category=f.get("category", "general")
                    )
                    self.db.add(new_mem)
            
            if facts:
                self.db.commit()
                logger.info(f"MemoryService: Stored {len(facts)} facts for user {user_id}")
                
        except Exception as e:
            logger.error(f"MemoryService Error (Extraction): {e}")

    async def get_user_context(self, user_id: int, query: str) -> str:
        """Retrieve facts that might be relevant to the current query."""
        # For v2.0 simplified: Get all memories and let the LLM decide, or just last 20.
        # Future: Vector search on memory values.
        memories = self.db.query(UserMemory).filter(UserMemory.user_id == user_id).limit(30).all()
        
        if not memories:
            return ""
            
        context_lines = []
        for m in memories:
            context_lines.append(f"- {m.key}: {m.value} ({m.category})")
            
        return "\nUser Personal Context (Memory):\n" + "\n".join(context_lines)
