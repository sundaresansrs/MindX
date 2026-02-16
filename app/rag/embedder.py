from app.embeddings.model_loader import get_embedding_model

class Embedder:
    def __init__(self):
        self.model = get_embedding_model()

    def embed(self, texts):
        if isinstance(texts, str):
            texts = [texts]
        return self.model.encode(texts, convert_to_tensor=False)
