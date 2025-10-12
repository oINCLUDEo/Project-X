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
    increment_pattern_cache,
    get_channel_reputation_by_post_id
)

logger = logging.getLogger(__name__)

RE_AD_KEYWORDS = re.compile(
    r'\b(скидка|акция|получи предложение|бронируй|только сегодня|новым клиентам|'
    r'закажи|цена|подарок|бесплатно|запишись|промокод|выиграй|скидки|суперцена|распродажа)\b', re.I)
RE_CTA = re.compile(
    r'\b(нажми|подпишись|позвони|забронируй|получи|ответь|зарегистрируйся|купить|заказать|получить предложение|'
    r'переходи|оформи|отправь|заходи|смотри|бронируй|присоединяйся|получить скидку|выиграй)\b', re.I)
RE_HASHTAG_AD = re.compile(r'#реклама|#promo|#advertisement|#ads|#рекламка', re.I)
RE_LINK = re.compile(r'https?://\S+')
RE_HREF = re.compile(r'href\s*=\s*"(https?://[^\"]+)"', re.I)
RE_ERID = re.compile(r'\berid\s*[:=]\s*[A-Za-z0-9\-]{6,}', re.I)
RE_CONTACTS = re.compile(r'@\w+|\+?\d[\d\-\s]{7,}', re.I)
RE_PROMO = re.compile(r'промокод\s*[A-Za-z0-9]+', re.I)
RE_PRICE = re.compile(r'(\d+[\s,]?\d*)\s*(₽|руб\.?|рублей|р\b)', re.I)
# Проценты вида -40%, 40%, допустимы разные тире; избегаем \b, чтобы ловить начало со знака
RE_PERCENT = re.compile(r'(?<!\w)[\-−–—]?\d{1,3}\s?%(?!\w)')
# Маркер рекламной пометки отдельной строкой/в скобках; допускаем ссылку в скобках после точки
RE_AD_TAG_LINE = re.compile(
    r'(^|\n|\()\s*(реклама|advertisement|ads|promo)\s*([.!:,])?(\s*\(https?://[^\s)]+\))?\s*$',
    re.I | re.M
)
RE_AD_LEGAL = re.compile(r'(^|\n)\s*реклама\s*[,.:!-]\s*(ООО|ИП|АО|ОАО|ПАО)\b', re.I)

# Часто встречающиеся короткие паттерны для кэша
COMMON_PATTERNS = [
    'скидка', 'акция', 'промокод', 'только сегодня', 'цена', 'бронируй', 'подпишись', 'реклама'
]

# Розыгрыши/конкурсы
RE_GIVEAWAY = re.compile(r'\b(розыгрыш|разыгрываем|конкурс|гив)\b', re.I)
RE_COMMENT = re.compile(r'комментар(ий|иях|ии|ев)', re.I)


