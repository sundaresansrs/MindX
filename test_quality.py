import asyncio
import re
from app.services.quality_pipeline import QualityPipeline
from app.database import get_db
from app.models.user import User

async def test_quality():
    print("Initializing Quality Pipeline...")
    # Mock user
    user = User(id=1, email="test@example.com", account_type="personal")
    
    # Initialize pipeline
    db_gen = get_db()
    db = next(db_gen)
    pipeline = QualityPipeline(db)
    
    queries = [
        "Explain quantum physics", 
        "What are the key principles of leadership?"
    ]
    
    for query in queries:
        print(f"\n\n--- Testing Query: {query} ---")
        print("Streaming response...")
        
        full_response = ""
        citation_leaked = False
        
        async for chunk in pipeline.stream_query(query, user, session_id="test_quality_session"):
            if chunk["type"] == "token":
                content = chunk["content"]
                full_response += content
                print(content, end="", flush=True)
                
                # Real-time check for leakage
                if re.search(r'\[\d+\]', content):
                    citation_leaked = True

        with open("quality_report.txt", "a", encoding="utf-8") as f:
            f.write(f"\n\n--- Query: {query} ---\n{full_response}\n")
            
            f.write("\n--- Quality Check ---\n")
            # 1. Check for Citation Leakage
            if citation_leaked or re.search(r'\[\d+\]', full_response):
                f.write("❌ FAILURE: Citation markers [N] found in output.\n")
            else:
                f.write("✅ SUCCESS: No citation markers found.\n")
                
            # 2. Check for Negative Answers
            negative_phrases = [
                "I did not find information",
                "search results don't contain",
                "based on search results",
                "according to the provided context"
            ]
            if any(phrase.lower() in full_response.lower() for phrase in negative_phrases):
                 f.write("❌ FAILURE: Negative/Hedging phrase found.\n")
            else:
                 f.write("✅ SUCCESS: No negative phrases found.\n")

            # 3. Check for Structure (Headers)
            if "##" in full_response:
                 f.write("✅ SUCCESS: Markdown headers detected.\n")
            else:
                 f.write("⚠️ WARNING: No markdown headers (##) found. (Might be short answer?)\n")

            # 4. Check for Bullets
            if "- **" in full_response or "• **" in full_response:
                 f.write("✅ SUCCESS: Bullet points with bold terms detected.\n")
            else:
                 f.write("⚠️ WARNING: No standard bullet points found.\n")

    print("\nTest Complete.")

if __name__ == "__main__":
    asyncio.run(test_quality())
