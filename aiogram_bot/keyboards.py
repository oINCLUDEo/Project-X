from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def get_feedback_keyboard(post_id):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="👍 Лайк", callback_data=f"like_{post_id}"),
            InlineKeyboardButton(text="👎 Дизлайк", callback_data=f"dislike_{post_id}"),
        ]
    ])
    return keyboard


def get_main_menu_keyboard():
    """Клавиатура главного меню для зарегистрированных пользователей"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔥 Мой профиль")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="👥 Пригласить друзей"), KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


def get_onboarding_keyboard():
    """Вводная клавиатура для новых пользователей"""
    # TODO: В будущем кнопка <Начать> должна вести не на onboarding_complete, а на onboarding_start с выбором категорий и тд
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🚀 Начать", callback_data="onboarding_complete"),
            InlineKeyboardButton(text="📖 Как это работает", callback_data="onboarding_how_it_works")
        ]
    ])
    return keyboard
