import logging
import os
from typing import Dict, Any
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Константы для позиционирования элементов
LIKES_POS = (213.37, 357)
DAYS_POS = (513.34, 357)
USERNAME_POS = (926, 716)
CATEGORIES_POS = (82, 880)
PHRASE_POS = (172, 780)

# Сдвиг координат при увеличении количества цифр
DIGIT_OFFSET = -17.165

# Цвета
TEXT_COLOR = '#FEFBEA'
ACCENT_COLOR = '#A10304'

# Размеры шрифтов
FONT_MANJARI_LARGE = 63
FONT_MANJARI_MEDIUM = 48
FONT_JURA_MEDIUM = 48
FONT_JURA_SMALL = 28

# Лимиты текста
MAX_PHRASE_LENGTH = 80
PHRASE_TRUNCATE_LENGTH = 77


def _load_font(font_name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """
    Загружает шрифт с fallback механизмом.
    
    Пытается загрузить шрифт из папки assets в следующем порядке:
    1. assets/{font_name}.ttf
    2. assets/{font_name}.ttc
    3. assets/{font_name}-Regular.ttf
    4. assets/{font_name}-Bold.ttf
    
    Если ни один шрифт не найден, использует default font.
    
    Args:
        font_name: Название шрифта
        size: Размер шрифта
        
    Returns:
        Font object (FreeTypeFont или ImageFont)
    """
    font_paths = [
        f'assets/{font_name}.ttf',
        f'assets/{font_name}.ttc',
        f'assets/{font_name}-Regular.ttf',
        f'assets/{font_name}-Bold.ttf',
    ]
    
    for path in font_paths:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except (OSError, IOError) as e:
            logger.debug(f"Не удалось загрузить шрифт {path}: {e}")
            continue
    
    logger.warning(f"Шрифт {font_name} не найден, используется шрифт по умолчанию")
    return ImageFont.load_default()


def _calculate_text_offset(text: str, base_pos: tuple[float, float], font: ImageFont.FreeTypeFont | ImageFont.ImageFont, max_text: str = "999 days") -> tuple[float, float]:
    """
    Вычисляет смещение координат для центрирования текста с переменной длиной.
    
    Измеряет фактическую ширину текста в пикселях и корректирует позицию
    для центрирования относительно максимального текста.
    
    Args:
        text: Текст для отрисовки
        base_pos: Базовая позиция (x, y) - позиция максимального текста
        font: Шрифт для измерения ширины
        max_text: Максимальный текст для центрирования (по умолчанию "999 days")
        
    Returns:
        Корректированные координаты (x, y)
    """
    try:
        # Измеряем ширину текущего и максимального текста
        current_width = font.getlength(text)
        max_width = font.getlength(max_text)
        
        # Вычисляем разницу и смещаем влево для центрирования
        x, y = base_pos
        width_diff = max_width - current_width
        # Сдвигаем влево на половину разницы для центрирования
        offset = width_diff / 2
        return (x + offset, y)
    except Exception:
        # В случае ошибки возвращаем исходную позицию
        return base_pos


def generate_profile_png(template_path: str, output_path: str, user_data: Dict[str, Any]) -> bool:
    """
    Генерирует персонализированный PNG профиль из шаблона.
    
    Args:
        template_path: Путь к PNG шаблону
        output_path: Путь сохранения PNG
        user_data: Словарь с данными пользователя:
            - username (str): Имя пользователя (без @)
            - likes (int): Количество поставленных лайков
            - days (int): Дней с регистрации
            - categories (list): Список категорий
            - phrase (str): Любимая фраза или bio
            
    Returns:
        True если генерация успешна, False иначе
    """
    try:
        # Валидация входных данных
        if not os.path.exists(template_path):
            logger.error(f"Шаблон не найден: {template_path}")
            return False
        
        if not user_data:
            logger.error("Пустой словарь user_data")
            return False
        
        # Загрузка шаблона
        img = Image.open(template_path)
        draw = ImageDraw.Draw(img)
        
        # Загрузка шрифтов
        font_manjari_large = _load_font('Manjari', FONT_MANJARI_LARGE)
        font_manjari_medium = _load_font('Manjari', FONT_MANJARI_MEDIUM)
        font_jura_small = _load_font('Jura', FONT_JURA_SMALL)
        font_jura_medium = _load_font('Jura', FONT_JURA_MEDIUM)
        
        # Подготовка данных для статистики
        likes_val = str(user_data.get('likes', 0))
        days_val = f"{user_data.get('days', 0)} days"
        
        # Отрисовка статистики с учетом смещения длины
        # Для "days" центрируем относительно "999 days"
        likes_pos = _calculate_text_offset(likes_val, LIKES_POS, font_manjari_large, "999")
        days_pos = _calculate_text_offset(days_val, DAYS_POS, font_manjari_large, "999 days")
        
        draw.text(likes_pos, likes_val, fill=TEXT_COLOR, font=font_manjari_large)
        draw.text(days_pos, days_val, fill=TEXT_COLOR, font=font_manjari_large)
        
        # Отрисовка имени пользователя
        username = f"@{user_data.get('username', 'user')}"
        draw.text(USERNAME_POS, username, fill=TEXT_COLOR, font=font_manjari_medium)
        
        # Отрисовка категорий
        categories = user_data.get('categories', [])
        categories_str = ' '.join(categories) if isinstance(categories, list) else str(categories)
        if categories_str:
            draw.text(CATEGORIES_POS, categories_str, fill=TEXT_COLOR, font=font_jura_medium)
        
        # Отрисовка фразы
        phrase = user_data.get('phrase', '')
        if phrase:
            # Обрезаем если слишком длинная
            if len(phrase) > MAX_PHRASE_LENGTH:
                phrase = phrase[:PHRASE_TRUNCATE_LENGTH] + '...'
            draw.text(PHRASE_POS, phrase, fill=ACCENT_COLOR, font=font_jura_small)
        
        # Сохранение изображения
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        img.save(output_path, 'PNG')
        
        logger.info(f"Профиль PNG успешно сгенерирован: {output_path}")
        return True
        
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {e}")
        return False
    except (IOError, OSError) as e:
        logger.error(f"Ошибка ввода-вывода при генерации профиля: {e}")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка при генерации профиля PNG: {e}", exc_info=True)
        return False
