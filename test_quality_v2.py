import os
import sys
import asyncio
import re
import logging

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.quality_pipeline import QualityPipeline

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

async def test_quality():
    print("\n========================================")
    print("MINDX v2.0 QUALITY VERIFICATION")
    print("========================================\n")
    
    pipeline = QualityPipeline(db=None) 
    
    # ---------------------------------------------------------
    # TEST 1: Structure & Bolding
    # ---------------------------------------------------------
    print("> TEST 1: Structure & Bolding ('Explain quantum physics')")
    query = "Explain quantum physics"
    
    # Mock user object
    class MockUser:
        id = "test_user"
    
    result = await pipeline.process_query(
        query=query, 
        user=MockUser(),
        use_search=True
    )
    
    answer = result.get('answer', '')
    print(f"\n[Answer Preview]:\n{answer[:600]}...\n")
    
    # Verification Logic
    errors = []
    if "**" not in answer: errors.append("FAIL: No bolding found (**)")
    
    # Check for any markdown header (##, ###, ####)
    if not re.search(r'^#{2,4}\s', answer, re.MULTILINE):
        errors.append("FAIL: No headers found (##, ###, or ####)")
    
    # Strict citation check [1]
    if re.search(r'\[\d+\]', answer):
        errors.append("FAIL: Citations [N] found in output!")
            
    if not errors:
        print("PASS STRUCTURE: Bolding, Headers, No Citations")
    else:
        print("FAIL STRUCTURE:")
        for e in errors: print(f"  - {e}")

    # ---------------------------------------------------------
    # TEST 2: Spam Filter
    # ---------------------------------------------------------
    print("\n> TEST 2: Spam Filtering ('key principles of effective leadership')")
    
    # This query historically triggered Chinese spam results
    query_2 = "key principles of effective leadership"
    result_2 = await pipeline.process_query(
        query=query_2, 
        user=MockUser(),
        use_search=True
    )
    
    sources = result_2.get('sources', [])
    spam_domains = ['csdn.net', 'zhihu.com', 'baidu.com', 'jianshu.com']
    found_spam = [s['url'] for s in sources if any(d in s['url'] for d in spam_domains)]
    
    if found_spam:
        print(f"FAIL FILTER: Found spam domains: {found_spam}")
    else:
        print(f"PASS FILTER: No blocked domains in {len(sources)} sources.")

if __name__ == "__main__":
    asyncio.run(test_quality())
