import os
import logging
from typing import List, Dict, Tuple
import re
import time

try:
    # OpenAI SDK v1.x
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from helpers.helpers import compute_heat_score
from database.db_connection import (
    get_system_param,
)

logger = logging.getLogger(__name__)


def _select_anchor_post(cluster_posts: List[Dict]) -> Dict:
    """
    Выбирает якорный (основной) пост из кластера для использования в качестве базы для генерации.
    
    Алгоритм выбора:
    - Вычисляет heat score (метрика вовлеченности) для каждого поста
    - Добавляет бонус за длину текста (до 1000 символов)
    - Возвращает пост с наивысшим комбинированным score
    
    Args:
        cluster_posts: Список постов кластера с полями views, reactions, comments, forwards, content
        
    Returns:
        Dict: Выбранный якорный пост или пустой словарь если кластер пустой
    """
    if not cluster_posts:
        return {}
    scored = []
    for p in cluster_posts:
        try:
            heat = compute_heat_score(
                p.get('views', 0),
                p.get('reactions', 0),
                p.get('comments', 0),
                p.get('forwards', 0),
            )
        except Exception:
            heat = 0.0
        length_bonus = min(1.0, len((p.get('content') or '').strip()) / 1000.0)
        score = 0.7 * heat + 0.3 * length_bonus
        scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored[0][1]




def _get_style_prefs() -> Dict:
    """
    Читает системные параметры стиля из базы данных и возвращает словарь настроек.
    
    Параметры:
    - content_style: auto|news|entertainment
    - content_tone: neutral|lively  
    - content_headings_enabled: разрешить явные заголовки
    - content_emojis_max: максимальное количество эмодзи (0-3)
    
    Returns:
        Dict: Словарь с настройками стиля
    """
    try:
        style = (get_system_param('content_style', 'auto'))
    except Exception:
        style = 'auto'
    try:
        tone = (get_system_param('content_tone', 'neutral'))
    except Exception:
        tone = 'neutral'
    try:
        headings = (get_system_param('content_headings_enabled', '0'))
    except Exception:
        headings = False
    try:
        emojis_max = int(get_system_param('content_emojis_max', '1'))
        if emojis_max < 0:
            emojis_max = 0
    except Exception:
        emojis_max = 1
    return {
        'style': style,         # auto|news|entertainment
        'tone': tone,           # neutral|lively
        'headings': headings,   # True => разрешить явные заголовки
        'emojis_max': emojis_max,
    }


def _get_length_prefs() -> Dict:
    """
    Читает параметры длины и структуры текста из системных параметров.
    
    Параметры:
    - content_len_mode: auto|short|long
    - content_min_paragraphs: минимальное количество абзацев
    - content_max_paragraphs: максимальное количество абзацев
    - content_allow_headline_only: разрешить только заголовок
    
    Returns:
        Dict: Словарь с настройками длины
    """
    try:
        mode = (get_system_param('content_len_mode', 'auto') or 'auto').lower()  # auto|short|long
    except Exception:
        mode = 'auto'
    try:
        min_p = max(1, int(get_system_param('content_min_paragraphs', '1') or '1'))
    except Exception:
        min_p = 1
    try:
        max_p = max(min_p, int(get_system_param('content_max_paragraphs', '6') or '6'))
    except Exception:
        max_p = 6
    try:
        allow_headline_only = (get_system_param('content_allow_headline_only', '1') or '1')
    except Exception:
        allow_headline_only = True
    return {
        'mode': mode,
        'min_p': min_p,
        'max_p': max_p,
        'allow_headline_only': allow_headline_only,
    }


def _text_to_shingles(text: str, k: int = 5) -> set:
    """
    Разбивает текст на шинглы (последовательности слов) для оценки новизны контента.
    
    Шинглы используются для определения уникальности текста путем сравнения
    последовательностей слов между разными постами.
    
    Args:
        text: Исходный текст
        k: Размер шингла (количество слов в последовательности)
        
    Returns:
        set: Множество шинглов из текста
    """
    tokens = re.findall(r"\w+", (text or '').lower(), flags=re.UNICODE)
    if len(tokens) < k:
        return set([" ".join(tokens)]) if tokens else set()
    return set(" ".join(tokens[i:i+k]) for i in range(len(tokens)-k+1))


