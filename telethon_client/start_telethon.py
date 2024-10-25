import logging

from telethon import events
from telethon_client.handlers.parser import *

logger = logging.getLogger(__name__) # Создание логгера под файл


def setup_handlers(client, channels):
    client.add_event_handler(album_handler, events.Album(chats=channels))
    client.add_event_handler(default_handler, events.NewMessage(chats=channels))
