import logging

from AI.Ai_Functions import get_embedding, is_similar_to_existing
from aiogram_bot.keyboards import get_feedback_keyboard
from database.db_connection import *
from database.db_connection import add_post
from helpers.helpers import remove_file

from aiogram import types
from telethon import utils
from aiogram.enums import ParseMode
from aiogram.utils.media_group import MediaGroupBuilder

bot = None
def set_bot(b):
    global bot
    bot = b
logger = logging.getLogger(__name__)


# TODO: Имеется проблема с видео: нет превью и размер превью видео маленький квадратик
# Обработчик для сообщений-альбомов
async def album_handler(event):
    logger.info("Получен альбом из канала")
    media_group = MediaGroupBuilder(caption=f'{event.text}')
    filename_list = []

    msg_from_channel_id = event.messages[0].peer_id.channel_id
    # Получаем категории канала
    channel_categories = get_channel_category(msg_from_channel_id)
    logger.info("ID канала: %s, Категории канала: %s", msg_from_channel_id, channel_categories)
    if not channel_categories:
        logger.warning("Канал %s не имеет категорий", msg_from_channel_id)
        return
        
    target_users = get_category_users(tuple(channel_categories))
    logger.info("Пользователи для отправки альбома: %s", target_users)
    if not target_users:
        logger.info("Нет пользователей для отправки альбома")
        return

    for file in event.messages:
        filename = await file.download_media()
        filename_list.append(filename)
        # Добавление в MediaGroup видео
        if utils.is_video(filename):
            media_group.add(type='video',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)
        # Добавление в MediaGroup фото
        elif utils.is_image(filename):
            media_group.add(type='photo',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)

    for user in target_users:
        try:
            await bot.send_media_group(chat_id=user,
                                       media=media_group.build())
            logger.info("Альбом успешно отправлен пользователю %s", user)
        except Exception as e:
            logger.error("Ошибка отправки альбома пользователю %s: %s", user, str(e))
        finally:
            remove_file(filename_list)


# Обработчик для обычных сообщений
async def default_handler(event):
    logger.info("Получено новое сообщение")
    message_text = event.message.text
    # Получаем ID канала
    msg_from_channel_id = event.peer_id.channel_id
    # Записываем в БД эмбеддинг и проверяем на схожесть пост
    text_encoding = get_embedding(message_text)
    if text_encoding is not None:
        is_similar, similarity_percent = is_similar_to_existing(text_encoding)
        if not is_similar:
            logger.info("Схожесть поста меньше порогового значения, считается уникальным. Процент схожести: %s", similarity_percent)
            add_post(msg_from_channel_id, message_text, text_encoding.tolist())
        else:
            logger.info("Данный пост схож с существующим в БД. Процент схожести: %s", similarity_percent)
            return
    # Получаем категории канала
    channel_categories = get_channel_category(msg_from_channel_id)
    logger.info("ID канала: %s, Категории канала: %s", msg_from_channel_id, channel_categories)
    if not channel_categories:
        logger.warning("Канал %s не имеет категорий", msg_from_channel_id)
        return
    
    # Получаем пользователей для отправки
    target_users = get_category_users(tuple(channel_categories))
    logger.info("Пользователи для отправки: %s", target_users)
    if not target_users:
        logger.info("Нет пользователей для отправки сообщения")
        return

    # Проверка наличия медиафайлов в сообщении
    # TODO: Можно оптимизировать получая объединив в один sql-запрос get_category_users & get_channel_category
    # Отправка группы фото и текста в одном сообщении
    # TODO @INCLUDE: В telethon нет поддержки
    if event.media:
        if not event.grouped_id:
            filename = await event.download_media()
            logger.info("Скачан медиафайл: %s", filename)
            
            try:
                # Отправка сообщения с видео
                if utils.is_video(filename):
                    for user in target_users:
                        await bot.send_video(chat_id=user,
                                             video=types.FSInputFile(path=filename),
                                             caption=f'{event.text}',
                                             parse_mode=ParseMode.HTML,
                                             reply_markup=get_feedback_keyboard(event.id))
                        logger.info("Видео отправлено пользователю %s", user)
                # Отправка сообщения с картинкой
                elif utils.is_image(filename):
                    for user in target_users:
                        await bot.send_photo(chat_id=user,
                                             photo=types.FSInputFile(path=filename),
                                             caption=f'{event.text}',
                                             parse_mode=ParseMode.HTML,
                                             reply_markup=get_feedback_keyboard(event.id))
                        logger.info("Фото отправлено пользователю %s", user)
                # Отправка сообщения с GIF
                elif utils.is_gif(filename):
                    for user in target_users:
                        await bot.send_animation(chat_id=user,
                                                 animation=types.FSInputFile(path=filename),
                                                 caption=f'{event.text}',
                                                 parse_mode=ParseMode.HTML,
                                                 reply_markup=get_feedback_keyboard(event.id))
                        logger.info("GIF отправлен пользователю %s", user)
            except Exception as e:
                logger.error("Ошибка отправки медиафайла: %s", str(e))
            finally:
                remove_file(filename)
    else:
        # Отправка только текста, если медиафайлов нет
        for user in target_users:
            try:
                await bot.send_message(chat_id=user,
                                       text=f'{event.text}',
                                       parse_mode=ParseMode.HTML,
                                       reply_markup=get_feedback_keyboard(event.id))
                logger.info("Текстовое сообщение отправлено пользователю %s", user)
            except Exception as e:
                logger.error("Ошибка отправки текстового сообщения пользователю %s: %s", user, str(e))