def _compute_novelty_score(posts: List[Dict]) -> float:
    """
    Вычисляет метрику новизны фактов в кластере постов.
    
    Алгоритм:
    1. Выбирает якорный пост (лучший по метрикам)
    2. Извлекает шинглы из якорного поста
    3. Считает долю шинглов из других постов, которых нет в якоре
    4. Возвращает значение 0..1 (0 = ничего нового, 1 = много новых фактов)
    
    Args:
        posts: Список постов кластера
        
    Returns:
        float: Метрика новизны от 0 до 1.5
    """
    anchor = _select_anchor_post(posts)
    anchor_shingles = _text_to_shingles(anchor.get('content'))
    union_new = set()
    total_shingles = 0
    for p in posts:
        sh = _text_to_shingles(p.get('content') or '')
        total_shingles += len(sh)
        union_new |= (sh - anchor_shingles)
    if total_shingles <= 0:
        return 0.0
    # Ограничим долю, чтобы шум не раздувал метрику
    score = min(1.5, len(union_new) / max(1, total_shingles))
    return float(score)


def _compute_avg_var_len(posts: List[Dict]) -> Tuple[float, float, int]:
    """
    Вычисляет статистики длины текстов в кластере постов.
    
    Args:
        posts: Список постов кластера
        
    Returns:
        Tuple[float, float, int]: (средняя длина, дисперсия длины, количество постов)
    """
    lengths = [len((p.get('content') or '').strip()) for p in posts]
    if not lengths:
        return 0.0, 0.0, 0
    n = len(lengths)
    avg = sum(lengths) / n
    var = sum((L - avg) ** 2 for L in lengths) / n
    return float(avg), float(var), n


def _compute_target_paragraphs_from_metrics(avg_len: float, var_len: float, novelty: float, style: str, tone: str) -> Tuple[int, int]:
    """
    Вычисляет оптимальное количество абзацев для генерируемого текста на основе метрик контента.
    
    Алгоритм:
    1. Определяет базовый диапазон по средней длине постов
    2. Добавляет бонусы за высокую дисперсию длин и новизну фактов
    3. Применяет ограничения стиля (entertainment = короче)
    4. Учитывает системные параметры min/max абзацев
    5. Ограничивает общую длину текста лимитами Telegram
    
    Args:
        avg_len: Средняя длина постов в символах
        var_len: Дисперсия длин постов
        novelty: Метрика новизны фактов (0..1)
        style: Стиль контента (auto|news|entertainment)
        tone: Тон контента (neutral|lively)
        
    Returns:
        Tuple[int, int]: (минимальное количество абзацев, максимальное количество абзацев)
    """
    lp = _get_length_prefs()
    
    # Telegram лимиты
    TELEGRAM_CAPTION_LIMIT = 1024  # Лимит подписи для медиа
    TELEGRAM_MESSAGE_LIMIT = 4096  # Лимит обычного сообщения
    
    # База по среднему размеру
    if lp['mode'] == 'short':
        base_min, base_max = max(1, lp['min_p']), max(1, min(2, lp['max_p']))
    elif lp['mode'] == 'long':
        base_min, base_max = max(2, lp['min_p']), max(3, lp['max_p'])
    else:
        if avg_len < 600:
            base_min, base_max = 1, max(1, min(2, lp['max_p']))
        elif avg_len < 1400:
            base_min, base_max = max(2, lp['min_p']), max(3, lp['max_p'])
        else:
            base_min, base_max = max(3, lp['min_p']), max(5, lp['max_p'])
    
    # Усилители: разброс и новизна
    bump = 0
    if var_len > 80000:  # ~разброс длин высок
        bump += 1
    if novelty > 0.3:    # достаточно новых фрагментов
        bump += 1
    
    min_p = min(lp['max_p'], base_min + bump)
    max_p = min(lp['max_p'], base_max + bump)
    
    # Стильные ограничения
    if style == 'entertainment':
        max_p = max(min_p, min(max_p, 3))
    
    # Ограничения по длине для Telegram
    # Предполагаем ~200-300 символов на абзац для ограничения общей длины
    estimated_chars_per_paragraph = 250
    max_paragraphs_by_caption = TELEGRAM_CAPTION_LIMIT // estimated_chars_per_paragraph
    max_paragraphs_by_message = TELEGRAM_MESSAGE_LIMIT // estimated_chars_per_paragraph
    
    # Ограничиваем максимальное количество абзацев лимитами Telegram
    max_p = min(max_p, max_paragraphs_by_caption)
    
    if min_p > max_p:
        min_p = max_p
    
    return min_p, max_p


