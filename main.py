import os
import asyncio
from helpers import remove_file
from db_connection import get_users, add_user

from aiogram.utils.media_group import MediaGroupBuilder
from telethon import TelegramClient, events, utils
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from dotenv import load_dotenv

# Загрузка переменных окружения из файла .env
load_dotenv()
api_id = int(os.getenv('API_ID'))
api_hash = os.getenv('API_HASH')
bot_token = os.getenv('BOT_TOKEN')

# Создание бота и диспетчера
bot = Bot(token=bot_token)
dp = Dispatcher()

client = TelegramClient('news_parser', api_id, api_hash)
client.parse_mode = 'html'

users = get_users()


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
    for user in users:
        await bot.send_media_group(chat_id=user, media=media_group.build())
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
                for user in users:
                    await bot.send_video(chat_id=user,
                                         video=types.FSInputFile(path=filename),
                                         caption=f'{event.text}',
                                         parse_mode=ParseMode.HTML)
            elif utils.is_image(filename):
                for user in users:
                    await bot.send_photo(chat_id=user,
                                         photo=types.FSInputFile(path=filename),
                                         caption=f'{event.text}',
                                         parse_mode=ParseMode.HTML)
            elif utils.is_gif(filename):
                for user in users:
                    await bot.send_animation(chat_id=user,
                                             animation=types.FSInputFile(path=filename),
                                             caption=f'{event.text}',
                                             parse_mode=ParseMode.HTML)
            remove_file(filename)
    else:
        # Отправка только текста, если медиафайлов нет
        for user in users:
            await bot.send_message(chat_id=user,
                                   text=f'{event.text}',
                                   parse_mode=ParseMode.HTML)


@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    print(add_user(message.from_user.id))


async def start_telethon():
    print("Channels parser started")
    await client.start()
    await client.run_until_disconnected()


async def start_aiogram():
    print("Bot started")
    await dp.start_polling(bot)


async def main():
    await asyncio.gather(start_telethon(), start_aiogram())

# Асинхронный запуск работает, но стоило бы рассмотреть подробнее его работу.
# Фрагменты кода функций запуска взяты из GPT

if __name__ == '__main__':
    # Получение текущего цикла событий
    loop = asyncio.get_event_loop()

    # Запуск основной функции в текущем цикле событий
    loop.run_until_complete(main())
