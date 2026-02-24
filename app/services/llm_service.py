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
        Uses the 'Enhanced User Prompt' pattern: Research results are injected 
        into the final user message for grounding, keeping history clean.
        """
        # 1. Base Identity System Prompt
        system_msg = "You are MindX AI, an intelligent research assistant."
        if system_prompt:
            system_msg += f"\n\nSTRICT TASK INSTRUCTIONS:\n{system_prompt}"
        
        # Add basic context awareness rules to system message
        system_msg += (
            "\n\nCONVERSATION RULES:\n"
            "- Refer to previous turns to resolve pronouns (he, she, it, they).\n"
            "- Provide citations in [1], [2] format based on the research results provided in the user prompt.\n"
            "- Be concise and professional."
        )

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_msg}
        ]

        # 2. Add recent chat history (ordered)
        if chat_history:
            visible_history = list(islice(chat_history, max(0, len(chat_history) - max_history), len(chat_history)))
            for m in visible_history:
                role = str(m.get('role', '')).lower()
                content = str(m.get('content', ''))
                
                if not content:
                    content = m.get('query') or m.get('role_user') or m.get('answer') or m.get('role_assistant') or ""
                
                if not role:
                    if m.get('query') or m.get('role_user'): role = "user"
                    elif m.get('answer') or m.get('role_assistant'): role = "assistant"
                
                if role in ["user", "assistant"] and content:
                    messages.append({"role": role, "content": content})

        # 3. Final Grounded User Message (Question + Context)
        enhanced_user_content = question
        if context:
            enhanced_user_content = (
                f"### Research Results\n{context}\n\n"
                f"### User Question\n{question}\n\n"
                f"Instructions: Use the research results to provide a comprehensive answer with citations. "
                f"If the results don't contain enough info, say so."
            )

        # 4. Handle vision/images if provided
        user_content: Any = enhanced_user_content
        if images:
            user_content_list: List[Dict[str, Any]] = [{"type": "text", "text": enhanced_user_content}]
            for b64_img in images:
                user_content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}
                })
            user_content = user_content_list

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

