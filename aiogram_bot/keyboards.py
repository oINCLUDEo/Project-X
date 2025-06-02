from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_feedback_keyboard(post_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Лайк", callback_data=f"like_{post_id}"),
            InlineKeyboardButton(text="👎 Дизлайк", callback_data=f"dislike_{post_id}"),
        ]
    ])
    return keyboard