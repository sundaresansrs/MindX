import requests
import os
from typing import List, Dict, Any

class EmbeddingsService:
    def __init__(self):
        self.jina_api_key = os.getenv("JINA_API_KEY")
        self.cohere_api_key = os.getenv("COHERE_API_KEY")
        self.jina_base_url = "https://api.jina.ai/v1/embeddings"
        self.jina_rerank_url = "https://api.jina.ai/v1/rerank" # Or use Cohere

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Jina AI v2"""
        if not self.jina_api_key:
            # Return dummy embeddings if no key (for testing)
            # 768 dimensions
            return [[0.0] * 768 for _ in texts]
            
        headers = {
            "Authorization": f"Bearer {self.jina_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "input": texts,
            "model": "jina-embeddings-v2-base-en"
        }
        
        try:
            response = requests.post(self.jina_base_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            # Sort by index to ensure order matches input
            sorted_data = sorted(data["data"], key=lambda x: x["index"])
            return [item["embedding"] for item in sorted_data]
        except Exception as e:
            print(f"Error generating embeddings: {e}")
            return [[0.0] * 768 for _ in texts]

    def rerank(self, query: str, documents: List[str]) -> List[Dict[str, Any]]:
        """Rerank documents using Jina Reranker or Cohere"""
        # Placeholder implementation or specific implementation if key exists
        pass
