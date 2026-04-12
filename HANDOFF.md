# Handoff Report — GEM 圖書銷量預測模型

> 最後更新: 2026-04-13

## Project: booksales_Prediction_model
- **Type**: Python 數據科學 / AI 預測模型 + 營運報表系統
- **Git**: master branch
- **位置**: `D:\claude project\booksales_Prediction_model`

## 專案背景

為金尉出版社建立圖書銷售預測模型（GEM），使用「三層疊代預測法」預測商業財經類新書的首印量與銷量。已從 v0.1 (prompt-only, 誤差 103.9%) 迭代至 v2.0 (真實資料校準, 紙本中位誤差 27.2%)。

## 檔案結構

```
booksales_Prediction_model/
├── HANDOFF.md                              # 本檔案
├── PLAN.md                                 # 完整改進計畫
├── index.html                              # 導覽首頁（GitHub Pages 環境偵測）
├── dashboard.html                          # 銷量預測模型 v2.0 儀表板（動態載入 JSON）
├── predictor.html                          # 新書銷量預測工具 v2.0（動態載入 config_v2.json）
├── author_models.html                      # 作者預估模型欄位校對（唯讀）
├── author_editor.html                      # 作者資訊編輯器（本地限定，需 API server）
├── start.bat                               # 本機啟動腳本（雙擊即開 API server）
├── requirements.txt                        # Python 依賴: pandas, pyyaml, pytest
├── 營收表-Rawdata.csv                      # 原始營收資料 (UTF-16 TSV, 227K筆)
├── 營收表-Rawdata_20260305_20260411.csv    # 增量營收資料 (833筆, 2026/3~4)
│
├── db/
│   ├── schema.sql                          # 6 張資料表定義（含 cmoney_followers）
│   ├── seed_cases.sql                      # 6 案例種子資料
│   ├── init_db.py                          # DB 初始化腳本
│   ├── booksales.db                        # SQLite 資料庫（67 作者, 117 書）
│   ├── api_server.py                       # REST API server (port 8000)
│   ├── export_author_models.py             # 匯出 JSON (author_models + config_v2)
│   └── import_from_revenue.py              # 從營收表匯入作者/書籍
│
├── models/heuristic/
│   ├── config.yaml                         # v1.0 校準參數
│   ├── config_v2.yaml                      # v2.0 校準參數（單一真相來源）
│   ├── predictor.py                        # v1.0 預測引擎
│   └── predictor_v2.py                     # v2.0 預測引擎（含電子書通道）
│
├── evaluation/
│   ├── backtest.py                         # v1.0 回測引擎
│   └── backtest_v2.py                      # v2.0 回測引擎
│
├── pipelines/
│   └── etl_revenue.py                      # 營收表 ETL pipeline
│
├── data/
│   ├── author_models.json                  # 作者模型 JSON（67 作者 + 117 書）
│   ├── config_v2.json                      # v2.0 模型參數 JSON（從 YAML 轉出）
│   ├── dashboard_data.json                 # 儀表板用資料（213 個月趨勢）
│   ├── book_sales_summary.csv              # 232 本書銷售彙總
│   ├── book_monthly_curves.csv             # 3,712 筆月度曲線
│   └── book_decay_stats.csv                # 118 本書衰退率統計
│
├── reports/                                # 營運報表系統（新建）
│   ├── __init__.py
│   ├── data_loader.py                      # CSV 資料載入 + 期間切割
│   ├── kpi_engine.py                       # KPI 計算引擎
│   ├── template.py                         # 麥肯錫風格 HTML 模板引擎
│   ├── weekly.py                           # 周報生成器
│   ├── generate.py                         # CLI 入口（周/月/季報）
│   └── output/                             # 生成的報表 HTML（36 份）
│       ├── weekly_2025W40~2026W14.html     # 27 份周報
│       ├── monthly_202510~202603.html      # 6 份月報
│       └── quarterly_2025Q4~2026Q1.html    # 2 份季報 + 1 份空周報
│
├── .github/workflows/
│   └── pages.yml                           # GitHub Pages 自動部署
│
├── prompts/                                # 原始 prompt 備份
└── training_data/                          # 原始訓練文件備份
```

## 本次 Session 完成項目 (2026-04-13)

### 1. fb_group_followers → cmoney_followers 欄位重新命名
- 「股市爆料同學會」是獨立 CMoney 社群平台，非 FB 社團
- 全面更新: schema.sql, api_server.py, author_models.html, author_editor.html

