import asyncio
import sys
import os
import json
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app.services.llm_service import LLMService
from app.services.quality_pipeline import QualityPipeline

async def main():
    llm = LLMService()
    
    question = "What are the health benefits of green tea?"
    answer = """
    Green tea is rich in antioxidants, particularly catechins like EGCG. 
    Studies suggest it may improve brain function, aid fat loss, and lower the risk of cancer.
    It also contains L-theanine, which promotes relaxation without drowsiness.
    """
    
    prompt = QualityPipeline.FOLLOWUP_SYSTEM
    
    print(f"Testing Follow-up Generation for:\nQ: {question}\nA: {answer}\n")
    
    try:
        response = await llm.generate_response(
            prompt=f"Q: {question}\nA: {answer}",
            system_prompt=prompt,
            model=llm.FAST_MODEL
        )
        print("Raw Response:", response)
        
        # Parse JSON
        followups = json.loads(response.replace('```json', '').replace('```', '').strip())
        print("\nGenerated Follow-ups:")
        for i, q in enumerate(followups):
            print(f"{i+1}. {q}")
            
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