def _compose_style_instructions() -> str:
    """
    Формирует инструкции по стилю для LLM на основе системных параметров.
    
    Включает:
    - Настройки заголовков
    - Тональность (нейтральная/живая)
    - Стиль по типу контента (новости/развлечения)
    - Ограничения на эмодзи
    - Разрешенные HTML теги для Telegram
    - Запрещенные элементы форматирования
    
    Returns:
        str: Текст инструкций для LLM
    """
    prefs = _get_style_prefs()
    parts: List[str] = []
    # Заголовки
    if not prefs['headings']:
        parts.append("Не вставляй явные заголовки разделов вроде 'Лид', 'Детали' — пиши цельный текст.")
    # Тональность
    if prefs['tone'] == 'lively':
        parts.append("Лёгкая динамика допускается, но без эмоций и без оценочных суждений.")
    else:
        parts.append("Строго нейтральный информационный стиль.")
    # Стиль по типу контента
    if prefs['style'] == 'entertainment':
        parts.append("Стиль: развлекательный канал — допускай более разговорную подачу, но без сленга и без эмоциональных оценок.")
    elif prefs['style'] == 'news':
        parts.append("Стиль: новостная заметка — кратко, фактически, без воды.")
    else:
        parts.append("Стиль: автоматически подбери между сжатой заметкой и мягкой подачей, сохраняя фактичность.")
    # Эмодзи
    if prefs['emojis_max'] <= 0:
        parts.append("Эмодзи не используй.")
    else:
        # TODO: Возможно стоит подправить
        #parts.append(f"Эмодзи — не более {prefs['emojis_max']} и только в начале первой строки, если уместно.")
        parts.append(f"Эмодзи — не более {prefs['emojis_max']} если уместно.")
    # HTML
    parts.append(
        "Формат вывода: HTML для Telegram. Разрешено: <b>/<strong>, <i>/<em>, <u>/<ins>, <s>/<strike>/<del>, "
        "<a href=...>, <code>, <pre>, <blockquote>, <tg-spoiler> или <span class=\"tg-spoiler\">…</span>. "
        "Кастомные эмодзи <tg-emoji> не используй без явной необходимости."
    )
    parts.append("Запрещено: <p>, <br>, списочные теги, произвольные атрибуты (кроме href у <a>). Абзацы разделяй пустой строкой.")
    # Верстка
    parts.append("Для маркированных пунктов используй обычные строки, без специальных тегов.")
    # Возвращаем часть запроса с описанием стиля
    return " ".join(parts)


def _build_prompt_mode_a(anchor: Dict, others: List[Dict], has_media: bool = False) -> Tuple[str, str]:
    """
    Строит промпт для режима A: перефразирование якорного поста + добавление деталей из других источников.
    
    Режим A подходит когда:
    - Есть один основной пост с хорошей информацией
    - Другие посты содержат дополнительные детали
    - Нужно сохранить структуру основного поста
    
    Args:
        anchor: Якорный (основной) пост
        others: Список дополнительных постов с деталями
        has_media: Есть ли медиа в кластере (влияет на лимит длины)
        
    Returns:
        Tuple[str, str]: (системный промпт, пользовательский промпт)
    """
    # Определяем лимит в зависимости от наличия медиа
    char_limit = 1024 if has_media else 4096
    limit_text = f"{char_limit} символов" if has_media else f"{char_limit} символов"
    
    system = (
        "Ты — нейтральный редактор новостей. Пиши фактически, без эмоций и оценочных суждений. "
        "Используй только предоставленные тексты постов. Не выдумывай фактов. Если данные расходятся, укажи это. "
        f"ВАЖНО: Длина итогового текста не должна превышать {limit_text} для корректной отправки в Telegram. "
        + _compose_style_instructions()
    )
    anchor_block = (
        f"Якорный пост (channel={anchor.get('channel_tg_id')}, post_id={anchor.get('post_id')}):\n"
        f"" + (anchor.get('content') or "").strip()
    )
    other_blocks = []
    for p in others:
        other_blocks.append(
            f"Источник (channel={p.get('channel_tg_id')}, post_id={p.get('post_id')}):\n" + (p.get('content') or "").strip()
        )
    # Определяем желаемый диапазон абзацев (по среднему размеру, разбросу и новизне)
    posts_for_metrics = [{**anchor}] + others
    avg_len, var_len, _ = _compute_avg_var_len(posts_for_metrics)
    novelty = _compute_novelty_score(posts_for_metrics)
    prefs = _get_style_prefs()
    min_p, max_p = _compute_target_paragraphs_from_metrics(avg_len, var_len, novelty, prefs['style'], prefs['tone'])
    len_hint = f"Сделай {min_p}–{max_p} абзацев." if min_p != max_p else f"Сделай {min_p} абзац(а)."

    user = (
        "Перепиши якорный пост нейтрально и добавь проверенные детали из других постов.\n"
        "Сделай первый ключевой факт выразительным (можно выделить <b>жирным</b>), затем плавно раскрой детали.\n"
        "Цитаты допустимо выделять <i>курсивом</i>. Не добавляй новых фактов.\n"
        f"{len_hint}\n\n"
        + anchor_block
        + "\n\nДополнительные источники:\n"
        + "\n\n".join(other_blocks)
        + "\n\nВыведи только HTML-текст и затем 'Источники:' (без ссылок) со списком (channel, post_id)."
    )
    return system, user


