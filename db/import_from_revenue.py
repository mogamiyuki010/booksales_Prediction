"""
從營收表 Raw Data 整理作者與書籍資料，匯入 booksales.db。

邏輯：
1. 解析營收表 CSV（UTF-16 / Tab 分隔）
2. 以「商品ID」(product_id) 為唯一鍵，精確辨識每本書
3. 合併同作者不同名稱（如 "塔米．米勒" / "Tammi Miller"）
4. 排除套書組合、加購、週年慶等非獨立書目
5. 寫入 authors + books 表，product_id 作為唯一識別碼
"""
import csv
import io
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "booksales.db"

# ── 1. 讀取營收表 ──────────────────────────────────────

def read_revenue_csv(path):
    text = open(path, encoding="utf-16").read()
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    cols = reader.fieldnames
    return list(reader), cols


# ── 2. 作者名稱正規化 ──────────────────────────────────

AUTHOR_ALIASES = {
    "Tammi Miller": "塔米．米勒",
    "塔米．米勒(Tammi Miller)": "塔米．米勒",
    "Erika Ayers Badan": "艾瑞卡．貝登",
    "田臨斌（老黑）": "老黑",
    "曾婉鈴": "曾琬鈴",
    "豬力安（李彥慶）": "豬力安",
    "莎拉(Sara Wang)": "莎拉王",
    "洪瑞泰、Easy": "洪瑞泰",
    "Finance168、Tivo168": "薛兆亨",
    "五線譜投資達人薛兆亨、Tivo": "薛兆亨",
    "薛兆亨、TIVO": "薛兆亨",
    "薛兆亨、Tivo168": "薛兆亨",
    "薛兆亨、Tivo168 合著": "薛兆亨",
    "郭勝, 林上仁": "郭勝",
    "林上仁、郭勝": "郭勝",
    "孫悟天，孫太": "孫悟天",
    "建業法律事務所 資深法律顧問團隊 余佳璋、金玉瑩、張少騰、李育錚、林心瀅、馬傲秋、黃品瑜、楊薪頻、蔡宜靜": "建業法律事務所",
}

SKIP_AUTHORS = {"0", "版權書", "CMoney", "Money錢"}
SKIP_COMBO_PATTERNS = ["+", "＋"]


def normalize_author(name):
    name = name.strip()
    if "開啟螢幕閱讀器" in name:
        parts = name.split()
        for p in parts:
            if any("\u4e00" <= c <= "\u9fff" for c in p) and "Money" not in p and "營收" not in p:
                return p.rstrip("、")
        return None
    if name in SKIP_AUTHORS:
        return None
    if any(p in name for p in SKIP_COMBO_PATTERNS):
        return None
    return AUTHOR_ALIASES.get(name, name)


# ── 3. 書名清理與排除 ──────────────────────────────────

EXCLUDE_BOOK_PATTERNS = [
    r"套書", r"加購", r"加價購", r"週年慶", r"超值組", r"預購",
    r"瑕疵書", r"聯訂", r"聖誕", r"新春", r"聯賣", r"續.*期",
    r"理財寶.*\$", r"代理商", r"三部曲", r"同學會", r"打造小小巴菲特套書",
    r"大禮包",
]
EXCLUDE_RE = re.compile("|".join(EXCLUDE_BOOK_PATTERNS))


def clean_book_title(raw_title):
    t = raw_title.strip()
    t = re.sub(r"[《》]", "", t)
    t = re.sub(r"\s*[｜|]\s*.+$", "", t)
    t = re.sub(r"\s*電子版\s*$", "", t)
    t = re.sub(r"【[^】]*】", "", t)
    t = re.sub(r"\s*\(金尉\)\s*", "", t)
    t = re.sub(r"\s*\((?:精裝書|單|1本裝)\)\s*", "", t)
    return t.strip()


def is_excluded_book(title):
    return bool(EXCLUDE_RE.search(title))


