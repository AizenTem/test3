import sqlite3

db_user = "database.db"
db_messages = "messages.db"


def conn_user():
    return sqlite3.connect(db_user)


def conn_mess():
    return sqlite3.connect(db_messages)


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
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_email TEXT NOT NULL,
                receiver_email TEXT NOT NULL,
                message TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dialogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user1 TEXT NOT NULL,
                user2 TEXT NOT NULL
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
    conn = get_db_connection()
    try:
        with conn:
            # Проверяем, существует ли уже чат
            cursor = conn.execute(
                "SELECT 1 FROM chats WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)",
                (user1, user2, user2, user1)
            )
            if not cursor.fetchone():
                conn.execute(
                    "INSERT INTO chats (user1, user2) VALUES (?, ?)",
                    (user1, user2)
                )
    finally:
        conn.close()


def get_dialog(username):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user1, user2 FROM dialogs WHERE user1 = ? OR user2 = ?",
            (username, username)
        )
        rows = cursor.fetchall()

        dialogs = []
        for u1, u2 in rows:
            dialogs.append(u2 if u1 == username else u1)
        return dialogs


def send_private_message(sender: str, recipient: str, text: str) -> int:
    """Отправить сообщение. Возвращает ID сообщения."""
    conn = get_db_connection()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO messages (sender, recipient, text) VALUES (?, ?, ?)",
                (sender, recipient, text)
            )
            message_id = cursor.lastrowid
        return message_id  # ← Уберите лишнюю скобку, должно быть так
    finally:
        conn.close()
def get_chat_history_after(user: str, recipient: str, after_id: int = 0):
    """Получить сообщения после указанного ID."""
    conn = get_db_connection()
    try:
        cursor = conn.execute(
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
    finally:
        conn.close()
def get_chat_history(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id, 
                sender_email, 
                message, 
                timestamp,
                strftime('%Y-%m-%dT%H:%M:%S', timestamp) as iso_time
            FROM chat_messages
            WHERE (sender_email = ? AND receiver_email = ?)
               OR (sender_email = ? AND receiver_email = ?)
            ORDER BY timestamp ASC, id ASC
        """, (user1, user2, user2, user1))
        return cursor.fetchall()   # теперь возвращает: (id, sender, message, timestamp, iso_time)


def delete_dialog(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM dialogs
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (user1, user2, user2, user1))

        cursor.execute("""
            DELETE FROM chat_messages
            WHERE (sender_email = ? AND receiver_email = ?)
               OR (sender_email = ? AND receiver_email = ?)
        """, (user1, user2, user2, user1))
        conn.commit()


def delete_message(mess_id, user):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM chat_messages WHERE id = ? AND sender_email = ?",
            (mess_id, user)
        )
        conn.commit()


def chat_exists(user1, user2):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM dialogs
            WHERE (user1 = ? AND user2 = ?) OR (user1 = ? AND user2 = ?)
        """, (user1, user2, user2, user1))
        return cursor.fetchone() is not None


def edit_message(message_id, user, new_text):
    with conn_mess() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_messages
            SET message = ?
            WHERE id = ? AND sender_email = ?
        """, (new_text, message_id, user))
        conn.commit()
