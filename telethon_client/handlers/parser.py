from database.db_connection import *
from helpers.helpers import remove_file
from AI.Ai_Functions import classify_post

from aiogram import types
from telethon import utils
from aiogram.enums import ParseMode
from aiogram.utils.media_group import MediaGroupBuilder

bot = None
def set_bot(b):
    global bot
    bot = b


# TODO: Имеется проблема с видео: нет превью и размер превью видео маленький квадратик
# Обработчик для сообщений-альбомов
async def album_handler(event):
    media_group = MediaGroupBuilder(caption=f'{event.text}')
    filename_list = []
    msg_from_channel_id = (await event.get_sender()).id
    target_users = get_category_users(tuple(get_channel_category(msg_from_channel_id)))
    for file in event.messages:
        filename = await file.download_media()
        filename_list.append(filename)
        if utils.is_video(filename):
            media_group.add(type='video',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)
        elif utils.is_image(filename):
            media_group.add(type='photo',
                            media=types.FSInputFile(path=filename),
                            parse_mode=ParseMode.HTML)
    for user in target_users:
        await bot.send_media_group(chat_id=user, media=media_group.build())
    remove_file(filename_list)


# Обработчик для обычных сообщений
async def default_handler(event):
    post_categories = classify_post(event.text)["labels"][0]
    # Проверка наличия медиафайлов в сообщении
    if event.media:
        if not event.grouped_id:
            msg_from_channel_id = (await event.get_sender()).id
            # TODO: Можно оптимизировать получая объединив в один sql-запрос get_category_users & get_channel_category
            target_users = get_category_users(tuple(get_channel_category(msg_from_channel_id)))
            filename = await event.download_media()
            # Отправка группы фото и текста в одном сообщении
            # TODO @INCLUDE: В telethon нет поддержки
            if utils.is_video(filename):
                for user in target_users:
                    await bot.send_video(chat_id=user,
                                         video=types.FSInputFile(path=filename),
                                         caption=f'{event.text}',
                                         parse_mode=ParseMode.HTML)
            elif utils.is_image(filename):
                for user in target_users:
                    await bot.send_photo(chat_id=user,
                                         photo=types.FSInputFile(path=filename),
                                         caption=f'{event.text}',
                                         parse_mode=ParseMode.HTML)
            elif utils.is_gif(filename):
                for user in target_users:
                    await bot.send_animation(chat_id=user,
                                             animation=types.FSInputFile(path=filename),
                                             caption=f'{event.text}',
                                             parse_mode=ParseMode.HTML)
            remove_file(filename)
    else:
        msg_from_channel_id = event.peer_id.channel_id
        target_users = get_category_users(tuple(get_channel_category(msg_from_channel_id)))
        # Отправка только текста, если медиафайлов нет
        for user in target_users:
            await bot.send_message(chat_id=user,
                                   text=f'Пост имеет категорию - {post_categories}\n {event.text}',
                                   parse_mode=ParseMode.HTML)
