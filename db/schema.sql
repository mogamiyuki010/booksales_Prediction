-- 金尉出版社圖書銷售預測模型 - 資料庫 Schema
-- 建立日期: 2026-04-10

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ============================================================
-- 作者資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS authors (
    author_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    author_type     TEXT NOT NULL CHECK (author_type IN ('KOP', 'KOC', 'Co-Branding', 'Debut')),
    primary_platform TEXT,                          -- 主要平台: YouTube, Instagram, Facebook, Course
    yt_subscribers  INTEGER DEFAULT 0,              -- YouTube 訂閱數
    ig_followers    INTEGER DEFAULT 0,              -- Instagram 粉絲數
    fb_followers    INTEGER DEFAULT 0,              -- Facebook 粉絲數
    cmoney_followers INTEGER DEFAULT 0,              -- 股市爆料同學會粉絲數 (CMoney 社群)
    course_students INTEGER DEFAULT 0,              -- 課程學員數
    app_subscribers INTEGER DEFAULT 0,              -- App 訂閱者
    previous_book_count INTEGER DEFAULT 0,          -- 過去出版書籍數量
    authority_score REAL DEFAULT 0.0,               -- 權威評分 (0-10)
    mentor_author_id INTEGER,                       -- Co-Branding 時的導師作者 ID
    notes           TEXT,
    snapshot_date   TEXT NOT NULL,                   -- 數據快照日期 (YYYY-MM-DD)
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (mentor_author_id) REFERENCES authors(author_id)
);

-- ============================================================
-- 書籍資料表
-- ============================================================
CREATE TABLE IF NOT EXISTS books (
    book_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      TEXT,                                  -- 營收表商品ID (如 B0000023)
    title           TEXT NOT NULL,
    author_id       INTEGER NOT NULL,
    category        TEXT NOT NULL DEFAULT '商業財經',  -- 大類
    subcategory     TEXT,                              -- 細分類: ETF存股, 技術分析, 財務自由...
    price_ntd       INTEGER,                           -- 定價 (NT$)
    page_count      INTEGER,
    format          TEXT DEFAULT 'single' CHECK (format IN ('single', 'set', 'upper_lower')),
    publish_date    TEXT,                               -- 出版日期 (YYYY-MM-DD)
    first_print_run INTEGER,                            -- 實際首印量
    author_type_at_publish TEXT,                         -- 出版時的作者類型分類
    is_sequel       INTEGER DEFAULT 0,                  -- 是否為續作
    predecessor_book_id INTEGER,                        -- 前作 book_id
    nth_book        INTEGER DEFAULT 1,                  -- 該作者的第 N 本書
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (author_id) REFERENCES authors(author_id),
    FOREIGN KEY (predecessor_book_id) REFERENCES books(book_id)
);

-- ============================================================
-- 月度銷售追蹤表
-- ============================================================
CREATE TABLE IF NOT EXISTS monthly_sales (
    sale_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id         INTEGER NOT NULL,
    month_number    INTEGER NOT NULL,                   -- 上市後第 N 個月 (1-based)
    units_sold      INTEGER NOT NULL DEFAULT 0,         -- 該月銷售量
    cumulative_units INTEGER NOT NULL DEFAULT 0,        -- 累計銷售量
    channel_online  INTEGER DEFAULT 0,                  -- 網路通路銷量
    channel_physical INTEGER DEFAULT 0,                 -- 實體通路銷量
    channel_direct  INTEGER DEFAULT 0,                  -- 直銷/活動銷量
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (book_id) REFERENCES books(book_id),
    UNIQUE (book_id, month_number)
);

-- ============================================================
-- 預測紀錄表
-- ============================================================
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    book_id         INTEGER NOT NULL,
    predicted_date  TEXT NOT NULL,                       -- 預測日期
    model_version   TEXT NOT NULL DEFAULT 'v1.0',       -- 模型版本
    -- 首印量預測
    print_run_low   INTEGER,                            -- 建議首印量（保守）
    print_run_high  INTEGER,                            -- 建議首印量（樂觀）
    -- 銷量預測
    sales_6m_low    INTEGER,                            -- 首 6 個月預測（保守）
    sales_6m_high   INTEGER,                            -- 首 6 個月預測（樂觀）
    sales_fy_low    INTEGER,                            -- 首年預測（保守）
    sales_fy_high   INTEGER,                            -- 首年預測（樂觀）
    -- 實際結果（回填）
    actual_6m_sales INTEGER,                            -- 實際 6 個月銷量
    actual_fy_sales INTEGER,                            -- 實際首年銷量
    -- 誤差追蹤
    error_pct_6m    REAL,                               -- 6 個月預測誤差 %
    error_pct_fy    REAL,                               -- 首年預測誤差 %
    -- 模型輸入參數快照
    params_snapshot TEXT,                                -- JSON: CR, decay, multiplier 等
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (book_id) REFERENCES books(book_id)
);

-- ============================================================
-- 作者社群指標歷史快照（追蹤變化）
-- ============================================================
CREATE TABLE IF NOT EXISTS author_metrics_history (
    metric_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    author_id       INTEGER NOT NULL,
    snapshot_date   TEXT NOT NULL,
    yt_subscribers  INTEGER DEFAULT 0,
    ig_followers    INTEGER DEFAULT 0,
    fb_followers    INTEGER DEFAULT 0,
    cmoney_followers INTEGER DEFAULT 0,                  -- 股市爆料同學會粉絲數
    course_students INTEGER DEFAULT 0,
    google_trends_index REAL,                           -- Google Trends 90天指數
    engagement_rate REAL,                                -- 加權互動率
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (author_id) REFERENCES authors(author_id)
);

-- ============================================================
-- 模型參數版本追蹤
-- ============================================================
CREATE TABLE IF NOT EXISTS model_parameters (
    param_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    version         TEXT NOT NULL,
    effective_date  TEXT NOT NULL,
    parameters      TEXT NOT NULL,                       -- JSON 格式的完整參數集
    calibration_source TEXT,                             -- 校準來源案例
    notes           TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_books_author ON books(author_id);
CREATE INDEX IF NOT EXISTS idx_books_publish_date ON books(publish_date);
CREATE INDEX IF NOT EXISTS idx_monthly_sales_book ON monthly_sales(book_id);
CREATE INDEX IF NOT EXISTS idx_predictions_book ON predictions(book_id);
CREATE INDEX IF NOT EXISTS idx_author_metrics_author ON author_metrics_history(author_id);
