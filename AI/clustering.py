import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from database.db_connection import get_recent_clusters_with_embeddings, add_post_to_cluster, create_new_cluster

SIMILARITY_THRESHOLD = 0.69

def find_similar_cluster(new_embedding: list[float], recent_clusters: list[tuple[int, list[float]]]):
    """Проверка на схожесть с существующими кластерами."""
    max_similarity = 0
    for cluster_id, cluster_embedding in recent_clusters:
        similarity = cosine_similarity(
            [np.array(new_embedding)], [np.array(cluster_embedding)]
        )[0][0]
        if similarity >= SIMILARITY_THRESHOLD:
            return cluster_id, similarity
        if max_similarity < similarity:
            max_similarity = similarity
    return None, max_similarity


def process_post_and_cluster(embedding: list[float], post_id: int):
    """Определяет, кластеризовать пост или создать новый кластер.

    Принимает уже рассчитанный embedding, чтобы избежать повторного вычисления.
    """
    # Получить последние n кластеров (например, 50)
    recent_clusters = get_recent_clusters_with_embeddings(limit=1000)

    cluster_id, similarity = find_similar_cluster(embedding, recent_clusters)

    if cluster_id:
        add_post_to_cluster(cluster_id, post_id)
        return {"status": "added", "cluster_id": cluster_id, "similarity": similarity}
    else:
        new_cluster_id = create_new_cluster(post_id)
        return {"status": "new_cluster", "cluster_id": new_cluster_id, "similarity": similarity}