def compute_ad_score(post, past_posts_texts, heat_score, channel_trust_level,
                     w1=0.22, w2=0.12, w3=0.18, w4=0.18, w5=0.1, w6=0.1, w7=0.1):
    try:
        text = get_post_content_by_id(post['post_id']) or ""
        text_len = max(1, len(text))  # избегаем деления на 0

        # 1. Оценка по ключевым словам
        keyword_count = len(RE_AD_KEYWORDS.findall(text))
        keyword_score = min(keyword_count / 5, 1.0)
        # 2. Плотность ссылок
        link_count = len(RE_LINK.findall(text))
        link_density = min(link_count / (text_len / 100), 1.0)
        # 3. Оценка призывов к действию (CTA)
        cta_count = len(RE_CTA.findall(text))
        cta_score = min(cta_count / 3, 1.0)
        # 4. Подозрительная активность, с учётом репутации источника
        channel_rep = get_channel_reputation_by_post_id(post['post_id'])
        trust = max(channel_trust_level, channel_rep)
        suspicious_engagement = 1.0 if heat_score > 0.8 and trust < 0.3 else 0.0
        # 5. Схожесть с шаблонами
        template_similarity = 0.0
        if past_posts_texts:
            corpus = [text] + past_posts_texts
            vec = TfidfVectorizer().fit_transform(corpus)
            sim_matrix = cosine_similarity(vec[0:1], vec[1:])
            template_similarity = float(np.max(sim_matrix))  # максимальное сходство с прошлым постом
        # 6. Наличие рекламных хэштегов
        hashtag_ad_score = 1.0 if RE_HASHTAG_AD.search(text) else 0.0
        # 7. Наличие контактов/промокодов/цен
        contacts_score = 1.0 if (RE_CONTACTS.search(text) or RE_PROMO.search(text) or RE_PRICE.search(text)) else 0.0
        # Итоговый рекламный score
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
    - Этап 1: быстрый фильтр по правилам и признакам (compute_ad_score)
    - Этап 2: AI-модель (если Stage 1 в серой зоне)

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

        # Явные правила: рекламная пометка отдельной строкой/в скобках 
        # или HTML-якорь с текстом "Реклама." / "Реклама" → сразу реклама
        if RE_AD_TAG_LINE.search(text) or re.search(r'>\s*реклама[.,!]?\s*<', text, re.I) or RE_AD_LEGAL.search(text):
            insert_ad_decision(post['post_id'], 1, 1.0, 'ad', None, {'rule': 'ad_tag_line'})
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
            return True

        # ERID или #реклама — однозначные индикаторы рекламы в РФ
        if RE_ERID.search(text) or RE_HASHTAG_AD.search(text):
            insert_ad_decision(post['post_id'], 1, 1.0, 'ad', None, {'rule': 'erid_or_hashtag'})
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
            return True

        # Явные сочетания: проценты скидок с коммерческими маркерами ИЛИ розыгрыши с условиями участия
        link_present = bool(RE_LINK.search(text) or RE_HREF.search(text))
        # ERID в href
        if not RE_ERID.search(text):
            for href in RE_HREF.findall(text):
                if RE_ERID.search(href):
                    insert_ad_decision(post['post_id'], 1, 1.0, 'ad', None, {'rule': 'erid_in_href'})
                    update_post_status(post['post_id'], "ad")
                    cluster_id = get_cluster_id_by_post(post['post_id'])
                    if cluster_id:
                        update_cluster_status(cluster_id, "ad")
                    return True
        if RE_PERCENT.search(text) and (RE_CONTACTS.search(text) or link_present or RE_PROMO.search(text)):
            insert_ad_decision(post['post_id'], 1, 0.95, 'ad', None, {'rule': 'percent_and_contact_or_link'})
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
            return True

        if RE_GIVEAWAY.search(text) and (RE_COMMENT.search(text) or RE_CONTACTS.search(text) or link_present):
            insert_ad_decision(post['post_id'], 1, 0.9, 'ad', None, {'rule': 'giveaway_and_call_to_action'})
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
                logger.error(f"Ошибка вывода AI-модели для поста {post['post_id']}: {e}")
                ai_prob = 0.0
            decision_stage2 = 'ad' if ai_prob >= ad_threshold else 'not_ad'
            insert_ad_decision(post['post_id'], 2, ai_prob, decision_stage2, model_version, None)
            is_ad = decision_stage2 == 'ad'

        logger.debug(f"[Ad Check] post_id={post['post_id']} stage1_score={ad_score:.3f} -> is_ad={is_ad}")

        # Если есть ручная разметка — переопределяем решение
        label = get_ad_label_for_post(post['post_id'])
        if label:
            is_ad = label['label'] == 'ad'
            logger.info(f"[Ad Check] Переопределено ручной разметкой: {label['label']}")

        if is_ad:
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
                logger.info(f"[Ad Check] Статус кластера {cluster_id} обновлён на 'ad' из-за поста {post['post_id']}")
        else:
            logger.debug(f"[Ad Check] Пост {post['post_id']} остаётся активным.")

        return is_ad
    except Exception as e:
        logger.error(f"Ошибка в process_post_for_ad_check: {e}")
        return False


