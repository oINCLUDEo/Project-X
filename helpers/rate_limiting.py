"""
Модуль для нормализации количества постов (rate limiting).
Ограничивает количество новостей, отправляемых пользователю в единицу времени.
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timedelta

from database.db_connection import (
    get_user_post_count_today,
    get_user_post_count_hour,
    get_user_activity_stats,
    get_system_param
)

logger = logging.getLogger(__name__)


def check_user_quota(user_id: int, current_hour: Optional[int] = None) -> Dict[str, any]:
    """
    Проверяет квоты пользователя для отправки новостей.
    
    Args:
        user_id: ID пользователя (user_id в БД)
        current_hour: Текущий час (0-23), если None - вычисляется автоматически
        
    Returns:
        Dict с полями:
        - can_send_hourly: bool - можно ли отправить в этот час
        - can_send_daily: bool - можно ли отправить сегодня
        - hourly_count: int - количество постов в этот час
        - daily_count: int - количество постов сегодня
        - hourly_limit: int - лимит постов в час
        - daily_limit: int - лимит постов в день
        - hourly_remaining: int - оставшееся количество постов в час
        - daily_remaining: int - оставшееся количество постов в день
    """
    try:
        if current_hour is None:
            current_hour = datetime.now().hour
        
        # Получаем лимиты из системных параметров
        try:
            hourly_limit = int(get_system_param('user_hourly_post_limit', '5') or '5')
            daily_limit = int(get_system_param('user_daily_post_limit', '20') or '20')
        except Exception as e:
            logger.warning(f"Ошибка получения лимитов постов: {e}, используем значения по умолчанию")
            hourly_limit = 5
            daily_limit = 20
        
        # Получаем текущие счетчики
        hourly_count = get_user_post_count_hour(user_id, current_hour)
        daily_count = get_user_post_count_today(user_id)
        
        # Проверяем квоты
        can_send_hourly = hourly_count < hourly_limit
        can_send_daily = daily_count < daily_limit
        
        hourly_remaining = max(0, hourly_limit - hourly_count)
        daily_remaining = max(0, daily_limit - daily_count)
        
        # Адаптивная квота: увеличиваем лимиты для активных пользователей
        activity_stats = get_user_activity_stats(user_id)
        if activity_stats:
            interaction_count = activity_stats.get('interaction_count', 0)
            # Если пользователь активно взаимодействует, увеличиваем лимиты
            if interaction_count > 50:
                hourly_limit = int(hourly_limit * 1.5)
                daily_limit = int(daily_limit * 1.5)
                can_send_hourly = hourly_count < hourly_limit
                can_send_daily = daily_count < daily_limit
                hourly_remaining = max(0, hourly_limit - hourly_count)
                daily_remaining = max(0, daily_limit - daily_count)
        
        result = {
            'can_send_hourly': can_send_hourly,
            'can_send_daily': can_send_daily,
            'hourly_count': hourly_count,
            'daily_count': daily_count,
            'hourly_limit': hourly_limit,
            'daily_limit': daily_limit,
            'hourly_remaining': hourly_remaining,
            'daily_remaining': daily_remaining
        }
        
        logger.debug(
            f"Quota check для user={user_id}: "
            f"hourly={hourly_count}/{hourly_limit} (can_send={can_send_hourly}), "
            f"daily={daily_count}/{daily_limit} (can_send={can_send_daily})"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка проверки квоты для user={user_id}: {e}", exc_info=True)
        # В случае ошибки разрешаем отправку (fail-open)
        return {
            'can_send_hourly': True,
            'can_send_daily': True,
            'hourly_count': 0,
            'daily_count': 0,
            'hourly_limit': 5,
            'daily_limit': 20,
            'hourly_remaining': 5,
            'daily_remaining': 20
        }


def get_user_priority_threshold(user_id: int) -> float:
    """
    Возвращает минимальный threshold personal_score для отправки новости.
    
    Threshold зависит от:
    - Заполненности квоты (чем больше заполнена, тем выше threshold)
    - Активности пользователя (активные пользователи имеют более низкий threshold)
    
    Args:
        user_id: ID пользователя
        
    Returns:
        float: Минимальный personal_score для отправки (0-1)
    """
    try:
        # Базовый threshold из системных параметров
        try:
            base_threshold = float(get_system_param('min_personal_score', '0.3') or '0.3')
        except Exception:
            base_threshold = 0.3
        
        # Получаем информацию о квоте
        quota = check_user_quota(user_id)
        
        # Вычисляем коэффициент заполненности квоты
        daily_fill_ratio = 0.0
        if quota['daily_limit'] > 0:
            daily_fill_ratio = quota['daily_count'] / quota['daily_limit']
        
        hourly_fill_ratio = 0.0
        if quota['hourly_limit'] > 0:
            hourly_fill_ratio = quota['hourly_count'] / quota['hourly_limit']
        
        # Чем больше заполнена квота, тем выше threshold
        # Используем максимальный fill_ratio (дневной или часовой)
        max_fill_ratio = max(daily_fill_ratio, hourly_fill_ratio)
        
        # Threshold увеличивается пропорционально заполненности
        # При заполненности 0% -> base_threshold
        # При заполненности 100% -> base_threshold * 2.0 (но не больше 0.9)
        threshold = base_threshold * (1.0 + max_fill_ratio)
        threshold = min(0.9, threshold)
        
        # Учитываем активность пользователя
        activity_stats = get_user_activity_stats(user_id)
        if activity_stats:
            interaction_count = activity_stats.get('interaction_count', 0)
            # Активные пользователи имеют более низкий threshold
            if interaction_count > 50:
                threshold *= 0.8  # Снижаем threshold на 20%
            elif interaction_count > 20:
                threshold *= 0.9  # Снижаем threshold на 10%
        
        logger.debug(
            f"Priority threshold для user={user_id}: {threshold:.3f} "
            f"(base={base_threshold:.3f}, fill_ratio={max_fill_ratio:.2f})"
        )
        
        return threshold
        
    except Exception as e:
        logger.error(f"Ошибка вычисления threshold для user={user_id}: {e}", exc_info=True)
        return 0.3  # Возвращаем базовый threshold в случае ошибки


def should_send_now(user_id: int, personal_score: float, priority: int) -> bool:
    """
    Определяет, нужно ли отправить новость пользователю сейчас.
    
    Учитывает:
    - Квоты пользователя
    - Персональный score новости
    - Приоритет новости
    - Время активности пользователя
    
    Args:
        user_id: ID пользователя
        personal_score: Персональный score новости
        priority: Приоритет новости (1-10)
        
    Returns:
        bool: True если нужно отправить сейчас, False если отложить
    """
    try:
        # Проверяем квоты
        quota = check_user_quota(user_id)
        if not quota['can_send_daily']:
            return False  # Дневная квота исчерпана
        
        # Проверяем threshold
        threshold = get_user_priority_threshold(user_id)
        if personal_score < threshold:
            return False  # Score ниже threshold
        
        # Высокоприоритетные новости (priority >= 8) отправляются немедленно
        # если есть место в квоте
        if priority >= 8 and quota['can_send_hourly']:
            return True
        
        # Обычные новости отправляются только если есть место в часовой квоте
        if quota['can_send_hourly']:
            return True
        
        # Если часовая квота исчерпана, но новость высокоприоритетная,
        # все равно отправляем (переполнение квоты для важных новостей)
        if priority >= 9 and personal_score > threshold * 1.5:
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Ошибка определения should_send_now для user={user_id}: {e}", exc_info=True)
        return False


def get_optimal_send_time(user_id: int, current_time: Optional[datetime] = None) -> datetime:
    """
    Определяет оптимальное время для отправки новости пользователю.
    
    Учитывает:
    - Время активности пользователя
    - Текущую заполненность квоты
    - Время суток (избегаем ночных часов)
    
    Args:
        user_id: ID пользователя
        current_time: Текущее время, если None - используется текущее время
        
    Returns:
        datetime: Оптимальное время для отправки
    """
    try:
        if current_time is None:
            current_time = datetime.now()
        
        # Получаем статистику активности пользователя
        activity_stats = get_user_activity_stats(user_id)
        
        if activity_stats and activity_stats.get('avg_active_hour') is not None:
            # Используем средний час активности пользователя
            optimal_hour = activity_stats['avg_active_hour']
        else:
            # Используем дефолтные часы активности (9:00, 13:00, 19:00)
            current_hour = current_time.hour
            if 7 <= current_hour < 10:
                optimal_hour = 9
            elif 12 <= current_hour < 14:
                optimal_hour = 13
            elif 18 <= current_hour < 22:
                optimal_hour = 19
            else:
                # Если текущее время не в активных часах, отправляем в ближайший активный час
                if current_hour < 7:
                    optimal_hour = 9
                elif current_hour < 12:
                    optimal_hour = 13
                elif current_hour < 18:
                    optimal_hour = 19
                else:
                    optimal_hour = 9  # Следующий день, утром
        
        # Вычисляем оптимальное время
        optimal_time = current_time.replace(hour=optimal_hour, minute=0, second=0, microsecond=0)
        
        # Если оптимальное время в прошлом, переносим на следующий день
        if optimal_time < current_time:
            optimal_time += timedelta(days=1)
        
        # Проверяем квоту в оптимальное время
        # Если квота будет исчерпана, ищем ближайшее доступное время
        optimal_hour_for_quota = optimal_time.hour
        quota = check_user_quota(user_id, optimal_hour_for_quota)
        
        if not quota['can_send_hourly']:
            # Если в оптимальное время квота исчерпана, отправляем в следующем доступном окне
            # Смещаем на 1-2 часа вперед
            optimal_time += timedelta(hours=1)
        
        return optimal_time
        
    except Exception as e:
        logger.error(f"Ошибка определения optimal_send_time для user={user_id}: {e}", exc_info=True)
        # В случае ошибки возвращаем текущее время + 1 час
        if current_time is None:
            current_time = datetime.now()
        return current_time + timedelta(hours=1)



