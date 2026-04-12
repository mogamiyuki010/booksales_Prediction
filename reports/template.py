"""
HTML Report Template Engine for 金尉出版社
==========================================
Generates self-contained, McKinsey-grade HTML reports for executive review.
All CSS is inline, charts use Chart.js CDN. Output is a single HTML file.

Usage:
    from reports.template import ReportTemplate

    rt = ReportTemplate('weekly', '2026年第15週', '2026-04-12 09:00')
    html = rt.render([
        {'type': 'executive_summary', 'data': { ... }},
        {'type': 'kpi_cards',         'data': [ ... ]},
        {'type': 'top_books_table',   'data': [ ... ]},
        {'type': 'bar_chart',         'data': { ... }},
        ...
    ])
    with open('report.html', 'w', encoding='utf-8') as f:
        f.write(html)
"""

from __future__ import annotations

import html as _html
from typing import Any


# ---------------------------------------------------------------------------
# Colour palette & constants
# ---------------------------------------------------------------------------
GOLD = "#b8860b"
CREAM = "#faf6ed"
RED = "#b22234"
DARK = "#3a2e1a"
LIGHT_GOLD = "#d4a84720"
WHITE = "#ffffff"

REPORT_TYPE_LABELS = {
    "weekly": "週報",
    "monthly": "月報",
    "quarterly": "季報",
}

CHART_PALETTE = [
    "#b8860b", "#b22234", "#3a2e1a", "#4a90d9",
    "#2e7d32", "#f57c00", "#7b1fa2", "#00838f",
]


