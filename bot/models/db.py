import sqlite3
from bot.config import DATABASE_PATH
from datetime import datetime

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, status TEXT DEFAULT 'pending', role TEXT DEFAULT 'user', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS schedule_tasks (task_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, groups_file_path TEXT, weekdays_file_path TEXT, status TEXT DEFAULT 'pending_files', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, result_message TEXT, FOREIGN KEY (user_id) REFERENCES users (telegram_id))''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS feedback (feedback_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, username TEXT, first_name TEXT, message_text TEXT, received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, is_viewed INTEGER DEFAULT 0, FOREIGN KEY (user_id) REFERENCES users (telegram_id))''')
    conn.commit(); conn.close()

def add_user(telegram_id: int, username: str | None, first_name: str | None):
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name, created_at) VALUES (?, ?, ?, ?)", (telegram_id, username, first_name, datetime.now())); conn.commit()
    finally: conn.close()

def get_user(telegram_id: int) -> tuple | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    cursor.execute("SELECT telegram_id, username, first_name, status, role, strftime('%Y-%m-%d %H:%M:%S', created_at) FROM users WHERE telegram_id = ?", (telegram_id,)); user_data = cursor.fetchone(); conn.close(); return user_data

def update_user_status_role(telegram_id: int, status: str | None = None, role: str | None = None):
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    updates = []
    params = []
    if status is not None: updates.append("status = ?"); params.append(status)
    if role is not None: updates.append("role = ?"); params.append(role)
    if not updates: return
    params.append(telegram_id)
    query = f"UPDATE users SET {', '.join(updates)} WHERE telegram_id = ?"
    try: cursor.execute(query, tuple(params)); conn.commit()
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при обновлении пользователя {telegram_id}: {e}")
    finally: conn.close()

def get_pending_users():
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    cursor.execute("SELECT telegram_id, username, first_name FROM users WHERE status = 'pending'"); users = cursor.fetchall(); conn.close(); return users

def create_schedule_task(user_id: int) -> int | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("INSERT INTO schedule_tasks (user_id, created_at, status) VALUES (?, ?, ?)", (user_id, datetime.now(), 'pending_groups_file')); task_id = cursor.lastrowid; conn.commit(); return task_id
    except sqlite3.Error: return None
    finally: conn.close()

def update_task_add_file(task_id: int, file_type: str, file_path: str):
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    if file_type == "groups": cursor.execute("UPDATE schedule_tasks SET groups_file_path = ? WHERE task_id = ?", (file_path, task_id))
    elif file_type == "weekdays": cursor.execute("UPDATE schedule_tasks SET weekdays_file_path = ? WHERE task_id = ?", (file_path, task_id))
    conn.commit(); conn.close()

def update_task_status(task_id: int, status: str, result_message: str | None = None):
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    cursor.execute("UPDATE schedule_tasks SET status = ?, result_message = ? WHERE task_id = ?", (status, result_message, task_id)); conn.commit(); conn.close()

def get_task_info(task_id: int) -> tuple | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    cursor.execute("SELECT user_id, groups_file_path, weekdays_file_path, status FROM schedule_tasks WHERE task_id = ?", (task_id,)); task = cursor.fetchone(); conn.close(); return task

def get_task_id_by_user_and_status(user_id: int, statuses: list) -> int | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor(); placeholders=','.join('?' for _ in statuses); query=f"SELECT task_id FROM schedule_tasks WHERE user_id = ? AND status IN ({placeholders}) ORDER BY created_at DESC LIMIT 1"
    try: cursor.execute(query, (user_id, *statuses)); task = cursor.fetchone(); return task[0] if task else None
    except sqlite3.Error: return None
    finally: conn.close()

def cancel_task_by_id(task_id: int):
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("UPDATE schedule_tasks SET status = 'cancelled' WHERE task_id = ? AND status NOT IN ('completed', 'completed_with_warnings', 'failed', 'processing', 'cancelled')", (task_id,)); conn.commit(); return cursor.rowcount > 0
    except sqlite3.Error: return False
    finally: conn.close()

def get_full_task_details(task_id: int) -> tuple | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    cursor.execute("SELECT t.task_id, t.user_id, u.username, u.first_name, t.groups_file_path, t.weekdays_file_path, t.status, strftime('%Y-%m-%d %H:%M:%S', t.created_at), t.result_message FROM schedule_tasks t LEFT JOIN users u ON t.user_id = u.telegram_id WHERE t.task_id = ?", (task_id,)); task = cursor.fetchone(); conn.close(); return task

def get_all_tasks(limit: int = 5, offset: int = 0, status_filter: str | None = None, user_id_filter: int | None = None) -> list:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor(); base_query="SELECT t.task_id, t.user_id, u.username, u.first_name, t.status, strftime('%Y-%m-%d %H:%M:%S', t.created_at) FROM schedule_tasks t LEFT JOIN users u ON t.user_id = u.telegram_id"; conditions=[]; params=[]
    if status_filter: conditions.append("t.status = ?"); params.append(status_filter)
    if user_id_filter: conditions.append("t.user_id = ?"); params.append(user_id_filter)
    if conditions: base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY t.task_id DESC LIMIT ? OFFSET ?"; params.extend([limit, offset]); cursor.execute(base_query, tuple(params)); tasks = cursor.fetchall(); conn.close(); return tasks

def count_all_tasks(status_filter: str | None = None, user_id_filter: int | None = None) -> int:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor(); base_query = "SELECT COUNT(t.task_id) FROM schedule_tasks t"; conditions=[]; params=[]
    if status_filter: conditions.append("t.status = ?"); params.append(status_filter)
    if user_id_filter: base_query += " LEFT JOIN users u ON t.user_id = u.telegram_id"; conditions.append("t.user_id = ?"); params.append(user_id_filter)
    if conditions: base_query += " WHERE " + " AND ".join(conditions)
    cursor.execute(base_query, tuple(params)); count_result = cursor.fetchone(); conn.close(); return count_result[0] if count_result else 0

def get_user_last_task_id(user_id: int) -> int | None:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("SELECT task_id FROM schedule_tasks WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,)); task = cursor.fetchone(); return task[0] if task else None
    except sqlite3.Error: return None
    finally: conn.close()

def force_update_task_status(task_id: int, new_status: str, admin_reason: str = "Принудительно изменено администратором") -> bool:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: message_to_store=f"Статус изменен на '{new_status}' администратором. Причина: {admin_reason}"; cursor.execute("UPDATE schedule_tasks SET status = ?, result_message = ? WHERE task_id = ?", (new_status, message_to_store, task_id)); conn.commit(); return cursor.rowcount > 0
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при принудительном обновлении статуса задачи {task_id}: {e}"); return False
    finally: conn.close()

def delete_task_from_db(task_id: int) -> bool:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("DELETE FROM schedule_tasks WHERE task_id = ?", (task_id,)); conn.commit(); return cursor.rowcount > 0
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при удалении задачи {task_id} из БД: {e}"); return False
    finally: conn.close()

def get_active_user_ids() -> list[int]:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("SELECT telegram_id FROM users WHERE status = 'active'"); user_ids = [row[0] for row in cursor.fetchall()]; return user_ids
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при получении ID активных пользователей: {e}"); return []
    finally: conn.close()

def save_feedback(user_id: int, username: str | None, first_name: str | None, message_text: str) -> bool:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("INSERT INTO feedback (user_id, username, first_name, message_text, received_at) VALUES (?, ?, ?, ?, ?)",(user_id, username, first_name, message_text, datetime.now())); conn.commit(); return True
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при сохранении фидбека от {user_id}: {e}"); return False
    finally: conn.close()

def get_unread_feedback(limit: int = 10) -> list:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("SELECT f.feedback_id, f.user_id, f.username, f.first_name, f.message_text, strftime('%Y-%m-%d %H:%M:%S', f.received_at) FROM feedback f WHERE f.is_viewed = 0 ORDER BY f.received_at ASC LIMIT ?", (limit,)); feedback_list = cursor.fetchall(); return feedback_list
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при получении непрочитанного фидбека: {e}"); return []
    finally: conn.close()

def mark_feedback_as_viewed(feedback_id: int) -> bool:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("UPDATE feedback SET is_viewed = 1 WHERE feedback_id = ?", (feedback_id,)); conn.commit(); return cursor.rowcount > 0
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при пометке фидбека {feedback_id} как прочитанного: {e}"); return False
    finally: conn.close()

def get_all_users_paginated(limit: int = 10, offset: int = 0, role_filter: str | None = None, status_filter: str | None = None) -> list:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor(); base_query="SELECT telegram_id, username, first_name, status, role, strftime('%Y-%m-%d %H:%M:%S', created_at) FROM users"; conditions=[]; params=[]
    if role_filter: conditions.append("role = ?"); params.append(role_filter)
    if status_filter: conditions.append("status = ?"); params.append(status_filter)
    if conditions: base_query += " WHERE " + " AND ".join(conditions)
    base_query += " ORDER BY telegram_id ASC LIMIT ? OFFSET ?"; params.extend([limit, offset])
    try: cursor.execute(base_query, tuple(params)); users = cursor.fetchall(); return users
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при получении списка пользователей: {e}"); return []
    finally: conn.close()

def count_all_users(role_filter: str | None = None, status_filter: str | None = None) -> int:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor(); base_query = "SELECT COUNT(telegram_id) FROM users"; conditions=[]; params=[]
    if role_filter: conditions.append("role = ?"); params.append(role_filter)
    if status_filter: conditions.append("status = ?"); params.append(status_filter)
    if conditions: base_query += " WHERE " + " AND ".join(conditions)
    try: cursor.execute(base_query, tuple(params)); count_result = cursor.fetchone(); return count_result[0] if count_result else 0
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при подсчете пользователей: {e}"); return 0
    finally: conn.close()

def get_user_task_count(user_id: int) -> int:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try: cursor.execute("SELECT COUNT(task_id) FROM schedule_tasks WHERE user_id = ?", (user_id,)); count_result = cursor.fetchone(); return count_result[0] if count_result else 0
    except sqlite3.Error: return 0
    finally: conn.close()

def delete_user_and_tasks(user_id_to_delete: int) -> bool:
    conn=sqlite3.connect(DATABASE_PATH); cursor=conn.cursor()
    try:
        cursor.execute("DELETE FROM feedback WHERE user_id = ?", (user_id_to_delete,)) # Сначала удаляем зависимые записи
        cursor.execute("DELETE FROM schedule_tasks WHERE user_id = ?", (user_id_to_delete,))
        cursor.execute("DELETE FROM users WHERE telegram_id = ?", (user_id_to_delete,)); conn.commit()
        return True # Если пользователь существовал, rowcount для DELETE users будет > 0
    except sqlite3.Error as e: print(f"DB_ERROR: Ошибка при удалении пользователя {user_id_to_delete} и его данных: {e}"); conn.rollback(); return False
    finally: conn.close()