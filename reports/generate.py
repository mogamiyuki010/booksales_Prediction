"""
報表生成 CLI 入口
用法:
    python reports/generate.py --type weekly
    python reports/generate.py --type weekly --period 2026-W15
    python reports/generate.py --type monthly --period 2026-03
    python reports/generate.py --type quarterly --period 2026-Q1
    python reports/generate.py --type all
"""

import argparse
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# 確保專案根目錄在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"


def _ensure_output_dir():
    """確保輸出目錄存在"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _get_data_loader():
    """
    初始化資料載入器
    嘗試載入 ReportData；若尚未實作，使用 fallback 直接讀 CSV
    """
    try:
        from reports.data_loader import ReportData
        loader = ReportData()
        print("  資料載入器: ReportData (data_loader.py)")
        return loader
    except ImportError:
        print("  資料載入器: FallbackDataLoader (直接讀 CSV)")
        return FallbackDataLoader()


class FallbackDataLoader:
    """
    當 data_loader.py 尚未就緒時的替代方案
    直接從 ETL pipeline 的原始 CSV 載入並篩選日期
    """

    def __init__(self):
        import pandas as pd
        self._df = None

    def _load(self):
        """延遲載入：首次呼叫時才讀 CSV"""
        if self._df is not None:
            return
        import pandas as pd

        try:
            from pipelines.etl_revenue import load_and_merge_raw_data, clean_book_data
            print("  載入原始營收資料...")
            raw = load_and_merge_raw_data()
            self._df = clean_book_data(raw)
            print(f"  清洗後: {len(self._df):,} 筆")
        except Exception as e:
            print(f"  [警告] 無法載入資料: {e}")
            self._df = pd.DataFrame()

    def get_data(self, start, end):
        """按日期範圍篩選資料"""
        import pandas as pd
        self._load()

        if self._df is None or len(self._df) == 0:
            return pd.DataFrame()

        df = self._df.copy()
        if "日期" not in df.columns:
            df["日期"] = pd.to_datetime(df["日期控制"], format="mixed", errors="coerce")

        mask = (df["日期"] >= pd.Timestamp(start)) & (df["日期"] <= pd.Timestamp(end))
        result = df[mask]
        print(f"  期間 {start.strftime('%Y/%m/%d')}~{end.strftime('%Y/%m/%d')}: {len(result):,} 筆")
        return result


# ================================================================== #
#  報表生成函式
# ================================================================== #

def generate_weekly(data_loader, period: str = None) -> str:
    """生成週報"""
    from reports.weekly import generate_weekly_report

    print("\n--- 生成週報 ---")
    html = generate_weekly_report(data_loader, period)

    # 決定檔名
    if period:
        filename = f"weekly_{period.replace('-', '')}.html"
    else:
        # 自動用上週
        today = datetime.now()
        last_monday = today - timedelta(days=today.weekday() + 7)
        iso_year, iso_week, _ = last_monday.isocalendar()
        filename = f"weekly_{iso_year}W{iso_week:02d}.html"

    out_path = OUTPUT_DIR / filename
    out_path.write_text(html, encoding="utf-8")
    print(f"  輸出: {out_path}")
    return str(out_path)


def generate_monthly(data_loader, period: str = None) -> str:
    """
    生成月報
    period 格式: '2026-03'
    """
    from reports.kpi_engine import KPIEngine
    import pandas as pd

    print("\n--- 生成月報 ---")

    # 決定月份
    if period:
        year, month = period.split("-")
        year, month = int(year), int(month)
    else:
        today = datetime.now()
        # 預設: 上個月
        first_of_this_month = today.replace(day=1)
        last_month_end = first_of_this_month - timedelta(days=1)
        year, month = last_month_end.year, last_month_end.month

    # 當月範圍
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(seconds=1)

    # 前月範圍
    prev_end = start - timedelta(seconds=1)
    prev_start = prev_end.replace(day=1, hour=0, minute=0, second=0)

    # 去年同月 (YoY)
    yoy_start = datetime(year - 1, month, 1)
    if month == 12:
        yoy_end = datetime(year, 1, 1) - timedelta(seconds=1)
    else:
        yoy_end = datetime(year - 1, month + 1, 1) - timedelta(seconds=1)

    month_label = f"{year}年{month:02d}月"
    print(f"  期間: {month_label}")

    df = data_loader.get_data(start, end)
    df_prev = data_loader.get_data(prev_start, prev_end)
    df_yoy = data_loader.get_data(yoy_start, yoy_end)

    if df is None or len(df) == 0:
        print("  [警告] 無資料，跳過月報生成")
        return ""

    engine = KPIEngine()
    kpis = engine.compute_all(df, df_prev, report_type="monthly")

    # YoY 指標
    if df_yoy is not None and len(df_yoy) > 0:
        yoy_overview = engine.compute_sales_overview(df, df_yoy)
        kpis["yoy"] = {
            "units_growth_pct": yoy_overview.get("units_growth_pct"),
            "revenue_growth_pct": yoy_overview.get("revenue_growth_pct"),
        }

    # 建構月報 HTML
    html = _build_monthly_html(month_label, start, end, kpis)

    filename = f"monthly_{year}{month:02d}.html"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(html, encoding="utf-8")
    print(f"  輸出: {out_path}")
    return str(out_path)


def generate_quarterly(data_loader, period: str = None) -> str:
    """
    生成季報
    period 格式: '2026-Q1'
    """
    from reports.kpi_engine import KPIEngine

    print("\n--- 生成季報 ---")

    if period:
        parts = period.split("-Q")
        year = int(parts[0])
        quarter = int(parts[1])
    else:
        today = datetime.now()
        year = today.year
        quarter = (today.month - 1) // 3
        if quarter == 0:
            quarter = 4
            year -= 1

    q_start_month = (quarter - 1) * 3 + 1
    start = datetime(year, q_start_month, 1)
    if q_start_month + 3 > 12:
        end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
    else:
        end = datetime(year, q_start_month + 3, 1) - timedelta(seconds=1)

    # 前季
    prev_q_start = start - timedelta(days=1)
    prev_q_start = prev_q_start.replace(day=1)
    prev_q_start = prev_q_start - timedelta(days=60)
    prev_q_start = prev_q_start.replace(day=1)
    prev_start = datetime(year if quarter > 1 else year - 1,
                          q_start_month - 3 if quarter > 1 else 10, 1)
    prev_end = start - timedelta(seconds=1)

    # 去年同季
    yoy_start = datetime(year - 1, q_start_month, 1)
    if q_start_month + 3 > 12:
        yoy_end = datetime(year, 1, 1) - timedelta(seconds=1)
    else:
        yoy_end = datetime(year - 1, q_start_month + 3, 1) - timedelta(seconds=1)

    quarter_label = f"{year}年 Q{quarter}"
    print(f"  期間: {quarter_label}")

    df = data_loader.get_data(start, end)
    df_prev = data_loader.get_data(prev_start, prev_end)
    df_yoy = data_loader.get_data(yoy_start, yoy_end)

    if df is None or len(df) == 0:
        print("  [警告] 無資料，跳過季報生成")
        return ""

    engine = KPIEngine()
    kpis = engine.compute_all(df, df_prev, report_type="quarterly")

    # YoY
    if df_yoy is not None and len(df_yoy) > 0:
        yoy_overview = engine.compute_sales_overview(df, df_yoy)
        kpis["yoy"] = {
            "units_growth_pct": yoy_overview.get("units_growth_pct"),
            "revenue_growth_pct": yoy_overview.get("revenue_growth_pct"),
        }

    html = _build_quarterly_html(quarter_label, start, end, kpis)

    filename = f"quarterly_{year}Q{quarter}.html"
    out_path = OUTPUT_DIR / filename
    out_path.write_text(html, encoding="utf-8")
    print(f"  輸出: {out_path}")
    return str(out_path)


# ================================================================== #
#  月報 / 季報 HTML Builder
# ================================================================== #

def _get_report_css():
    """共用 CSS — 從 weekly.py 取得"""
    from reports.weekly import _get_base_css
    return _get_base_css()


def _build_monthly_html(month_label: str, start, end, kpis: dict) -> str:
    """建構月報 HTML"""
    from reports.weekly import (
        _format_currency, _format_growth, _growth_color,
        _build_kpi_card, _build_top_books_rows, _build_channel_rows,
        _build_alerts_section, _build_chart_scripts,
    )

    overview = kpis["overview"]
    summary = kpis["executive_summary"]
    top_books = kpis["top_books"]
    channel = kpis["channel_mix"]
    book_type = kpis["book_type"]
    alerts = kpis["alerts"]
    daily = kpis["daily_trend"]
    authors = kpis.get("author_ranking", [])
    new_back = kpis.get("new_vs_backlist", {})
    yoy = kpis.get("yoy", {})

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_range = f"{start.strftime('%Y/%m/%d')} ~ {end.strftime('%Y/%m/%d')}"

    # 作者排名表格
    author_rows = ""
    for a in authors:
        author_rows += f"""
                <tr>
                    <td>{a['rank']}</td>
                    <td>{a['name']}</td>
                    <td class="num">{a['units']:,}</td>
                    <td class="num">{_format_currency(a['revenue'])}</td>
                    <td class="num">{a['book_count']}</td>
                    <td class="book-title">{a.get('top_book', '')[:25]}</td>
                </tr>"""

    # YoY 指標
    yoy_html = ""
    if yoy:
        yoy_html = f"""
        <div class="kpi-grid" style="margin-top: 16px;">
            {_build_kpi_card("銷量 YoY", _format_growth(yoy.get("units_growth_pct")), "",
                             yoy.get("units_growth_pct"), "vs 去年同期")}
            {_build_kpi_card("營收 YoY", _format_growth(yoy.get("revenue_growth_pct")), "",
                             yoy.get("revenue_growth_pct"), "vs 去年同期")}
        </div>"""

    # 新書 vs 長銷書
    new_back_html = ""
    if new_back:
        new_books_list = ""
        for nb in new_back.get("new_books", [])[:5]:
            new_books_list += f"<li>{nb['title'][:20]}（{nb['author']}）: {nb['units']:,} 冊</li>"

        new_back_html = f"""
    <section class="section" id="new-vs-backlist">
        <h2>新書 vs 長銷書</h2>
        <div class="type-split-grid">
            <div class="type-card">
                <h3>新書（6 個月內）</h3>
                <div class="type-value">{new_back.get('new_units', 0):,} <span class="unit">冊</span></div>
                <div class="type-ratio">{new_back.get('new_pct', 0)}% | {new_back.get('new_title_count', 0)} 個品項</div>
            </div>
            <div class="type-card">
                <h3>長銷書</h3>
                <div class="type-value">{new_back.get('backlist_units', 0):,} <span class="unit">冊</span></div>
                <div class="type-ratio">{new_back.get('backlist_pct', 0)}% | {new_back.get('backlist_title_count', 0)} 個品項</div>
            </div>
        </div>
        <div style="margin-top: 16px; background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <h4>新書銷量 TOP 5</h4>
            <ol>{new_books_list}</ol>
        </div>
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>金尉出版 月報 {month_label}</title>
    <style>{_get_report_css()}</style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
