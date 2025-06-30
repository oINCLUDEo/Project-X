import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from database.db_connection import get_latest_embeddings

# classifier = pipeline("zero-shot-classification", model="joeddav/xlm-roberta-large-xnli")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Функция для генерации эмбеддингов
def get_embedding(text: str):
    return embedding_model.encode([text])[0]


def is_similar_to_existing(new_emb: str):
    max_similarity = 0
    for old_emb in get_latest_embeddings(100):
        similarity = cosine_similarity([np.array(new_emb).reshape(-1)],
                                       [np.array(old_emb).reshape(-1)])
        if max_similarity < similarity:
            max_similarity = similarity
        if max_similarity > 0.74:
            return True, max_similarity # Отправляем информацию, что посты схожи
    return False, max_similarity
