## [1.0.5] - 2025-10-12
### Улучшено:
- refactor(ai): добавлено логирование в AI/Ai_Functions.py для лучшей отладки
- refactor(synthesizer): значительная оптимизация AI/news_synthesizer.py
  - Удален дублирующий код функции _normalize_output
  - Улучшена обработка ошибок импорта OpenAI SDK
  - Добавлено логирование ошибок вычисления heat score
- refactor(ad): улучшена система фильтрации рекламы в helpers/ad_helper.py
  - Улучшены регулярные выражения для фильтрации рекламы
  - Оптимизированы комментарии и структура кода
- refactor(main): упрощена инициализация Telethon клиента в main.py
  - Использование контекстного менеджера для автоматического управления соединением
  - Добавлены параметры device_model, system_version, app_version
- refactor(handlers): улучшена обработка в telethon_client/handlers/handler_utils.py
- refactor(db): удалены неиспользуемые импорты в database/db_connection.py
- refactor(content): упрощен код в AI/content_generator.py
- refactor(config): оптимизированы настройки в config/config.py
- refactor(helpers): удален неиспользуемый код в helpers/helpers.py
- refactor(telethon): упрощена инициализация в telethon_client/start_telethon.py
- fix(clustering): удалена лишняя переменная при вызове функции в AI/clustering.py

## [1.0.4] - 2025-10-11
### Добавлено:
- feat(bot): добавлена команда /info для отладки и мониторинга постов и кластеров
  - Поддержка двух режимов: /info <post_id> и reply на сообщение бота
  - Отображение метаданных поста: канал, кластер, репутация, engagement score
  - Показ истории решений классификатора рекламы
  - Агрегированная статистика кластера (просмотры, реакции, комментарии, репосты)

### Исправлено:
- fix(db): исправлены функции get_generated_articles_by_date, get_generated_article_cluster_id_by_text_prefix и get_cluster_metadata

## [1.0.3] - 2025-10-09
### Добавлено:
- db_connection Реализовано кэширование системных параметров с TTL, для уменьшения затрат на запросы к БД
- config.py Был улучшен, добавлена валидация конфигурируемых параметров с помощью pydantic
### Изменено:
- news_synthesizer Использует новый список AI Моделей, должны быть более качественными и работают на территории РФ
### Удалено: