import logging
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from database.db_connection import update_post_status, get_cluster_id_by_post, update_cluster_status, \
    get_engagement_score_score_by_post_id, get_post_content_by_id

logger = logging.getLogger(__name__)

RE_AD_KEYWORDS = re.compile(
    r'\b(скидка|акция|получи предложение|бронируй|только сегодня|новым клиентам|'
    r'закажи|цена|подарок|бесплатно|запишись|промокод|выиграй|скидки|суперцена|распродажа)\b', re.I)
RE_CTA = re.compile(
    r'\b(нажми|подпишись|позвони|забронируй|получи|ответь|зарегистрируйся|купить|заказать|получить предложение|'
    r'переходи|оформи|отправь|заходи|смотри|бронируй|присоединяйся|получить скидку|выиграй)\b', re.I)
RE_HASHTAG_AD = re.compile(r'#реклама|#promo|#advertisement|#ads|#рекламка', re.I)
RE_LINK = re.compile(r'https?://[^\s]+')


def compute_ad_score(post, past_posts_texts, heat_score, channel_trust_level,
                     w1=0.25, w2=0.15, w3=0.2, w4=0.2, w5=0.1, w6=0.1):
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

        ad_score = (w1 * keyword_score +
                    w2 * link_density +
                    w3 * cta_score +
                    w4 * suspicious_engagement +
                    w5 * template_similarity +
                    w6 * hashtag_ad_score)

        return ad_score
    except Exception as e:
        logger.error(f"Ошибка в compute_ad_score: {e}")
        return 0.0


def process_post_for_ad_check(post, ad_threshold, channel_trust_level = 0.3):
    # Получаем тексты прошлых постов (пример, нужно реализовать)
    try:
        past_posts_texts = []  # функция для получения списка текстов прошлых постов

        # Считаем engagement_score
        engagement_score = get_engagement_score_score_by_post_id(post['post_id'])  # функция должна вернуть float

        # Считаем ad_score с нужными параметрами
        ad_score = compute_ad_score(post,
            past_posts_texts,
            engagement_score,
            channel_trust_level)

        is_ad = ad_score > ad_threshold

        logger.info(
            f"[Ad Check] post_id={post['post_id']} ad_score={ad_score:.3f} | "
            f"engagement_score={engagement_score:.2f}, channel_trust_level={channel_trust_level:.2f}, "
            f"is_ad={is_ad}"
        )

        if is_ad:
            update_post_status(post['post_id'], "ad")
            cluster_id = get_cluster_id_by_post(post['post_id'])
            if cluster_id:
                update_cluster_status(cluster_id, "ad")
                logger.info(f"Cluster {cluster_id} status updated to 'ad' due to post {post['post_id']}")
        else:
            logger.info(f"Post {post['post_id']} marked as active.")

        return is_ad
    except Exception as e:
        logger.error(f"Ошибка в process_post_for_ad_check: {e}")


