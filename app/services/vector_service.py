
import numpy as np

class VectorService:
    def __init__(self):
        self.vector_store = {}

    def add_vector(self, vector_id: str, vector: list[float]):
        self.vector_store[vector_id] = np.array(vector)

    def search(self, query_vector: list[float], top_n: int = 5) -> list[str]:
        query_vector = np.array(query_vector)
        similarities = {
            vector_id: self._cosine_similarity(query_vector, vector)
            for vector_id, vector in self.vector_store.items()
        }
        sorted_vectors = sorted(similarities.items(), key=lambda item: item[1], reverse=True)
        return [vector_id for vector_id, _ in sorted_vectors[:top_n]]

    def _cosine_similarity(self, vec1, vec2):
        return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