def guess_subcategory(book_title):
    kw_map = {
        "ETF": "ETF存股", "存股": "ETF存股", "存自己": "ETF存股", "金融股": "ETF存股",
        "K線": "技術分析", "技術分析": "技術分析", "飆股": "技術分析", "線圖": "技術分析",
        "走圖": "技術分析", "型態": "技術分析", "當沖": "當沖",
        "權證": "權證",
        "房": "房地產", "房仲": "房地產",
        "理財": "新手理財", "財務自由": "新手理財", "退休": "新手理財",
        "親子": "親子理財", "小小巴菲特": "親子理財", "小孩": "親子理財", "少年": "親子理財",
        "巴菲特選股": "價值投資", "價值": "價值投資",
        "籌碼": "籌碼分析", "主力": "籌碼分析",
        "基金": "基金投資", "海外": "基金投資",
        "心理": "心靈成長", "修行": "心靈成長", "重新找回": "心靈成長",
        "人工智慧": "科技趨勢", "AIGC": "科技趨勢",
        "商業模式": "商業經營", "致富習慣": "商業經營",
        "律師": "法律常識", "法律": "法律常識",
        "可轉債": "可轉債",
    }
    for kw, sub in kw_map.items():
        if kw in book_title:
            return sub
    return None


def estimate_publish_date(earliest_date_str):
    if not earliest_date_str or earliest_date_str == "9999":
        return None
    parts = earliest_date_str.split("/")
    if len(parts) == 3:
        return f"{parts[0]}-{int(parts[1]):02d}-01"
    return None


# ── 4. 以 product_id 為主鍵提取書籍 ───────────────────

def extract_by_product_id():
    """以 product_id 為唯一鍵提取所有書籍資料"""
    all_rows = []
    cols = None
    for fname in ["營收表-Rawdata.csv", "營收表-Rawdata_20260305_20260411.csv"]:
        path = ROOT / fname
        if path.exists():
            rows, c = read_revenue_csv(path)
            if cols is None:
                cols = c
            all_rows.extend(rows)

    pid_col = cols[3]    # 商品ID
    book_col = cols[4]   # 產品名稱
    author_col = cols[5] # 作者名稱
    cat_col = cols[6]    # 類別
    date_col = cols[1]   # 銷售日期

    book_cats = {"紙本書", "電子書"}

    # product_id -> { raw_title, author, category, records, earliest_date }
    pid_map = {}

    for r in all_rows:
        pid = r.get(pid_col, "").strip()
        raw_book = r.get(book_col, "").strip()
        raw_author = r.get(author_col, "").strip()
        cat = r.get(cat_col, "").strip()
        date = r.get(date_col, "").strip()

        if cat not in book_cats or not raw_author or not raw_book:
            continue

        author = normalize_author(raw_author)
        if not author:
            continue

        if is_excluded_book(raw_book):
            continue

        if not pid:
            # 沒有 product_id 的用 clean_title 作為 fallback key
            pid = "_NO_PID_" + clean_book_title(raw_book)

        if pid not in pid_map:
            pid_map[pid] = {
                "product_id": pid if not pid.startswith("_NO_PID_") else None,
                "raw_title": raw_book,
                "clean_title": clean_book_title(raw_book),
                "author": author,
                "category": cat,
                "categories": {cat},
                "records": 0,
                "earliest_date": "9999",
            }

        pid_map[pid]["records"] += 1
        pid_map[pid]["categories"].add(cat)
        if date < pid_map[pid]["earliest_date"]:
            pid_map[pid]["earliest_date"] = date

    return pid_map


# ── 5. 合併同書不同版本的 product_id ────────────────────