<div class="container">

    <header class="report-header">
        <div class="header-left">
            <h1>金尉出版 營運月報</h1>
            <p class="period">{month_label} | {date_range}</p>
        </div>
        <div class="header-right">
            <p class="generated">報表產生時間: {generated_at}</p>
        </div>
    </header>

    <!-- Executive Summary -->
    <section class="section">
        <h2>經營摘要</h2>
        <div class="summary-grid">
            <div class="summary-card highlights">
                <h3>本月亮點</h3>
                <ul>{"".join(f'<li>{h}</li>' for h in summary["highlights"])}</ul>
            </div>
            <div class="summary-card actions">
                <h3>行動建議</h3>
                <ul>{"".join(f'<li>{a}</li>' for a in summary["actions"])}</ul>
            </div>
        </div>
    </section>

    <!-- KPI Cards + YoY -->
    <section class="section">
        <h2>關鍵指標</h2>
        <div class="kpi-grid">
            {_build_kpi_card("銷售冊數", f'{overview["total_units"]:,}', "冊",
                             overview.get("units_growth_pct"), "MoM")}
            {_build_kpi_card("營收", _format_currency(overview["total_revenue"]), "",
                             overview.get("revenue_growth_pct"), "MoM")}
            {_build_kpi_card("訂單數", f'{overview["total_orders"]:,}', "筆",
                             overview.get("orders_growth_pct"), "MoM")}
            {_build_kpi_card("平均客單價", _format_currency(int(overview["avg_order_value"])), "",
                             None, "")}
        </div>
        {yoy_html}
    </section>

    <!-- Top Books -->
    <section class="section">
        <h2>暢銷書 TOP 20</h2>
        <table class="data-table">
            <thead><tr>
                <th>#</th><th>書名</th><th>作者</th><th>類別</th>
                <th class="num">銷量</th><th class="num">營收</th>
            </tr></thead>
            <tbody>{_build_top_books_rows(top_books)}</tbody>
        </table>
    </section>

    <!-- Author Ranking -->
    <section class="section">
        <h2>作者銷量排名 TOP 15</h2>
        <table class="data-table">
            <thead><tr>
                <th>#</th><th>作者</th><th class="num">銷量</th>
                <th class="num">營收</th><th class="num">書籍數</th><th>暢銷書</th>
            </tr></thead>
            <tbody>{author_rows}</tbody>
        </table>
    </section>

    <!-- Channel Mix -->
    <section class="section">
        <h2>通路分佈</h2>
        <div class="chart-row">
            <div class="chart-container"><canvas id="channelPieChart"></canvas></div>
            <div class="channel-table-container">
                <table class="data-table compact">
                    <thead><tr><th>通路</th><th class="num">銷量</th><th class="num">佔比</th><th class="num">營收</th></tr></thead>
                    <tbody>{_build_channel_rows(channel)}</tbody>
                </table>
            </div>
        </div>
    </section>

    <!-- Paper vs Ebook -->
    <section class="section">
        <h2>紙本書 vs 電子書</h2>
        <div class="type-split-grid">
            <div class="type-card">
                <h3>紙本書</h3>
                <div class="type-value">{book_type["paper_units"]:,} <span class="unit">冊</span></div>
                <div class="type-revenue">{_format_currency(book_type["paper_revenue"])}</div>
            </div>
            <div class="type-card">
                <h3>電子書</h3>
                <div class="type-value">{book_type["ebook_units"]:,} <span class="unit">冊</span></div>
                <div class="type-revenue">{_format_currency(book_type["ebook_revenue"])}</div>
                <div class="type-ratio">佔銷量 {book_type["ebook_unit_ratio"]}% | 佔營收 {book_type["ebook_revenue_ratio"]}%</div>
            </div>
        </div>
    </section>

    <!-- New vs Backlist -->
    {new_back_html}

    <!-- Alerts -->
    {_build_alerts_section(alerts)}

    <!-- Daily Trend -->
    <section class="section">
        <h2>每日銷售趨勢</h2>
        <div class="chart-container wide"><canvas id="dailyTrendChart"></canvas></div>
    </section>

    <footer><p>金尉出版社 營運分析系統 | 自動產生於 {generated_at}</p></footer>
