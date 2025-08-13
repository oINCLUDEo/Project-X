import math
import os
from database.db_connection import get_channel_category, get_category_users
from typing import List, Dict


def remove_file(filenames_list):
    if type(filenames_list) is list:
        for filename in filenames_list:
            os.remove(filename)
    elif type(filenames_list) is str:
        os.remove(filenames_list)


def sigmoid(x):
    return 1 / (1 + math.exp(-x))


def get_users_for_post(channel_tg_id):
    categories = get_channel_category(channel_tg_id)
    return get_category_users(tuple(categories))


def compute_heat_score(views, reactions, comments, forwards,
                       a=1, b=1.5, c=2, alpha=1):
    """
    Тепловой скоринг поста без временного распада, рассчитанный по общему уровню вовлеченности.
    heat = sigmoid((a*reactions + b*comments + c*forwards) / (views^alpha + 1))
    """
    numerator = a * reactions + b * comments + c * forwards
    denominator = (views ** alpha) + 1
    base = numerator / denominator if denominator > 0 else 0.0
    return sigmoid(base)


def compute_cluster_score(cluster_posts: List[Dict], a=1, b=1.5, c=2, alpha=1,
                          channel_reputation_weight: float = 0.3,
                          diversity_weight: float = 0.35,
                          absolute_views_weight: float = 0.25,
                          views_scale: float = 5000.0):
    """
    Улучшенный скоринг кластера:
    - Engagement rate склеенный по кластеру
    - Мультипликатор разнообразия источников (логарифм числа уникальных каналов)
    - Средняя репутация каналов в кластере
    score = sigmoid(ER * 10) * (1 + diversity_weight * log(1 + unique_channels)) * (1 - channel_reputation_weight + channel_reputation_weight * avg_rep)
    """
    total_views = sum(p['views'] for p in cluster_posts)
    total_reactions = sum(p['reactions'] for p in cluster_posts)
    total_comments = sum(p['comments'] for p in cluster_posts)
    total_forwards = sum(p['forwards'] for p in cluster_posts)
    unique_channels = len(set(p['channel_id'] for p in cluster_posts))
    avg_rep = None
    reps = [p.get('channel_reputation') for p in cluster_posts if p.get('channel_reputation') is not None]
    if reps:
        avg_rep = sum(reps) / len(reps)
    else:
        avg_rep = 0.5

    numerator = a * total_reactions + b * total_comments + c * total_forwards
    denominator = (total_views ** alpha) + 1
    er = numerator / denominator if denominator > 0 else 0.0

    diversity_multiplier = 1.0 + diversity_weight * math.log(unique_channels + 1)
    absolute_views_multiplier = 1.0 + absolute_views_weight * math.log(1.0 + (total_views / max(1.0, views_scale)))
    reputation_multiplier = (1.0 - channel_reputation_weight) + channel_reputation_weight * avg_rep
    score = sigmoid(er * 10) * diversity_multiplier * absolute_views_multiplier * reputation_multiplier
    return score
