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
    reputation_score REAL DEFAULT 0.5,
    ad_ratio REAL DEFAULT 0.0,
    quality_score REAL DEFAULT 0.0,
    last_reputation_update TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
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
    views_count INTEGER DEFAULT 0,
    reactions_count INTEGER DEFAULT 0,
    comments_count INTEGER DEFAULT 0,
    forwards_count INTEGER DEFAULT 0,
    engagement_score REAL DEFAULT 0,
    last_engagement_update TIMESTAMP WITH TIME ZONE,
    prev_views_count INTEGER DEFAULT 0,
    prev_reactions_count INTEGER DEFAULT 0,
    prev_comments_count INTEGER DEFAULT 0,
    prev_forwards_count INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'active',
    message_id BIGINT
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

-- Создание таблицы кластеров
CREATE TABLE clusters (
    cluster_id SERIAL PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lifetime_minutes INTEGER NOT NULL,
    main_post_id INTEGER,
    expires_at TIMESTAMP,
    post_count INTEGER DEFAULT 0,
    status VARCHAR(16) DEFAULT 'active'
);

-- Создание таблицы связи кластера с постами
CREATE TABLE cluster_posts (
    cluster_id INTEGER REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    post_id INTEGER REFERENCES posts(post_id) ON DELETE CASCADE,
    PRIMARY KEY (cluster_id, post_id)
);

-- Создание индексов для оптимизации запросов
CREATE INDEX IF NOT EXISTS idx_news_published_at ON posts(published_at);
CREATE INDEX IF NOT EXISTS idx_news_is_hot ON posts(is_hot);
CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status);
CREATE INDEX IF NOT EXISTS idx_user_news_is_read ON user_posts(is_read);
CREATE INDEX IF NOT EXISTS idx_channels_is_active ON channels(is_active);
CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active);
CREATE INDEX IF NOT EXISTS idx_clusters_status ON clusters(status);
CREATE INDEX IF NOT EXISTS idx_cluster_posts_cluster_id ON cluster_posts(cluster_id);
CREATE INDEX IF NOT EXISTS idx_cluster_posts_post_id ON cluster_posts(post_id);

-- Уникальность поста в рамках канала по message_id
CREATE UNIQUE INDEX IF NOT EXISTS uq_posts_channel_message ON posts(channel_tg_id, message_id);

-- Триггер для счета количества постов в кластере
CREATE OR REPLACE FUNCTION increment_post_count()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.cluster_id IS NOT NULL THEN
        UPDATE clusters
        SET post_count = post_count + 1
        WHERE cluster_id = NEW.cluster_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_increment_post_count ON cluster_posts;

CREATE TRIGGER trg_increment_post_count
AFTER INSERT ON cluster_posts
FOR EACH ROW
EXECUTE FUNCTION increment_post_count();

-- Триггер высчитывает время истекания кластера
CREATE OR REPLACE FUNCTION set_expires_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.expires_at := NEW.created_at + (NEW.lifetime_minutes * interval '1 minute');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_set_expires_at
BEFORE INSERT ON clusters
FOR EACH ROW
EXECUTE FUNCTION set_expires_at();

-- Триггер удаления осиротевших постов(после удаления кластера)
CREATE OR REPLACE FUNCTION delete_orphan_posts()
RETURNS TRIGGER AS $$
BEGIN
    DELETE FROM posts
    WHERE post_id IN (
        SELECT p.post_id
        FROM posts p
        LEFT JOIN cluster_posts cp ON p.post_id = cp.post_id
        WHERE cp.post_id IS NULL
    );
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_delete_orphan_posts ON cluster_posts;

CREATE TRIGGER trg_delete_orphan_posts
AFTER DELETE ON cluster_posts
FOR EACH STATEMENT
EXECUTE FUNCTION delete_orphan_posts();


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

-- ====================
-- Таблицы для системы фильтрации рекламы
-- ====================

-- Логи решений по рекламе (для аудита и обучения)
CREATE TABLE IF NOT EXISTS ad_decisions (
    decision_id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(post_id) ON DELETE CASCADE,
    stage SMALLINT NOT NULL, -- 1: префильтр, 2: AI
    score REAL,              -- скалярная оценка вероятности рекламы [0..1]
    decision VARCHAR(16) NOT NULL, -- 'ad' | 'not_ad' | 'review'
    model_version VARCHAR(64),
    features JSONB,          -- сохраняем интерпретируемые признаки префильтра или AI
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ad_decisions_post_id ON ad_decisions(post_id);
CREATE INDEX IF NOT EXISTS idx_ad_decisions_created_at ON ad_decisions(created_at);

-- Ручная разметка постов по рекламе
CREATE TABLE IF NOT EXISTS ad_labels (
    label_id SERIAL PRIMARY KEY,
    post_id INTEGER REFERENCES posts(post_id) ON DELETE CASCADE,
    label VARCHAR(16) NOT NULL, -- 'ad' | 'not_ad' | 'ambiguous'
    source VARCHAR(32) DEFAULT 'admin', -- 'admin' | 'user' | 'auto'
    reviewer_tg_id BIGINT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_ad_labels_post ON ad_labels(post_id);
CREATE INDEX IF NOT EXISTS idx_ad_labels_created_at ON ad_labels(created_at);

-- Кэш часто встречающихся рекламных паттернов
CREATE TABLE IF NOT EXISTS ad_pattern_cache (
    pattern TEXT PRIMARY KEY,
    hits INTEGER DEFAULT 0,
    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Регистр версий моделей
CREATE TABLE IF NOT EXISTS model_versions (
    model_name VARCHAR(64) PRIMARY KEY,
    version VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Системные параметры (ключ-значение) для онлайн-калибровки/настроек
CREATE TABLE IF NOT EXISTS system_params (
    param_key VARCHAR(128) PRIMARY KEY,
    param_value TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Логи скоринга кластеров для A/B и визуализации
CREATE TABLE IF NOT EXISTS cluster_scores (
    id SERIAL PRIMARY KEY,
    cluster_id INTEGER REFERENCES clusters(cluster_id) ON DELETE CASCADE,
    algorithm VARCHAR(32) NOT NULL, -- 'baseline' | 'improved'
    score REAL NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cluster_scores_cluster_id ON cluster_scores(cluster_id);