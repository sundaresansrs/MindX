from groq import AsyncGroq
import os
from itertools import islice
from typing import List, Dict, Optional, Any


class LLMService:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        self.client = AsyncGroq(api_key=api_key, timeout=30.0)

        # ✅ NEW MULTI-MODEL SETUP
        self.FAST_MODEL = "llama-3.1-8b-instant"    # For expansion & scoring
        self.SMART_MODEL = "llama-3.3-70b-versatile" # For reasoning & formatting
        self.VISION_MODEL = "llama-3.2-11b-vision-preview" # For image analysis
        self.model = self.FAST_MODEL # default

    async def generate_response(
        self,
        prompt: str,
        context: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        history: Optional[List[Dict]] = None,
        images: Optional[List[str]] = None
    ) -> str:
        """Non-streaming version of generates chat completion."""
        if images or history or context or system_prompt:
             messages = await self.build_messages_with_history(
                 question=prompt,
                 context=context or "",
                 chat_history=history or [],
                 system_prompt=system_prompt,
                 images=images
             )
        else:
             messages = [{"role": "user", "content": prompt}]

        response = await self.client.chat.completions.create(
            model=model or self.model,
            messages=messages, # type: ignore
            temperature=0.3,
        )

        return response.choices[0].message.content or ""

    async def stream_response(
        self,
        prompt: str,
        context: str | None = None,
        model: str | None = None,
        system_prompt: str | None = None,
        history: Optional[List[Dict]] = None,
        images: Optional[List[str]] = None
    ):
        """Streaming version of generate_chat_completion."""
        if images or history or context or system_prompt:
             # Use the more robust message builder if we have complex inputs
             messages = await self.build_messages_with_history(
                 question=prompt,
                 context=context or "",
                 chat_history=history or [],
                 system_prompt=system_prompt,
                 images=images
             )
        else:
             messages = [{"role": "user", "content": prompt}]

        stream = await self.client.chat.completions.create(
            model=model or self.model,
            messages=messages, # type: ignore
            temperature=0.3,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


    async def build_messages_with_history(
        self,
        question: str,
        context: str,
        chat_history: List[Dict],
        max_history: int = 8,
        system_prompt: Optional[str] = None,
        images: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Build the full message array including conversation history and images.
        Uses a proper message array for history instead of string concatenation.
        """
        # Base System instructions with Context
        system_base = f"""You are MindX AI, an intelligent research assistant.

You have access to live search results (Context) AND the conversation history.

CONTEXT RULES:
- Always refer to previous messages when answering follow-up questions
- If user says "he", "she", "it", "they" — refer to the conversation to understand who/what
- If user says "tell me more" — expand on the previous answer topic
- If user asks "why" after a fact — explain the fact from previous answer
- Never say "I don't have context from our previous conversation"
- You have full access to everything discussed in this session

Search Results (Context):
{context}"""

        if system_prompt:
            system_msg = system_base + "\n\nSTRICT TASK INSTRUCTIONS:\n" + system_prompt
        else:
            system_msg = system_base

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_msg}
        ]

        # Add recent chat history as individual messages
        if chat_history:
            # Get last N messages (usually 2-4 exchanges)
            visible_history = list(islice(chat_history, max(0, len(chat_history) - max_history), len(chat_history)))
            for m in visible_history:
                # Map various history formats to role/content
                role = str(m.get('role', '')).lower()
                content = str(m.get('content', ''))
                
                # Check for alternative keys used in QA history
                if not content:
                    content = m.get('query') or m.get('role_user') or m.get('answer') or m.get('role_assistant') or ""
                
                if not role:
                    if m.get('query') or m.get('role_user'):
                        role = "user"
                    elif m.get('answer') or m.get('role_assistant'):
                        role = "assistant"
                
                if role in ["user", "assistant"] and content:
                    messages.append({"role": role, "content": content})

        user_content: Any = question
        if images:
            # Multi-modal content format
            user_content = [{"type": "text", "text": question}]
            for b64_img in images:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                })

        messages.append({"role": "user", "content": user_content})

        return messages


    async def generate_chat_completion(
        self,
        messages: List[Dict],
        model: str | None = None,
        temperature: float = 0.3
    ) -> str:
        """Low-level method to generate response from raw messages."""
        response = await self.client.chat.completions.create(
            model=model or self.model,
            messages=messages, # type: ignore
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