</div>
<script>{_build_chart_scripts(channel, daily)}</script>
</body>
</html>"""
    return html


def _build_quarterly_html(quarter_label: str, start, end, kpis: dict) -> str:
    """建構季報 HTML — 包含長期趨勢分析"""
    from reports.weekly import (
        _format_currency, _format_growth, _growth_color,
        _build_kpi_card, _build_top_books_rows, _build_channel_rows,
        _build_alerts_section, _build_chart_scripts,
    )

    overview = kpis["overview"]
    summary = kpis["executive_summary"]
    top_books = kpis["top_books"]
    channel = kpis["channel_mix"]
    book_type = kpis["book_type"]
    alerts = kpis["alerts"]
    daily = kpis["daily_trend"]
    authors = kpis.get("author_ranking", [])
    new_back = kpis.get("new_vs_backlist", {})
    cat_trend = kpis.get("category_trend", {})
    yoy = kpis.get("yoy", {})

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_range = f"{start.strftime('%Y/%m/%d')} ~ {end.strftime('%Y/%m/%d')}"

    # 作者排名
    author_rows = ""
    for a in authors:
        author_rows += f"""
                <tr>
                    <td>{a['rank']}</td><td>{a['name']}</td>
                    <td class="num">{a['units']:,}</td>
                    <td class="num">{_format_currency(a['revenue'])}</td>
                    <td class="num">{a['book_count']}</td>
                    <td class="book-title">{a.get('top_book', '')[:25]}</td>
                </tr>"""

    # YoY
    yoy_html = ""
    if yoy:
        yoy_html = f"""
        <div class="kpi-grid" style="margin-top: 16px;">
            {_build_kpi_card("銷量 YoY", _format_growth(yoy.get("units_growth_pct")), "",
                             yoy.get("units_growth_pct"), "vs 去年同季")}
            {_build_kpi_card("營收 YoY", _format_growth(yoy.get("revenue_growth_pct")), "",
                             yoy.get("revenue_growth_pct"), "vs 去年同季")}
        </div>"""

    # 分類月度趨勢
    import json
    cat_months_json = json.dumps(cat_trend.get("months", []), ensure_ascii=False)
    cat_datasets = ""
    cat_colors = {"紙本書": "#b8860b", "電子書": "#8b1a2b"}
    for cat_name, values in cat_trend.get("categories", {}).items():
        color = cat_colors.get(cat_name, "#9e8e6e")
        cat_datasets += f"""
                {{
                    label: '{cat_name}',
                    data: {json.dumps(values)},
                    borderColor: '{color}',
                    backgroundColor: '{color}22',
                    fill: true,
                    tension: 0.3,
                }},"""

    # 新書 vs 長銷書
    new_back_html = ""
    if new_back:
        new_books_list = ""
        for nb in new_back.get("new_books", [])[:5]:
            new_books_list += f"<li>{nb['title'][:20]}（{nb['author']}）: {nb['units']:,} 冊</li>"
        new_back_html = f"""
    <section class="section">
        <h2>新書 vs 長銷書</h2>
        <div class="type-split-grid">
            <div class="type-card">
                <h3>新書（6 個月內）</h3>
                <div class="type-value">{new_back.get('new_units', 0):,} <span class="unit">冊</span></div>
                <div class="type-ratio">{new_back.get('new_pct', 0)}% | {new_back.get('new_title_count', 0)} 個品項</div>
            </div>
            <div class="type-card">
                <h3>長銷書</h3>
                <div class="type-value">{new_back.get('backlist_units', 0):,} <span class="unit">冊</span></div>
                <div class="type-ratio">{new_back.get('backlist_pct', 0)}% | {new_back.get('backlist_title_count', 0)} 個品項</div>
            </div>
        </div>
        <div style="margin-top: 16px; background: white; border-radius: 8px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <h4>新書銷量 TOP 5</h4>
            <ol>{new_books_list}</ol>
        </div>
    </section>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>金尉出版 季報 {quarter_label}</title>
    <style>{_get_report_css()}</style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