# ---------------------------------------------------------------------------
# CSS (self-contained)
# ---------------------------------------------------------------------------
def _build_css() -> str:
    return f"""
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html {{ font-size: 15px; }}
    body {{
        font-family: "Noto Sans TC", "Microsoft JhengHei", "PingFang TC",
                     -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: {CREAM};
        color: {DARK};
        line-height: 1.7;
        padding: 0;
    }}
    .report-wrapper {{
        max-width: 1200px;
        margin: 0 auto;
        padding: 40px 32px 60px;
    }}

    /* ---- Header ---- */
    header {{
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        border-bottom: 3px solid {GOLD};
        padding-bottom: 16px;
        margin-bottom: 40px;
    }}
    header .brand {{
        font-size: 1.6rem;
        font-weight: 700;
        color: {DARK};
        letter-spacing: 0.04em;
    }}
    header .brand span {{ color: {GOLD}; }}
    header .meta {{
        font-size: 0.9rem;
        color: #8a7e6a;
    }}

    /* ---- Section titles ---- */
    .section-title {{
        font-size: 1.25rem;
        font-weight: 700;
        border-left: 4px solid {GOLD};
        padding-left: 14px;
        margin: 48px 0 20px;
        color: {DARK};
    }}
    .section-title:first-of-type {{ margin-top: 0; }}

    /* ---- Insight (So What?) ---- */
    .insight {{
        background: {LIGHT_GOLD};
        border-left: 3px solid {GOLD};
        padding: 10px 16px;
        margin: 12px 0 24px;
        font-size: 0.92rem;
        color: #6b5b3e;
        border-radius: 0 6px 6px 0;
    }}
    .insight strong {{ color: {GOLD}; }}

    /* ---- KPI Cards ---- */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 20px;
        margin-bottom: 32px;
    }}
    .kpi-card {{
        background: {WHITE};
        border-radius: 10px;
        padding: 24px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        text-align: center;
        transition: transform 0.15s;
    }}
    .kpi-card:hover {{ transform: translateY(-2px); }}
    .kpi-label {{
        font-size: 0.82rem;
        color: #8a7e6a;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    .kpi-value {{
        font-size: 2rem;
        font-weight: 800;
        color: {DARK};
        line-height: 1.1;
    }}
    .kpi-change {{
        margin-top: 6px;
        font-size: 0.88rem;
        font-weight: 600;
    }}
    .kpi-change.up   {{ color: #2e7d32; }}
    .kpi-change.down {{ color: {RED}; }}
    .kpi-change.flat {{ color: #8a7e6a; }}

    /* ---- Tables ---- */
    .report-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 16px 0 28px;
        font-size: 0.92rem;
    }}
    .report-table th {{
        background: {DARK};
        color: {WHITE};
        padding: 12px 14px;
        text-align: left;
        font-weight: 600;
        white-space: nowrap;
    }}
    .report-table td {{
        padding: 11px 14px;
        border-bottom: 1px solid #e8e0d0;
    }}
    .report-table tr:nth-child(even) td {{
        background: #f7f2e8;
    }}
    .report-table tr:hover td {{
        background: #f0e8d6;
    }}
    .report-table .num {{
        text-align: right;
        font-variant-numeric: tabular-nums;
        font-weight: 600;
    }}

    /* Progress bar inside table */
    .bar-cell {{ position: relative; min-width: 100px; }}
    .bar-bg {{
        height: 8px;
        border-radius: 4px;
        background: #e8e0d0;
        overflow: hidden;
    }}
    .bar-fill {{
        height: 100%;
        border-radius: 4px;
        background: {GOLD};
    }}

    /* ---- Charts ---- */
    .chart-container {{
        background: {WHITE};
        border-radius: 10px;
        padding: 24px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin: 16px 0 28px;
    }}
    .chart-container canvas {{
        max-height: 380px;
    }}

    /* ---- Executive Summary ---- */
    .exec-summary {{
        background: {WHITE};
        border-radius: 10px;
        padding: 28px 32px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.06);
        margin-bottom: 36px;
    }}
    .exec-summary h2 {{
        font-size: 1.15rem;
        color: {GOLD};
        margin-bottom: 14px;
        display: flex;
        align-items: center;
        gap: 8px;
    }}
    .exec-summary ul {{
        list-style: none;
        padding: 0;
    }}
    .exec-summary ul li {{
        padding: 6px 0 6px 20px;
        position: relative;
        font-size: 0.95rem;
    }}
    .exec-summary ul li::before {{
        content: "";
        position: absolute;
        left: 0;
        top: 14px;
        width: 8px;
        height: 8px;
        background: {GOLD};
        border-radius: 50%;
    }}
    .exec-actions {{
        margin-top: 20px;
        padding-top: 16px;
        border-top: 1px solid #e8e0d0;
    }}
    .exec-actions h3 {{
        font-size: 0.95rem;
        color: {RED};
        margin-bottom: 10px;
    }}
    .exec-actions li::before {{
        background: {RED} !important;
    }}

    /* ---- Alert Box ---- */
    .alert-box {{
        border-radius: 10px;
        padding: 20px 24px;
        margin: 16px 0 28px;
    }}
    .alert-box.warning {{
        background: #fff8e1;
        border-left: 4px solid #f9a825;
    }}
    .alert-box.danger {{
        background: #fce4ec;
        border-left: 4px solid {RED};
    }}
    .alert-box.info {{
        background: #e3f2fd;
        border-left: 4px solid #1976d2;
    }}
    .alert-box h4 {{
        margin-bottom: 10px;
        font-size: 1rem;
    }}
    .alert-box ul {{
        list-style: disc;
        padding-left: 20px;
    }}
    .alert-box li {{
        padding: 3px 0;
        font-size: 0.92rem;
    }}

    /* ---- Comparison table ---- */
    .comp-current {{ color: {GOLD}; font-weight: 700; }}
    .comp-previous {{ color: #8a7e6a; }}

    /* ---- Footer ---- */
    footer {{
        margin-top: 56px;
        padding-top: 16px;
        border-top: 2px solid {GOLD};
        display: flex;
        justify-content: space-between;
        font-size: 0.8rem;
        color: #8a7e6a;
    }}

    /* ---- Print ---- */
    @media print {{
        body {{ background: white; font-size: 13px; }}
        .report-wrapper {{ padding: 0; max-width: 100%; }}
        .kpi-card, .chart-container, .exec-summary {{
            box-shadow: none;
            border: 1px solid #ddd;
            break-inside: avoid;
        }}
        .chart-container {{ page-break-inside: avoid; }}
        header {{ border-bottom-width: 2px; }}
        footer {{ margin-top: 24px; }}
    }}

    /* ---- Responsive ---- */
    @media (max-width: 900px) {{
        .kpi-grid {{ grid-template-columns: repeat(2, 1fr); }}
    }}
    @media (max-width: 520px) {{
        .kpi-grid {{ grid-template-columns: 1fr; }}
        .report-wrapper {{ padding: 20px 14px 40px; }}
        header {{ flex-direction: column; gap: 6px; }}
    }}
    """


