"""
Модуль для персонализации рекомендаций новостей.
Вычисляет персональные скоринги для кластеров на основе предпочтений пользователя.
"""

import logging
import math
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from database.db_connection import (
    get_user_category_weights,
    get_cluster_categories,
    get_user_preferred_embedding,
    get_cluster_embedding,
    get_user_channel_preferences,
    get_cluster_channels,
    get_user_activity_stats,
    get_cluster_created_at,
    get_user_liked_clusters,
    get_system_param
)
from helpers.helpers import sigmoid

logger = logging.getLogger(__name__)


def calculate_personal_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет персональный score кластера для пользователя.
    
    Компоненты скоринга:
    1. Категорийный вес (30%) - насколько пользователь интересуется категориями кластера
    2. Фидбек score (25%) - на основе истории лайков/дизлайков похожих новостей
    3. Канальная репутация (15%) - предпочтения пользователя к каналам в кластере
    4. Временная релевантность (15%) - свежесть новости и время активности пользователя
    5. Content similarity (15%) - схожесть с понравившимися пользователю новостями
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя (user_id в БД, не user_tg_id)
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # 1. Категорийный вес (30%)
        category_weight_score = get_category_weight_score(cluster_id, user_id)
        
        # 2. Фидбек score (25%)
        feedback_score = get_feedback_score(cluster_id, user_id)
        
        # 3. Канальная репутация (15%)
        channel_reputation_score = get_channel_reputation_score(cluster_id, user_id)
        
        # 4. Временная релевантность (15%)
        temporal_score = get_temporal_relevance_score(cluster_id, user_id)
        
        # 5. Content similarity (15%)
        content_similarity_score = get_content_similarity_score(cluster_id, user_id)
        
        # Веса компонентов (настраиваются через системные параметры)
        try:
            w_category = float(get_system_param('personal_score_weight_category', '0.3') or '0.3')
            w_feedback = float(get_system_param('personal_score_weight_feedback', '0.25') or '0.25')
            w_channel = float(get_system_param('personal_score_weight_channel', '0.15') or '0.15')
            w_temporal = float(get_system_param('personal_score_weight_temporal', '0.15') or '0.15')
            w_content = float(get_system_param('personal_score_weight_content', '0.15') or '0.15')
        except Exception as e:
            logger.warning(f"Ошибка получения весов для personal score: {e}, используем значения по умолчанию")
            w_category, w_feedback, w_channel, w_temporal, w_content = 0.3, 0.25, 0.15, 0.15, 0.15
        
        # Нормализуем веса (на случай если сумма не равна 1.0)
        total_weight = w_category + w_feedback + w_channel + w_temporal + w_content
        if total_weight > 0:
            w_category /= total_weight
            w_feedback /= total_weight
            w_channel /= total_weight
            w_temporal /= total_weight
            w_content /= total_weight
        
        # Комбинированный score
        personal_score = (
            category_weight_score * w_category +
            feedback_score * w_feedback +
            channel_reputation_score * w_channel +
            temporal_score * w_temporal +
            content_similarity_score * w_content
        )
        
        # Ограничиваем значение от 0 до 1
        personal_score = max(0.0, min(1.0, personal_score))
        
        logger.debug(
            f"Personal score для user={user_id}, cluster={cluster_id}: "
            f"{personal_score:.3f} (cat={category_weight_score:.3f}, "
            f"fb={feedback_score:.3f}, ch={channel_reputation_score:.3f}, "
            f"tmp={temporal_score:.3f}, sim={content_similarity_score:.3f})"
        )
        
        return personal_score
        
    except Exception as e:
        logger.error(f"Ошибка вычисления personal score для user={user_id}, cluster={cluster_id}: {e}", exc_info=True)
        # Возвращаем нейтральный score в случае ошибки
        return 0.5