<div class="container">

    <header class="report-header">
        <div class="header-left">
            <h1>金尉出版 營運季報</h1>
            <p class="period">{quarter_label} | {date_range}</p>
        </div>
        <div class="header-right">
            <p class="generated">報表產生時間: {generated_at}</p>
        </div>
    </header>

    <!-- Executive Summary -->
    <section class="section">
        <h2>經營摘要</h2>
        <div class="summary-grid">
            <div class="summary-card highlights">
                <h3>本季亮點</h3>
                <ul>{"".join(f'<li>{h}</li>' for h in summary["highlights"])}</ul>
            </div>
            <div class="summary-card actions">
                <h3>行動建議</h3>
                <ul>{"".join(f'<li>{a}</li>' for a in summary["actions"])}</ul>
            </div>
        </div>
    </section>

    <!-- KPI Cards + YoY -->
    <section class="section">
        <h2>關鍵指標</h2>
        <div class="kpi-grid">
            {_build_kpi_card("銷售冊數", f'{overview["total_units"]:,}', "冊",
                             overview.get("units_growth_pct"), "QoQ")}
            {_build_kpi_card("營收", _format_currency(overview["total_revenue"]), "",
                             overview.get("revenue_growth_pct"), "QoQ")}
            {_build_kpi_card("訂單數", f'{overview["total_orders"]:,}', "筆",
                             overview.get("orders_growth_pct"), "QoQ")}
            {_build_kpi_card("平均客單價", _format_currency(int(overview["avg_order_value"])), "",
                             None, "")}
        </div>
        {yoy_html}
    </section>

    <!-- Long-term Category Trend -->
    <section class="section">
        <h2>分類月度趨勢（長期）</h2>
        <div class="chart-container wide">
            <canvas id="categoryTrendChart"></canvas>
        </div>
    </section>

    <!-- Top Books -->
    <section class="section">
        <h2>暢銷書 TOP 30</h2>
        <table class="data-table">
            <thead><tr>
                <th>#</th><th>書名</th><th>作者</th><th>類別</th>
                <th class="num">銷量</th><th class="num">營收</th>
            </tr></thead>
            <tbody>{_build_top_books_rows(top_books)}</tbody>
        </table>
    </section>

    <!-- Author Ranking -->
    <section class="section">
        <h2>作者銷量排名 TOP 15</h2>
        <table class="data-table">
            <thead><tr>
                <th>#</th><th>作者</th><th class="num">銷量</th>
                <th class="num">營收</th><th class="num">書籍數</th><th>暢銷書</th>
            </tr></thead>
            <tbody>{author_rows}</tbody>
        </table>
    </section>

    <!-- Channel Mix -->
    <section class="section">
        <h2>通路分佈</h2>
        <div class="chart-row">
            <div class="chart-container"><canvas id="channelPieChart"></canvas></div>
            <div class="channel-table-container">
                <table class="data-table compact">
                    <thead><tr><th>通路</th><th class="num">銷量</th><th class="num">佔比</th><th class="num">營收</th></tr></thead>
                    <tbody>{_build_channel_rows(channel)}</tbody>
                </table>
            </div>
        </div>
    </section>

    <!-- Paper vs Ebook -->
    <section class="section">
        <h2>紙本書 vs 電子書</h2>
        <div class="type-split-grid">
            <div class="type-card">
                <h3>紙本書</h3>
                <div class="type-value">{book_type["paper_units"]:,} <span class="unit">冊</span></div>
                <div class="type-revenue">{_format_currency(book_type["paper_revenue"])}</div>
            </div>
            <div class="type-card">
                <h3>電子書</h3>
                <div class="type-value">{book_type["ebook_units"]:,} <span class="unit">冊</span></div>
                <div class="type-revenue">{_format_currency(book_type["ebook_revenue"])}</div>
                <div class="type-ratio">佔銷量 {book_type["ebook_unit_ratio"]}% | 佔營收 {book_type["ebook_revenue_ratio"]}%</div>
            </div>
        </div>
    </section>

    <!-- New vs Backlist -->
    {new_back_html}

    <!-- Alerts -->
    {_build_alerts_section(alerts)}

    <!-- Daily Trend -->
    <section class="section">
        <h2>每日銷售趨勢</h2>
        <div class="chart-container wide"><canvas id="dailyTrendChart"></canvas></div>
    </section>

    <footer><p>金尉出版社 營運分析系統 | 自動產生於 {generated_at}</p></footer>
