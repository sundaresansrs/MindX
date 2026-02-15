import os
from groq import Groq
from app.config import settings

class LLMService:
    def __init__(self):
        self.client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    def generate_text(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"Error: {str(e)}"
