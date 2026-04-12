"""
週報生成器
使用 KPIEngine 計算指標，透過 ReportTemplate 渲染 HTML
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

# 確保專案根目錄在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from reports.kpi_engine import KPIEngine


def _get_week_range(period: Optional[str] = None) -> tuple[datetime, datetime]:
    """
    解析週期間字串，回傳 (start, end) 日期
    Args:
        period: 格式 '2026-W15' 或 None（自動取上週）
    Returns:
        (start_date, end_date) 皆為 datetime
    """
    if period:
        # 解析 ISO week: 2026-W15
        year, week = period.split("-W")
        year, week = int(year), int(week)
        # ISO week: 週一開始
        start = datetime.strptime(f"{year}-W{week:02d}-1", "%Y-W%W-%w")
        # 修正：使用 ISO 週計算
        jan4 = datetime(year, 1, 4)
        start_of_w1 = jan4 - timedelta(days=jan4.isoweekday() - 1)
        start = start_of_w1 + timedelta(weeks=week - 1)
        end = start + timedelta(days=6)
    else:
        # 預設: 上一個完整週（週一~週日）
        today = datetime.now()
        last_monday = today - timedelta(days=today.weekday() + 7)
        start = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=6, hours=23, minutes=59, seconds=59)

    return start, end


def _get_prev_week_range(start: datetime) -> tuple[datetime, datetime]:
    """取得前一週的日期範圍"""
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    return prev_start, prev_end


def _format_currency(value: int) -> str:
    """格式化金額: NT$1,234,567"""
    return f"NT${value:,}"


def _format_growth(pct: Optional[float]) -> str:
    """格式化成長率: +12.3% / -5.1%"""
    if pct is None:
        return "N/A"
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct}%"


def _growth_color(pct: Optional[float]) -> str:
    """成長率顏色 class"""
    if pct is None:
        return "neutral"
    if pct > 5:
        return "positive"
    elif pct < -5:
        return "negative"
    return "neutral"


def generate_weekly_report(data_loader, period: Optional[str] = None) -> str:
    """
    生成週報 HTML
    Args:
        data_loader: ReportData 實例，提供 get_data(start, end) 方法
        period: 週期間字串 (e.g. '2026-W15')，None 則自動取上週
    Returns:
        str: 完整的 HTML 報表字串
    """
    # ----- 1. 取得日期範圍 ----- #
    start, end = _get_week_range(period)
    prev_start, prev_end = _get_prev_week_range(start)

    week_label = f"{start.strftime('%Y-W%V')}"
    date_range_str = f"{start.strftime('%Y/%m/%d')} ~ {end.strftime('%Y/%m/%d')}"
    prev_range_str = f"{prev_start.strftime('%Y/%m/%d')} ~ {prev_end.strftime('%Y/%m/%d')}"

    # ----- 2. 載入資料 ----- #
    df = data_loader.get_data(start, end)
    df_prev = data_loader.get_data(prev_start, prev_end)

    if df is None or len(df) == 0:
        return _build_empty_report(week_label, date_range_str)

    # ----- 3. 計算 KPI ----- #
    engine = KPIEngine()
    kpis = engine.compute_all(df, df_prev, report_type="weekly")

    # ----- 4. 建構 HTML ----- #
    html = _build_weekly_html(
        week_label=week_label,
        date_range=date_range_str,
        prev_range=prev_range_str,
        kpis=kpis,
    )

    return html


def _build_empty_report(week_label: str, date_range: str) -> str:
    """無資料時的空報表"""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <title>金尉出版 週報 {week_label}</title>
    <style>{_get_base_css()}</style>
</head>
<body>
    <div class="container">
        <header class="report-header">
            <h1>金尉出版 營運週報</h1>
            <p class="period">{week_label} | {date_range}</p>
        </header>
        <div class="alert-box warning">
            <h3>本週無銷售資料</h3>
            <p>指定期間內無銷售紀錄，請確認資料是否已匯入。</p>
        </div>
    </div>
</body>
</html>"""


