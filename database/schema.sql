-- Создание таблицы пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
    user_tg_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

-- Создание таблицы категорий
CREATE TABLE IF NOT EXISTS categories (
    category_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы каналов
CREATE TABLE IF NOT EXISTS channels (
    channel_id SERIAL PRIMARY KEY,
    channel_tg_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    subscribers_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Создание таблицы новостей
CREATE TABLE IF NOT EXISTS posts (
    post_id SERIAL PRIMARY KEY,
    channel_tg_id BIGINT REFERENCES channels(channel_tg_id),
    content TEXT NOT NULL,
    embedding DOUBLE PRECISION[] NOT NULL,
    media_urls TEXT[],
    published_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_hot BOOLEAN DEFAULT FALSE,
    views_count INTEGER DEFAULT 0
);

-- Создание таблицы связи пользователей с категориями
CREATE TABLE IF NOT EXISTS user_categories (
    user_id INTEGER REFERENCES users(user_id),
    category_id INTEGER REFERENCES categories(category_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, category_id)
);

-- Создание таблицы связи каналов с категориями
CREATE TABLE IF NOT EXISTS channel_categories (
	channel_id INTEGER REFERENCES channels(channel_id) ON DELETE CASCADE,
	category_id INTEGER REFERENCES categories(category_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, category_id)
);

-- Создание таблицы истории взаимодействия пользователей с новостями
CREATE TABLE IF NOT EXISTS user_posts (
    user_id INTEGER REFERENCES users(user_id),
    post_id INTEGER REFERENCES posts(post_id),
    is_read BOOLEAN DEFAULT FALSE,
    is_liked BOOLEAN DEFAULT FALSE,
    is_hidden BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, post_id)
);

-- Создание индексов для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_news_published_at ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_news_is_hot ON posts(is_hot);
CREATE INDEX IF NOT EXISTS idx_user_news_is_read ON user_posts(is_read);
CREATE INDEX IF NOT EXISTS idx_channels_is_active ON channels(is_active);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- 1. Создание функции для триггера
CREATE OR REPLACE FUNCTION enforce_limit()
RETURNS TRIGGER AS $$
BEGIN
    -- Удалить все записи, кроме 100 самых новых
    DELETE FROM posts
    WHERE post_id NOT IN (
        SELECT post_id FROM posts
        ORDER BY created_at DESC
        LIMIT 100
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
-- 2. Создание триггера, который будет вызываться после каждой вставки
DROP TRIGGER IF EXISTS limit_posts ON posts;

CREATE TRIGGER limit_posts
AFTER INSERT ON posts
FOR EACH STATEMENT
EXECUTE FUNCTION enforce_limit();

-- Добавление категорий примера
-- TODO: Категории должны добавляться парсингом с tgstat.ru
INSERT INTO categories (name, description) VALUES
    ('Ульяновск', 'Тестовая категория для ульяновска'),
    ('Политика', 'Тестовая категория Новости политики и государственного управления'),
    ('Экономика', 'Тестовая категория Новости экономики и финансов'),
    ('Технологии', 'Тестовая категория Новости технологий и инноваций'),
    ('Спорт', 'Тестовая категория Спортивные новости и события'),
    ('Культура', 'Тестовая категория Новости культуры и искусства'),
    ('Наука', 'Тестовая категория Научные открытия и исследования'),
    ('Общество', 'Тестовая категория Новости общественной жизни'),
    ('Происшествия', 'Тестовая категория Новости о происшествиях и чрезвычайных ситуациях')
ON CONFLICT (name) DO NOTHING;