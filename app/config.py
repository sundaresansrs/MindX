import os
from dotenv import load_dotenv

dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)

class Settings:
    # Database configuration
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

    # JWT settings
    SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30

    # LLM and Embedding services
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    COHERE_API_KEY = os.getenv("COHERE_API_KEY")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

settings = Settings()