def _build_weekly_html(week_label: str, date_range: str,
                       prev_range: str, kpis: dict) -> str:
    """組裝完整週報 HTML"""
    overview = kpis["overview"]
    summary = kpis["executive_summary"]
    top_books = kpis["top_books"]
    channel = kpis["channel_mix"]
    book_type = kpis["book_type"]
    alerts = kpis["alerts"]
    daily = kpis["daily_trend"]

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>金尉出版 週報 {week_label}</title>
    <style>{_get_base_css()}</style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
<div class="container">

    <!-- Header -->
    <header class="report-header">
        <div class="header-left">
            <h1>金尉出版 營運週報</h1>
            <p class="period">{week_label} | {date_range}</p>
            <p class="sub-period">對比期間: {prev_range}</p>
        </div>
        <div class="header-right">
            <p class="generated">報表產生時間: {generated_at}</p>
        </div>
    </header>

    <!-- Section 1: Executive Summary -->
    <section class="section" id="executive-summary">
        <h2>經營摘要</h2>
        <div class="summary-grid">
            <div class="summary-card highlights">
                <h3>本週亮點</h3>
                <ul>
                    {"".join(f'<li>{h}</li>' for h in summary["highlights"])}
                </ul>
            </div>
            <div class="summary-card actions">
                <h3>行動建議</h3>
                <ul>
                    {"".join(f'<li>{a}</li>' for a in summary["actions"])}
                </ul>
            </div>
            {_build_concerns_card(summary.get("concerns", []))}
        </div>
    </section>

    <!-- Section 2: KPI Cards -->
    <section class="section" id="kpi-cards">
        <h2>關鍵指標</h2>
        <div class="kpi-grid">
            {_build_kpi_card("銷售冊數", f'{overview["total_units"]:,}', "冊",
                             overview.get("units_growth_pct"), "WoW")}
            {_build_kpi_card("營收", _format_currency(overview["total_revenue"]), "",
                             overview.get("revenue_growth_pct"), "WoW")}
            {_build_kpi_card("訂單數", f'{overview["total_orders"]:,}', "筆",
                             overview.get("orders_growth_pct"), "WoW")}
            {_build_kpi_card("平均客單價", _format_currency(int(overview["avg_order_value"])), "",
                             None, "")}
        </div>
    </section>

    <!-- Section 3: Top 10 Books -->
    <section class="section" id="top-books">
        <h2>暢銷書 TOP 10</h2>
        <table class="data-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>書名</th>
                    <th>作者</th>
                    <th>類別</th>
                    <th class="num">銷量</th>
                    <th class="num">營收</th>
                </tr>
            </thead>
            <tbody>
                {_build_top_books_rows(top_books)}
            </tbody>
        </table>
    </section>

    <!-- Section 4: Channel Distribution -->
    <section class="section" id="channel-mix">
        <h2>通路分佈</h2>
        <div class="chart-row">
            <div class="chart-container">
                <canvas id="channelPieChart"></canvas>
            </div>
            <div class="channel-table-container">
                <table class="data-table compact">
                    <thead>
                        <tr><th>通路</th><th class="num">銷量</th><th class="num">佔比</th><th class="num">營收</th></tr>
                    </thead>
                    <tbody>
                        {_build_channel_rows(channel)}
                    </tbody>
                </table>
            </div>
        </div>
    </section>

    <!-- Section 5: Paper vs Ebook -->
    <section class="section" id="book-type">
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

    <!-- Section 6: Alerts -->
    {_build_alerts_section(alerts)}

    <!-- Daily Trend Chart -->
    <section class="section" id="daily-trend">
        <h2>每日銷售趨勢</h2>
        <div class="chart-container wide">
            <canvas id="dailyTrendChart"></canvas>
        </div>
    </section>

    <footer>
        <p>金尉出版社 營運分析系統 | 自動產生於 {generated_at}</p>
    </footer>

