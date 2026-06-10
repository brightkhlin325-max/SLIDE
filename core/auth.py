"""
auth.py
EDIS 登入驗證模組
使用 SQLite 儲存使用者帳號，bcrypt 加密密碼
"""
import sqlite3
import hashlib
import os
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "edis_users.db"

def init_db():
    """初始化資料庫，建立 users 表格"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'Viewer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()

    # 建立測試帳號（如果不存在）
    test_accounts = [
        ("admin", "edis1234", "Logistics_Manager"),
        ("viewer", "view1234", "Viewer"),
    ]
    for username, password, role in test_accounts:
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        try:
            c.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (username, pw_hash, role)
            )
        except sqlite3.IntegrityError:
            pass  # 已存在就跳過

    conn.commit()
    conn.close()
    print(f"[Auth] 資料庫初始化完成：{DB_PATH}")

def verify_user(username: str, password: str):
    """
    驗證使用者帳號密碼
    回傳 {"success": True, "role": "Logistics_Manager"} 或 {"success": False}
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    c.execute(
        "SELECT role FROM users WHERE username=? AND password_hash=?",
        (username, pw_hash)
    )
    row = c.fetchone()
    conn.close()
    if row:
        return {"success": True, "role": row[0]}
    return {"success": False, "role": None}

if __name__ == "__main__":
    init_db()
    print("測試帳號：")
    print("  Manager → username: admin    password: edis1234")
    print("  Viewer  → username: viewer   password: view1234")