def _build_prompt_mode_b(posts: List[Dict], has_media: bool = False) -> Tuple[str, str]:
    """
    Строит промпт для режима B: синтез новой статьи с нуля на основе всех источников.
    
    Режим B подходит когда:
    - Все посты содержат равнозначную информацию
    - Нужно создать принципиально новую структуру
    - Посты дополняют друг друга фактами
    
    Args:
        posts: Список всех постов кластера
        has_media: Есть ли медиа в кластере (влияет на лимит длины)
        
    Returns:
        Tuple[str, str]: (системный промпт, пользовательский промпт)
    """
    # Определяем лимит в зависимости от наличия медиа
    char_limit = 1024 if has_media else 4096
    limit_text = f"{char_limit} символов"
    
    system = (
        "Ты — редактор постов различного характера. "
        f"ВАЖНО: Длина итогового текста не должна превышать {limit_text} для корректной отправки в Telegram. "
        + _compose_style_instructions()
    )
    blocks = []
    for p in posts:
        blocks.append(
            f"Источник (channel={p.get('channel_tg_id')}, post_id={p.get('post_id')}):\n" + (p.get('content') or "").strip()
        )
    avg_len, var_len, _ = _compute_avg_var_len(posts)
    novelty = _compute_novelty_score(posts)
    prefs = _get_style_prefs()
    min_p, max_p = _compute_target_paragraphs_from_metrics(avg_len, var_len, novelty, prefs['style'], prefs['tone'])
    lp = _get_length_prefs()
    if lp['allow_headline_only'] and min_p == 1:
        headline_hint = "Разрешено: жирный лид и один короткий абзац. "
    else:
        headline_hint = ""
    len_hint = f"Сделай {min_p}–{max_p} абзацев." if min_p != max_p else f"Сделай {min_p} абзац(а)."

    user = (
        "Синтезируй цельный текст заметки.\n"
        f"Первый ключевой факт можно выделить <b>жирным</b>. Детали раскрой плавно, цитаты — <i>курсивом</i>. {headline_hint}{len_hint}\n"
        "Требования: не добавляй фактов, которых нет в источниках.\n"
        "Если есть противоречия — укажи их нейтрально. Вывод строго в HTML, без Markdown и без кода.\n\n"
        + "\n\n".join(blocks)
        + "\n\nВыведи только HTML-текст"
    )
    return system, user


def _get_model_candidates(preferred: str | None) -> List[str]:
    """
    Формирует список кандидатов моделей для LLM с fallback механизмом.
    
    Приоритет:
    1. Предпочитаемая модель (если указана)
    2. Модель из OPENAI_MODEL
    3. Бесплатные модели OpenRouter
    4. Платные модели OpenRouter
    
    Args:
        preferred: Предпочитаемая модель (может быть None)
        
    Returns:
        List[str]: Список моделей в порядке приоритета
    """
    raw = os.getenv("OPENAI_MODEL_CANDIDATES")
    if raw:
        models = [m.strip() for m in raw.split(",") if m.strip()]
        if models:
            return models
    # Sane defaults for OpenRouter
    defaults = [
        preferred or os.getenv("OPENAI_MODEL", ""),
        "meta-llama/llama-3.1-8b-instruct",
        "qwen/qwen-2.5-14b-instruct",
    ]
    # "deepseek/deepseek-chat-v3-0324:free" - Вырезан из списка по причине плохой работы
    # Deduplicate while preserving order and removing empties
    seen = set()
    result = []
    for m in defaults:
        if not m:
            continue
        if m not in seen:
            seen.add(m)
            result.append(m)
    return result


