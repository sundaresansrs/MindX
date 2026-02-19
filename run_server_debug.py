import uvicorn
import os
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    # Check if key is set
    if not os.environ.get("GROQ_API_KEY"):
        print("Warning: GROQ_API_KEY not found in environment or .env")
    
    print("Starting MindX Server on port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, timeout_keep_alive=45)
