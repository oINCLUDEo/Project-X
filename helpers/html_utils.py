import re
import logging
from html.parser import HTMLParser
from html import escape

logger = logging.getLogger(__name__)


class TelegramHTMLParser(HTMLParser):
    """
    Парсер HTML для Telegram с поддержкой только разрешенных тегов.
    """
    
    ALLOWED_TAGS = {'b', 'i', 'u', 's', 'a', 'code', 'pre', 'blockquote', 'tg-spoiler'}
    ALLOWED_ATTRS = {'href'}  # только для тега <a>
    
    def __init__(self):
        super().__init__()
        self.result = []
        self.open_tags = []
        self.max_length = None
        self.current_length = 0
        self.truncated = False
    
    def handle_starttag(self, tag, attrs):
        if tag not in self.ALLOWED_TAGS:
            return
            
        # Обрабатываем атрибуты
        if tag == 'a':
            # Для ссылок оставляем только href
            href = None
            for attr_name, attr_value in attrs:
                if attr_name == 'href':
                    href = attr_value
                    break
            if href:
                tag_html = f'<a href="{escape(href)}">'
            else:
                return  # Не добавляем ссылку без href
        elif tag == 'tg-spoiler':
            tag_html = '<tg-spoiler>'
        else:
            tag_html = f'<{tag}>'
        
        # Проверяем длину перед добавлением тега
        if self.current_length + len(tag_html) > self.max_length:
            self.truncated = True
            return
            
        self.result.append(tag_html)
        self.current_length += len(tag_html)
        self.open_tags.append(tag)
    
    def handle_endtag(self, tag):
        if tag not in self.ALLOWED_TAGS:
            return
            
        # Закрываем тег только если он был открыт
        if tag in self.open_tags:
            tag_html = f'</{tag}>'
            self.result.append(tag_html)
            self.current_length += len(tag_html)
            self.open_tags.remove(tag)
            # Проверяем длину перед добавлением закрывающего тега
            if self.current_length > self.max_length:
                self.truncated = True
                return
    
    def handle_data(self, data):
        if self.truncated:
            return
            
        remaining = self.max_length - self.current_length
        if remaining <= 0:
            self.truncated = True
            return

        if len(data) > remaining:
            data = data[:remaining]
            self.truncated = True
            if remaining > 0:
                data += "..."
        
        self.result.append(data)
        self.current_length += len(data)
    
    def handle_entityref(self, name):
        # Обрабатываем HTML entities
        if self.truncated:
            return
            
        entity_html = f'&{name};'
        if self.current_length + len(entity_html) > self.max_length:
            self.truncated = True
            return
            
        self.result.append(entity_html)
        self.current_length += len(entity_html)
    
    def handle_charref(self, name):
        # Обрабатываем числовые HTML entities
        if self.truncated:
            return
            
        entity_html = f'&#{name};'
        if self.current_length + len(entity_html) > self.max_length:
            self.truncated = True
            return
            
        self.result.append(entity_html)
        self.current_length += len(entity_html)
    
    def get_result(self):
        # Закрываем все открытые теги
        while self.open_tags:
            tag = self.open_tags.pop()
            tag_html = f'</{tag}>'
            self.result.append(tag_html)
            self.current_length += len(tag_html)
            # Проверяем, не превысим ли лимит при закрытии тегов
            if self.current_length > self.max_length:
                break

        return ''.join(self.result)


def fix_html_tags(text: str, max_length: int = None) -> str:
    """
    Исправляет незакрытые HTML-теги в тексте и обрезает его безопасно.
    
    Args:
        text: Исходный текст с возможными HTML-тегами
        max_length: Максимальная длина текста (если None, не обрезается)
    
    Returns:
        Исправленный текст с корректными HTML-тегами
    """
    if not text:
        return ""
    
    parser = TelegramHTMLParser()
    parser.max_length = max_length
    parser.feed(text)
    return parser.get_result()


def normalize_html_for_telegram(html: str, has_media: bool = False) -> str:
    """
    Нормализует HTML для совместимости с Telegram.
    
    Выполняет:
    1. Нормализацию синонимичных тегов (strong->b, em->i)
    2. Удаление запрещенных тегов (<p>, <br>)
    3. Фильтрацию HTML тегов (только разрешенные для Telegram)
    4. Обрезку текста до лимита Telegram
    
    Args:
        html: Исходный HTML текст
        has_media: Есть ли медиа (влияет на лимит длины)
        
    Returns:
        str: Нормализованный HTML текст для Telegram
    """
    if not html:
        return html
    
    # Нормализация синонимичных тегов
    html = re.sub(r"</?strong>", lambda m: "</b>" if m.group(0).startswith("</") else "<b>", html, flags=re.IGNORECASE)
    html = re.sub(r"</?em>",     lambda m: "</i>" if m.group(0).startswith("</") else "<i>", html, flags=re.IGNORECASE)
    html = re.sub(r"</?ins>",    lambda m: "</u>" if m.group(0).startswith("</") else "<u>", html, flags=re.IGNORECASE)
    html = re.sub(r"</?(strike|del)>", lambda m: "</s>" if m.group(0).startswith("</") else "<s>", html, flags=re.IGNORECASE)
    
    # Удаление запрещенных тегов
    html = re.sub(r"<\s*/?\s*p\s*>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<\s*/?\s*br\s*/?>", "", html, flags=re.IGNORECASE)
    
    # Специальный случай span.tg-spoiler
    html = re.sub(r"<\s*span\s+class=\"tg-spoiler\"\s*>", "<tg-spoiler>", html, flags=re.IGNORECASE)
    
    # Используем парсер для безопасной обработки
    max_length = 1024 if has_media else 4096
    return fix_html_tags(html, max_length)
