"""
回測引擎 v2.0: 使用真實營收資料驗證 GEM v1.0 vs v2.0 預測準確度
資料來源: 營收表-Rawdata.csv 的實際月度銷售曲線
"""

import sys
import os
import statistics

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from models.heuristic.predictor import GEMPredictor, AuthorProfile as AP1, BookInfo as BI1
from models.heuristic.predictor_v2 import GEMPredictorV2, AuthorProfile, BookInfo


# ============================================================
# 真實銷售資料校準案例
# 來源: 營收表-Rawdata.csv 月度彙總 (不含退貨)
# 社群粉絲數為合理推估值
# ============================================================

REAL_CASES = [
    {
        "name": "陳重銘 - 存100張金融股",
        "book_id": "B0000086",
        "author": AuthorProfile(
            name="陳重銘", author_type="KOP",
            yt_subscribers=250000, ig_followers=50000, fb_followers=300000,
            course_students=5000, engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="存100張金融股", subcategory="ETF存股",
            price_ntd=380, nth_book=6,
        ),
        "actual_paper_12m": 16260,
        "actual_ebook_12m": 1457,
    },
    {
        "name": "陳重銘 - 富媽媽窮媽媽",
        "book_id": "B0000131",
        "author": AuthorProfile(
            name="陳重銘", author_type="KOP",
            yt_subscribers=280000, ig_followers=60000, fb_followers=320000,
            course_students=6000, engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="富媽媽窮媽媽", subcategory="親子理財",
            price_ntd=350, nth_book=8,
        ),
        "actual_paper_12m": 11871,
        "actual_ebook_12m": 999,
    },
    {
        "name": "朱家泓 - 活用技術分析寶典",
        "book_id": "B0000116",
        "author": AuthorProfile(
            name="朱家泓", author_type="KOP",
            yt_subscribers=100000, ig_followers=30000, fb_followers=200000,
            course_students=8000, engagement_rate=0.035,
        ),
        "book": BookInfo(
            title="活用技術分析寶典", subcategory="技術分析",
            price_ntd=820, nth_book=5, format="set",
        ),
        "actual_paper_12m": 13150,
        "actual_ebook_12m": 1864,
    },
    {
        "name": "艾蜜莉 - 存股術2.0",
        "book_id": "B0000105",
        "author": AuthorProfile(
            name="艾蜜莉", author_type="KOC",
            yt_subscribers=30000, ig_followers=80000, fb_followers=200000,
            course_students=3000, app_subscribers=2000,
            engagement_rate=0.04,
        ),
        "book": BookInfo(
            title="艾蜜莉存股術2.0", subcategory="ETF存股",
            price_ntd=420, is_sequel=True, nth_book=2,
        ),
        "actual_paper_12m": 14651,
        "actual_ebook_12m": 1869,
    },
    {
        "name": "莎拉王 - 新式型態學",
        "book_id": "B0000110",
        "author": AuthorProfile(
            name="莎拉王", author_type="KOC",
            yt_subscribers=50000, ig_followers=180000, fb_followers=60000,
            course_students=1000, engagement_rate=0.05,
        ),
        "book": BookInfo(
            title="新式型態學", subcategory="技術分析型態學",
            price_ntd=380, nth_book=1,
        ),
        "actual_paper_12m": 11252,
        "actual_ebook_12m": 868,
    },
    {
        "name": "楊禮軒 - 教官財報有問題",
        "book_id": "B0000068",
        "author": AuthorProfile(
            name="楊禮軒", author_type="KOC",
            yt_subscribers=80000, ig_followers=30000, fb_followers=50000,
            course_students=500, engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="教官財報有問題", subcategory="基本面分析",
            price_ntd=350, nth_book=1,
        ),
        "actual_paper_12m": 11281,
        "actual_ebook_12m": 1137,
    },
    {
        "name": "蕭啟斌 - 可轉債存股術",
        "book_id": "B0000063",
        "author": AuthorProfile(
            name="蕭啟斌", author_type="KOC",
            yt_subscribers=60000, ig_followers=20000, fb_followers=40000,
            course_students=800, engagement_rate=0.02,
        ),
        "book": BookInfo(
            title="可轉債存股術", subcategory="可轉債",
            price_ntd=350, nth_book=1,
        ),
        "actual_paper_12m": 12597,
        "actual_ebook_12m": 1056,
    },
    {
        "name": "權證小哥 - 短線終極戰法",
        "book_id": "B0000124",
        "author": AuthorProfile(
            name="權證小哥", author_type="KOC",
            yt_subscribers=100000, ig_followers=40000, fb_followers=80000,
            course_students=2000, engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="短線終極戰法", subcategory="權證",
            price_ntd=420, nth_book=1,
        ),
        "actual_paper_12m": 9257,
        "actual_ebook_12m": 1114,
    },
    {
        "name": "林穎 - 學會走圖SOP",
        "book_id": "B0000080",
        "author": AuthorProfile(
            name="林穎", author_type="Co-Branding",
            yt_subscribers=20000, ig_followers=40000, fb_followers=100000,
            course_students=2000, app_subscribers=1000,
            mentor_historical_sales=13237,
            engagement_rate=0.03,
        ),
        "book": BookInfo(
            title="學會走圖SOP", subcategory="技術分析",
            price_ntd=380, nth_book=1,
        ),
        "actual_paper_12m": 14282,
        "actual_ebook_12m": 1292,
    },
    {
        "name": "秦嗣林 - 人生流當品",
        "book_id": "B0000072",
        "author": AuthorProfile(
            name="秦嗣林", author_type="Debut",
            yt_subscribers=10000, ig_followers=5000, fb_followers=30000,
            course_students=0, engagement_rate=0.01,
        ),
        "book": BookInfo(
            title="人生流當品", subcategory="人生勵志",
            price_ntd=350, nth_book=1,
        ),
        "actual_paper_12m": 7552,
        "actual_ebook_12m": 469,
    },
]


