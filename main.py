import os
from helpers import remove_file

from aiogram.utils.media_group import MediaGroupBuilder
from telethon import TelegramClient, events, utils
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')

users = ['734313964']  # затычка вместо базы данных с пользователями

# Создание бота и диспетчера
bot = Bot(token=bot_token)
dp = Dispatcher()

client = TelegramClient('news_parser', api_id, api_hash)


# TODO: Имеется проблема с видео: нет превью и размер превью видео маленький квадратик
@client.on(events.Album(chats=[1074845292, 1457994499, 2228559702]))
async def albums_handler(event):
    media_group = MediaGroupBuilder(caption=f'{event.text}')
    filename_list = []

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
        elif utils.is_gif(filename):
            await bot.send_animation(chat_id=users[0],
                                     animation=types.FSInputFile(path=filename),
                                     caption=f'{event.raw_text}',
                                     parse_mode=ParseMode.HTML)

    await bot.send_media_group(chat_id=users[0], media=media_group.build())
    remove_file(filename_list)


@client.on(events.NewMessage(chats=[1074845292, 1457994499, 2228559702]))
async def my_event_handler(event):
    # Проверка наличия медиафайлов в сообщении
    if event.media:
        if not event.grouped_id:
            filename = await event.download_media()
            # Отправка группы фото и текста в одном сообщении
            # TODO @INCLUDE: В telethon нет поддержки
            if utils.is_video(filename):
                await bot.send_video(chat_id=users[0],
                                     video=types.FSInputFile(path=filename),
                                     caption=f'{event.raw_text}',
                                     parse_mode=ParseMode.HTML)
            elif utils.is_image(filename):
                await bot.send_photo(chat_id=users[0],
                                     photo=types.FSInputFile(path=filename),
                                     caption=f'{event.raw_text}',
                                     parse_mode=ParseMode.HTML)
            elif utils.is_gif(filename):
                await bot.send_animation(chat_id=users[0],
                                         animation=types.FSInputFile(path=filename),
                                         caption=f'{event.raw_text}',
                                         parse_mode=ParseMode.HTML)
            remove_file(filename)
    else:
        # Отправка только текста, если медиафайлов нет
        # await bot.send_message(chat_id=users[0], text=f'{event.raw_text}')
        await bot.send_message(chat_id=users[0],
                               text=f'{event.text}',
                               parse_mode=ParseMode.HTML)


client.parse_mode = 'html'
client.start()
# запуск в режиме “пока есть хоть одна работающая функция внутри”:
client.run_until_disconnected()
