from sentence_transformers import SentenceTransformer
from transformers import pipeline

# Функция для генерации эмбеддингов
def get_embedding(text: str):
    # Загружаем модель для эмбеддингов
    embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

    return embedding_model.encode([text])[0]


# Функция классификации текста по категориям
def classify_post(text: str):
    classifier = pipeline("zero-shot-classification", model="joeddav/xlm-roberta-large-xnli")

    categories = ["Политика", "Спорт", "Технологии", "Экономика", "Здоровье", "Город"]
    result = classifier(text, candidate_labels=categories, multi_label=True)

    return result