# ---------------------------------------------------------------------------
# Template class
# ---------------------------------------------------------------------------
class ReportTemplate:
    """Generate self-contained HTML reports for 金尉出版社 executive review."""

    def __init__(
        self,
        report_type: str,
        period_label: str,
        generated_at: str,
    ) -> None:
        """
        Parameters
        ----------
        report_type : str
            One of 'weekly', 'monthly', 'quarterly'.
        period_label : str
            Human-readable period, e.g. '2026年第15週'.
        generated_at : str
            Timestamp string, e.g. '2026-04-12 09:00'.
        """
        self.report_type = report_type
        self.type_label = REPORT_TYPE_LABELS.get(report_type, report_type)
        self.period_label = period_label
        self.generated_at = generated_at
        self._chart_counter = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def render(self, sections: list[dict[str, Any]]) -> str:
        """Render a complete HTML report.

        Parameters
        ----------
        sections : list of dict
            Each dict has ``type`` (str) and ``data`` (dict/list).
            Supported types: executive_summary, kpi_cards, top_books_table,
            bar_chart, line_chart, pie_chart, comparison_table, alert_box.

        Returns
        -------
        str
            Complete, self-contained HTML document (UTF-8).
        """
        self._chart_counter = 0
        body_parts: list[str] = []

        dispatch = {
            "executive_summary": self._render_executive_summary,
            "kpi_cards": self._render_kpi_cards,
            "top_books_table": self._render_top_books_table,
            "bar_chart": self._render_bar_chart,
            "line_chart": self._render_line_chart,
            "pie_chart": self._render_pie_chart,
            "comparison_table": self._render_comparison_table,
            "alert_box": self._render_alert_box,
        }

        for section in sections:
            renderer = dispatch.get(section["type"])
            if renderer is None:
                body_parts.append(
                    f'<p style="color:{RED};">⚠ 未知區塊類型: '
                    f'{_html.escape(section["type"])}</p>'
                )
                continue
            body_parts.append(renderer(section["data"]))

        return self._wrap_html("\n".join(body_parts))

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------
    def _render_executive_summary(self, data: dict) -> str:
        """Executive summary with key highlights and action items.

        data: { highlights: [str], actions: [str] }
        """
        highlights = data.get("highlights", [])
        actions = data.get("actions", [])

        hl_items = "\n".join(
            f"<li>{_html.escape(h)}</li>" for h in highlights
        )
        act_items = "\n".join(
            f"<li>{_html.escape(a)}</li>" for a in actions
        )

        actions_block = ""
        if actions:
            actions_block = f"""
            <div class="exec-actions">
                <h3>&#9888; 建議行動</h3>
                <ul>{act_items}</ul>
            </div>"""

        return f"""
        <div class="exec-summary">
            <h2>&#x1F4CB; 本期重點摘要</h2>
            <ul>{hl_items}</ul>
            {actions_block}
        </div>"""

    def _render_kpi_cards(self, data: list[dict]) -> str:
        """Row of KPI cards with trend indicators.

        data: [{ label, value, change_pct, trend }]
              trend: 'up' | 'down' | 'flat'
        """
        cards: list[str] = []
        for item in data:
            trend = item.get("trend", "flat")
            arrow = {"up": "&#8593;", "down": "&#8595;", "flat": "&#8594;"}.get(
                trend, "&#8594;"
            )
            css_class = {"up": "up", "down": "down"}.get(trend, "flat")
            change = item.get("change_pct", 0)
            sign = "+" if change > 0 else ""
            cards.append(f"""
            <div class="kpi-card">
                <div class="kpi-label">{_html.escape(str(item['label']))}</div>
                <div class="kpi-value">{_html.escape(str(item['value']))}</div>
                <div class="kpi-change {css_class}">
                    {arrow} {sign}{change}%
                </div>
            </div>""")

        return f"""
        <h3 class="section-title">關鍵績效指標</h3>
        <div class="kpi-grid">
            {"".join(cards)}
        </div>"""

    def _render_top_books_table(self, data: list[dict]) -> str:
        """Ranked table of top-selling books with progress bars.

        data: [{ rank, title, author, sales, revenue, change_pct }]
        """
        max_sales = max((b.get("sales", 0) for b in data), default=1) or 1

        rows: list[str] = []
        for book in data:
            pct = book.get("sales", 0) / max_sales * 100
            change = book.get("change_pct", 0)
            trend_cls = "up" if change > 0 else ("down" if change < 0 else "flat")
            arrow = {"up": "↑", "down": "↓", "flat": "→"}[trend_cls]
            sign = "+" if change > 0 else ""
            rows.append(f"""
            <tr>
                <td class="num">{book.get('rank', '')}</td>
                <td>{_html.escape(str(book.get('title', '')))}</td>
                <td>{_html.escape(str(book.get('author', '')))}</td>
                <td class="num">{book.get('sales', 0):,}</td>
                <td class="bar-cell">
                    <div class="bar-bg"><div class="bar-fill" style="width:{pct:.0f}%"></div></div>
                </td>
                <td class="num">${book.get('revenue', 0):,.0f}</td>
                <td class="num kpi-change {trend_cls}">{arrow} {sign}{change}%</td>
            </tr>""")

        return f"""
        <h3 class="section-title">暢銷書排行</h3>
        <table class="report-table">
            <thead>
                <tr>
                    <th>#</th><th>書名</th><th>作者</th>
                    <th>銷量</th><th>佔比</th><th>營收</th><th>變化</th>
                </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
        </table>"""

    def _render_bar_chart(self, data: dict) -> str:
        """Horizontal bar chart via Chart.js.

        data: { title, insight, labels, values, color? }
        """
        canvas_id = self._next_chart_id()
        color = data.get("color", GOLD)
        labels_js = _js_string_array(data.get("labels", []))
        values_js = _js_number_array(data.get("values", []))
        insight = data.get("insight", "")

        insight_html = ""
        if insight:
            insight_html = (
                f'<div class="insight"><strong>So What?</strong> '
                f"{_html.escape(insight)}</div>"
            )

        return f"""
        <h3 class="section-title">{_html.escape(data.get('title', '長條圖'))}</h3>
        {insight_html}
        <div class="chart-container">
            <canvas id="{canvas_id}"></canvas>
        </div>
        <script>
        new Chart(document.getElementById('{canvas_id}'), {{
            type: 'bar',
            data: {{
                labels: {labels_js},
                datasets: [{{
                    data: {values_js},
                    backgroundColor: '{color}',
                    borderRadius: 4,
                    barThickness: 28
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                plugins: {{
                    legend: {{ display: false }},
                    tooltip: {{
                        callbacks: {{
                            label: ctx => ctx.parsed.x.toLocaleString()
                        }}
                    }}
                }},
                scales: {{
                    x: {{
                        ticks: {{ callback: v => v.toLocaleString() }},
                        grid: {{ color: '#e8e0d020' }}
                    }},
                    y: {{ grid: {{ display: false }} }}
                }}
            }}
        }});
        </script>"""

    def _render_line_chart(self, data: dict) -> str:
        """Line chart for trend data via Chart.js.

        data: { title, insight, labels, datasets: [{label, values, color?}] }
        """
        canvas_id = self._next_chart_id()
        labels_js = _js_string_array(data.get("labels", []))
        insight = data.get("insight", "")

        datasets_js_parts: list[str] = []
        for i, ds in enumerate(data.get("datasets", [])):
            c = ds.get("color", CHART_PALETTE[i % len(CHART_PALETTE)])
            datasets_js_parts.append(
                f"""{{
                    label: {_js_string(ds.get('label', ''))},
                    data: {_js_number_array(ds.get('values', []))},
                    borderColor: '{c}',
                    backgroundColor: '{c}22',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }}"""
            )

        insight_html = ""
        if insight:
            insight_html = (
                f'<div class="insight"><strong>So What?</strong> '
                f"{_html.escape(insight)}</div>"
            )

        return f"""
        <h3 class="section-title">{_html.escape(data.get('title', '趨勢圖'))}</h3>
        {insight_html}
        <div class="chart-container">
            <canvas id="{canvas_id}"></canvas>
        </div>
        <script>
        new Chart(document.getElementById('{canvas_id}'), {{
            type: 'line',
            data: {{
                labels: {labels_js},
                datasets: [{','.join(datasets_js_parts)}]
            }},
            options: {{
                responsive: true,
                interaction: {{ intersect: false, mode: 'index' }},
                plugins: {{
                    legend: {{ position: 'bottom' }},
                    tooltip: {{
                        callbacks: {{
                            label: ctx => ctx.dataset.label + ': ' + ctx.parsed.y.toLocaleString()
                        }}
                    }}
                }},
                scales: {{
                    y: {{
                        ticks: {{ callback: v => v.toLocaleString() }},
                        grid: {{ color: '#e8e0d040' }}
                    }},
                    x: {{ grid: {{ display: false }} }}
                }}
            }}
        }});
        </script>"""

    def _render_pie_chart(self, data: dict) -> str:
        """Donut / pie chart via Chart.js.

        data: { title, insight, labels, values }
        """
        canvas_id = self._next_chart_id()
        labels_js = _js_string_array(data.get("labels", []))
        values_js = _js_number_array(data.get("values", []))
        n = len(data.get("labels", []))
        colors_js = str(CHART_PALETTE[:n]).replace("'", '"')
        insight = data.get("insight", "")

        insight_html = ""
        if insight:
            insight_html = (
                f'<div class="insight"><strong>So What?</strong> '
                f"{_html.escape(insight)}</div>"
            )

        return f"""
        <h3 class="section-title">{_html.escape(data.get('title', '佔比分析'))}</h3>
        {insight_html}
        <div class="chart-container" style="max-width:520px;margin-left:auto;margin-right:auto;">
            <canvas id="{canvas_id}"></canvas>
        </div>
        <script>
        new Chart(document.getElementById('{canvas_id}'), {{
            type: 'doughnut',
            data: {{
                labels: {labels_js},
                datasets: [{{
                    data: {values_js},
                    backgroundColor: {colors_js},
                    borderWidth: 2,
                    borderColor: '#fff'
                }}]
            }},
            options: {{
                responsive: true,
                cutout: '55%',
                plugins: {{
                    legend: {{ position: 'bottom' }},
                    tooltip: {{
                        callbacks: {{
                            label: ctx => {{
                                const total = ctx.dataset.data.reduce((a,b) => a+b, 0);
                                const pct = (ctx.parsed / total * 100).toFixed(1);
                                return ctx.label + ': ' + ctx.parsed.toLocaleString() + ' (' + pct + '%)';
                            }}
                        }}
                    }}
                }}
            }}
        }});
        </script>"""

    def _render_comparison_table(self, data: dict) -> str:
        """Side-by-side comparison table (current vs previous period).

        data: {
            title: str,
            insight: str,
            headers: [str, str, str, str],  # e.g. ['指標', '本期', '上期', '變化']
            rows: [{ label, current, previous, change_pct }]
        }
        """
        headers = data.get("headers", ["指標", "本期", "上期", "變化"])
        insight = data.get("insight", "")

        hdr_html = "".join(f"<th>{_html.escape(h)}</th>" for h in headers)

        rows: list[str] = []
        for row in data.get("rows", []):
            change = row.get("change_pct", 0)
            trend_cls = "up" if change > 0 else ("down" if change < 0 else "flat")
            arrow = {"up": "↑", "down": "↓", "flat": "→"}[trend_cls]
            sign = "+" if change > 0 else ""
            rows.append(f"""
            <tr>
                <td>{_html.escape(str(row.get('label', '')))}</td>
                <td class="num comp-current">{_html.escape(str(row.get('current', '')))}</td>
                <td class="num comp-previous">{_html.escape(str(row.get('previous', '')))}</td>
                <td class="num kpi-change {trend_cls}">{arrow} {sign}{change}%</td>
            </tr>""")

        insight_html = ""
        if insight:
            insight_html = (
                f'<div class="insight"><strong>So What?</strong> '
                f"{_html.escape(insight)}</div>"
            )

        return f"""
        <h3 class="section-title">{_html.escape(data.get('title', '期間比較'))}</h3>
        {insight_html}
        <table class="report-table">
            <thead><tr>{hdr_html}</tr></thead>
            <tbody>{"".join(rows)}</tbody>
        </table>"""

    def _render_alert_box(self, data: dict) -> str:
        """Warning / attention / info alert box.

        data: { level: 'warning'|'danger'|'info', title?: str, items: [str] }
        """
        level = data.get("level", "info")
        level_css = level if level in ("warning", "danger", "info") else "info"
        icons = {"warning": "&#9888;", "danger": "&#10060;", "info": "&#8505;"}
        default_titles = {
            "warning": "注意事項",
            "danger": "警示",
            "info": "資訊",
        }
        title = data.get("title", default_titles.get(level, "提示"))
        items = "\n".join(
            f"<li>{_html.escape(item)}</li>" for item in data.get("items", [])
        )

        return f"""
        <div class="alert-box {level_css}">
            <h4>{icons.get(level, '')} {_html.escape(title)}</h4>
            <ul>{items}</ul>
        </div>"""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _next_chart_id(self) -> str:
        self._chart_counter += 1
        return f"chart_{self._chart_counter}"

    def _wrap_html(self, body: str) -> str:
        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>金尉出版社 — {_html.escape(self.type_label)} {_html.escape(self.period_label)}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>{_build_css()}</style>