</div>

<!-- Chart.js Scripts -->
<script>
{_build_chart_scripts(channel, daily)}
</script>

</body>
</html>"""
    return html


# ================================================================== #
#  HTML Building Helpers
# ================================================================== #

def _build_kpi_card(title: str, value: str, unit: str,
                    growth_pct: Optional[float], growth_label: str) -> str:
    """建構單一 KPI 卡片 HTML"""
    growth_html = ""
    if growth_pct is not None:
        color = _growth_color(growth_pct)
        growth_html = f"""
            <div class="kpi-growth {color}">
                {_format_growth(growth_pct)} <span class="growth-label">{growth_label}</span>
            </div>"""

    return f"""
            <div class="kpi-card">
                <div class="kpi-title">{title}</div>
                <div class="kpi-value">{value} <span class="kpi-unit">{unit}</span></div>
                {growth_html}
            </div>"""


def _build_concerns_card(concerns: list[str]) -> str:
    """建構關注事項卡片（僅在有內容時顯示）"""
    if not concerns:
        return ""
    return f"""
            <div class="summary-card concerns">
                <h3>需關注事項</h3>
                <ul>
                    {"".join(f'<li>{c}</li>' for c in concerns)}
                </ul>
            </div>"""


def _build_top_books_rows(top_books: list[dict]) -> str:
    """暢銷書表格行"""
    rows = []
    for b in top_books:
        rows.append(f"""
                <tr>
                    <td>{b['rank']}</td>
                    <td class="book-title">{b['title']}</td>
                    <td>{b['author']}</td>
                    <td><span class="badge {'ebook' if b['category'] == '電子書' else 'paper'}">{b['category']}</span></td>
                    <td class="num">{b['units']:,}</td>
                    <td class="num">{_format_currency(b['revenue'])}</td>
                </tr>""")
    return "\n".join(rows)


def _build_channel_rows(channel: dict) -> str:
    """通路分佈表格行"""
    rows = []
    labels = channel.get("labels", [])
    units = channel.get("units", [])
    unit_pcts = channel.get("unit_pcts", [])
    revenues = channel.get("revenue", [])

    for i in range(len(labels)):
        rows.append(f"""
                        <tr>
                            <td>{labels[i]}</td>
                            <td class="num">{units[i]:,}</td>
                            <td class="num">{unit_pcts[i] if i < len(unit_pcts) else 0}%</td>
                            <td class="num">{_format_currency(revenues[i]) if i < len(revenues) else '-'}</td>
                        </tr>""")
    return "\n".join(rows)


def _build_alerts_section(alerts: list[dict]) -> str:
    """警示區塊"""
    if not alerts:
        return """
    <section class="section" id="alerts">
        <h2>異常警示</h2>
        <div class="alert-box info">
            <p>本週無異常警示，各項指標正常。</p>
        </div>
    </section>"""

    alert_html = []
    for a in alerts:
        alert_html.append(f"""
            <div class="alert-box {a['level']}">
                <h4>{a['title']}</h4>
                <p>{a['message']}</p>
                <p class="alert-detail">{a.get('detail', '')}</p>
            </div>""")

    return f"""
    <section class="section" id="alerts">
        <h2>異常警示</h2>
        {"".join(alert_html)}
    </section>"""


def _build_chart_scripts(channel: dict, daily: dict) -> str:
    """Chart.js 圖表腳本"""
    import json

    channel_labels = json.dumps(channel.get("labels", [])[:8], ensure_ascii=False)
    channel_data = json.dumps(channel.get("units", [])[:8])

    daily_labels = json.dumps(daily.get("dates", []), ensure_ascii=False)
    daily_units = json.dumps(daily.get("units", []))
    daily_revenue = json.dumps(daily.get("revenue", []))

    colors = [
        "'#b8860b'", "'#b22234'", "'#3a2e1a'", "'#d4a517'",
        "'#2e7d32'", "'#996515'", "'#8b1a2b'", "'#5c4a2a'"
    ]
    bg_colors = f"[{', '.join(colors[:8])}]"

    return f"""
    // 通路圓餅圖
    new Chart(document.getElementById('channelPieChart'), {{
        type: 'pie',
        data: {{
            labels: {channel_labels},
            datasets: [{{
                data: {channel_data},
                backgroundColor: {bg_colors},
            }}]
        }},
        options: {{
            responsive: true,
            plugins: {{
                legend: {{ position: 'right' }},
                title: {{ display: true, text: '銷售通路佔比（銷量）' }}
            }}
        }}
    }});

    // 每日趨勢圖
    new Chart(document.getElementById('dailyTrendChart'), {{
        type: 'line',
        data: {{
            labels: {daily_labels},
            datasets: [
                {{
                    label: '銷量（冊）',
                    data: {daily_units},
                    borderColor: '#b8860b',
                    backgroundColor: 'rgba(184, 134, 11, 0.1)',
                    fill: true,
                    tension: 0.3,
                    yAxisID: 'y',
                }},
                {{
                    label: '營收（NT$）',
                    data: {daily_revenue},
                    borderColor: '#2e7d32',
                    backgroundColor: 'rgba(46, 125, 50, 0.1)',
                    fill: false,
                    tension: 0.3,
                    yAxisID: 'y1',
                }}
            ]
        }},
        options: {{
            responsive: true,
            interaction: {{ mode: 'index', intersect: false }},
            scales: {{
                y: {{ type: 'linear', position: 'left', title: {{ display: true, text: '銷量' }} }},
                y1: {{ type: 'linear', position: 'right', title: {{ display: true, text: '營收' }}, grid: {{ drawOnChartArea: false }} }}
            }}
        }}
    }});
    """


# ================================================================== #
#  CSS Styles
# ================================================================== #

def _get_base_css() -> str:
    """報表基礎 CSS 樣式"""
    return """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft JhengHei", sans-serif;
        background: #faf6ed; color: #3a2e1a; line-height: 1.6;
    }
    .container { max-width: 1100px; margin: 0 auto; padding: 24px; }

    /* Header */
    .report-header {
        display: flex; justify-content: space-between; align-items: flex-start;
        background: linear-gradient(135deg, #3a2e1a 0%, #5c4a2a 40%, #7a6340 100%);
        color: white; padding: 32px; border-radius: 12px; margin-bottom: 32px;
        position: relative;
    }
    .report-header::after {
        content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 4px;
        background: linear-gradient(90deg, #b22234, #d4a517, #b8860b, #d4a517, #b22234);
        border-radius: 0 0 12px 12px;
    }
    .report-header h1 {
        font-size: 1.8rem;
        background: linear-gradient(135deg, #f5e6b8 0%, #d4a517 40%, #f5e6b8 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .period { font-size: 1.1rem; color: #f5e6b8; margin-top: 4px; }
    .sub-period { font-size: 0.9rem; color: #ddd0b0; }
    .generated { font-size: 0.85rem; color: #ddd0b0; text-align: right; }

    /* Sections */
    .section { margin-bottom: 36px; }
    .section h2 {
        font-size: 1.3rem; color: #3a2e1a; border-left: 4px solid #b8860b;
        padding-left: 12px; margin-bottom: 16px;
    }

    /* Summary Cards */
    .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
    .summary-card {
        background: white; border-radius: 8px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .summary-card h3 { font-size: 1rem; margin-bottom: 10px; }
    .summary-card ul { padding-left: 20px; }
    .summary-card li { margin-bottom: 6px; font-size: 0.95rem; }
    .highlights { border-top: 3px solid #2e7d32; }
    .highlights h3 { color: #2e7d32; }
    .actions { border-top: 3px solid #b8860b; }
    .actions h3 { color: #b8860b; }
    .concerns { border-top: 3px solid #b22234; }
    .concerns h3 { color: #b22234; }

    /* KPI Cards */
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
    .kpi-card {
        background: white; border-radius: 8px; padding: 20px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .kpi-title { font-size: 0.85rem; color: #9e8e6e; margin-bottom: 8px; text-transform: uppercase; }
    .kpi-value { font-size: 1.6rem; font-weight: 700; color: #3a2e1a; }
    .kpi-unit { font-size: 0.9rem; font-weight: 400; color: #9e8e6e; }
    .kpi-growth { font-size: 0.9rem; margin-top: 6px; font-weight: 600; }
    .kpi-growth.positive { color: #2e7d32; }
    .kpi-growth.negative { color: #b22234; }
    .kpi-growth.neutral { color: #9e8e6e; }
    .growth-label { font-weight: 400; color: #9e8e6e; font-size: 0.8rem; }

    /* Tables */
    .data-table { width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .data-table thead { background: #f0e8d4; }
    .data-table th { padding: 12px 16px; text-align: left; font-size: 0.85rem; color: #5c4a2a; font-weight: 600; }
    .data-table td { padding: 10px 16px; border-top: 1px solid #f0e8d4; font-size: 0.9rem; }
    .data-table tr:hover { background: #faf6ed; }
    .num { text-align: right !important; font-variant-numeric: tabular-nums; }
    .book-title { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .compact td, .compact th { padding: 8px 12px; }

    /* Badges */
    .badge {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.75rem; font-weight: 600;
    }
    .badge.paper { background: #f5e6b8; color: #996515; }
    .badge.ebook { background: #f8e0e4; color: #8b1a2b; }

    /* Charts */
    .chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; align-items: start; }
    .chart-container { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
    .chart-container.wide { width: 100%; }
    .channel-table-container { }

    /* Type Split */
    .type-split-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .type-card {
        background: white; border-radius: 8px; padding: 24px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .type-card h3 { color: #5c4a2a; margin-bottom: 8px; }
    .type-value { font-size: 1.8rem; font-weight: 700; color: #3a2e1a; }
    .type-value .unit { font-size: 1rem; font-weight: 400; }
    .type-revenue { font-size: 1rem; color: #9e8e6e; margin-top: 4px; }
    .type-ratio { font-size: 0.85rem; color: #b8860b; margin-top: 8px; }

    /* Alerts */
    .alert-box {
        border-radius: 8px; padding: 16px 20px; margin-bottom: 12px;
    }
    .alert-box h4 { margin-bottom: 4px; }
    .alert-box.danger { background: #fef2f2; border-left: 4px solid #b22234; }
    .alert-box.danger h4 { color: #b22234; }
    .alert-box.warning { background: #fffbeb; border-left: 4px solid #f59e0b; }
    .alert-box.warning h4 { color: #d97706; }
    .alert-box.info { background: #faf6ed; border-left: 4px solid #b8860b; }
    .alert-box.info h4 { color: #b8860b; }
    .alert-detail { font-size: 0.85rem; color: #9e8e6e; margin-top: 4px; }

    /* Footer */
    footer {
        text-align: center; padding: 24px 0; margin-top: 32px;
        border-top: 1px solid #f0e8d4; color: #9e8e6e; font-size: 0.85rem;
    }

    /* Responsive */
    @media (max-width: 768px) {
        .kpi-grid { grid-template-columns: repeat(2, 1fr); }
        .chart-row { grid-template-columns: 1fr; }
        .type-split-grid { grid-template-columns: 1fr; }
        .report-header { flex-direction: column; }
    }

    @media print {
        body { background: white; }
        .container { max-width: 100%; padding: 0; }
        .section { page-break-inside: avoid; }
    }
    """
