# 金尉出版社圖書銷售預測模型 — 改進計畫

## Context

金尉出版社目前使用「GEM 智能圖書印量預估模型」，以 prompt 驅動的「三層疊代預測法」來預估新書首印量與首年銷量。現有資產僅 3 個文件（prompt、JSON 訓練文件、MD 訓練文件），包含 6 個實際案例的校準資料，無任何程式碼或結構化數據庫。

**核心問題**：6 案例中有 5 個系統性高估（中位數高估約 45%），且無自動化數據收集、無回饋迴路、無外部數據增強。本計畫旨在從「純 prompt 方法」升級為「數據驅動的混合預測系統」，同時保留並強化已驗證的三層方法論。

---

## Phase 1：數據基礎建設 + 啟發式模型立即修正（第 1-4 週）

### 1.1 建立結構化數據庫

建立 SQLite 資料庫，schema 如下：

**檔案**: `db/schema.sql`

| 資料表 | 用途 | 關鍵欄位 |
|--------|------|----------|
| `books` | 書籍主資料 | book_id, title, author_id, category, subcategory, price_ntd, publish_date, first_print_run, author_type |
| `authors` | 作者基本資料與社群指標 | author_id, name, author_type, yt_subscribers, ig_followers, fb_followers, course_students, snapshot_date |
| `monthly_sales` | 逐月銷售追蹤 | book_id, month_number, units_sold, cumulative_units |
| `predictions` | 預測紀錄與誤差追蹤 | prediction_id, book_id, model_version, predicted_low, predicted_high, actual_sales, error_pct |

**行動**：將現有 6 個案例寫入資料庫作為種子資料。與出版社合作回填過去 5 年所有出版品的銷售數據。

### 1.2 啟發式模型四項立即修正

在 `models/heuristic/predictor.py` 中實作：

1. **系統性修正係數**：對 N_Committed 乘以 0.55-0.65 的校正因子，立即降低高估問題
2. **收緊中層 CR**：從 3%-8% 下修至 1.5%-4%（原 4.1% 安全下限在結合衰退後實際有效 CR 更低）
3. **月度軌跡建模**：用指數衰退函數產出 12 個月銷售曲線，取代單一年度總量
   - KOP：`sales_t = peak × 0.80^(t-1)`（月衰退 20%）
   - KOC：`sales_t = peak × 0.55^(t-1)`（月衰退 45%）
   - Co-Branding：`sales_t = peak × 0.65^(t-1)`（月衰退 35%）
4. **區分首印量 vs 首年預測**：首印量以 3 個月銷售量為目標（保守），首年預測為獨立預估

**驗證**：對 6 個案例回測，目標將中位數誤差從 ~45% 降至 20% 以下。

### 1.3 專案目錄結構

```
booksales_Prediction_model/
├── data/raw/                  # 出版社原始銷售匯出
├── data/processed/            # 清洗後 CSV
├── data/external/             # 外部數據快照
├── db/
│   ├── schema.sql
│   ├── seed_cases.sql         # 6 案例種子資料
│   └── booksales.db
├── models/
│   ├── heuristic/
│   │   ├── config.yaml        # 校準參數（CR、衰退率、乘數）
│   │   └── predictor.py       # 三層模型 Python 實作
│   ├── statistical/           # Phase 3 統計模型
│   └── ensemble/              # Phase 3 混合模型
├── agents/                    # Agent Team（見 Phase 4）
├── pipelines/
│   ├── ingest_sales.py        # 銷售數據 ETL
│   ├── enrich_author.py       # 社群數據收集
│   └── monthly_update.py      # 定期重校準
├── evaluation/
│   ├── backtest.py            # 回測引擎
│   └── metrics.py             # MAPE、偏差分析
├── prompts/                   # 原始 prompt（保留不動）
├── training_data/             # 原始訓練文件（保留不動）
└── config/settings.yaml       # API keys、設定
```

---

## Phase 2：外部數據增強（第 5-8 週）

