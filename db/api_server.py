"""輕量 API Server — 提供靜態檔 + 作者/書籍/快照 CRUD"""
import json
import sqlite3
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "booksales.db"
PORT = 8000


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def row_to_dict(row):
    return {k: row[k] for k in row.keys()} if row else None


def json_response(handler, data, status=200):
    body = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0))
    return json.loads(handler.rfile.read(length)) if length else {}


# ── Authors ──────────────────────────────────────────────

def get_authors():
    conn = get_conn()
    authors = [row_to_dict(r) for r in conn.execute("SELECT * FROM authors ORDER BY author_id").fetchall()]
    books = [row_to_dict(r) for r in conn.execute("SELECT * FROM books ORDER BY author_id, publish_date").fetchall()]
    metrics = [row_to_dict(r) for r in conn.execute("SELECT * FROM author_metrics_history ORDER BY author_id, snapshot_date").fetchall()]
    predictions = {r["book_id"]: row_to_dict(r) for r in conn.execute("SELECT * FROM predictions").fetchall()}
    author_map = {a["author_id"]: a for a in authors}
    for a in authors:
        a["mentor_name"] = author_map[a["mentor_author_id"]]["name"] if a.get("mentor_author_id") else None
        a["books"] = []
        a["metrics_history"] = [m for m in metrics if m["author_id"] == a["author_id"]]
    for b in books:
        b["prediction"] = predictions.get(b["book_id"])
        if b["author_id"] in author_map:
            author_map[b["author_id"]]["books"].append(b)
    conn.close()
    return authors


AUTHOR_FIELDS = [
    "name", "author_type", "primary_platform",
    "yt_subscribers", "ig_followers", "fb_followers",
    "cmoney_followers", "course_students", "app_subscribers",
    "previous_book_count", "authority_score",
    "mentor_author_id", "notes", "snapshot_date",
]

def update_author(author_id, data):
    conn = get_conn()
    sets, vals = [], []
    for f in AUTHOR_FIELDS:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])
    if not sets:
        conn.close()
        return None
    sets.append("updated_at = datetime('now')")
    vals.append(author_id)
    conn.execute(f"UPDATE authors SET {', '.join(sets)} WHERE author_id = ?", vals)
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM authors WHERE author_id = ?", (author_id,)).fetchone())
    conn.close()
    return row


def create_author(data):
    conn = get_conn()
    fields = [f for f in AUTHOR_FIELDS if f in data]
    placeholders = ", ".join(["?"] * len(fields))
    vals = [data[f] for f in fields]
    cur = conn.execute(f"INSERT INTO authors ({', '.join(fields)}) VALUES ({placeholders})", vals)
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM authors WHERE author_id = ?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


def delete_author(author_id):
    conn = get_conn()
    conn.execute("DELETE FROM author_metrics_history WHERE author_id = ?", (author_id,))
    conn.execute("DELETE FROM predictions WHERE book_id IN (SELECT book_id FROM books WHERE author_id = ?)", (author_id,))
    conn.execute("DELETE FROM monthly_sales WHERE book_id IN (SELECT book_id FROM books WHERE author_id = ?)", (author_id,))
    conn.execute("DELETE FROM books WHERE author_id = ?", (author_id,))
    conn.execute("DELETE FROM authors WHERE author_id = ?", (author_id,))
    conn.commit()
    conn.close()


# ── Books ────────────────────────────────────────────────

BOOK_FIELDS = [
    "product_id", "title", "author_id", "category", "subcategory",
    "price_ntd", "page_count", "format", "publish_date",
    "first_print_run", "author_type_at_publish",
    "is_sequel", "predecessor_book_id", "nth_book", "notes",
]

def update_book(book_id, data):
    conn = get_conn()
    sets, vals = [], []
    for f in BOOK_FIELDS:
        if f in data:
            sets.append(f"{f} = ?")
            vals.append(data[f])
    if not sets:
        conn.close()
        return None
    sets.append("updated_at = datetime('now')")
    vals.append(book_id)
    conn.execute(f"UPDATE books SET {', '.join(sets)} WHERE book_id = ?", vals)
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone())
    conn.close()
    return row


def create_book(data):
    conn = get_conn()
    fields = [f for f in BOOK_FIELDS if f in data]
    placeholders = ", ".join(["?"] * len(fields))
    vals = [data[f] for f in fields]
    cur = conn.execute(f"INSERT INTO books ({', '.join(fields)}) VALUES ({placeholders})", vals)
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM books WHERE book_id = ?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


# ── Metrics History ──────────────────────────────────────

METRIC_FIELDS = [
    "author_id", "snapshot_date",
    "yt_subscribers", "ig_followers", "fb_followers",
    "cmoney_followers", "course_students",
    "google_trends_index", "engagement_rate", "notes",
]

def create_metric(data):
    conn = get_conn()
    fields = [f for f in METRIC_FIELDS if f in data]
    placeholders = ", ".join(["?"] * len(fields))
    vals = [data[f] for f in fields]
    cur = conn.execute(f"INSERT INTO author_metrics_history ({', '.join(fields)}) VALUES ({placeholders})", vals)
    conn.commit()
    row = row_to_dict(conn.execute("SELECT * FROM author_metrics_history WHERE metric_id = ?", (cur.lastrowid,)).fetchone())
    conn.close()
    return row


def delete_metric(metric_id):
    conn = get_conn()
    conn.execute("DELETE FROM author_metrics_history WHERE metric_id = ?", (metric_id,))
    conn.commit()
    conn.close()


# ── Handler ──────────────────────────────────────────────

class ApiHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/authors":
            json_response(self, get_authors())
        elif path == "/api/author_types":
            json_response(self, ["KOP", "KOC", "Co-Branding", "Debut"])
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        data = read_body(self)
        if path == "/api/authors":
            row = create_author(data)
            json_response(self, row, 201)
        elif path == "/api/books":
            row = create_book(data)
            json_response(self, row, 201)
        elif path == "/api/metrics":
            row = create_metric(data)
            json_response(self, row, 201)
        else:
            json_response(self, {"error": "not found"}, 404)

    def do_PUT(self):
        path = urlparse(self.path).path
        data = read_body(self)
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "authors":
            row = update_author(int(parts[2]), data)
            json_response(self, row or {"error": "no fields"}, 200 if row else 400)
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "books":
            row = update_book(int(parts[2]), data)
            json_response(self, row or {"error": "no fields"}, 200 if row else 400)
        else:
            json_response(self, {"error": "not found"}, 404)

    def do_DELETE(self):
        path = urlparse(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "authors":
            delete_author(int(parts[2]))
            json_response(self, {"ok": True})
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "metrics":
            delete_metric(int(parts[2]))
            json_response(self, {"ok": True})
        else:
            json_response(self, {"error": "not found"}, 404)

    def log_message(self, format, *args):
        if "/api/" in (args[0] if args else ""):
            super().log_message(format, *args)


if __name__ == "__main__":
    print(f"Server: http://localhost:{PORT}")
    print(f"DB:     {DB_PATH}")
    print(f"Root:   {ROOT}")
    HTTPServer(("", PORT), ApiHandler).serve_forever()
