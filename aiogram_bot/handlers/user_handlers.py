import logging

from database.db_connection import add_user, insert_ad_label, record_user_feedback, \
    get_cluster_posts_full, get_cluster_metadata, \
    get_channel_tg_id_for_post, get_post_content_by_id, get_engagement_score_score_by_post_id, \
    get_cluster_id_by_post, get_channel_reputation_by_post_id, get_ad_label_for_post, \
    get_recent_ad_decisions, get_system_param, get_generated_articles_by_date
from helpers.html_utils import fix_html_tags
from datetime import timedelta
from aiogram import Router, Dispatcher
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command

# Инициализируем роутер уровня модуля
router = Router()
dp = Dispatcher()
logger = logging.getLogger(__name__) # Создание логгера под файл

@router.message(CommandStart())
async def cmd_start(message: Message):
    user_tg_id : int = message.from_user.id
    username : str = message.from_user.username
    first_name : str = message.from_user.first_name
    full_name : str = message.from_user.full_name
    logger.debug("Запрос на добавление пользователя - ", user_tg_id, full_name)
    add_user(user_tg_id, username, first_name, full_name)


@router.callback_query(lambda c: c.data.startswith(('like_', 'dislike_')))
async def process_like_dislike(callback_query: CallbackQuery):
    action, post_id = callback_query.data.split('_')  # Разделяем "like_123" → ("like", "123")
    user_id = callback_query.from_user.id
    try:
        post_id_int = int(post_id)
    except ValueError:
        await callback_query.answer("Некорректный ID поста", show_alert=True)
        return
    try:
        if action in ("like", "dislike"):
            record_user_feedback(user_id, post_id_int, action)
            if action == "like":
                await callback_query.answer("Спасибо за лайк! ❤️")
            else:
                await callback_query.answer("Учтём ваш дизлайк", show_alert=False)
        else:
            await callback_query.answer("Неизвестное действие", show_alert=True)
    except Exception as e:
        logger.error("Ошибка сохранения фидбека: %s", str(e))
        await callback_query.answer("Ошибка, попробуйте позже", show_alert=True)


@router.message(Command("label"))
async def cmd_label(message: Message):
    """
    Ручная разметка постов как реклама/не реклама.
    Использование: /label <post_id> <ad|not_ad|ambiguous> [notes]
    """
    try:
        parts = (message.text or "").split(maxsplit=3)
        if len(parts) < 3:
            await message.reply("Использование: /label <post_id> <ad|not_ad|ambiguous> [notes]")
            return
        _, post_id_str, label = parts[:3]
        notes = parts[3] if len(parts) > 3 else None
        post_id = int(post_id_str)
        if label not in ("ad", "not_ad", "ambiguous"):
            await message.reply("label должен быть ad|not_ad|ambiguous")
            return
        insert_ad_label(post_id, label, reviewer_tg_id=message.from_user.id, notes=notes, source='admin')
        await message.reply(f"OK: пост {post_id} размечен как {label}")
    except Exception as e:
        logger.error("Ошибка ручной разметки: %s", str(e))
        await message.reply("Ошибка обработки команды")