def _is_ratelimit_error(err: Exception) -> bool:
    """
    Проверяет, является ли ошибка связанной с превышением лимитов запросов.
    
    Args:
        err: Исключение для проверки
        
    Returns:
        bool: True если это ошибка rate limit
    """
    msg = str(err).lower()
    return ("429" in msg) or ("rate-limit" in msg) or ("temporarily rate-limited" in msg) or ("insufficient_quota" in msg)


def _llm_generate(system: str, user: str, model: str | None = None, max_output_tokens: int = 700) -> Tuple[str | None, str | None]:
    """
    Выполняет запрос к LLM API с поддержкой fallback механизмов.
    
    Особенности:
    - Поддержка OpenAI v1 и legacy API
    - Автоматический fallback между моделями при rate limit
    - Экспоненциальная задержка при повторных попытках
    - Поддержка OpenRouter с кастомными заголовками
    
    Args:
        system: Системный промпт
        user: Пользовательский промпт
        model: Предпочитаемая модель (опционально)
        max_output_tokens: Максимальное количество токенов в ответе
        
    Returns:
        Tuple[str | None, str | None]: (текст ответа, название использованной модели)
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        logger.warning("[SYNTH] OpenAI API key missing or SDK not available — using fallback")
        return None, None
    try:
        base_url = os.getenv("OPENAI_BASE_URL")
        default_headers = None
        if base_url and "openrouter.ai" in base_url:
            headers = {}
            ref = os.getenv("OPENROUTER_REFERER")
            title = os.getenv("OPENROUTER_TITLE")
            if ref:
                headers["HTTP-Referer"] = ref
            if title:
                headers["X-Title"] = title
            default_headers = headers if headers else None

        # Подготовим клиента v1
        client = OpenAI(base_url=base_url, default_headers=default_headers) if base_url else OpenAI(default_headers=default_headers)

        candidates = _get_model_candidates(model)
        backoff_s = 1.0
        for idx, used_model in enumerate(candidates):
            try:
                logger.info(f"[SYNTH] LLM try {idx+1}/{len(candidates)} model={used_model}")
                resp = client.chat.completions.create(
                    model=used_model,
                    temperature=0.2,
                    max_tokens=max_output_tokens,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                )
                return (resp.choices[0].message.content or "").strip(), used_model
            except Exception as e1:
                if _is_ratelimit_error(e1) and (idx + 1) < len(candidates):
                    logger.warning(f"[SYNTH] Rate-limited on model={used_model}, will try next after {backoff_s:.1f}s")
                    time.sleep(backoff_s)
                    backoff_s = min(backoff_s * 2.0, 6.0)
                    continue
                # Фолбэк к legacy клиенту для этой же модели
                try:
                    import openai as openai_legacy  # type: ignore
                    openai_legacy.api_key = api_key
                    if base_url:
                        openai_legacy.api_base = base_url
                    logger.info(f"[SYNTH] Legacy LLM try model={used_model}")
                    resp = openai_legacy.ChatCompletion.create(
                        model=used_model,
                        temperature=0.2,
                        max_tokens=max_output_tokens,
                        messages=[
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                    )
                    content = resp["choices"][0]["message"]["content"]
                    return (content or "").strip(), used_model
                except Exception as e2:
                    if _is_ratelimit_error(e2) and (idx + 1) < len(candidates):
                        logger.warning(f"[SYNTH] Rate-limited (legacy) on model={used_model}, will try next after {backoff_s:.1f}s")
                        time.sleep(backoff_s)
                        backoff_s = min(backoff_s * 2.0, 6.0)
                        continue
                    logger.error(f"[SYNTH] Model {used_model} failed: {e2}")
                    # Если это последняя — прорвёмся наружу к общему except
                    if (idx + 1) == len(candidates):
                        raise e2
                    # Иначе пробуем следующую без задержки
                    continue
    except Exception as e:  # pragma: no cover
        logger.error(f"[SYNTH] OpenAI call failed: {e}", exc_info=True)
        return None, None


def _split_sentences(text: str) -> List[str]:
    """
    Разбивает текст на предложения по знакам препинания.
    
    Args:
        text: Исходный текст
        
    Returns:
        List[str]: Список предложений
    """
    if not text:
        return []
    # Простая эвристика: разбиваем по . ! ? с возможными пробелами и кавычками
    parts = re.split(r"(?<=[\.!?;])\s+", text.strip())
    return [p.strip() for p in parts if p and len(p.strip()) > 0]


def _extract_lead(text: str, max_sentences: int = 2) -> str:
    """
    Извлекает лид (краткое введение) из текста.
    
    Args:
        text: Исходный текст
        max_sentences: Максимальное количество предложений в лиде
        
    Returns:
        str: Извлеченный лид
    """
    sents = _split_sentences(text)
    return " ".join(sents[:max_sentences]).strip()


def synthesize_news(cluster_posts: List[Dict], mode: str = 'A', has_media: bool = False) -> Tuple[str, Dict]:
    """
    Основная функция генерации новостной статьи из кластера постов.

    Поддерживает два режима:
    - Mode A: Перефразирование якорного поста + добавление деталей
    - Mode B: Синтез новой статьи с нуля на основе всех источников

    Args:
        cluster_posts: Список постов кластера с полями:
                      post_id, channel_tg_id, content, media_urls, views, reactions, comments, forwards
        mode: Режим генерации ('A' или 'B')
        has_media: Есть ли медиа в кластере (влияет на лимит длины: 1024 для медиа, 4096 для текста)

    Returns:
        Tuple[str, Dict]: (сгенерированный текст, метаданные)
                         Метаданные содержат: mode, posts, model, prompt_len, has_media
    """
    # Валидация входных данных
    if not cluster_posts:
        logger.warning("[SYNTH] Empty cluster_posts")
        return "", {"mode": mode, "posts": 0, "model": "none", "prompt_len": 0, "has_media": has_media}
    
    # Валидация режима
    if mode.upper() not in ['A', 'B']:
        logger.error(f"[SYNTH] Invalid mode '{mode}', using 'A' as default")
        mode = 'A'
    
    # Определяем наличие медиа в кластере, если не передано явно
    if not has_media:
        has_media = any(
            post.get('media_urls') and 
            post.get('media_urls') != [] and 
            post.get('media_urls') != [None] and
            post.get('media_urls') != ['']
            for post in cluster_posts
        )
    
    # Нормализуем и отсортируем по важности (views/reactions)
    posts = list(cluster_posts)
    posts.sort(key=lambda p: (p.get('views', 0), p.get('reactions', 0), len((p.get('content') or ''))), reverse=True)
    # Ограничиваем количество постов для обработки (разумный лимит для LLM)
    max_posts = 10
    posts = posts[:max_posts]

    # Генерация в зависимости от режима
    if mode.upper() == 'A':
        anchor = _select_anchor_post(posts)
        others = [p for p in posts if p.get('post_id') != anchor.get('post_id')]
        system, user = _build_prompt_mode_a(anchor, others, has_media)
    else:
        system, user = _build_prompt_mode_b(posts, has_media)

    # Генерация текста через LLM
    text, model_used = _llm_generate(system, user)
    if not text:
        # Фолбэк без LLM
        logger.warning("[SYNTH] LLM generation failed, using fallback")
        # TODO: Нужно реализовать метод, чтобы при подобных ошибках администраторы оперативно получали информацию об этом

    # Нормализация выхода
    normalized = _normalize_output(text, has_media)
    return normalized, {"mode": mode, "posts": len(cluster_posts), "model": model_used, "prompt_len": len(user), "has_media": has_media}


def _normalize_output(text: str, has_media: bool = False) -> str:
    """
    Пост-обработка вывода LLM для совместимости с Telegram HTML.
    
    Выполняет:
    1. Удаление внутренних ссылок на источники
    2. Удаление markdown разметки
    3. Схлопывание лишних пустых строк
    4. Автоматическое выделение первой строки жирным
    5. Фильтрацию HTML тегов (только разрешенные для Telegram)
    6. Нормализацию синонимичных тегов (strong->b, em->i)
    7. Сохранение блока источников в конце
    8. Обрезку текста до лимита Telegram (1024 символа)
    
    Args:
        text: Исходный текст от LLM
        
    Returns:
        str: Нормализованный HTML текст для Telegram
    """
    if not text:
        return text
    lines = [l.rstrip() for l in text.splitlines()]
    cleaned: List[str] = []
    sources_block: List[str] = []
    in_sources = False
    for l in lines:
        low = l.strip().lower()
        if low.startswith('источники:'):
            in_sources = True
            sources_block.append(l)
            continue
        if in_sources:
            # часть списка источников — сохраняем как есть
            sources_block.append(l)
            continue
        # удаляем строки начинающиеся на "Источник ", markdown-маркеры и явные заголовки
        if re.match(r'^\s*источник\b', low, flags=re.IGNORECASE):
            continue
        if re.match(r'^\s*(лид|детали|что известно/что не подтверждено)\s*:?', low, flags=re.IGNORECASE):
            continue
        if low.startswith('- ') or low.startswith('* '):
            # заменим markdown-список на простой текст с переносом строки
            cleaned.append(l[2:].strip())
            continue
        cleaned.append(l)
    # схлопываем лишние пустые строки
    tmp: List[str] = []
    prev_empty = False
    for l in cleaned:
        is_empty = len(l.strip()) == 0
        if is_empty and prev_empty:
            continue
        tmp.append(l)
        prev_empty = is_empty
    cleaned = tmp
    # удаляем лишние пустые строки в конце
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()

    # Автоматически подчёркиваем первую строку (если нет HTML-тегов и она короткая)
    if cleaned:
        first = cleaned[0]
        if ('<' not in first and '>' not in first) and 5 <= len(first) <= 140:
            cleaned[0] = f"<b>{first}</b>"

    body = "\n".join(cleaned).strip()

    # Жёсткая фильтрация HTML: всегда extended whitelist
    def _strict_filter(html: str) -> str:
        # normalize synonyms
        html = re.sub(r"</?strong>", lambda m: "</b>" if m.group(0).startswith("</") else "<b>", html, flags=re.IGNORECASE)
        html = re.sub(r"</?em>",     lambda m: "</i>" if m.group(0).startswith("</") else "<i>", html, flags=re.IGNORECASE)
        html = re.sub(r"</?ins>",    lambda m: "</u>" if m.group(0).startswith("</") else "<u>", html, flags=re.IGNORECASE)
        html = re.sub(r"</?(strike|del)>", lambda m: "</s>" if m.group(0).startswith("</") else "<s>", html, flags=re.IGNORECASE)
        # always remove <p> and <br>
        html = re.sub(r"<\s*/?\s*p\s*>", "", html, flags=re.IGNORECASE)
        html = re.sub(r"<\s*/?\s*br\s*/?>", "", html, flags=re.IGNORECASE)
        # allow b,i,u,s,a,code,pre,blockquote,tg-spoiler/span.tg-spoiler
        # Strip attributes except href on <a>
        # 1) sanitize <a>: keep only href
        html = re.sub(r"<a\s+[^>]*href=\"([^\"]+)\"[^>]*>", r"<a href=\"\1\">", html, flags=re.IGNORECASE)
        # 2) keep closing tags
        html = re.sub(r"</\s*(b|i|u|s|code|pre|blockquote|a|tg-spoiler)\s*>", r"</\1>", html, flags=re.IGNORECASE)
        # 3) keep opening tags (no attrs), special-case span.tg-spoiler -> <tg-spoiler>
        html = re.sub(r"<\s*span\s+class=\"tg-spoiler\"\s*>", "<tg-spoiler>", html, flags=re.IGNORECASE)
        html = re.sub(r"<\s*(b|i|u|s|code|pre|blockquote|a|tg-spoiler)\s*>", r"<\1>", html, flags=re.IGNORECASE)
        # finally remove any other tag
        html = re.sub(r"<\s*(?!/?(?:b|i|u|s|code|pre|blockquote|a|tg-spoiler)\b)[^>]*>", "", html, flags=re.IGNORECASE)
        return html

    body = _strict_filter(body)

    tail = "\n".join(sources_block).strip()
    if tail:
        full_text = (body + "\n\n" + tail).strip()
    else:
        full_text = body
    
    # Обрезка до лимита Telegram в зависимости от наличия медиа
    char_limit = 1024 if has_media else 4096
    if len(full_text) > char_limit:
        # Обрезаем до лимита, стараясь не разрывать слова
        truncated = full_text[:char_limit]
        last_space = truncated.rfind(' ')
        if last_space > char_limit * 0.8:  # Если нашли пробел в разумных пределах
            truncated = truncated[:last_space]
        full_text = truncated + "..."
        logger.warning(f"[SYNTH] Text truncated to {len(full_text)} chars (limit: {char_limit}, has_media: {has_media})")
    
    return full_text