### 2.1 台灣市場數據源

| 數據源 | 取得方式 | 可獲得資訊 | 優先級 |
|--------|----------|-----------|--------|
| **YouTube Data API** | 官方 API | 訂閱數、近期影片觀看數、互動率 | 高 |
| **Google Trends (pytrends)** | 官方 API | 作者名／主題的搜尋熱度（台灣，90 天） | 高 |
| **博客來** | Web scraping | 暢銷排行、讀者評論數、預購排名 | 高 |
| **Facebook/Instagram** | 官方 API（有限制） | 粉絲數、貼文互動率 | 中 |
| **TAAZE 讀冊** | Web scraping | 二手價格（需求衰退代理指標） | 中 |
| **PTT 批踢踢** | Scraping | 股票/理財版討論聲量、情感分析 | 中 |

### 2.2 收集的關鍵特徵

- 作者全平台粉絲數（預測時間點快照）
- 近 30 天平均互動率（按讚/留言 per post）
- Google Trends 90 天指數（作者名 + 主題關鍵字）
- 同子類別近 6 個月競品數量
- 博客來預購排名（若有）
- 出版月份（季節性因子）

**實作**：`pipelines/enrich_author.py` + `pipelines/ingest_sales.py`

---

## Phase 3：統計模型 + 混合預測（第 9-16 週）

### 3.1 統計模型（當案例數 >= 20）

**模型選擇**：LightGBM 梯度提升回歸 + 分位數回歸（產出信賴區間）

**特徵工程**：
- `author_type`（類別型）
- `log_total_followers`（對數化總粉絲數）
- `engagement_rate`（加權互動率）
- `course_students`（內層受眾代理）
- `price_ntd`（定價）
- `previous_book_sales`（續作/co-brand 時）
- `google_trends_90d`
- `month_of_year`（季節性）
- `competing_titles_6m`
- `nth_book`（第 N 本書效應 — 通常遞減）

**驗證**：Leave-one-out 交叉驗證，報告 MAPE 和方向準確率。

### 3.2 混合 Ensemble

```
final = w_heuristic × heuristic_pred + w_statistical × statistical_pred
```

初始權重 `w_heuristic=0.7, w_statistical=0.3`，隨統計模型累積數據逐步調整。

### 3.3 數據量與模型選擇對照

| 案例數 | 適用模型 |
|--------|---------|
| 6（現在） | 純啟發式 + 修正係數 |
| 15-20 | 加入 Ridge 回歸作為 sanity check |
| 50+ | LightGBM 為主要預測器 |
| 100+ | 可考慮深度學習 |

---

## Phase 4：Agent Team 架構（第 17-24 週）

### 4.1 五個 Agent 角色

| Agent | 角色 | 職責 | 工具 |
|-------|------|------|------|
| **Orchestrator 指揮官** | 流程總控 | 接收預測請求、調度其他 Agent、匯整結果、產出 C-Level 報告 | 所有 Agent 調用、DB 讀寫 |
| **Data Collector 數據蒐集員** | 作者數據收集 | 從社群 API、網站抓取作者指標 | YouTube API、Google Trends、博客來 scraper |
| **Market Analyst 市場分析師** | 市場情境分析 | 競品分析、類別趨勢、季節性調整 | 博客來分類 scraper、Google Trends、歷史 DB |
| **Predictor 預測引擎** | 數值預測 | 執行啟發式 + 統計模型，輸出月度曲線與信賴區間 | 模型程式碼、config.yaml |
| **Calibrator 校準員** | 回饋校準 | 比較預測 vs 實際，更新參數，標記異常 | DB 寫入、參數更新、回測引擎 |

### 4.2 Agent 協作流程

