"""
回測引擎: 對 6 個校準案例執行改進後的 GEM v1.0 模型
比較 v0.1 (prompt) vs v1.0 (改進版) 的預測準確度
"""

import sys
import os

# 加入專案根目錄到路徑
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from models.heuristic.predictor import GEMPredictor, AuthorProfile, BookInfo


# ============================================================
# 6 個校準案例 (基於訓練文件中的真實數據)
# 注意: 社群粉絲數為合理推估值，實際應從 API 取得
# ============================================================

CASE_STUDIES = [
    {
        "name": "陳重銘",
        "author": AuthorProfile(
            name="陳重銘",
            author_type="KOP",
            yt_subscribers=250000,
            ig_followers=50000,
            fb_followers=300000,
            course_students=5000,
            app_subscribers=0,
            engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="陳重銘新書",
            subcategory="ETF存股",
            price_ntd=420,
            is_sequel=False,
            nth_book=5,
        ),
        "actual_sales": 14000,
        "actual_period_months": 3.7,
        "v01_prediction": (29250, 35100),
    },
    {
        "name": "艾蜜莉 2.0",
        "author": AuthorProfile(
            name="艾蜜莉",
            author_type="KOC",           # 自身品牌續作，非 Co-Branding 繼承
            yt_subscribers=30000,
            ig_followers=80000,
            fb_followers=200000,
            course_students=3000,
            app_subscribers=2000,
            mentor_historical_sales=0,    # 非 Co-Branding，無導師
            engagement_rate=0.04,
        ),
        "book": BookInfo(
            title="艾蜜莉存股術 2.0",
            subcategory="ETF存股",
            price_ntd=420,
            is_sequel=True,
            nth_book=2,
        ),
        "actual_sales": 13740,
        "actual_period_months": 8,
        "v01_prediction": (25000, 30000),
    },
    {
        "name": "陳威良",
        "author": AuthorProfile(
            name="陳威良",
            author_type="KOC",
            yt_subscribers=150000,
            ig_followers=20000,
            fb_followers=30000,
            course_students=500,
            app_subscribers=0,
            engagement_rate=0.02,
        ),
        "book": BookInfo(
            title="陳威良投資書",
            subcategory="技術分析",
            price_ntd=380,
            is_sequel=False,
            nth_book=1,
        ),
        "actual_sales": 4500,
        "actual_period_months": 6,
        "v01_prediction": (8450, 10400),
    },
    {
        "name": "朱家泓",
        "author": AuthorProfile(
            name="朱家泓",
            author_type="KOP",
            yt_subscribers=100000,
            ig_followers=30000,
            fb_followers=200000,
            course_students=8000,
            app_subscribers=0,
            engagement_rate=0.035,
        ),
        "book": BookInfo(
            title="朱家泓技術分析套書",
            subcategory="技術分析K線實戰",
            price_ntd=820,
            is_sequel=False,
            nth_book=4,
            format="set",
        ),
        "actual_sales": 13237,
        "actual_period_months": 7,
        "v01_prediction": (25000, 30000),
    },
    {
        "name": "莎拉王",
        "author": AuthorProfile(
            name="莎拉王",
            author_type="KOC",
            yt_subscribers=50000,
            ig_followers=180000,
            fb_followers=60000,
            course_students=1000,
            app_subscribers=0,
            engagement_rate=0.05,
        ),
        "book": BookInfo(
            title="莎拉王理財書",
            subcategory="新手財務自由",
            price_ntd=380,
            is_sequel=False,
            nth_book=1,
        ),
        "actual_sales": 10568,
        "actual_period_months": 4.5,
        "v01_prediction": (10000, 12000),
    },
    {
        "name": "林穎",
        "author": AuthorProfile(
            name="林穎",
            author_type="Co-Branding",
            yt_subscribers=20000,
            ig_followers=40000,
            fb_followers=100000,
            course_students=2000,
            app_subscribers=1000,
            mentor_historical_sales=13237,  # 導師朱家泓的歷史銷量 (7個月)
            engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="林穎投資傳承書",
            subcategory="ETF存股",
            price_ntd=400,
            is_sequel=False,
            nth_book=1,
        ),
        "actual_sales": 18551,
        "actual_period_months": 29,
        "v01_prediction": (22000, 25000),
    },
]


def compute_error(pred_low: int, pred_high: int, actual: int) -> dict:
    """計算預測誤差指標"""
    mid = (pred_low + pred_high) / 2
    error_pct = ((mid - actual) / actual) * 100
    abs_error_pct = abs(error_pct)
    # 檢查實際值是否落在預測區間內
    in_range = pred_low <= actual <= pred_high
    return {
        "mid_prediction": mid,
        "error_pct": error_pct,
        "abs_error_pct": abs_error_pct,
        "in_range": in_range,
    }


