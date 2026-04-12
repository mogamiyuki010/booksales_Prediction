"""
ETL Pipeline: 營收表 Raw Data → 清洗後的紙本書/電子書銷售資料
輸入: 營收表-Rawdata.csv (UTF-16 TSV)
輸出: data/paper_books_sales.csv, data/ebook_sales.csv, data/book_monthly_curves.csv
"""

import os
import sys
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

RAW_CSV = os.path.join(PROJECT_ROOT, "營收表-Rawdata.csv")
RAW_CSV_INCREMENTAL = os.path.join(PROJECT_ROOT, "營收表-Rawdata_20260305_20260411.csv")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data")


def load_raw_data(path: str = RAW_CSV) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-16", sep="\t", low_memory=False)
    df.columns = [
        "r", "日期控制", "Order_ID", "商品ID", "商品名稱", "作者名稱",
        "分類", "銷售方式", "銷售通路", "銷售形式", "售出商品數量", "售出商品營收",
    ]
    return df


def load_and_merge_raw_data() -> pd.DataFrame:
    """載入主檔 + 增量檔，合併去重"""
    df1 = load_raw_data(RAW_CSV)
    if os.path.exists(RAW_CSV_INCREMENTAL):
        df2 = load_raw_data(RAW_CSV_INCREMENTAL)
        # 用 r 欄位去重（r 為流水號）
        combined = pd.concat([df1, df2], ignore_index=True)
        combined = combined.drop_duplicates(subset=["r", "Order_ID"], keep="first")
        print(f"  主檔: {len(df1):,} 筆 + 增量檔: {len(df2):,} 筆 → 合併後: {len(combined):,} 筆")
        return combined
    return df1


def clean_book_data(df: pd.DataFrame) -> pd.DataFrame:
    """篩選紙本書/電子書，清洗數值欄位"""
    book_df = df[df["分類"].isin(["紙本書", "電子書"])].copy()

    for col in ["售出商品數量", "售出商品營收"]:
        book_df[col] = pd.to_numeric(
            book_df[col].astype(str).str.replace(",", ""), errors="coerce"
        )

    book_df["日期"] = pd.to_datetime(book_df["日期控制"], format="mixed", errors="coerce")
    book_df["年月"] = book_df["日期"].dt.to_period("M")

    # 標記是否為退貨
    book_df["is_return"] = book_df["銷售方式"] == "外部(PdReturn)"

    return book_df


def build_book_summary(book_df: pd.DataFrame) -> pd.DataFrame:
    """彙總每本書的銷售統計"""
    summary = book_df.groupby(["商品ID", "商品名稱", "作者名稱", "分類"]).agg(
        淨銷量=("售出商品數量", "sum"),
        總營收=("售出商品營收", "sum"),
        訂單數=("Order_ID", "nunique"),
        首次銷售日=("日期", "min"),
        最後銷售日=("日期", "max"),
    ).reset_index()

    summary["銷售月數"] = (
        (summary["最後銷售日"].dt.year - summary["首次銷售日"].dt.year) * 12
        + (summary["最後銷售日"].dt.month - summary["首次銷售日"].dt.month)
        + 1
    )
    summary["月均銷量"] = (summary["淨銷量"] / summary["銷售月數"]).round(1)

    return summary.sort_values("淨銷量", ascending=False)


def build_monthly_curves(book_df: pd.DataFrame, min_sales: int = 500) -> pd.DataFrame:
    """建立每本書的月度銷售曲線（從首次銷售日起算）"""
    # 只含正向銷售（不含退貨），聚焦有意義的書
    sales_df = book_df[~book_df["is_return"]].copy()

    records = []
    for (book_id, book_name, author, category), group in sales_df.groupby(
        ["商品ID", "商品名稱", "作者名稱", "分類"]
    ):
        monthly = group.groupby("年月").agg(
            月銷量=("售出商品數量", "sum"),
            月營收=("售出商品營收", "sum"),
        ).reset_index()

        if monthly["月銷量"].sum() < min_sales:
            continue

        monthly["年月_ts"] = monthly["年月"].dt.to_timestamp()
        pub_month = monthly["年月_ts"].min()

        monthly["上市後月數"] = (
            (monthly["年月_ts"].dt.year - pub_month.year) * 12
            + (monthly["年月_ts"].dt.month - pub_month.month)
            + 1
        )

        monthly["累計銷量"] = monthly.sort_values("上市後月數")["月銷量"].cumsum()

        for _, row in monthly.iterrows():
            records.append({
                "商品ID": book_id,
                "商品名稱": book_name,
                "作者名稱": author,
                "分類": category,
                "上市後月數": row["上市後月數"],
                "月銷量": row["月銷量"],
                "月營收": row["月營收"],
                "累計銷量": row["累計銷量"],
            })

    return pd.DataFrame(records)


