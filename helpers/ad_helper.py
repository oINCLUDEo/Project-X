import logging
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from database.db_connection import (
    update_post_status,
    get_cluster_id_by_post,
    update_cluster_status,
    get_engagement_score_score_by_post_id,
    get_post_content_by_id,
    insert_ad_decision,
    get_ad_label_for_post,
    increment_pattern_cache
)

logger = logging.getLogger(__name__)

RE_AD_KEYWORDS = re.compile(
    r'\b(скидка|акция|получи предложение|бронируй|только сегодня|новым клиентам|'
    r'закажи|цена|подарок|бесплатно|запишись|промокод|выиграй|скидки|суперцена|распродажа)\b', re.I)
RE_CTA = re.compile(
    r'\b(нажми|подпишись|позвони|забронируй|получи|ответь|зарегистрируйся|купить|заказать|получить предложение|'
    r'переходи|оформи|отправь|заходи|смотри|бронируй|присоединяйся|получить скидку|выиграй)\b', re.I)
RE_HASHTAG_AD = re.compile(r'#реклама|#promo|#advertisement|#ads|#рекламка', re.I)
RE_LINK = re.compile(r'https?://[^\s]+')
RE_CONTACTS = re.compile(r'@\w+|\+?\d[\d\-\s]{7,}', re.I)
RE_PROMO = re.compile(r'промокод\s*[A-Za-z0-9]+', re.I)
RE_PRICE = re.compile(r'(\d+[\s\,]?\d*)\s*(₽|руб\.?|рублей|р\b)', re.I)
RE_PERCENT = re.compile(r'\b-?\d{1,3}\s?%\b')
RE_PLAIN_AD = re.compile(r'\bреклама\b', re.I)

# Часто встречающиеся короткие паттерны для кэша
COMMON_PATTERNS = [
    'скидка', 'акция', 'промокод', 'только сегодня', 'цена', 'бронируй', 'подпишись', 'реклама'
]


def compute_ad_score(post, past_posts_texts, heat_score, channel_trust_level,
                     w1=0.22, w2=0.12, w3=0.18, w4=0.18, w5=0.1, w6=0.1, w7=0.1):
    try:
        text = get_post_content_by_id(post['post_id'])
        text_len = len(text) or 1  # избегаем деления на 0

        # 1. Keyword score
        keyword_count = len(RE_AD_KEYWORDS.findall(text))
        keyword_score = min(keyword_count / 5, 1.0)

        # 2. Link density
        link_count = len(RE_LINK.findall(text))
        link_density = min(link_count / (text_len / 100), 1.0)

        # 3. CTA score
        cta_count = len(RE_CTA.findall(text))
        cta_score = min(cta_count / 3, 1.0)

        # 4. Suspicious engagement
        suspicious_engagement = 1.0 if heat_score > 0.8 and channel_trust_level < 0.3 else 0.0

        # 5. Template similarity
        template_similarity = 0.0
        if past_posts_texts:
            corpus = [text] + past_posts_texts
            vec = TfidfVectorizer().fit_transform(corpus)
            sim_matrix = cosine_similarity(vec[0:1], vec[1:])
            template_similarity = float(np.max(sim_matrix))  # максимальное сходство с прошлым постом

        # 6. Hashtag ad presence
        hashtag_ad_score = 1.0 if RE_HASHTAG_AD.search(text) else 0.0

        # 7. Contacts/promocode/price presence
        contacts_score = 1.0 if (RE_CONTACTS.search(text) or RE_PROMO.search(text) or RE_PRICE.search(text)) else 0.0

        ad_score = (w1 * keyword_score +
                    w2 * link_density +
                    w3 * cta_score +
                    w4 * suspicious_engagement +
                    w5 * template_similarity +
                    w6 * hashtag_ad_score +
                    w7 * contacts_score)

        return ad_score
    except Exception as e:
        logger.error(f"Ошибка в compute_ad_score: {e}")
        return 0.0


def process_post_for_ad_check(post, ad_threshold, channel_trust_level = 0.3, model_pred_func=None, model_version: str | None = None):
    """
    Двухуровневая проверка рекламного контента:
    - Stage 1: быстрый префильтр по правилам и признакам (compute_ad_score)
    - Stage 2: AI-модель (если Stage 1 в серой зоне)

    model_pred_func: Callable[[str], float] возвращает вероятность рекламы [0..1]
    """
    try:
        text = get_post_content_by_id(post['post_id']) or ""
        # предварительное обновление кэша паттернов
        text_lower = text.lower()
        for p in COMMON_PATTERNS:
            if p in text_lower:
                increment_pattern_cache(p)

        # Получаем тексты прошлых постов (placeholder)
        past_posts_texts = []

        # Считаем engagement_score
        engagement_score = get_engagement_score_score_by_post_id(post['post_id'])

        # Явные правила: если встречается слово "Реклама" как отдельное слово — сразу реклама
        if RE_PLAIN_AD.search(text):
            insert_ad_decision(post['post_id'], 1, 1.0, 'ad', None, {'rule': 'plain_ad_word'})
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
            return True

        # Явное сочетание: процент скидки и контакт/бот/ссылка — сильный признак рекламы
        if RE_PERCENT.search(text) and (RE_CONTACTS.search(text) or RE_LINK.search(text) or RE_PROMO.search(text)):
            insert_ad_decision(post['post_id'], 1, 0.95, 'ad', None, {'rule': 'percent_and_contact_or_link'})
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
            return True

        # Stage 1: быстрый score
        ad_score = compute_ad_score(post, past_posts_texts, engagement_score, channel_trust_level)

        # Пороговая логика: ad >= ad_threshold, not_ad <= low_threshold, иначе review
        low_threshold = min(ad_threshold * 0.5, 0.2)
        if ad_score >= ad_threshold:
            decision_stage1 = 'ad'
        elif ad_score <= low_threshold:
            decision_stage1 = 'not_ad'
        else:
            decision_stage1 = 'review'
        insert_ad_decision(post['post_id'], 1, ad_score, decision_stage1, None, {
            'engagement_score': engagement_score,
            'channel_trust_level': channel_trust_level
        })

        # Если ярко выраженная реклама или явно не реклама — завершаем
        if decision_stage1 in ('ad', 'not_ad') or model_pred_func is None:
            is_ad = decision_stage1 == 'ad'
        else:
            # Stage 2: AI-модель
            try:
                ai_prob = float(model_pred_func(text))
            except Exception as e:
                logger.error(f"AI model inference error for post {post['post_id']}: {e}")
                ai_prob = 0.0
            decision_stage2 = 'ad' if ai_prob >= ad_threshold else 'not_ad'
            insert_ad_decision(post['post_id'], 2, ai_prob, decision_stage2, model_version, None)
            is_ad = decision_stage2 == 'ad'

        logger.info(f"[Ad Check] post_id={post['post_id']} stage1_score={ad_score:.3f} -> is_ad={is_ad}")

        # Если есть ручная разметка — переопределяем решение
        label = get_ad_label_for_post(post['post_id'])
        if label:
            is_ad = label['label'] == 'ad'
            logger.info(f"[Ad Check] Overridden by manual label: {label['label']}")

        if is_ad:
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
                logger.info(f"Cluster {cluster_id} status updated to 'ad' due to post {post['post_id']}")
        else:
            logger.info(f"Post {post['post_id']} remains active.")

        return is_ad
    except Exception as e:
        logger.error(f"Ошибка в process_post_for_ad_check: {e}")
        return False