### 2. GitHub Pages 靜態部署架構
- index.html: 環境偵測，無 API 時編輯器卡片自動灰化
- author_models.html: API + 靜態 JSON 雙 fallback
- .github/workflows/pages.yml: push 到 master 自動部署
- start.bat: 本機雙擊啟動 API server

### 3. 資料來源統一（Phase A1）— 修正關鍵 bug
- **predictor.html**: 移除硬編碼，改為動態載入 `data/config_v2.json` + `data/author_models.json`
  - **修正**: 轉換率從過期 v1.0 值 (middle CR 0.025-0.060) 更新為 v2.0 (0.010-0.025)
  - 含 fallback 機制，離線時使用預設值
- **dashboard.html**: 移除硬編碼，改為動態載入 `data/dashboard_data.json`
  - 資料從 51 個月擴展為 213 個月完整歷史
- **export_author_models.py**: 一次匯出三個 JSON (author_models + config_v2 + dashboard_data)
  - 新增 `--push` 旗標：匯出後自動 git commit + push

### 4. 營運報表系統（Phase B）— 全新建立
- **data_loader.py**: UTF-16 CSV 讀取、合併去重、期間切割
- **kpi_engine.py**: 11 種 KPI 計算 + 自動 Executive Summary 生成 + 異常偵測
- **template.py**: 麥肯錫風格 HTML 模板引擎，Chart.js 圖表
- **weekly.py**: 周報生成器（KPI 卡片 + TOP 10 + 通路分析 + 警示）
- **generate.py**: CLI 入口，支援 `--type weekly/monthly/quarterly/all`
- **CSS 品牌統一**: gold/cream/red 配色系統，與預測系統一致
- **批次生成 36 份報表**: 2025-W40 ~ 2026-W14 周報 + 月報 + 季報

### 報表使用方式
```bash
# 生成周報（自動偵測最新一周）
python reports/generate.py --type weekly

# 指定期間
python reports/generate.py --type weekly --period 2026-W14
python reports/generate.py --type monthly --period 2026-03
python reports/generate.py --type quarterly --period 2026-Q1

# 匯出資料 + 推送到 GitHub Pages
python db/export_author_models.py --push
```

## 待辦事項 (Action Items)

### 未完成的計畫項目

| # | 項目 | 優先級 | 說明 |
|---|------|--------|------|
| 1 | **Phase A2: 完整測試套件** | 高 | pytest: test_data_sync (資料一致性) + test_predictor (預測邏輯) + test_etl + test_api |
| 2 | **Phase A3: CI 整合** | 中 | .github/workflows/test.yml — push 時自動跑測試 |
| 3 | **報表索引頁** | 中 | reports/index.html — 列出所有報表，加入首頁導覽 |
| 4 | **月報/季報增強** | 低 | 預測追蹤 (預測 vs 實際)、庫存/印量建議 |

### 需要手動提供的資料

| # | 項目 | 說明 | 影響 |
|---|------|------|------|
| 1 | **各作者出書時的社群粉絲數** | YT/IG/FB/CMoney，從合約/企劃書取得 | **最大誤差來源** |
| 2 | 每本書的實際首印量 | 當初決定印多少本 | 校準首印量建議 |
| 3 | 作者課程學員數 / App 訂閱者 | 內層受眾量化 | 改善 inner CR |

### Phase 路線圖

| Phase | 內容 | 狀態 |
|-------|------|------|
| 1 | 資料庫 + 啟發式模型 | **完成** |
| 1.5 | 真實營收 ETL + v2.0 校準 | **完成** |
| 1.6 | 互動預測工具 + CMoney + 書種分類 | **完成** |
| 1.7 | 資料連動 + 報表系統 + GitHub Pages | **完成 (本次)** |
| A2 | 完整測試套件 (pytest) | **待做** |
| 2 | 外部數據增強 (YouTube API, Google Trends) | 待做 |
| 3 | 統計模型 LightGBM + Ensemble | 待做 |
| 4 | Agent Team | 待做 |
| 5 | 自動化回饋迴路 | 待做 |

## 執行指令

```bash
# 本機開發（雙擊 start.bat 或）
python db/api_server.py

# ETL pipeline
python pipelines/etl_revenue.py

# 匯出靜態 JSON
python db/export_author_models.py

# 生成報表
python reports/generate.py --type weekly
python reports/generate.py --type monthly --period 2026-03
python reports/generate.py --type quarterly --period 2026-Q1

# 匯出 + 推送到 GitHub Pages
python db/export_author_models.py --push
```
