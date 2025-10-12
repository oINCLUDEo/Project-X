import logging
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import joblib
import os
from database.db_connection import upsert_model_version
from sklearn.metrics.pairwise import cosine_similarity

logger = logging.getLogger(__name__)

embedding_model = SentenceTransformer("paraphrase-multilingual-mpnet-base-v2")

# Легкая классификационная модель для рекламы (можно заменить на вашу)
_AD_MODEL_NAME = "cointegrated/rubert-tiny2-char"
try:
    ad_tokenizer = AutoTokenizer.from_pretrained(_AD_MODEL_NAME)
    ad_model = AutoModelForSequenceClassification.from_pretrained(
        _AD_MODEL_NAME, num_labels=2
    )
    ad_model.eval()
    AD_MODEL_VERSION = _AD_MODEL_NAME
except Exception as e:
    ad_tokenizer = None
    ad_model = None
    AD_MODEL_VERSION = "none"
    logger.error(f"[AI] Ошибка загрузки модели для идентификации рекламы {_AD_MODEL_NAME}: {e}")

# Альтернативная лёгкая модель (TF-IDF + LR), загружаемая из файла
_CLASSIC_MODEL_PATH = os.getenv('AD_CLASSIC_MODEL_PATH', 'models/ad_classifier.pkl')
classic_model = None
if os.path.exists(_CLASSIC_MODEL_PATH):
    try:
        classic_model = joblib.load(_CLASSIC_MODEL_PATH)
        upsert_model_version('ad_classifier', 'classic_file')
        logger.info(f"Классическая модель успешно загружена из {_CLASSIC_MODEL_PATH}")
    except Exception as e:
        logger.error(f"Ошибка загрузки классической модели: {e}")
        classic_model = None


def get_embedding(text: str) -> list[float]:
    """
    Генерирует эмбеддинг для переданного текста.
    """
    return embedding_model.encode([text])[0].tolist()


def get_similarity(emb1: list[float], emb2: list[float]) -> float:
    """
    Вычисляет косинусное сходство между двумя эмбеддингами.
    """
    emb1 = np.array(emb1).reshape(1, -1)
    emb2 = np.array(emb2).reshape(1, -1)
    return float(cosine_similarity(emb1, emb2)[0][0])


def predict_ad_probability(text: str) -> float:
    """
    Возвращает вероятность того, что текст является рекламой [0..1].
    В качестве заглушки используется классификатор; при отсутствии модели вернёт 0.0.
    """
    if not text:
        return 0.0
    if ad_model is None or ad_tokenizer is None:
        # fallback на классическую модель
        if classic_model is not None:
            try:
                prob = float(classic_model.predict_proba([text])[0][1])
                return prob
            except Exception as predict_error:
                logger.warning(f"Ошибка предсказания классической модели: {predict_error}")
                return 0.0
        return 0.0
    with torch.no_grad():
        tokens = ad_tokenizer(
            text,
            truncation=True,
            max_length=256,
            padding=True,
            return_tensors="pt"
        )
        outputs = ad_model(**tokens)
        logits = outputs.logits
        probs = torch.softmax(logits, dim=-1).cpu().numpy()[0]
        # предполагаем, что индекс 1 соответствует классу 'ad'
        return float(probs[1])
