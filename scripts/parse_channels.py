import asyncio
import logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException
import re
from database.db_connection import add_channel, update_channel_info
from telethon import TelegramClient
from telethon.tl.types import Channel
from config.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
config = load_config()


def get_channels_from_tgstat(url: str = "https://tgstat.ru/tag/ulyanovsk-region"):
    """
    Получает список каналов с tgstat.ru используя Selenium
    Args:
        url: Ссылка на категорию для парсинга с tgstat.ru
    Returns:
        List[Dict[str, Any]]: Список словарей с информацией о каналах из tgstat
    """
    if config is None:
        logger.error("Не удалось загрузить конфигурацию. Невозможно запустить парсинг tgstat.")
        return []
    channels = []
    # Настройка Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Запуск в фоновом режиме (без открытия окна браузера)
    chrome_options.add_argument('--no-sandbox')  # Отключение песочницы (для некоторых окружений, например, Docker)
    chrome_options.add_argument('--disable-dev-shm-usage')  # Обход проблемы с /dev/shm
    chrome_options.add_argument('--disable-gpu')  # Отключение GPU (иногда нужно для headless)
    chrome_options.add_argument('--window-size=1280,1024')  # Установка размера окна
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36') # Использование актуального User-Agent
    try:
        logger.info("Инициализация Chrome Driver...")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
        logger.info("Chrome Driver успешно инициализирован")
        logger.info(f"Открываем страницу: {url}")
        driver.get(url)
        ## logger.info("Ожидаем загрузку страницы и обход защиты...")
        ## time.sleep(10)  # Увеличили время ожидания на случай сложного обхода Cloudflare

        # Ждем появления хотя бы одной карточки канала с таймаутом
        wait = WebDriverWait(driver, 10)  # Увеличили таймаут ожидания элементов
        try:
            channel_cards = wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, "peer-item-box"))
            )
            logger.info(f"Найдено {len(channel_cards)} карточек каналов на странице")
        except TimeoutException:
            logger.error("Время ожидания истекло: Не удалось найти карточки каналов на странице.")
            with open('debug_page_timeout.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logger.info("HTML страницы при таймауте сохранен в debug_page_timeout.html")
            return []

        # Сохраняем страницу после загрузки для отладки
        try:
            with open('debug_page_success.html', 'w', encoding='utf-8') as f:
                f.write(driver.page_source)
            logger.info("HTML страницы после успешной загрузки сохранен в debug_page_success.html")
        except Exception as e:
            logger.error(f"Ошибка при сохранении debug_page_success.html: {str(e)}")

        # Парсим каналы
        for i, card in enumerate(channel_cards, 1):
            try:
                logger.debug(f"Обработка карточки {i}/{len(channel_cards)}")
                try:
                    # Сначала пробуем найти любую ссылку внутри карточки, содержащую /channel/
                    channel_url = card.find_element(By.CSS_SELECTOR, "a[href*='/channel/']").get_attribute('href')
                except NoSuchElementException:
                    logger.warning(f"Не найдена ссылка на канал в карточке {i}")
                    continue

                username = channel_url.split('/')[-1]
                if username.startswith("@"):
                    username = username[1:]
                if not username:
                    logger.warning(f"Не удалось извлечь username из ссылки в карточке {i}: {channel_url}")
                    continue
                # TODO: проверить есть ли нужда в этих всех данных
                # Получаем название канала
                title = None
                try:
                    # Ищем элемент с названием внутри карточки
                    title_elem = card.find_element(By.CSS_SELECTOR, ".font-16.text-dark")
                    title = title_elem.text.strip()
                    if not title:
                        logger.warning(f"Пустое название канала для @{username} в карточке {i}")
                        # Продолжаем, даже если название пустое, если есть username
                except NoSuchElementException:
                    logger.warning(f"Не найден элемент названия канала для @{username} в карточке {i}")
                    # Продолжаем, даже если название не найдено, если есть username

                # Получаем описание канала
                description = None
                try:
                    description_elem = card.find_element(By.CSS_SELECTOR, ".font-14.text-muted")
                    description = description_elem.text.strip()
                except NoSuchElementException:
                    logger.debug(f"Не найдено описание канала для @{username} в карточке {i}")

                # Получаем категорию
                category = None
                try:
                    # Ищем элемент категории внутри карточки
                    category_elem = card.find_element(By.CSS_SELECTOR, ".font-12.text-body")
                    category = category_elem.text.strip()
                except NoSuchElementException:
                    logger.debug(f"Не найдена категория канала для @{username} в карточке {i}")

                # Получаем количество подписчиков
                subscribers = 0
                try:
                    # Ищем элемент с количеством подписчиков
                    subscribers_elem = card.find_element(By.CSS_SELECTOR, ".font-12.text-truncate")
                    subscribers_text = subscribers_elem.text.strip()
                    # Ищем число в тексте (например, "125 245 подписчиков")
                    subscribers_match = re.search(r'(\d[\d\s]*)', subscribers_text)
                    if subscribers_match:
                        # Удаляем пробелы и преобразуем в int
                        subscribers = int(subscribers_match.group(1).replace(' ', ''))
                    else:
                        logger.debug(
                            f"Не удалось найти число подписчиков в тексте: '{subscribers_text}' для @{username} в карточке {i}")
                        subscribers = 0  # Если не нашли число, ставим 0
                except (NoSuchElementException, ValueError) as e:
                    subscribers = 0
                    logger.debug(f"Не удалось получить количество подписчиков для @{username} в карточке {i}: {str(e)}")

                # Получаем время последней публикации
                last_post = None
                try:
                    last_post_elem = card.find_element(By.CSS_SELECTOR, ".text-center.text-muted.font-12")
                    last_post = last_post_elem.text.strip()
                except NoSuchElementException:
                    logger.debug(f"Не найдено время последней публикации для @{username} в карточке {i}")

                if subscribers > 15000:
                    channel_info = {
                        'username': username,
                        'title': title,
                        'description': description,
                        'category': category,
                        'subscribers': subscribers,
                        'last_post': last_post,
                    }
                    logger.info(f"Успешно обработан канал из tgstat {i}/{len(channel_cards)}: {title} (@{username})")
                    logger.debug(f"Детали канала из tgstat: {channel_info}")
                    channels.append(channel_info)
            except Exception as e:
                logger.error(f"Ошибка при парсинге карточки {i}: {str(e)}", exc_info=True)
                continue
    except Exception as e:
        logger.error(f"Критическая ошибка при работе с Selenium: {str(e)}", exc_info=True)
    finally:
        if driver:
            try:
                driver.quit()
                logger.info("Chrome Driver закрыт")
            except Exception as e:
                logger.error(f"Ошибка при закрытии Chrome Driver: {str(e)}")
    logger.info(f"Завершено парсинг tgstat.ru. Всего найдено {len(channels)} каналов.")
    return channels


async def get_telegram_channel_info(client: TelegramClient, username: str) -> dict:
    """
    Получает дополнительную информацию о канале через Telegram API
    Args:
        client: Telethon клиент
        username: Username канала
    Returns:
        dict: Информация о канале из Telegram API или None в случае ошибки
    """
    if not username:
        logger.warning(f"Некорректный username для получения инфо из Telegram: {username}")
        return None
    logger.info(f"Получение информации о канале {username} через Telegram API")

    # TODO: Нужно добавить поддержку для приватных каналов потому, что не работает получение по их ссылкам
    try:
        entity = await client.get_entity(username)
        logger.debug(f"Объект entity для {username}: {entity}")
        logger.debug(f"Тип объекта entity: {type(entity)}")
        # Закомментировано, так как может выводить очень много информации
        # logger.debug(f"Атрибуты объекта entity: {dir(entity)}")

        # Проверяем, что это действительно канал
        if not isinstance(entity, Channel):
            logger.warning(f"Полученный объект для {username} не является каналом: {type(entity)}")
            return None
        channel_info = {
            'channel_tg_id': entity.id,
            'username': entity.username,
            'title': entity.title,
            'subscribers_count': entity.participants_count
        }
        logger.info(f"Успешно получена информация из Telegram для {username}")
        logger.debug(f"Информация из Telegram: {channel_info}")

        # Проверка, что хотя бы Telegram ID получен
        if channel_info.get('channel_tg_id') is None:
            logger.warning(f"Не удалось получить Telegram ID для {username}")
            return None
        return channel_info
    except Exception as e:
        logger.error(f"Ошибка при получении информации о канале {username} через Telegram API: {str(e)}", exc_info=True)
        return None


async def save_channels_to_db(channels: list):
    """
    Сохраняет каналы в базу данных, объединяя информацию из tgstat и Telegram API.
    Args:
        channels: Список словарей с информацией о каналах из tgstat.ru
    """
    if config is None:
        logger.error("Не удалось загрузить конфигурацию. Невозможно сохранить каналы в БД.")
        return
    if not channels:
        logger.warning("Получен пустой список каналов для сохранения в БД")
        return

    logger.info(f"Начинаем сохранение {len(channels)} каналов в базу данных")
    # Инициализация Telethon клиента
    client = TelegramClient(
        session='tgstat_parser',
        api_id=config.telethon_client.api_id,
        api_hash=config.telethon_client.api_hash
    )

    try:
        try:
            logger.info(f"Попытка подключения к Telegram API...")
            await client.start(password=config.telethon_client.password)
            logger.info("Успешно подключились к Telegram API")
        except Exception as e:
            logger.error(f"Не удалось подключится к Telegram API не удалась: {str(e)}")
            return

        if not client.is_connected():
            logger.error("Telethon клиент не подключен. Пропускаем сохранение в БД.")
            return
        # Счетчики для статистики
        total_channels = len(channels)
        successful_adds = 0
        successful_updates = 0
        failed_channels = 0

        for i, channel_tgstat in enumerate(channels, 1):
            # Копируем информацию из tgstat, чтобы использовать ее по умолчанию
            channel_data_to_save = channel_tgstat.copy()

            tgstat_username = channel_tgstat.get('username')
            if not tgstat_username:
                logger.warning(f"Пропускаем канал {i}/{total_channels} из tgstat - нет username")
                failed_channels += 1
                continue

            logger.info(f"Обработка канала для сохранения {i}/{total_channels}: @{tgstat_username}")

            # Получаем дополнительную информацию через Telegram API
            tg_info = await get_telegram_channel_info(client, f'@{tgstat_username}')  # Передаем username с '@'

            # Объединяем информацию: данные из Telegram имеют приоритет, если они доступны
            channel_tg_id = None
            if tg_info:
                channel_tg_id = tg_info.get('channel_tg_id')
                # Обновляем данные для сохранения, если информация из Telegram API лучше
                if tg_info.get('username') is not None:
                    channel_data_to_save['username'] = tg_info['username']
                    logger.debug("username Получен из Telegram API")
                if tg_info.get('title') is not None:
                    channel_data_to_save['title'] = tg_info['title']
                    logger.debug("title Получен из Telegram API")
                if tg_info.get(
                        'description') is not None:  # Используем description из Telegram, даже если оно None, т.к. оно актуальнее
                    channel_data_to_save['description'] = tg_info['description']
                    logger.debug("description Получен из Telegram API")
                # Используем subscribers_count из Telegram, если оно не None и больше 0 (предполагаем, что tgstat может быть неточным)
                if tg_info.get('subscribers_count') is not None and tg_info.get('subscribers_count', 0) > 0:
                    channel_data_to_save['subscribers'] = tg_info['subscribers_count']
                    logger.debug("subscribers Получен из Telegram API")
            else:
                logger.warning(
                    f"Не удалось получить информацию из Telegram API для @{tgstat_username}. Используем только данные из tgstat.")

            # Проверяем, что у нас есть Telegram ID для сохранения (критично)
            if channel_tg_id is None:
                logger.warning(f"Пропускаем канал @{tgstat_username} - не удалось получить Telegram ID ниоткуда.")
                failed_channels += 1
                continue
            # Добавляем Telegram ID в данные для сохранения
            channel_data_to_save['channel_tg_id'] = channel_tg_id

            # Определяем категорию канала (приоритет: из tgstat, затем по описанию)
            category_to_save = channel_data_to_save.get('category')
            # TODO: заменить на ИИ определение категории
            if not category_to_save:
                description_for_category = channel_data_to_save.get('description', '') or channel_tgstat.get(
                    'description', '') or ''
                category_to_save = 'Общество'  # Категория по умолчанию
                # Более надежное определение по ключевым словам в описании
                desc_lower = description_for_category.lower()
                if any(word in desc_lower for word in ['новости', 'сми', 'журналист', 'чп', 'инцидент']):
                    category_to_save = 'Новости и СМИ'
                elif any(word in desc_lower for word in ['политика', 'власть', 'правительство', 'дума']):
                    category_to_save = 'Политика'
                elif any(word in desc_lower for word in ['экономика', 'бизнес', 'финансы', 'рынок']):
                    category_to_save = 'Экономика'
            logger.debug(
                f"Определенная категория для @{channel_data_to_save.get('username', tgstat_username)}: {category_to_save}")

            # Добавляем канал в базу данных
            try:
                channel_id_db = add_channel(
                    channel_tg_id=channel_data_to_save['channel_tg_id'],
                    username=channel_data_to_save.get('username'),
                    # username может быть None для некоторых типов чатов/каналов
                    title=channel_data_to_save.get('title', 'Без названия'),
                    # Указываем значение по умолчанию, если title None
                    description=channel_data_to_save.get('description'),
                    subscribers_count=channel_data_to_save.get('subscribers', 0),  # Указываем значение по умолчанию
                    category_name="Ульяновск" # TODO: временная затычка, ждет реализации определения категорий
                )
                logger.info(
                    f"Успешно добавлен канал: {channel_data_to_save.get('title', 'Без названия')} (@{channel_data_to_save.get('username', 'N/A')}) с внутренним ID: {channel_id_db}")
                successful_adds += 1
            except Exception as e:
                # Обработка ошибки добавления (например, дубликат channel_tg_id)
                logger.warning(
                    f"Не удалось добавить канал @{channel_data_to_save.get('username', tgstat_username)} в БД: {str(e)}")
                # Пробуем обновить информацию о существующем канале
                try:
                    if update_channel_info(
                            channel_tg_id=channel_data_to_save['channel_tg_id'],
                            username=channel_data_to_save.get('username'),
                            title=channel_data_to_save.get('title'),
                            description=channel_data_to_save.get('description'),
                            subscribers_count=channel_data_to_save.get('subscribers')
                    ):
                        logger.info(
                            f"Успешно обновлена информация о канале: {channel_data_to_save.get('title', 'Без названия')} (@{channel_data_to_save.get('username', tgstat_username)})")
                        successful_updates += 1
                    else:
                        logger.warning(
                            f"Не удалось обновить информацию о канале @{channel_data_to_save.get('username', tgstat_username)} - канал не найден в БД для обновления.")
                        failed_channels += 1  # Считаем как неудачно обработанный, если и добавить и обновить не получилось
                except Exception as update_error:
                    logger.error(
                        f"Критическая ошибка при обновлении канала @{channel_data_to_save.get('username', tgstat_username)}: {str(update_error)}",
                        exc_info=True)
                    failed_channels += 1
            # Добавляем небольшую асинхронную задержку между запросами к Telegram API
            await asyncio.sleep(1)  # Увеличена задержка для снижения нагрузки на API
        # Выводим статистику
        logger.info("\n*** Статистика обработки каналов ***")
        logger.info(f"Всего каналов из tgstat: {total_channels}")
        logger.info(f"Успешно добавлено в БД: {successful_adds}")
        logger.info(f"Успешно обновлено в БД: {successful_updates}")
        logger.info(f"Не удалось обработать (пропущено или ошибка): {failed_channels}")
        logger.info("************************************")
    except Exception as e:
        logger.error(f"Критическая ошибка в функции save_channels_to_db: {str(e)}", exc_info=True)
    finally:
        # Корректное закрытие соединения с Telegram API
        if client and client.is_connected():
            try:
                await client.disconnect()
                logger.info("Отключились от Telegram API")
            except Exception as e:
                logger.error(f"Ошибка при отключении от Telegram API: {str(e)}")


async def main():
    logger.info("--- Запуск основного скрипта парсинга каналов ---")
    # Получаем каналы с tgstat.ru
    url = input("Введите ссылку категории с tgstat.ru: ")
    if url:
        channels_from_tgstat = get_channels_from_tgstat(url)
    else:
        channels_from_tgstat = get_channels_from_tgstat()
    if channels_from_tgstat:
        logger.info(f"Получено {len(channels_from_tgstat)} каналов с tgstat.ru. Переходим к сохранению в БД.")
        # Сохраняем каналы в базу данных, получая доп. инфо из Telegram API
        await save_channels_to_db(channels_from_tgstat)
    else:
        logger.error("Не удалось получить каналы с tgstat.ru. Скрипт завершает работу.")


if __name__ == '__main__':
    try:
        # Запускаем асинхронную функцию main
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Скрипт прерван пользователем (Ctrl+C).")
    except Exception as e:
        logger.error(f"Критическая ошибка при выполнении скрипта: {str(e)}", exc_info=True)
