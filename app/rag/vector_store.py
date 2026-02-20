import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

class VectorStore:
    def __init__(self):
        self.embeddings = []
        self.texts = []

    def add(self, texts, embeddings):
        self.texts.extend(texts)
        self.embeddings.extend(embeddings)

    def search(self, query_embedding, top_k=3):
        if not self.embeddings:
            return []

        sims = cosine_similarity(
            np.array([query_embedding]), np.array(self.embeddings)
        )[0]

        top_indices = np.argsort(sims)[::-1][:top_k]

        return [self.texts[i] for i in top_indices]