```
[新書預測請求]
       │
       v
   Orchestrator
       │
       ├──→ Data Collector ──→ 作者 Profile
       │
       ├──→ Market Analyst ──→ 市場情境報告
       │
       v (等待兩者完成)
       │
       v
    Predictor ← 作者 Profile + 市場情境
       │
       v
   Orchestrator ← 原始預測結果
       │
       v
   [C-Level 決策報告]

=== 月度回饋迴路 ===

   [實際銷售數據]
       │
       v
    Calibrator
       ├──→ 更新 config.yaml 參數
       ├──→ 更新 DB 訓練資料
       ├──→ 觸發模型重訓練（若達閾值）
       └──→ 產出準確度儀表板
```

### 4.3 技術選型

- **Agent 框架**：Claude API + Tool Use（每個 Agent 為獨立 Claude prompt + 特定工具），或用 LangGraph/CrewAI 做複雜編排
- **資料庫**：SQLite（Phase 1-2），PostgreSQL（Phase 4 若需多用戶）
- **排程**：Python `schedule` 或 cron
- **前端**：Streamlit 儀表板供出版社團隊使用
- **語言**：Python 3.11+

---

## Phase 5：回饋迴路與持續校準

### 數據收集時間點

| 時間點 | 收集內容 | 觸發方式 |
|--------|----------|----------|
| 出版前 | 作者指標快照、預測產出 | 新書建檔 |
| 上市第 1 週 | 首週銷量、預購兌現量 | 手動輸入 |
| 第 1 個月 | 月度銷售總量 | 自動排程 |
| 第 3 個月 | 季度累計 + 通路分佈 | 自動排程 |
| 第 6 個月 | 半年累計 | 自動排程 |
| 第 12 個月 | 全年累計 | 自動排程 |

### 重校準觸發條件

- 任一查核點實際銷量偏離預測 > 25% → Calibrator 標記並提議參數調整
- 每新增 5 個完整案例（12 個月數據）→ 觸發統計模型重訓練
- 實際銷量超過預測 2 倍 → 警報：考慮加印
- 3 個月累計低於預測 50% → 標記進行事後分析

---

## 三層方法論的保留與增強

### 保留
- 原始 `預估圖書銷量prompt.txt` 和訓練文件保持不動，存於 `prompts/` 和 `training_data/`
- 所有校準參數可追溯至原始案例

### 增強
1. **新增第 4 類作者型態**：「新人作者」— 無既有受眾，預測依賴主題熱度 + 出版社行銷力度
2. **價格敏感度調整**：朱家泓案例（NT$820 套書）顯示高價書有不同動態，加入價格帶修正因子
3. **第 N 本書效應**：同作者後續出版通常遞減，從歷史數據量化此因子
4. **預測目標調整**：主要預測「首 6 個月銷量」（對印量決策最實用），首年為次要

---

## 關鍵檔案清單

| 檔案 | 狀態 | 用途 |
|------|------|------|
| `預估圖書銷量prompt.txt` | 現有，保留 | 三層方法論規格書 |
| `預估圖書銷量訓練文件.json` | 現有，保留 | 6 案例種子數據 |
| `預估圖書銷量訓練文件.md` | 現有，保留 | 校準參數文件 |
| `db/schema.sql` | 待建立 | 資料庫結構定義（Phase 1 最重要的新檔案） |
| `models/heuristic/config.yaml` | 待建立 | 可版本控管的校準參數 |
| `models/heuristic/predictor.py` | 待建立 | 三層模型 Python 實作 + 4 項修正 |
| `pipelines/enrich_author.py` | 待建立 | 社群數據自動收集 |
| `agents/orchestrator.py` | 待建立 | Agent Team 主控 |

---

## 驗證方式

1. **Phase 1 回測**：對 6 個案例執行改進後的啟發式模型，比較 MAPE 是否從 ~45% 降至 <20%
2. **Phase 2 驗證**：加入外部數據後的預測是否比純內部數據更準
3. **Phase 3 交叉驗證**：Leave-one-out CV 的 MAPE 和方向準確率
4. **Phase 4 端到端測試**：模擬新書預測請求，驗證 Agent Team 完整流程
5. **持續監控**：每月追蹤所有在售書籍的預測 vs 實際偏差