# 同一本書不同 product_id 的對照（S 後綴 = 金尉版，原版 = 外部版）
# 這些應合併為同一本書，使用主要的 product_id
def group_product_ids(pid_map):
    """
    將同一本書的不同 product_id 分組。
    規則：同作者 + 清理後書名完全相同 → 歸為同組，取 records 最多的 pid 為主鍵。
    """
    # author -> clean_title -> [pid_entries]
    groups = defaultdict(lambda: defaultdict(list))
    for pid, info in pid_map.items():
        groups[info["author"]][info["clean_title"]].append(info)

    # 輸出：每組取主 pid + 合併所有 pid
    result = []
    for author, titles in groups.items():
        for clean_title, entries in titles.items():
            entries.sort(key=lambda x: -x["records"])
            primary = entries[0]
            all_pids = [e["product_id"] for e in entries if e["product_id"]]
            total_records = sum(e["records"] for e in entries)
            earliest = min(e["earliest_date"] for e in entries)
            all_cats = set()
            for e in entries:
                all_cats |= e["categories"]

            result.append({
                "product_ids": all_pids,
                "primary_pid": all_pids[0] if all_pids else None,
                "clean_title": clean_title,
                "raw_title": primary["raw_title"],
                "author": author,
                "categories": all_cats,
                "records": total_records,
                "earliest_date": earliest,
                "is_ebook_only": all_cats == {"電子書"},
            })

    return result