def compute_decay_stats(curves_df: pd.DataFrame) -> pd.DataFrame:
    """從月度曲線計算每本書的衰退率統計"""
    results = []
    for (book_id, category), group in curves_df.groupby(["商品ID", "分類"]):
        first12 = group[group["上市後月數"] <= 12].sort_values("上市後月數")
        if len(first12) < 3:
            continue

        sales = first12["月銷量"].values
        month1 = sales[0]
        total_12m = sales.sum()
        total_6m = sales[:6].sum() if len(sales) >= 6 else sales.sum()
        total_3m = sales[:3].sum() if len(sales) >= 3 else sales.sum()

        # 月衰退率: 用前 6 個月相鄰月比值
        ratios = []
        for i in range(1, min(len(sales), 6)):
            if sales[i - 1] > 50:  # 避免極小值干擾
                ratios.append(sales[i] / sales[i - 1])

        avg_retention = np.mean(ratios) if ratios else 1.0
        decay_rate = max(0, 1 - avg_retention)

        # 首月佔比
        month1_ratio = month1 / total_12m if total_12m > 0 else 0

        book_name = group.iloc[0]["商品名稱"]
        author = group.iloc[0]["作者名稱"]

        results.append({
            "商品ID": book_id,
            "商品名稱": book_name,
            "作者名稱": author,
            "分類": category,
            "首月銷量": month1,
            "3月累計": total_3m,
            "6月累計": total_6m,
            "12月累計": total_12m,
            "首月佔比": round(month1_ratio, 3),
            "月衰退率": round(decay_rate, 3),
            "月保留率": round(1 - decay_rate, 3),
        })

    return pd.DataFrame(results).sort_values("12月累計", ascending=False)


def run_etl():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("=" * 60)
    print("  ETL Pipeline: 營收表 → 紙本書/電子書 清洗資料")
    print("=" * 60)

    # Step 1: Load
    print("\n[1/5] 載入原始資料（含增量合併）...")
    raw = load_and_merge_raw_data()
    print(f"  合併後總筆數: {len(raw):,}")

    # Step 2: Clean
    print("\n[2/5] 清洗與篩選...")
    book_df = clean_book_data(raw)
    paper = book_df[book_df["分類"] == "紙本書"]
    ebook = book_df[book_df["分類"] == "電子書"]
    print(f"  紙本書: {len(paper):,} 筆")
    print(f"  電子書: {len(ebook):,} 筆")

    # Step 3: Book summary
    print("\n[3/5] 建立書籍銷售彙總...")
    summary = build_book_summary(book_df)
    summary_path = os.path.join(OUTPUT_DIR, "book_sales_summary.csv")
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    print(f"  輸出: {summary_path} ({len(summary)} 本書)")

    # Step 4: Monthly curves
    print("\n[4/5] 建立月度銷售曲線...")
    curves = build_monthly_curves(book_df)
    curves_path = os.path.join(OUTPUT_DIR, "book_monthly_curves.csv")
    curves.to_csv(curves_path, index=False, encoding="utf-8-sig")
    print(f"  輸出: {curves_path} ({len(curves):,} 筆月度記錄)")

    # Step 5: Decay stats
    print("\n[5/5] 計算衰退率統計...")
    decay = compute_decay_stats(curves)
    decay_path = os.path.join(OUTPUT_DIR, "book_decay_stats.csv")
    decay.to_csv(decay_path, index=False, encoding="utf-8-sig")
    print(f"  輸出: {decay_path} ({len(decay)} 本書)")

    # Summary report
    print(f"\n{'=' * 60}")
    print("  ETL 完成摘要")
    print(f"{'=' * 60}")

    for cat in ["紙本書", "電子書"]:
        cat_decay = decay[decay["分類"] == cat]
        if len(cat_decay) == 0:
            continue
        print(f"\n  --- {cat} ({len(cat_decay)} 本) ---")
        print(f"  平均月衰退率: {cat_decay['月衰退率'].mean():.3f}")
        print(f"  中位月衰退率: {cat_decay['月衰退率'].median():.3f}")
        print(f"  平均首月佔比: {cat_decay['首月佔比'].mean():.3f}")
        print(f"  平均 12 月累計: {cat_decay['12月累計'].mean():,.0f}")

    return book_df, summary, curves, decay