@router.message(Command("info"))
async def cmd_info(message: Message):
    """"
    Отправляет основную информацию о посте

    Использование:
            1. /info <post_id> [notes]
            2. Реплай на пост с командой /info
    """
    try:
        if message.reply_to_message:
            # Режим: админ отвечает на сгенерированную новость бота → показать инфо по кластеру
            replied_msg = message.reply_to_message
            replied_msg_date = replied_msg.date
            # Ищем по времени с учётом смещения
            offset_minutes = int(get_system_param('local_tz_offset_minutes', '240'))
            adjusted_date = replied_msg_date + timedelta(minutes=offset_minutes)

            cluster_id = None
            candidates = get_generated_articles_by_date(str(adjusted_date))
            if candidates:
                if len(candidates) == 1:
                    cluster_id = candidates[0]['cluster_id']
                else:
                    text_source = (replied_msg.text or replied_msg.caption or "").strip().replace('\n', ' ')
                    prefix_len = int(get_system_param('generated_lookup_prefix_len', '10'))
                    prefix = (text_source[:prefix_len] if text_source else "")
                    matched = None
                    for candidate in candidates:
                        cand_text = (candidate.get('text') or '').strip().replace('\n', ' ')
                        if cand_text.startswith(prefix) and prefix:
                            matched = candidate
                            break
                    if matched:
                        cluster_id = matched['cluster_id']
            if not candidates or not cluster_id:
                await message.reply("Не удалось найти кластер по этому сообщению"
                                    f"\nИсходная дата: {replied_msg_date}"
                                    f"\nСмещение: +{offset_minutes}мин"
                                    f"\nДата после смещения: {adjusted_date}")
                return

            meta = get_cluster_metadata(cluster_id) or {}
            posts = get_cluster_posts_full(cluster_id) or []

            total_views = sum(p.get('views', 0) for p in posts)
            total_reacts = sum(p.get('reactions', 0) for p in posts)
            total_comments = sum(p.get('comments', 0) for p in posts)
            total_forwards = sum(p.get('forwards', 0) for p in posts)
            count = max(len(posts), 1)

            # Подборка первых 5 постов
            lines = []
            for p in posts[:5]:
                snippet = (p.get('content') or "").strip().replace('\n', ' ')
                # Исправляем HTML-теги и безопасно обрезаем текст
                snippet = fix_html_tags(snippet, max_length=150)
                lines.append(
                    f"• <b>#{p['post_id']}</b> | ch:<code>{p['channel_tg_id']}</code> | 👁️ {p['views']} | ❤ {p['reactions']} | 💬 {p['comments']} | 🔁 {p['forwards']}\n"
                    f"  {snippet}"
                )

            header = (
                f"<b>Кластер #{cluster_id}</b>\n"
                f"Статус: <code>{(meta.get('status') or 'unknown') if meta else 'unknown'}</code>\n"
                f"Создан: <code>{meta.get('created_at')}</code> | Истекает: <code>{meta.get('expires_at')}</code>\n"
                f"Постов: <b>{len(posts)}</b>\n\n"
            )
            agg = (
                f"<b>Суммарные метрики</b>: 👁️ {total_views} | ❤ {total_reacts} | 💬 {total_comments} | 🔁 {total_forwards}\n"
                f"<b>Средние на пост</b>: 👁️ {total_views//count} | ❤ {total_reacts//count} | 💬 {total_comments//count} | 🔁 {total_forwards//count}\n\n"
            )
            body = "\n\n".join(lines) if lines else "Нет постов в кластере"

            await message.reply(header + agg + body, parse_mode='HTML')
            return

        # Режим: /info <post_id>
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 2:
            await message.reply("Использование: /info <post_id> [notes]")
            return
        _, post_id_str = parts[:2]
        _notes = parts[2] if len(parts) > 2 else None  # зарезервировано на будущее

        try:
            post_id = int(post_id_str)
        except ValueError:
            await message.reply("post_id должен быть числом")
            return

        # Проверяем существование поста
        channel_tg_id = get_channel_tg_id_for_post(post_id)
        if channel_tg_id is None:
            await message.reply(f"❌ Пост с ID <code>{post_id}</code> не найден в базе данных", parse_mode='HTML')
            return

        content = get_post_content_by_id(post_id) or ""
        cluster_id = get_cluster_id_by_post(post_id)
        engagement = get_engagement_score_score_by_post_id(post_id) or 0.0
        reputation = get_channel_reputation_by_post_id(post_id) or 0.5
        label_info = get_ad_label_for_post(post_id)

        # Фильтруем последние решения по этому посту
        decisions = [d for d in (get_recent_ad_decisions(limit=200) or []) if d.get('post_id') == post_id]
        decisions = decisions[:5]

        snippet = content.strip().replace('\n', ' ')
        # Исправляем HTML-теги и безопасно обрезаем текст
        snippet = fix_html_tags(snippet, max_length=150)

        label_line = "—"
        if label_info:
            label_line = f"{label_info['label']} (by: <code>{label_info.get('reviewer_tg_id') or 'n/a'}</code>)"

        dec_lines = []
        for d in decisions:
            dec_lines.append(
                f"• [stage {d['stage']}] {d['decision']} | score={d['score']:.3f} | model={d.get('model_version') or '-'}"
            )
        decisions_block = "\n".join(dec_lines) if dec_lines else "нет данных"

        reply_text = (
            f"<b>Пост #{post_id}</b>\n"
            f"Канал: <code>{channel_tg_id}</code>\n"
            f"Кластер: <b>{cluster_id if cluster_id is not None else '—'}</b>\n"
            f"Репутация канала: <b>{reputation:.3f}</b>\n"
            f"Engagement score: <b>{engagement:.3f}</b>\n"
            f"Разметка (ad): <b>{label_line}</b>\n\n"
            f"<b>Текст</b>: {snippet}\n\n"
            f"<b>Последние решения классификатора</b>:\n{decisions_block}"
        )
        await message.reply(reply_text, parse_mode='HTML')
    except Exception as e:
        logger.error("Ошибка получения информации о посте: %s", str(e))