# ── 6. 主流程 ──────────────────────────────────────

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")

    # 清除舊的自動匯入資料（保留 seed 的 6 筆原始資料 author_id 1-6, book_id 1-6）
    conn.execute("DELETE FROM predictions WHERE book_id IN (SELECT book_id FROM books WHERE book_id > 6)")
    conn.execute("DELETE FROM monthly_sales WHERE book_id IN (SELECT book_id FROM books WHERE book_id > 6)")
    conn.execute("DELETE FROM books WHERE book_id > 6")
    conn.execute("DELETE FROM author_metrics_history WHERE author_id IN (SELECT author_id FROM authors WHERE author_id > 6)")
    conn.execute("DELETE FROM authors WHERE author_id > 6")
    # 清除 seed 書籍的 product_id（重新填入）
    conn.execute("UPDATE books SET product_id = NULL")
    conn.commit()

    # 取得 seed 作者
    seed_authors = {}
    for r in conn.execute("SELECT * FROM authors WHERE author_id <= 6"):
        seed_authors[r["name"]] = dict(r)

    # 取得 seed 書籍
    seed_books = {}
    for r in conn.execute("SELECT * FROM books WHERE book_id <= 6"):
        seed_books[r["book_id"]] = dict(r)

    # 提取營收表資料
    pid_map = extract_by_product_id()
    grouped = group_product_ids(pid_map)

    # 按作者分組
    author_groups = defaultdict(list)
    for g in grouped:
        if g["records"] >= 3 and len(g["clean_title"]) >= 3:
            author_groups[g["author"]].append(g)

    new_authors = 0
    new_books = 0
    updated_pid = 0

    # 作者 name -> author_id
    author_id_map = {r["name"]: r["author_id"] for r in conn.execute("SELECT name, author_id FROM authors")}

    for author_name in sorted(author_groups.keys()):
        books = author_groups[author_name]

        # 新增或取得 author_id
        if author_name in author_id_map:
            author_id = author_id_map[author_name]
        else:
            total_records = sum(b["records"] for b in books)
            if total_records >= 1000:
                author_type = "KOP"
            elif total_records >= 100:
                author_type = "KOC"
            else:
                author_type = "Debut"

            earliest = min(b["earliest_date"] for b in books)
            snapshot = estimate_publish_date(earliest) or "2024-01-01"

            cur = conn.execute(
                "INSERT INTO authors (name, author_type, previous_book_count, snapshot_date, notes) VALUES (?, ?, ?, ?, ?)",
                (author_name, author_type, len(books), snapshot, f"自動匯入自營收表，共 {total_records} 筆銷售紀錄")
            )
            author_id = cur.lastrowid
            author_id_map[author_name] = author_id
            new_authors += 1

        # 處理書籍
        for book in sorted(books, key=lambda b: b["earliest_date"]):
            pid = book["primary_pid"]
            all_pids_str = ", ".join(book["product_ids"]) if book["product_ids"] else None

            # 檢查 DB 是否已有此 product_id
            if pid:
                existing = conn.execute("SELECT book_id FROM books WHERE product_id = ?", (pid,)).fetchone()
                if existing:
                    continue

            # 檢查 seed 書籍是否匹配（用書名模糊比對）
            matched_seed = None
            for bid, sb in seed_books.items():
                if sb["author_id"] == author_id and (
                    book["clean_title"][:10] in sb["title"] or
                    sb["title"][:10] in book["clean_title"]
                ):
                    matched_seed = bid
                    break

            if matched_seed:
                # 更新 seed 書籍的 product_id
                conn.execute("UPDATE books SET product_id = ?, updated_at = datetime('now') WHERE book_id = ?",
                             (pid, matched_seed))
                if all_pids_str and all_pids_str != pid:
                    old_notes = conn.execute("SELECT notes FROM books WHERE book_id = ?", (matched_seed,)).fetchone()[0] or ""
                    conn.execute("UPDATE books SET notes = ?, updated_at = datetime('now') WHERE book_id = ?",
                                 (old_notes + f"\n相關商品ID: {all_pids_str}", matched_seed))
                updated_pid += 1
                continue

            # 新增書籍
            pub_date = estimate_publish_date(book["earliest_date"])
            has_ebook = "電子書" in book["categories"]
            subcategory = guess_subcategory(book["clean_title"])

            notes_parts = [f"營收表 {book['records']} 筆紀錄"]
            if has_ebook:
                notes_parts.append("含電子書版")
            if all_pids_str and all_pids_str != pid:
                notes_parts.append(f"相關商品ID: {all_pids_str}")

            atype = conn.execute("SELECT author_type FROM authors WHERE author_id = ?", (author_id,)).fetchone()[0]

            conn.execute(
                """INSERT INTO books (product_id, title, author_id, category, subcategory,
                   publish_date, author_type_at_publish, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pid, book["clean_title"], author_id, "商業財經", subcategory,
                 pub_date, atype, "；".join(notes_parts))
            )
            new_books += 1

    # 更新 nth_book + previous_book_count
    for r in conn.execute("SELECT DISTINCT author_id FROM books ORDER BY author_id"):
        aid = r[0]
        rows = conn.execute("SELECT book_id FROM books WHERE author_id = ? ORDER BY publish_date, book_id", (aid,)).fetchall()
        for i, br in enumerate(rows, 1):
            conn.execute("UPDATE books SET nth_book = ? WHERE book_id = ?", (i, br[0]))
        conn.execute("UPDATE authors SET previous_book_count = ?, updated_at = datetime('now') WHERE author_id = ?",
                     (len(rows), aid))

    conn.commit()

    # 統計
    total_authors = conn.execute("SELECT COUNT(*) FROM authors").fetchone()[0]
    total_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    books_with_pid = conn.execute("SELECT COUNT(*) FROM books WHERE product_id IS NOT NULL").fetchone()[0]
    books_no_pid = conn.execute("SELECT COUNT(*) FROM books WHERE product_id IS NULL").fetchone()[0]
    conn.close()

    print(f"匯入完成:")
    print(f"  新增作者: {new_authors} 位")
    print(f"  新增書籍: {new_books} 本")
    print(f"  更新 seed 書籍 product_id: {updated_pid} 本")
    print(f"  資料庫總計: {total_authors} 位作者, {total_books} 本書")
    print(f"  有商品ID: {books_with_pid} 本")
    print(f"  無商品ID: {books_no_pid} 本")

    # 匯出更新後的 JSON
    from export_author_models import main as export_main
    export_main()


if __name__ == "__main__":
    main()
