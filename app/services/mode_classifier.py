"""
MindX AI — Mode Classifier Service
Classifies every user query into one of three modes:
  SEARCH → needs live web data (factual, current events, people, etc.)
  CHAT   → no search needed, straight to LLM (creative, code, math, etc.)
  HYBRID → follow-up to a previous search (pronoun references, "tell me more")

Uses llama-3.1-8b-instant for speed (~50ms).
"""

import os
import re
import logging
from typing import List, Dict, Optional
from groq import AsyncGroq  # type: ignore

logger = logging.getLogger(__name__)


CLASSIFIER_PROMPT = """Classify this user message into exactly ONE mode.

SEARCH — needs live web data:
  factual questions, current events, people, companies, prices,
  "who is", "what is", "latest", "news", "when did", "how many",
  any question requiring up-to-date or real-world information.

CHAT — no web search needed:
  creative writing, code generation, math, explanations of known concepts,
  "write me", "explain", debugging help, "thanks", conversational,
  reasoning tasks, brainstorming, translation, summarization.

HYBRID — follow-up referencing a previous search result:
  uses pronouns like he/she/it/they/this/that/these/those,
  "tell me more", "what about", "and also", "why did",
  any question that only makes sense with prior context from search.

Return ONLY one word: SEARCH, CHAT, or HYBRID"""


class ModeClassifier:
    """
    Fast tri-mode classifier using the smallest/fastest model.
    """

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")
        self.client = AsyncGroq(api_key=api_key, timeout=10.0)
        self.model = "llama-3.1-8b-instant"

    async def classify(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """
        Classify a user query into SEARCH, CHAT, or HYBRID.

        Args:
            question: The user's raw question.
            history: Recent conversation history (list of {role, content} dicts).

        Returns:
            One of "SEARCH", "CHAT", or "HYBRID".
        """
        # ── Fast-path heuristics (skip LLM for obvious cases) ──
        q = question.lower().strip()

        # Obvious greetings / thanks → CHAT
        chat_exact = [
            "hi", "hello", "hey", "thanks", "thank you", "bye",
            "who are you", "help", "ok", "okay", "yes", "no",
            "good morning", "good night",
        ]
        if q in chat_exact or len(q.split()) < 2:
            return "CHAT"

        # Obviously creative / code tasks → CHAT (but only if no history)
        chat_prefixes = [
            "write ", "explain how to code", "debug ", "fix this",
            "convert ", "translate ", "summarize ", "rewrite ",
            "generate ", "create a ", "make a ", "build ",
        ]
        if any(q.startswith(p) for p in chat_prefixes):
            # If there is history, it might be "write the same in java" (HYBRID)
            # So we only auto-return CHAT if no prior context exists.
            if not (history and len(history) >= 2):
                return "CHAT"

        # Obvious reference to prior context → HYBRID
        hybrid_starters = [
            "tell me more", "what about", "and also", "why did",
            "can you elaborate", "go deeper", "expand on",
        ]
        if any(q.startswith(s) for s in hybrid_starters):
            has_history = bool(history and len(history) >= 2)
            return "HYBRID" if has_history else "SEARCH"

        # Pronoun-heavy short follow-ups with history → HYBRID
        pronoun_pattern = re.compile(
            r'\b(he|she|it|they|this|that|these|those|his|her|its|their|him|them)\b',
            re.IGNORECASE,
        )
        if history and len(history) >= 2 and len(q.split()) < 10:
            if pronoun_pattern.search(q):
                return "HYBRID"

        # ── LLM classification for ambiguous queries ──
        try:
            # Build a compact history snippet for context
            history_snippet = ""
            if history:
                recent = list(history[-4:])  # type: ignore  # last 2 exchanges
                lines: list[str] = []
                for m in recent:
                    role = "User" if m.get("role") == "user" else "AI"
                    content = str(m.get("content", ""))[:150]  # type: ignore
                    lines.append(f"{role}: {content}")  # type: ignore
                history_snippet = "\nRecent conversation:\n" + "\n".join(lines)

            user_msg = f"Message: {question}{history_snippet}"

            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLASSIFIER_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.1,
                max_tokens=5,
            )

            raw = (response.choices[0].message.content or "").strip().upper()

            # Parse — only accept valid modes
            if "HYBRID" in raw:
                # Only allow HYBRID if there's actual conversation history
                return "HYBRID" if (history and len(history) >= 2) else "SEARCH"
            elif "CHAT" in raw:
                return "CHAT"
            else:
                return "SEARCH"  # default to SEARCH for safety

        except Exception as e:
            logger.warning(f"ModeClassifier LLM call failed: {e}")
            # Fallback: default to SEARCH (safest — will always produce an answer)
            return "SEARCH"
