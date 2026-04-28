import sqlite3
from datetime import datetime

db_user = "database.db"
db_messages = "messages.db"


def conn_user():
    return sqlite3.connect(db_user)


def conn_mess():
    return sqlite3.connect(db_messages)


def get_db_connection():
    """Для совместимости с кодом, который использует get_db_connection"""
    return conn_mess()


def create_tables():
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                nickname TEXT,
                avatar TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS photos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL,
                file_path TEXT NOT NULL
            )
        """)

        cursor.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]
        if "avatar" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN avatar TEXT")

        conn.commit()


def create_tables_messenger():
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                text TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                edited BOOLEAN DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1 TEXT NOT NULL,
                user2 TEXT NOT NULL,
                UNIQUE(user1, user2)
            )
        """)
        conn.commit()


def add_user(name, password):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, password) VALUES (?, ?)",
            (name, password)
        )
        conn.commit()


def check(name, password):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM users WHERE name = ? AND password = ?",
            (name, password)
        )
        return cursor.fetchone() is not None


def check_users(name):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE name = ?", (name,))
        return cursor.fetchone() is not None


def set_user_avatar(username, avatar_path):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET avatar = ? WHERE name = ?",
            (avatar_path, username)
        )
        conn.commit()


def get_user_avatar(username):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT avatar FROM users WHERE name = ?", (username,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else None


def add_photo(username, file_path):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO photos (user_name, file_path) VALUES (?, ?)",
            (username, file_path)
        )
        conn.commit()


def delete_photo(file_path):
    with conn_user() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM photos WHERE file_path = ?", (file_path,))
        conn.commit()


def create_chats(user1: str, user2: str):
    """Создать запись о чате между пользователями."""
    with conn_mess() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT OR IGNORE INTO chats (user1, user2) VALUES (?, ?)",
                (min(user1, user2), max(user1, user2))
            )
            conn.commit()
        except sqlite3.OperationalError:
            # Если таблица chats ещё не создана
            pass


def get_dialog(username):
    with conn_mess() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "SELECT user1, user2 FROM chats WHERE user1 = ? OR user2 = ?",
                (username, username)
            )
            rows = cursor.fetchall()

            dialogs = []
            for u1, u2 in rows:
                dialogs.append(u2 if u1 == username else u1)
            return dialogs
        except sqlite3.OperationalError:
            return []


def send_private_message(sender: str, recipient: str, text: str) -> int:
    """Отправить сообщение. Возвращает ID сообщения."""
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)",
            (sender, recipient, text)
        )
        conn.commit()
        return cursor.lastrowid


def get_chat_history(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id, 
                sender, 
                text, 
                strftime('%H:%M', timestamp) as timestamp,
                timestamp as iso_time
            FROM messages
            WHERE (sender = ? AND recipient = ?)
               OR (sender = ? AND recipient = ?)
            ORDER BY timestamp ASC, id ASC
        """, (user1, user2, user2, user1))
        return cursor.fetchall()


def get_chat_history_after(user: str, recipient: str, after_id: int = 0):
    """Получить сообщения после указанного ID."""
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """SELECT id, sender, text, 
                      strftime('%H:%M', timestamp) as timestamp,
                      timestamp as iso_time
               FROM messages 
               WHERE ((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?))
               AND id > ?
               ORDER BY id ASC""",
            (user, recipient, recipient, user, after_id)
        )
        return cursor.fetchall()


def delete_dialog(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM chats
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (user1, user2, user2, user1))

        cursor.execute("""
            DELETE FROM messages
            WHERE (sender = ? AND recipient = ?)
               OR (sender = ? AND recipient = ?)
        """, (user1, user2, user2, user1))
        conn.commit()


def delete_message(mess_id, user):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM messages WHERE id = ? AND sender = ?",
            (mess_id, user)
        )
        conn.commit()


def chat_exists(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT 1 FROM chats
                WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
            """, (user1, user2, user2, user1))
            return cursor.fetchone() is not None
        except sqlite3.OperationalError:
            return False


def edit_message(message_id, user, new_text):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE messages
            SET text = ?, edited = 1
            WHERE id = ? AND sender = ?
        """, (new_text, message_id, user))
        conn.commit()
