import os
import logging
from typing import List, Dict, Tuple
import hashlib
import re

try:
    # OpenAI SDK v1.x
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None  # type: ignore

from helpers.helpers import compute_heat_score
from database.db_connection import (
    get_cached_generated_article,
    put_cached_generated_article,
)

logger = logging.getLogger(__name__)


def _select_anchor_post(cluster_posts: List[Dict]) -> Dict:
    """
    Выбирает якорный пост по комбинации метрик вовлечённости и длины текста.
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


def _truncate_text(text: str, max_chars: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 3)].rstrip() + "..."


def _build_prompt_mode_a(anchor: Dict, others: List[Dict]) -> Tuple[str, str]:
    system = (
        "Ты — нейтральный редактор новостей. Пиши фактически, без эмоций и оценочных суждений. "
        "Используй только предоставленные тексты постов. Не выдумывай фактов. Если данные расходятся, укажи это. "
        "Формат вывода: HTML, совместимый с Telegram parse_mode=HTML. Используй только теги <b>, <i>, <u>. "
        "Ссылки <a> не используй. Эмодзи — не более одного, только в заголовке, если уместно."
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
    user = (
        "Перепиши якорный пост нейтрально и добавь проверенные детали из других постов.\n"
        "Структура: короткий лид (кто/что/где/когда), затем детали, цитаты и контекст.\n"
        "Запрещено: новые факты, эмоциональная лексика. Чётко отмечай спорные моменты.\n"
        "Выводи HTML без обёрток кода. Заголовок сделай жирным (<b>..</b>). Пункты деталей — как список с переносами строк.\n\n"
        + anchor_block
        + "\n\nДополнительные источники:\n"
        + "\n\n".join(other_blocks)
        + "\n\nВыведи только HTML-текст новости (3–6 абзацев) и затем строку 'Источники:' (без ссылок) со списком (channel, post_id)."
    )
    return system, user


def _build_prompt_mode_b(posts: List[Dict]) -> Tuple[str, str]:
    system = (
        "Ты — нейтральный редактор новостей. Пиши фактически, без эмоций, только по источникам. "
        "Формат вывода: HTML, совместимый с Telegram parse_mode=HTML. Допустимые теги: <b>, <i>, <u>. "
        "Не используй <a>. Эмодзи — максимум три"
    )
    blocks = []
    for p in posts:
        blocks.append(
            f"Источник (channel={p.get('channel_tg_id')}, post_id={p.get('post_id')}):\n" + (p.get('content') or "").strip()
        )
    user = (
        "Синтезируй новость с нуля по всем источникам.\n"
        "Строго следуй структуре и объёму, не вставляй исходные тексты целиком.\n"
        "Структура:\n"
        "1) <b>Лид</b> (1–2 предложения: кто/что/где/когда).\n"
        "2) Детали (1–2 абзаца, только подтверждённые факты, используй переносы строк для разделения пунктов).\n"
        "3) Цитаты/реакции (если есть), выдели <i>курсивом</i>.\n"
        "4) 'Что известно/что не подтверждено'.\n"
        "Требования: не копируй фразы из источников, переформулируй. Не добавляй фактов, которых нет в источниках.\n"
        "Если есть противоречия — опиши нейтрально. Вывод строго в HTML, без Markdown и без кода.\n\n"
        + "\n\n".join(blocks)
        + "\n\nВыведи только HTML-текст (3–6 абзацев) и затем 'Источники:' (без ссылок) со списком (channel, post_id)."
    )
    return system, user


def _llm_generate(system: str, user: str, model: str | None = None, max_output_tokens: int = 700) -> Tuple[str | None, str | None]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or OpenAI is None:
        logger.warning("[SYNTH] OpenAI API key missing or SDK not available — using fallback")
        return None, None
    try:
        # Попытка v1-клиента
        try:
            base_url = os.getenv("OPENAI_BASE_URL")
            default_headers = None
            # Специфика OpenRouter: рекомендуемые заголовки
            if base_url and "openrouter.ai" in base_url:
                headers = {}
                ref = os.getenv("OPENROUTER_REFERER")
                title = os.getenv("OPENROUTER_TITLE")
                if ref:
                    headers["HTTP-Referer"] = ref
                if title:
                    headers["X-Title"] = title
                default_headers = headers if headers else None
            if base_url:
                client = OpenAI(base_url=base_url, default_headers=default_headers)
            else:
                client = OpenAI(default_headers=default_headers)  # ключ берётся из OPENAI_API_KEY
            # Подбор дефолтной модели под OpenRouter, если не указано явно
            if (not model) and (not os.getenv("OPENAI_MODEL")) and base_url and "openrouter.ai" in base_url:
                used_model = "meta-llama/llama-3.1-8b-instruct"
            else:
                used_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
        except TypeError as e:
            # На некоторых версиях SDK падает из-за несовместимого параметра 'proxies' — фолбэк на legacy API
            logger.warning(f"[SYNTH] OpenAI v1 client init failed ({e}); falling back to legacy API")
            import openai as openai_legacy  # type: ignore
            openai_legacy.api_key = api_key
            base_url = os.getenv("OPENAI_BASE_URL")
            if base_url:
                openai_legacy.api_base = base_url
            # Дефолт под OpenRouter
            if (not model) and (not os.getenv("OPENAI_MODEL")) and base_url and "openrouter.ai" in base_url:
                used_model = "meta-llama/llama-3.1-8b-instruct"
            else:
                used_model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
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
    except Exception as e:  # pragma: no cover
        logger.error(f"[SYNTH] OpenAI call failed: {e}", exc_info=True)
        return None, None


def _split_sentences_ru(text: str) -> List[str]:
    if not text:
        return []
    # Простая эвристика: разбиваем по . ! ? с возможными пробелами и кавычками
    parts = re.split(r"(?<=[\.!?])\s+", text.strip())
    return [p.strip() for p in parts if p and len(p.strip()) > 0]


def _extract_lead(text: str, max_sentences: int = 2, max_chars: int = 400) -> str:
    sents = _split_sentences_ru(text)
    lead = " ".join(sents[:max_sentences]).strip()
    return _truncate_text(lead, max_chars)


def _fallback_generate_mode_a(anchor: Dict, others: List[Dict]) -> str:
    # Фолбэк без LLM: краткий лид из якоря + лаконичные детали из других источников + список источников
    anchor_text = (anchor.get('content') or '').strip()
    lead = _extract_lead(anchor_text, max_sentences=2, max_chars=400)
    details = []
    used_sources = [(anchor.get('channel_tg_id'), anchor.get('post_id'))]
    for p in others:
        txt = (p.get('content') or '').strip()
        if not txt:
            continue
        bullet = _extract_lead(txt, max_sentences=1, max_chars=160)
        if bullet:
            details.append(f"- {bullet}")
            used_sources.append((p.get('channel_tg_id'), p.get('post_id')))
        if len(details) >= 6:
            break
    parts = []
    if lead:
        parts.append(lead)
    if details:
        parts.append("Детали:")
        parts.append("\n".join(details))
    parts.append("Источники: " + ", ".join([f"({cid}, {pid})" for cid, pid in used_sources]))
    return "\n\n".join(parts)


def _fallback_generate_mode_b(posts: List[Dict]) -> str:
    # Фолбэк без LLM: лид из лучшего поста + краткие пункты из остальных + источники
    if not posts:
        return ""
    main = _select_anchor_post(posts)
    lead = _extract_lead((main.get('content') or ''), max_sentences=2, max_chars=400)
    details = []
    used_ids = set([(main.get('channel_tg_id'), main.get('post_id'))])
    for p in posts:
        if p.get('post_id') == main.get('post_id'):
            continue
        txt = (p.get('content') or '').strip()
        if not txt:
            continue
        bullet = _extract_lead(txt, max_sentences=1, max_chars=160)
        if bullet:
            details.append(f"- {bullet}")
            used_ids.add((p.get('channel_tg_id'), p.get('post_id')))
        if len(details) >= 8:
            break
    parts = []
    if lead:
        parts.append(lead)
    if details:
        parts.append("Детали:")
        parts.append("\n".join(details))
    parts.append("Источники: " + ", ".join([f"({cid}, {pid})" for cid, pid in used_ids]))
    return "\n\n".join(parts)


def synthesize_news(cluster_posts: List[Dict], mode: str = 'A') -> Tuple[str, Dict]:
    """
    Генерация итогового текста по кластеру.

    :param cluster_posts: список постов кластера (post_id, channel_tg_id, content, views, reactions, comments, forwards)
    :param mode: 'A' — перефразирование якоря + детали; 'B' — синтез с нуля по всем источникам
    :return: (text, meta)
    """
    meta: Dict = {"mode": mode, "posts": len(cluster_posts or [])}
    if not cluster_posts:
        return "", meta

    # Нормализуем и отсортируем по важности (views/reactions)
    posts = list(cluster_posts)
    posts.sort(key=lambda p: (p.get('views', 0), p.get('reactions', 0), len((p.get('content') or ''))), reverse=True)

    # Подрежем вход до разумного размера для промпта
    max_posts = 10
    posts = posts[:max_posts]

    if mode.upper() == 'A':
        anchor = _select_anchor_post(posts)
        others = [p for p in posts if p.get('post_id') != anchor.get('post_id')]
        # Подрежем тексты
        anchor['content'] = _truncate_text(anchor.get('content') or '', 2000)
        for p in others:
            p['content'] = _truncate_text(p.get('content') or '', 800)
        system, user = _build_prompt_mode_a(anchor, others)
        # Кэш по (cluster_id отсутствует здесь) — кэшируем на уровне вызова synthesize_news
        text, model_used = _llm_generate(system, user)
        if not text:
            text = _fallback_generate_mode_a(anchor, others)
        meta["model"] = model_used or "fallback"
        meta["prompt_len"] = len(user)
        return text, meta

    # Mode B
    for p in posts:
        p['content'] = _truncate_text(p.get('content') or '', 1200)
    system, user = _build_prompt_mode_b(posts)
    text, model_used = _llm_generate(system, user)
    if not text:
        text = _fallback_generate_mode_b(posts)
    meta["model"] = model_used or "fallback"
    meta["prompt_len"] = len(user)
    return text, meta


def _prompt_hash(system: str, user: str) -> str:
    s = f"v1|{system}\n\n{user}".encode('utf-8', errors='ignore')
    return hashlib.sha256(s).hexdigest()


def synthesize_news_with_cache(cluster_id: int, cluster_posts: List[Dict], mode: str = 'A') -> Tuple[str, Dict]:
    """
    Обёртка над synthesize_news с кэшированием результата в БД по (cluster_id, mode, prompt_hash).
    """
    # Подготовка текста промпта для хэширования
    preview_posts = list(cluster_posts)
    preview_posts.sort(key=lambda p: (p.get('views', 0), p.get('reactions', 0), len((p.get('content') or ''))), reverse=True)
    preview_posts = preview_posts[:10]

    if mode.upper() == 'A':
        anchor = _select_anchor_post(preview_posts)
        others = [p for p in preview_posts if p.get('post_id') != anchor.get('post_id')]
        anchor_text = _truncate_text(anchor.get('content') or '', 2000)
        other_text = "\n".join(_truncate_text(p.get('content') or '', 800) for p in others)
        sys_preview, user_preview = _build_prompt_mode_a(
            {**anchor, 'content': anchor_text},
            [{**p, 'content': _truncate_text(p.get('content') or '', 800)} for p in others]
        )
    else:
        sys_preview, user_preview = _build_prompt_mode_b([
            {**p, 'content': _truncate_text(p.get('content') or '', 600)} for p in preview_posts
        ])

    phash = _prompt_hash(sys_preview, user_preview)

    # Чтение из кэша
    cached = get_cached_generated_article(cluster_id, mode.upper(), phash)
    if cached and (cached.get('text') or '').strip():
        logger.info(f"[SYNTH][CACHE] hit cluster={cluster_id} mode={mode} hash={phash[:8]}... id={cached.get('id')}")
        return cached['text'], {"mode": mode, "posts": len(cluster_posts or []), "cached": True, "cache_id": cached.get('id'), "model": cached.get('model_name'), "prompt_len": len(user_preview)}

    # Генерация (внутри повторим логику synthesize_news, чтобы иметь доступ к system/user)
    if mode.upper() == 'A':
        anchor = _select_anchor_post(preview_posts)
        others = [p for p in preview_posts if p.get('post_id') != anchor.get('post_id')]
        system, user = _build_prompt_mode_a(
            {**anchor, 'content': _truncate_text(anchor.get('content') or '', 2000)},
            [{**p, 'content': _truncate_text(p.get('content') or '', 800)} for p in others]
        )
    else:
        system, user = _build_prompt_mode_b([
            {**p, 'content': _truncate_text(p.get('content') or '', 600)} for p in preview_posts
        ])

    text, model_used = _llm_generate(system, user)
    if not text:
        # Фолбэк без кэширования модели
        if mode.upper() == 'A':
            text = _fallback_generate_mode_a(_select_anchor_post(preview_posts), [p for p in preview_posts if p.get('post_id') != _select_anchor_post(preview_posts).get('post_id')])
        else:
            text = _fallback_generate_mode_b(preview_posts)
        text = _normalize_output(text)
        return text, {"mode": mode, "posts": len(cluster_posts or []), "cached": False, "model": "fallback", "prompt_len": len(user)}

    # Запись в кэш
    try:
        normalized = _normalize_output(text)
        cache_id = put_cached_generated_article(
            cluster_id=cluster_id,
            mode=mode.upper(),
            prompt_hash=phash,
            text=normalized,
            model_name=model_used,
            facts_json=None,
        )
        logger.info(f"[SYNTH][CACHE] put cluster={cluster_id} mode={mode} hash={phash[:8]}... id={cache_id}")
    except Exception as e:
        logger.warning(f"[SYNTH][CACHE] put failed: {e}")

    return normalized, {"mode": mode, "posts": len(cluster_posts or []), "cached": False, "model": model_used, "prompt_len": len(user)}


def _normalize_output(text: str) -> str:
    """
    Пост-обработка вывода: удаляем построчные вставки вида "Источник ..." внутри тела,
    схлопываем пустые строки, оставляем (или добавляем) секцию Источники в конце как есть.
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
        # удаляем строки начинающиеся на "Источник " или markdown-маркеры
        if re.match(r'^\s*источник\b', low, flags=re.IGNORECASE):
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

    body = "\n".join(cleaned).strip()
    tail = "\n".join(sources_block).strip()
    if tail:
        return (body + "\n\n" + tail).strip()
    return body


