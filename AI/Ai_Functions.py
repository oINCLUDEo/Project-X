import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# classifier = pipeline("zero-shot-classification", model="joeddav/xlm-roberta-large-xnli")
embedding_model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

def get_embedding(text: str) -> list[float]:
    """
    Генерирует эмбеддинг для переданного текста.
    """
    return embedding_model.encode([text])[0]


def get_similarity(emb1: list[float], emb2: list[float]) -> float:
    """
    Вычисляет косинусное сходство между двумя эмбеддингами.
    """
    emb1 = np.array(emb1).reshape(1, -1)
    emb2 = np.array(emb2).reshape(1, -1)
    return float(cosine_similarity(emb1, emb2)[0][0])