def get_category_weight_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет score на основе весов категорий пользователя.
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # Получаем категории кластера
        cluster_categories = get_cluster_categories(cluster_id)
        if not cluster_categories:
            return 0.5  # Нейтральный score если категории неизвестны
        
        # Получаем веса категорий пользователя
        user_weights = get_user_category_weights(user_id)
        if not user_weights:
            return 0.5  # Нейтральный score если нет данных о предпочтениях
        
        # Вычисляем средний вес категорий кластера
        weights_sum = 0.0
        weights_count = 0
        
        for category_id in cluster_categories:
            if category_id in user_weights:
                weight = user_weights[category_id]
                weights_sum += weight
                weights_count += 1
        
        if weights_count == 0:
            return 0.5  # Нет совпадений по категориям
        
        avg_weight = weights_sum / weights_count
        
        # Нормализуем вес: 0.0 -> 0.0, 1.0 -> 0.5, 2.0 -> 1.0
        # Используем сигмоиду для плавного перехода
        normalized_score = sigmoid((avg_weight - 1.0) * 3.0)  # Масштабируем для лучшей чувствительности
        
        return normalized_score
        
    except Exception as e:
        logger.error(f"Ошибка вычисления category weight score: {e}", exc_info=True)
        return 0.5


def get_feedback_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет score на основе истории фидбека пользователя.
    
    Ищет похожие кластеры, которые пользователь лайкнул/дизлайкнул,
    и использует их для предсказания интереса к текущему кластеру.
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # Получаем понравившиеся пользователю кластеры
        liked_clusters = get_user_liked_clusters(user_id, limit=50)
        if not liked_clusters:
            return 0.5  # Нейтральный score если нет истории
        
        # Получаем embedding текущего кластера
        cluster_embedding = get_cluster_embedding(cluster_id)
        if not cluster_embedding:
            return 0.5
        
        # Вычисляем схожесть с понравившимися кластерами
        similarities = []
        for liked_cluster_id, liked_embedding in liked_clusters:
            if liked_embedding:
                similarity = cosine_similarity(cluster_embedding, liked_embedding)
                similarities.append(similarity)
        
        if not similarities:
            return 0.5
        
        # Используем среднюю схожесть, взвешенную по свежести лайка
        # (более свежие лайки имеют больший вес)
        avg_similarity = sum(similarities) / len(similarities)
        
        # Применяем сигмоиду для нормализации
        feedback_score = sigmoid((avg_similarity - 0.5) * 4.0)
        
        return feedback_score
        
    except Exception as e:
        logger.error(f"Ошибка вычисления feedback score: {e}", exc_info=True)
        return 0.5


def get_channel_reputation_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет score на основе репутации каналов в кластере для пользователя.
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # Получаем каналы в кластере
        cluster_channels = get_cluster_channels(cluster_id)
        if not cluster_channels:
            return 0.5
        
        # Получаем предпочтения пользователя к каналам
        user_preferences = get_user_channel_preferences(user_id)
        if not user_preferences:
            return 0.5
        
        # Вычисляем средний preference_score каналов в кластере
        preferences_sum = 0.0
        preferences_count = 0
        
        for channel_tg_id in cluster_channels:
            if channel_tg_id in user_preferences:
                preference = user_preferences[channel_tg_id]
                preferences_sum += preference
                preferences_count += 1
        
        if preferences_count == 0:
            return 0.5  # Нет данных о предпочтениях к каналам кластера
        
        avg_preference = preferences_sum / preferences_count
        return avg_preference
        
    except Exception as e:
        logger.error(f"Ошибка вычисления channel reputation score: {e}", exc_info=True)
        return 0.5


