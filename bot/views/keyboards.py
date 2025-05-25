from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

def confirm_schedule_generation_kb(task_id: int):
    keyboard = InlineKeyboardMarkup(row_width=1); keyboard.add(InlineKeyboardButton("🚀 Запустить генерацию!", callback_data=f"run_task_{task_id}")); return keyboard
def admin_approve_user_kb(telegram_id: int, username: str = None, first_name: str = None):
    user_label = first_name or username or str(telegram_id); keyboard = InlineKeyboardMarkup(row_width=1); keyboard.add(InlineKeyboardButton(f"✅ Активировать {user_label}", callback_data=f"admin_approve_{telegram_id}")); return keyboard
def main_menu_kb(is_admin: bool = False):
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False); keyboard.row(KeyboardButton("📅 Новое расписание"), KeyboardButton("❓ Помощь")); keyboard.row(KeyboardButton("📊 Статус моей задачи"), KeyboardButton("📝 Оставить отзыв"))
    if is_admin: keyboard.row(KeyboardButton("👑 Админ-панель")) # Эта кнопка осталась, но вызывает /admin
    return keyboard
def cancel_state_kb():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); keyboard.add(KeyboardButton("❌ Отменить текущее")); return keyboard
TASK_STATUSES_FOR_FILTER = {"Все": "all", "⏳ Ожидают файлы": "pending_files", "⏳ Ждет файл групп": "pending_groups_file", "⏳ Ждет файл дней": "pending_weekdays_file", "🔄 В обработке": "processing", "✅ Завершены": "completed", "⚠️ С предупреждением": "completed_with_warnings", "❌ Ошибки": "failed", "🚫 Отменены": "cancelled", "👨‍💻 Ошибки админа": "failed_by_admin"}
def tasks_filter_kb():
    keyboard = InlineKeyboardMarkup(row_width=2); buttons = [InlineKeyboardButton(dn, callback_data=f"tasklist_filter_{sc}_page_0") for dn, sc in TASK_STATUSES_FOR_FILTER.items()]; keyboard.add(*buttons); return keyboard
def tasks_pagination_kb(current_page: int, total_pages: int, current_filter: str = "all"):
    keyboard = InlineKeyboardMarkup(row_width=3); nav_buttons = []
    if current_page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"tasklist_filter_{current_filter}_page_{current_page - 1}"))
    if total_pages > 0 : nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data=f"tasklist_filter_{current_filter}_page_{current_page}"))
    if current_page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"tasklist_filter_{current_filter}_page_{current_page + 1}"))
    if nav_buttons: keyboard.row(*nav_buttons)
    keyboard.add(InlineKeyboardButton("⚙️ Фильтры статусов", callback_data="tasklist_show_filters")); return keyboard
def task_status_actions_kb(task_id: int, task_status: str, results_exist: bool = False):
    keyboard = InlineKeyboardMarkup(row_width=1)
    if task_status in ["completed", "completed_with_warnings"] and results_exist: keyboard.add(InlineKeyboardButton("📊 Повторно скачать результаты", callback_data=f"resend_results_{task_id}"))
    return keyboard
def confirm_delete_task_kb(task_id: int):
    keyboard = InlineKeyboardMarkup(row_width=2); keyboard.add(InlineKeyboardButton("🗑️ Да, удалить!", callback_data=f"admin_confirm_delete_task_{task_id}"), InlineKeyboardButton("Нет, отмена", callback_data=f"admin_cancel_delete_task_{task_id}")); return keyboard # Изменил callback_data
def mark_feedback_viewed_kb(feedback_id: int):
    keyboard = InlineKeyboardMarkup(row_width=1); keyboard.add(InlineKeyboardButton(f"✅ Отметить отзыв #{feedback_id} как прочитанный", callback_data=f"admin_mark_fb_viewed_{feedback_id}")); return keyboard
