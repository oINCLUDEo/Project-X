from telethon import events
from telethon_client.handlers.album_handler import album_handler
from telethon_client.handlers.default_handler import default_handler


def setup_handlers(client, channels, bot):
    client.add_event_handler(lambda event: album_handler(event, bot), events.Album(chats=channels))
    client.add_event_handler(lambda event: default_handler(event, bot), events.NewMessage(chats=channels))
