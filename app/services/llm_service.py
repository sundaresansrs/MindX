import os
from groq import AsyncGroq


class LLMService:
    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set")

        self.client = AsyncGroq(api_key=api_key, timeout=30.0)

        # ✅ CURRENTLY SUPPORTED MODEL
        self.model = "llama-3.1-8b-instant"

    async def generate_response(
        self,
        prompt: str,
        context: str | None = None,
    ) -> str:
        messages = []

        if context:
            messages.append({
                "role": "system",
                "content": (
                    "You are a helpful assistant. "
                    "Use the following context if relevant:\n\n"
                    f"{context}"
                )
            })

        messages.append({
            "role": "user",
            "content": prompt,
        })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
        )

        return response.choices[0].message.content

    async def stream_response(
        self,
        prompt: str,
        context: str | None = None,
    ):
        messages = []
        if context:
            messages.append({
                "role": "system",
                "content": f"You are a helpful assistant. Use this context if relevant:\n\n{context}"
            })
        
        messages.append({"role": "user", "content": prompt})

        stream = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.3,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

