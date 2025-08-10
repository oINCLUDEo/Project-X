import math
import os
from database.db_connection import get_channel_category, get_category_users


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
    numerator = a * reactions + b * comments + c * forwards
    denominator = views ** alpha + 1
    x = numerator / denominator
    return sigmoid(x)


def compute_cluster_score(cluster_posts, a=1, b=1.5, c=2, alpha=1):
    total_views = sum(p['views'] for p in cluster_posts)
    total_reactions = sum(p['reactions'] for p in cluster_posts)
    total_comments = sum(p['comments'] for p in cluster_posts)
    total_forwards = sum(p['forwards'] for p in cluster_posts)
    unique_channels = len(set(p['channel_id'] for p in cluster_posts))

    numerator = a * total_reactions + b * total_comments + c * total_forwards
    denominator = total_views ** alpha + 1
    er = numerator / denominator

    heat_multiplier = math.log(unique_channels + 1)
    score = sigmoid(er * 10) * heat_multiplier

    return score