def generate_dashboard_data(book_df: pd.DataFrame, summary: pd.DataFrame):
    """從合併後的資料生成 dashboard_data.json"""
    import json

    paper = book_df[book_df["分類"] == "紙本書"].copy()
    ebook = book_df[book_df["分類"] == "電子書"].copy()

    # Monthly trend
    paper_monthly = paper.groupby("年月")["售出商品數量"].sum().sort_index()
    ebook_monthly = ebook.groupby("年月")["售出商品數量"].sum().sort_index()

    all_months = sorted(set(paper_monthly.index) | set(ebook_monthly.index))
    trend_labels = [str(m) for m in all_months]
    paper_vals = [int(paper_monthly.get(m, 0)) for m in all_months]
    ebook_vals = [int(ebook_monthly.get(m, 0)) for m in all_months]

    # TOP15 paper books
    paper_summary = summary[summary["分類"] == "紙本書"].head(15)
    top_names = paper_summary["商品名稱"].tolist()
    top_vals = paper_summary["淨銷量"].astype(int).tolist()
    top_authors = paper_summary["作者名稱"].tolist()

    # Key curves (same 6 books)
    key_books = {
        "存100張金融股 (陳重銘)": {"search": "存100張金融股", "type": "KOP"},
        "艾蜜莉存股術2.0 (艾蜜莉)": {"search": "艾蜜莉存股術2.0", "type": "KOC"},
        "新式型態學 (莎拉王)": {"search": "新式型態學", "type": "KOC"},
        "學會走圖SOP (林穎)": {"search": "學會走圖SOP", "type": "Co-Branding"},
        "活用技術分析寶典 (朱家泓)": {"search": "活用技術分析寶典", "type": "KOP"},
        "短線終極戰法 (權證小哥)": {"search": "短線終極戰法", "type": "KOC"},
    }
    curves_data = {}
    paper_no_return = paper[~paper["is_return"]]
    for label, info in key_books.items():
        bk = paper_no_return[paper_no_return["商品名稱"].str.contains(info["search"], na=False)]
        if len(bk) == 0:
            continue
        monthly = bk.groupby("年月")["售出商品數量"].sum().sort_index()
        pub_month = monthly.index.min()
        first12 = []
        for i in range(12):
            m = pub_month + i
            first12.append(int(monthly.get(m, 0)))
        curves_data[label] = {"data": first12, "type": info["type"]}

    # Channel distribution
    channel_dist = paper.groupby("銷售通路")["售出商品數量"].sum().sort_values(ascending=False).head(8)
    channel_labels = channel_dist.index.tolist()
    channel_vals = channel_dist.values.astype(int).tolist()

    # Ebook ratio by author
    paper_by_author = paper.groupby("作者名稱")["售出商品數量"].sum()
    ebook_by_author = ebook.groupby("作者名稱")["售出商品數量"].sum()
    ebook_ratio = []
    for author in paper_by_author.sort_values(ascending=False).head(15).index:
        p = int(paper_by_author.get(author, 0))
        e = int(ebook_by_author.get(author, 0))
        if p > 0:
            ebook_ratio.append({
                "author": author,
                "paper": p,
                "ebook": e,
                "ratio": round(e / p * 100, 1),
            })

    # Yearly breakdown for table
    paper["年"] = paper["日期"].dt.year
    ebook["年"] = ebook["日期"].dt.year
    yearly_paper = paper.groupby("年").agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum")).to_dict("index")
    yearly_ebook = ebook.groupby("年").agg(銷量=("售出商品數量", "sum"), 營收=("售出商品營收", "sum")).to_dict("index")

    yearly_data = []
    for y in sorted(set(list(yearly_paper.keys()) + list(yearly_ebook.keys()))):
        if y < 2022 or pd.isna(y):
            continue
        yp = yearly_paper.get(y, {"銷量": 0, "營收": 0})
        ye = yearly_ebook.get(y, {"銷量": 0, "營收": 0})
        yearly_data.append({
            "year": int(y),
            "paper_qty": int(yp["銷量"]),
            "paper_rev": int(yp["營收"]),
            "ebook_qty": int(ye["銷量"]),
            "ebook_rev": int(ye["營收"]),
        })

    # Yearly TOP5
    yearly_top5 = {}
    for y in [2022, 2023, 2024, 2025, 2026]:
        yr_paper = paper[paper["年"] == y]
        top5 = yr_paper.groupby(["商品名稱", "作者名稱"])["售出商品數量"].sum().sort_values(ascending=False).head(5)
        items = []
        for (name, author), qty in top5.items():
            items.append({"name": name[:30], "author": author, "qty": int(qty)})
        if items:
            yearly_top5[str(y)] = items

    dashboard = {
        "trend_labels": trend_labels,
        "paper_monthly": paper_vals,
        "ebook_monthly": ebook_vals,
        "top_paper_names": top_names,
        "top_paper_vals": top_vals,
        "top_paper_authors": top_authors,
        "key_curves": curves_data,
        "channel_labels": channel_labels,
        "channel_vals": channel_vals,
        "ebook_ratio": ebook_ratio,
        "yearly_data": yearly_data,
        "yearly_top5": yearly_top5,
    }

    out_path = os.path.join(OUTPUT_DIR, "dashboard_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dashboard, f, ensure_ascii=False, indent=2)
    print(f"\n  Dashboard 數據已更新: {out_path}")
    return dashboard


if __name__ == "__main__":
    book_df, summary, curves, decay = run_etl()
    generate_dashboard_data(book_df, summary)