def get_temporal_relevance_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет score на основе временной релевантности.
    
    Учитывает:
    - Свежесть кластера (более свежие новости имеют больший вес)
    - Время активности пользователя (новости отправляются в оптимальное время)
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # Получаем время создания кластера
        cluster_created_at = get_cluster_created_at(cluster_id)
        if not cluster_created_at:
            return 0.5
        
        # Получаем статистику активности пользователя
        activity_stats = get_user_activity_stats(user_id)
        if not activity_stats:
            return 0.5
        
        # Вычисляем свежесть кластера (в часах)
        now = datetime.now(cluster_created_at.tzinfo)
        age_hours = (now - cluster_created_at).total_seconds() / 3600.0
        
        # Свежесть: новости младше 24 часов имеют высокий score
        # Используем экспоненциальное затухание
        freshness_score = math.exp(-age_hours / 24.0)
        
        # Проверяем соответствие времени активности пользователя
        current_hour = now.hour
        avg_active_hour = activity_stats.get('avg_active_hour')
        
        if avg_active_hour is not None:
            # Вычисляем разницу во времени (учитываем циклический характер часов)
            hour_diff = min(abs(current_hour - avg_active_hour), 24 - abs(current_hour - avg_active_hour))
            # Чем ближе к времени активности, тем выше score
            time_match_score = 1.0 - (hour_diff / 12.0)  # Максимальная разница 12 часов
            time_match_score = max(0.0, min(1.0, time_match_score))
        else:
            time_match_score = 0.5
        
        # Комбинируем свежесть и соответствие времени
        temporal_score = (freshness_score * 0.7 + time_match_score * 0.3)
        
        return temporal_score
        
    except Exception as e:
        logger.error(f"Ошибка вычисления temporal relevance score: {e}", exc_info=True)
        return 0.5


def get_content_similarity_score(cluster_id: int, user_id: int) -> float:
    """
    Вычисляет score на основе схожести контента с предпочтениями пользователя.
    
    Использует embedding кластера и предпочтительный embedding пользователя
    (средний embedding понравившихся новостей).
    
    Args:
        cluster_id: ID кластера
        user_id: ID пользователя
        
    Returns:
        float: Score от 0 до 1
    """
    try:
        # Получаем embedding кластера
        cluster_embedding = get_cluster_embedding(cluster_id)
        if not cluster_embedding:
            return 0.5
        
        # Получаем предпочтительный embedding пользователя
        user_embedding = get_user_preferred_embedding(user_id)
        if not user_embedding:
            return 0.5  # Нет данных о предпочтениях пользователя
        
        # Вычисляем косинусную схожесть
        similarity = cosine_similarity(cluster_embedding, user_embedding)
        
        # Нормализуем: косинусная схожесть обычно в диапазоне [-1, 1],
        # но для embedding новостей обычно в [0, 1]
        # Применяем сигмоиду для улучшения распределения
        content_score = sigmoid((similarity - 0.5) * 4.0)
        
        return content_score
        
    except Exception as e:
        logger.error(f"Ошибка вычисления content similarity score: {e}", exc_info=True)
        return 0.5


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Вычисляет косинусную схожесть между двумя векторами.
    
    Args:
        vec1: Первый вектор
        vec2: Второй вектор
        
    Returns:
        float: Косинусная схожесть от -1 до 1
    """
    if len(vec1) != len(vec2):
        logger.warning(f"Размеры векторов не совпадают: {len(vec1)} != {len(vec2)}")
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(a * a for a in vec2))
    
    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0
    
    return dot_product / (magnitude1 * magnitude2)


def calculate_priority(personal_score: float, cluster_score: float, base_priority: int = 5) -> int:
    """
    Вычисляет приоритет новости для очереди на основе personal_score и cluster_score.
    
    Args:
        personal_score: Персональный score для пользователя (0-1)
        cluster_score: Общий score кластера (0-1)
        base_priority: Базовый приоритет (по умолчанию 5)
        
    Returns:
        int: Приоритет от 1 до 10, где 10 - высший приоритет
    """
    # Комбинируем personal_score и cluster_score
    # personal_score имеет больший вес для персональной очереди
    combined_score = personal_score * 0.7 + cluster_score * 0.3
    
    # Преобразуем score в приоритет (1-10)
    # Высокий score -> высокий приоритет
    priority = int(base_priority + (combined_score - 0.5) * 10)
    priority = max(1, min(10, priority))  # Ограничиваем диапазон
    
    return priority

