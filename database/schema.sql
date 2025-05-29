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
CREATE TABLE IF NOT EXISTS news (
    news_id SERIAL PRIMARY KEY,
    channel_id INTEGER REFERENCES channels(channel_id),
    message_id BIGINT NOT NULL,
    content TEXT NOT NULL,
    media_urls TEXT[],
    published_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    is_hot BOOLEAN DEFAULT FALSE,
    views_count INTEGER DEFAULT 0,
    UNIQUE(channel_id, message_id)
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
    channel_id INTEGER REFERENCES channels(channel_id),
    category_id INTEGER REFERENCES categories(category_id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, category_id)
);

-- Создание таблицы истории взаимодействия пользователей с новостями
CREATE TABLE IF NOT EXISTS user_news (
    user_id INTEGER REFERENCES users(user_id),
    news_id INTEGER REFERENCES news(news_id),
    is_read BOOLEAN DEFAULT FALSE,
    is_liked BOOLEAN DEFAULT FALSE,
    is_hidden BOOLEAN DEFAULT FALSE,
    read_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, news_id)
);

-- Создание индексов для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_news_published_at ON news(published_at);
CREATE INDEX IF NOT EXISTS idx_news_is_hot ON news(is_hot);
CREATE INDEX IF NOT EXISTS idx_user_news_is_read ON user_news(is_read);
CREATE INDEX IF NOT EXISTS idx_channels_is_active ON channels(is_active);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);

-- Добавление базовых категорий
INSERT INTO categories (name, description) VALUES
    ('Политика', 'Новости политики и государственного управления'),
    ('Экономика', 'Новости экономики и финансов'),
    ('Технологии', 'Новости технологий и инноваций'),
    ('Спорт', 'Спортивные новости и события'),
    ('Культура', 'Новости культуры и искусства'),
    ('Наука', 'Научные открытия и исследования'),
    ('Общество', 'Новости общественной жизни'),
    ('Происшествия', 'Новости о происшествиях и чрезвычайных ситуациях')
ON CONFLICT (name) DO NOTHING; 