</div>
<script>
{_build_chart_scripts(channel, daily)}

// 分類月度趨勢圖
new Chart(document.getElementById('categoryTrendChart'), {{
    type: 'line',
    data: {{
        labels: {cat_months_json},
        datasets: [{cat_datasets}]
    }},
    options: {{
        responsive: true,
        plugins: {{
            title: {{ display: true, text: '紙本書 vs 電子書 月度銷量趨勢' }}
        }},
        scales: {{
            y: {{ title: {{ display: true, text: '銷量（冊）' }} }}
        }}
    }}
}});
</script>
</body>
</html>"""
    return html


# ================================================================== #
#  CLI Main
# ================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description="金尉出版 營運報表生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例:
  python reports/generate.py --type weekly
  python reports/generate.py --type weekly --period 2026-W15
  python reports/generate.py --type monthly --period 2026-03
  python reports/generate.py --type quarterly --period 2026-Q1
  python reports/generate.py --type all
        """,
    )
    parser.add_argument(
        "--type",
        choices=["weekly", "monthly", "quarterly", "all"],
        required=True,
        help="報表類型: weekly(週報), monthly(月報), quarterly(季報), all(全部)",
    )
    parser.add_argument(
        "--period",
        help="指定期間 (e.g., 2026-W15, 2026-03, 2026-Q1)。未指定則自動取最近完整期間",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("  金尉出版 營運報表生成系統")
    print("=" * 60)

    _ensure_output_dir()

    # 載入資料
    print("\n[初始化] 載入資料...")
    data_loader = _get_data_loader()

    outputs = []

    if args.type in ("weekly", "all"):
        period = args.period if args.type == "weekly" else None
        path = generate_weekly(data_loader, period)
        if path:
            outputs.append(("週報", path))

    if args.type in ("monthly", "all"):
        period = args.period if args.type == "monthly" else None
        path = generate_monthly(data_loader, period)
        if path:
            outputs.append(("月報", path))

    if args.type in ("quarterly", "all"):
        period = args.period if args.type == "quarterly" else None
        path = generate_quarterly(data_loader, period)
        if path:
            outputs.append(("季報", path))

    # 總結
    print(f"\n{'=' * 60}")
    print("  報表生成完成")
    print(f"{'=' * 60}")
    if outputs:
        for label, path in outputs:
            print(f"  {label}: {path}")
    else:
        print("  未生成任何報表（可能資料不足）")
    print()


if __name__ == "__main__":
    main()