def compute_error(pred_low: int, pred_high: int, actual: int) -> dict:
    mid = (pred_low + pred_high) / 2
    error_pct = ((mid - actual) / actual) * 100 if actual > 0 else 0
    in_range = pred_low <= actual <= pred_high
    return {
        "mid": mid,
        "error_pct": error_pct,
        "abs_error_pct": abs(error_pct),
        "in_range": in_range,
    }


def run_backtest():
    v1 = GEMPredictor()
    v2 = GEMPredictorV2()

    print("=" * 96)
    print("  GEM 模型回測: v1.0 vs v2.0 (真實營收資料驗證)")
    print("  資料來源: 營收表-Rawdata.csv | 10 個真實案例 | 紙本書 + 電子書")
    print("=" * 96)

    v1_errors = []
    v2_paper_errors = []
    v2_ebook_errors = []
    v2_combined_errors = []
    v2_in_range_count = 0

    for case in REAL_CASES:
        # Build v1 compatible objects
        a = case["author"]
        b = case["book"]
        a1 = AP1(
            name=a.name, author_type=a.author_type,
            yt_subscribers=a.yt_subscribers, ig_followers=a.ig_followers,
            fb_followers=a.fb_followers, course_students=a.course_students,
            app_subscribers=a.app_subscribers,
            mentor_historical_sales=a.mentor_historical_sales,
            engagement_rate=a.engagement_rate,
        )
        b1 = BI1(
            title=b.title, subcategory=b.subcategory,
            price_ntd=b.price_ntd, is_sequel=b.is_sequel,
            nth_book=b.nth_book, format=b.format,
        )

        # v1.0 prediction
        r1 = v1.predict(a1, b1)
        v1_err = compute_error(r1.sales_fy_low, r1.sales_fy_high, case["actual_paper_12m"])
        v1_errors.append(v1_err["abs_error_pct"])

        # v2.0 prediction
        r2 = v2.predict(a, b)

        # Paper
        v2_paper_err = compute_error(r2.sales_fy_low, r2.sales_fy_high, case["actual_paper_12m"])
        v2_paper_errors.append(v2_paper_err["abs_error_pct"])
        if v2_paper_err["in_range"]:
            v2_in_range_count += 1

        # Ebook
        v2_ebook_err = compute_error(r2.ebook_fy_low, r2.ebook_fy_high, case["actual_ebook_12m"])
        v2_ebook_errors.append(v2_ebook_err["abs_error_pct"])

        # Combined
        actual_combined = case["actual_paper_12m"] + case["actual_ebook_12m"]
        v2_comb_err = compute_error(r2.combined_fy_low, r2.combined_fy_high, actual_combined)
        v2_combined_errors.append(v2_comb_err["abs_error_pct"])

        # Print case details
        range_mark = "[OK]" if v2_paper_err["in_range"] else "[Miss]"
        print(f"\n--- {case['name']} ({a.author_type}, 第{b.nth_book}本) ---")
        print(f"  實際紙本12M: {case['actual_paper_12m']:>7,}  |  實際電子12M: {case['actual_ebook_12m']:>5,}")
        print(
            f"  v1.0 紙本預測: {r1.sales_fy_low:>7,} - {r1.sales_fy_high:>7,}"
            f"  中位 {v1_err['mid']:>7,.0f}  誤差 {v1_err['error_pct']:>+6.1f}%"
        )
        print(
            f"  v2.0 紙本預測: {r2.sales_fy_low:>7,} - {r2.sales_fy_high:>7,}"
            f"  中位 {v2_paper_err['mid']:>7,.0f}  誤差 {v2_paper_err['error_pct']:>+6.1f}%  {range_mark}"
        )
        print(
            f"  v2.0 電子預測: {r2.ebook_fy_low:>7,} - {r2.ebook_fy_high:>7,}"
            f"  中位 {v2_ebook_err['mid']:>7,.0f}  誤差 {v2_ebook_err['error_pct']:>+6.1f}%"
        )
        print(
            f"  v2.0 合併預測: {r2.combined_fy_low:>7,} - {r2.combined_fy_high:>7,}"
            f"  中位 {v2_comb_err['mid']:>7,.0f}  誤差 {v2_comb_err['error_pct']:>+6.1f}%"
        )
        # 首月驗證
        bm = r2.benchmark_month1
        print(
            f"  首月驗證: CR法 {bm['cr_method_low']:,}-{bm['cr_method_high']:,}"
            f"  Benchmark {bm['benchmark_median']:,}  [{bm['check']}]"
        )

    # ============================================================
    # 彙總統計
    # ============================================================
    print(f"\n{'=' * 96}")
    print(f"  彙總統計 ({len(REAL_CASES)} 個真實案例)")
    print(f"{'=' * 96}")

    def stats_line(name, errors):
        avg = statistics.mean(errors)
        med = statistics.median(errors)
        mx = max(errors)
        mn = min(errors)
        return avg, med, mn, mx, f"  {name}: MAE={avg:.1f}% | 中位={med:.1f}% | 最小={mn:.1f}% | 最大={mx:.1f}%"

    avg1, med1, _, _, line1 = stats_line("v1.0 紙本首年", v1_errors)
    avg2p, med2p, _, _, line2p = stats_line("v2.0 紙本首年", v2_paper_errors)
    avg2e, med2e, _, _, line2e = stats_line("v2.0 電子首年", v2_ebook_errors)
    avg2c, med2c, _, _, line2c = stats_line("v2.0 合併首年", v2_combined_errors)

    print(f"\n{line1}")
    print(f"{line2p}")
    print(f"{line2e}")
    print(f"{line2c}")

    print(f"\n  v2.0 紙本命中率 (實際落在區間): {v2_in_range_count}/{len(REAL_CASES)} ({v2_in_range_count/len(REAL_CASES)*100:.0f}%)")

    print(f"\n  --- 改善幅度 ---")
    if med1 > 0:
        imp_med = ((med1 - med2p) / med1) * 100
        print(f"  紙本中位數誤差: {med1:.1f}% → {med2p:.1f}% (改善 {imp_med:+.0f}%)")
    if avg1 > 0:
        imp_avg = ((avg1 - avg2p) / avg1) * 100
        print(f"  紙本平均誤差:   {avg1:.1f}% → {avg2p:.1f}% (改善 {imp_avg:+.0f}%)")

    print(f"\n  電子書預測 MAE: {avg2e:.1f}% (首次建立基準線)")
    print(f"{'=' * 96}")

    # Print one full report
    print(f"\n\n--- 範例完整報告 (莎拉王 - 新式型態學) ---")
    sara_r = v2.predict(REAL_CASES[4]["author"], REAL_CASES[4]["book"])
    print(v2.format_report(sara_r))


if __name__ == "__main__":
    run_backtest()