def admin_panel_kb():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("⏳ Ожидающие юзеры", callback_data="admin_panel_pending_users"), InlineKeyboardButton("👥 Все пользователи", callback_data="admin_panel_list_all_users_page_0")) # Новая кнопка
    keyboard.add(InlineKeyboardButton("📋 Список всех задач", callback_data="admin_panel_list_tasks"), InlineKeyboardButton("📬 Просмотреть отзывы", callback_data="admin_panel_view_feedback"))
    keyboard.add(InlineKeyboardButton("📢 Рассылка (инфо)", callback_data="admin_panel_broadcast_info")); return keyboard
def user_profile_actions_kb(target_user_id: int, current_status: str, current_role: str):
    keyboard = InlineKeyboardMarkup(row_width=2)
    if current_status == "active": keyboard.add(InlineKeyboardButton("🚫 Забанить", callback_data=f"admin_useract_ban_{target_user_id}"))
    elif current_status == "banned": keyboard.add(InlineKeyboardButton("✅ Разбанить", callback_data=f"admin_useract_unban_{target_user_id}"))
    if current_role == "user": keyboard.add(InlineKeyboardButton("👑 Сделать админом", callback_data=f"admin_useract_setadmin_{target_user_id}"))
    elif current_role == "admin": keyboard.add(InlineKeyboardButton("👤 Сделать юзером", callback_data=f"admin_useract_setuser_{target_user_id}"))
    keyboard.add(InlineKeyboardButton(f"📋 Задачи юзера ({target_user_id})", callback_data=f"admin_useract_viewtasks_{target_user_id}"))
    keyboard.add(InlineKeyboardButton("🗑️ Удалить юзера и данные", callback_data=f"admin_useract_confirmdelete_{target_user_id}"))
    return keyboard
def confirm_user_data_delete_kb(target_user_id: int):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(InlineKeyboardButton("🗑️ ДА, УДАЛИТЬ ЮЗЕРА!", callback_data=f"admin_useract_dodelete_{target_user_id}"), InlineKeyboardButton("Отмена", callback_data=f"admin_useract_canceldelete_{target_user_id}"))
    return keyboard
def user_list_filters_kb(current_status_filter: str | None = None, current_role_filter: str | None = None):
    keyboard = InlineKeyboardMarkup(row_width=2)
    statuses = {"Все статусы": "all_status", "Активные": "active", "В ожидании": "pending", "Забаненные": "banned"}
    roles = {"Все роли": "all_role", "Админы": "admin", "Пользователи": "user"}
    for display, code in statuses.items():
        prefix = "✅ " if code == current_status_filter or (code == "all_status" and current_status_filter is None) else ""
        keyboard.insert(InlineKeyboardButton(f"{prefix}{display}", callback_data=f"admin_userlist_filter_status_{code}_role_{current_role_filter or 'all_role'}_page_0"))
    for display, code in roles.items():
        prefix = "✅ " if code == current_role_filter or (code == "all_role" and current_role_filter is None) else ""
        keyboard.insert(InlineKeyboardButton(f"{prefix}{display}", callback_data=f"admin_userlist_filter_status_{current_status_filter or 'all_status'}_role_{code}_page_0"))
    keyboard.add(InlineKeyboardButton("‹‹ Назад к списку", callback_data=f"admin_userlist_filter_{current_status_filter or 'all_status'}_role_{current_role_filter or 'all_role'}_page_0"))
    return keyboard

def user_list_pagination_kb(current_page: int, total_pages: int, status_filter: str | None, role_filter: str | None):
    status_f = status_filter or "all_status"
    role_f = role_filter or "all_role"
    keyboard = InlineKeyboardMarkup(row_width=3)
    nav_buttons = []
    if current_page > 0: nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"admin_userlist_filter_status_{status_f}_role_{role_f}_page_{current_page - 1}"))
    if total_pages > 0: nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data=f"admin_userlist_filter_status_{status_f}_role_{role_f}_page_{current_page}"))
    if current_page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"admin_userlist_filter_status_{status_f}_role_{role_f}_page_{current_page + 1}"))
    if nav_buttons: keyboard.row(*nav_buttons)
    keyboard.add(InlineKeyboardButton("🔧 Фильтры", callback_data=f"admin_userlist_show_filters_status_{status_f}_role_{role_f}"))
    return keyboard