</head>
<body>
<div class="report-wrapper">
    <header>
        <div class="brand"><span>金尉</span>出版社</div>
        <div class="meta">{_html.escape(self.type_label)} &middot; {_html.escape(self.period_label)}</div>
    </header>

    {body}

    <footer>
        <span>產生時間：{_html.escape(self.generated_at)}</span>
        <span>GEM v2.0 | 金尉出版社營運報表系統</span>
    </footer>
</div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# JavaScript literal helpers
# ---------------------------------------------------------------------------
def _js_string(s: str) -> str:
    """Wrap a Python string as a JS string literal."""
    escaped = s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
    return f"'{escaped}'"


def _js_string_array(items: list) -> str:
    return "[" + ",".join(_js_string(str(i)) for i in items) + "]"


def _js_number_array(items: list) -> str:
    return "[" + ",".join(str(float(v)) for v in items) + "]"


# ---------------------------------------------------------------------------
# Quick demo / smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    rt = ReportTemplate("weekly", "2026年第15週", "2026-04-12 09:00")

    demo_sections = [
        {
            "type": "executive_summary",
            "data": {
                "highlights": [
                    "本週整體銷量 4,280 冊，較上週成長 12%",
                    "新書《超級個體》首週即登暢銷榜第二名，銷量 680 冊",
                    "電子書佔比首次突破 25%，達 26.3%",
                ],
                "actions": [
                    "加印《超級個體》2,000 冊，預計下週到貨",
                    "追蹤《被動收入全攻略》庫存，目前僅剩 320 冊",
                    "安排《超級個體》作者下週三直播活動",
                ],
            },
        },
        {
            "type": "kpi_cards",
            "data": [
                {"label": "總銷量", "value": "4,280 冊", "change_pct": 12, "trend": "up"},
                {"label": "總營收", "value": "NT$1,520K", "change_pct": 8.5, "trend": "up"},
                {"label": "平均單價", "value": "NT$355", "change_pct": -2.1, "trend": "down"},
                {"label": "退貨率", "value": "4.2%", "change_pct": -0.8, "trend": "down"},
            ],
        },
        {
            "type": "top_books_table",
            "data": [
                {"rank": 1, "title": "被動收入全攻略", "author": "張志銘", "sales": 820, "revenue": 295200, "change_pct": -5},
                {"rank": 2, "title": "超級個體", "author": "林心怡", "sales": 680, "revenue": 251600, "change_pct": 999},
                {"rank": 3, "title": "投資心理學", "author": "陳家豪", "sales": 540, "revenue": 189000, "change_pct": 3},
                {"rank": 4, "title": "從零開始學理財", "author": "王美玲", "sales": 450, "revenue": 148500, "change_pct": -12},
                {"rank": 5, "title": "創業者手冊", "author": "李大偉", "sales": 390, "revenue": 140400, "change_pct": 7},
            ],
        },
        {
            "type": "bar_chart",
            "data": {
                "title": "各通路銷量分布",
                "insight": "博客來持續主導，佔比達 42%；但蝦皮成長最快（+35%），值得加大投入。",
                "labels": ["博客來", "誠品", "金石堂", "蝦皮", "官網", "其他"],
                "values": [1798, 856, 642, 428, 342, 214],
            },
        },
        {
            "type": "line_chart",
            "data": {
                "title": "近 8 週銷量趨勢",
                "insight": "整體銷量連續 4 週上升，本週為近兩個月新高。",
                "labels": ["W8", "W9", "W10", "W11", "W12", "W13", "W14", "W15"],
                "datasets": [
                    {"label": "紙本書", "values": [2800, 2650, 2900, 2750, 3000, 3100, 3200, 3150], "color": "#b8860b"},
                    {"label": "電子書", "values": [650, 700, 720, 780, 820, 900, 1000, 1130], "color": "#4a90d9"},
                ],
            },
        },
        {
            "type": "pie_chart",
            "data": {
                "title": "營收類別佔比",
                "insight": "商業理財類仍為主力（58%），但心理勵志類成長 15%，潛力可期。",
                "labels": ["商業理財", "心理勵志", "投資理財", "職場技能", "其他"],
                "values": [882, 304, 198, 91, 45],
            },
        },
        {
            "type": "comparison_table",
            "data": {
                "title": "本週 vs 上週比較",
                "insight": "營收及銷量雙雙成長，但退書量略增，需關注《從零開始學理財》退貨趨勢。",
                "headers": ["指標", "本週", "上週", "變化"],
                "rows": [
                    {"label": "總銷量（冊）", "current": "4,280", "previous": "3,820", "change_pct": 12},
                    {"label": "總營收（NT$）", "current": "1,520K", "previous": "1,402K", "change_pct": 8.5},
                    {"label": "退書量（冊）", "current": "180", "previous": "165", "change_pct": 9.1},
                    {"label": "新客訂單", "current": "312", "previous": "280", "change_pct": 11.4},
                ],
            },
        },
        {
            "type": "alert_box",
            "data": {
                "level": "warning",
                "items": [
                    "《被動收入全攻略》庫存僅剩 320 冊，預估 2.5 週後售罄",
                    "蝦皮通路本週出現 3 筆異常退貨，已通知客服跟進",
                ],
            },
        },
        {
            "type": "alert_box",
            "data": {
                "level": "info",
                "title": "近期排程",
                "items": [
                    "4/15（三）《超級個體》作者直播（博客來 x Facebook）",
                    "4/18（六）誠品信義店實體簽書會",
                ],
            },
        },
    ]

    output = rt.render(demo_sections)
    out_path = "reports/output/demo_weekly_report.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Demo report written to {out_path}")
    print(f"Total length: {len(output):,} characters")
