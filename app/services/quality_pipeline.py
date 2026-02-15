
from app.services.llm_service import LLMService
from app.services.embedding_service import EmbeddingService
from app.services.vector_service import VectorService
from app.services.rerank_service import RerankService
from app.utils.query_expansion import QueryExpansion

class QualityPipeline:
    def __init__(self):
        self.llm_service = LLMService()
        self.embedding_service = EmbeddingService()
        self.vector_service = VectorService()
        self.rerank_service = RerankService()
        self.query_expansion = QueryExpansion()

    def run(self, query: str) -> str:
        # 1. Expand the query
        expanded_queries = self.query_expansion.expand(query)

        # 2. Generate embeddings for all queries
        all_queries = [query] + expanded_queries
        query_embeddings = self.embedding_service.generate_embeddings(all_queries)

        # 3. Search for relevant documents
        retrieved_docs = []
        for embedding in query_embeddings:
            retrieved_docs.extend(self.vector_service.search(embedding))
        
        # 4. Rerank the documents
        reranked_docs = self.rerank_service.rerank(query, retrieved_docs)

        # 5. Generate the final answer
        context = "\n".join(reranked_docs)
        prompt = f"Given the following context:\n{context}\n\nAnswer the question: {query}"
        answer = self.llm_service.generate_text(prompt)

        return answer