def run_backtest():
    predictor = GEMPredictor()

    print("=" * 90)
    print("  GEM 模型回測報告: v0.1 (prompt) vs v1.0 (改進版)")
    print("=" * 90)

    v01_errors = []
    v10_errors = []
    v10_period_errors = []

    for case in CASE_STUDIES:
        result = predictor.predict(case["author"], case["book"])
        actual = case["actual_sales"]
        period = case["actual_period_months"]

        # v0.1 誤差 (首年預測 vs 部分期間實際)
        v01_err = compute_error(
            case["v01_prediction"][0], case["v01_prediction"][1], actual
        )
        v01_errors.append(v01_err["abs_error_pct"])

        # v1.0 首年預測誤差
        v10_fy_err = compute_error(result.sales_fy_low, result.sales_fy_high, actual)
        v10_errors.append(v10_fy_err["abs_error_pct"])

        # v1.0 對應期間預測 (用月度曲線取對應月份的累計值)
        period_int = int(round(period))
        period_int = max(1, min(period_int, 12))
        v10_period_low = result.curve_conservative.total_at_month(period_int)
        v10_period_high = result.curve_optimistic.total_at_month(period_int)
        v10_period_err = compute_error(v10_period_low, v10_period_high, actual)
        v10_period_errors.append(v10_period_err["abs_error_pct"])

        print(f"\n--- {case['name']} ({case['author'].author_type}) ---")
        print(f"  實際銷量: {actual:,} 本 ({period} 個月)")
        print(
            f"  v0.1 首年預測: {case['v01_prediction'][0]:,} - {case['v01_prediction'][1]:,}"
            f"  中位 {v01_err['mid_prediction']:,.0f}  誤差 {v01_err['error_pct']:+.1f}%"
        )
        print(
            f"  v1.0 首年預測: {result.sales_fy_low:,} - {result.sales_fy_high:,}"
            f"  中位 {v10_fy_err['mid_prediction']:,.0f}  誤差 {v10_fy_err['error_pct']:+.1f}%"
        )
        in_range_str = "[OK]" if v10_period_err["in_range"] else "[Miss]"
        print(
            f"  v1.0 {period_int}M predict: {v10_period_low:,} - {v10_period_high:,}"
            f"  mid {v10_period_err['mid_prediction']:,.0f}  err {v10_period_err['error_pct']:+.1f}%"
            f"  {in_range_str}"
        )
        print(f"  首印量建議: {result.print_run_low:,} - {result.print_run_high:,} 本")

    # 彙總統計
    import statistics

    print(f"\n{'=' * 90}")
    print(f"  彙總統計")
    print(f"{'=' * 90}")

    def stats_summary(name, errors):
        avg = statistics.mean(errors)
        med = statistics.median(errors)
        mx = max(errors)
        mn = min(errors)
        print(f"\n  {name}:")
        print(f"    平均絕對誤差 (MAE%): {avg:.1f}%")
        print(f"    中位數誤差:          {med:.1f}%")
        print(f"    最小誤差:            {mn:.1f}%")
        print(f"    最大誤差:            {mx:.1f}%")
        return med

    med_v01 = stats_summary("v0.1 (prompt) - 首年預測 vs 部分期間實際", v01_errors)
    med_v10 = stats_summary("v1.0 (改進版) - 首年預測 vs 部分期間實際", v10_errors)
    med_v10p = stats_summary("v1.0 (改進版) - 對應期間預測 vs 實際", v10_period_errors)

    print(f"\n  --- 改善幅度 ---")
    if med_v01 > 0:
        improvement = ((med_v01 - med_v10) / med_v01) * 100
        print(f"  首年預測中位數誤差改善: {med_v01:.1f}% → {med_v10:.1f}% (改善 {improvement:.0f}%)")
    improvement_p = ((med_v01 - med_v10p) / med_v01) * 100 if med_v01 > 0 else 0
    print(f"  對應期間預測中位數誤差: {med_v10p:.1f}% (相對 v0.1 改善 {improvement_p:.0f}%)")
    print(f"{'=' * 90}")

    # 輸出一份完整報告
    print(f"\n\n--- 範例完整報告 (莎拉王) ---")
    sara_result = predictor.predict(CASE_STUDIES[4]["author"], CASE_STUDIES[4]["book"])
    print(predictor.format_report(sara_result))


if __name__ == "__main__":
    run_backtest()
