from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from bot.config import ADMIN_IDS

USER_STATUSES_FOR_FILTER = {"Все статусы": "all_status", "Активные": "active", "В ожидании": "pending", "Забаненные": "banned"}
USER_ROLES_FOR_FILTER = {"Все роли": "all_role", "Админы": "admin", "Пользователи": "user"}
TASK_STATUSES_FOR_FILTER = {"Все": "all", "⏳ Ожидают файлы": "pending_files", "⏳ Ждет файл групп": "pending_groups_file", "⏳ Ждет файл дней": "pending_weekdays_file", "🔄 В обработке": "processing", "✅ Завершены": "completed", "⚠️ С предупреждением": "completed_with_warnings", "❌ Ошибки": "failed", "🚫 Отменены": "cancelled", "👨‍💻 Отменено админом": "failed_by_admin"}

CB_PREFIX_ADMIN_PANEL = "ap"
CB_PREFIX_USER_LIST = "ul"
CB_PREFIX_USER_ACTION = "ua"
CB_PREFIX_TASK_LIST = "tl"
CB_PREFIX_TASK_ACTION = "ta"
CB_PREFIX_FEEDBACK = "fb"
CB_PREFIX_RUN_TASK = "rt"
CB_PREFIX_NOOP = "noop"

def confirm_schedule_generation_kb(task_id: int):
    kb = InlineKeyboardMarkup(row_width=1); kb.add(InlineKeyboardButton("🚀 Запустить генерацию!", callback_data=f"{CB_PREFIX_RUN_TASK}:confirm:{task_id}")); return kb # Изменен разделитель

def admin_approve_user_kb(telegram_id: int, username: str = None, first_name: str = None):
    user_label = first_name or username or str(telegram_id); kb = InlineKeyboardMarkup(row_width=1); kb.add(InlineKeyboardButton(f"✅ Активировать {user_label}", callback_data=f"{CB_PREFIX_USER_ACTION}:approve:{telegram_id}")); return kb

def main_menu_kb(is_admin: bool = False):
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False); kb.row(KeyboardButton("📅 Новое расписание"), KeyboardButton("❓ Помощь")); kb.row(KeyboardButton("📊 Статус моей задачи"), KeyboardButton("📝 Оставить отзыв"))
    if is_admin: kb.row(KeyboardButton("👑 Админ-панель"))
    return kb

def cancel_state_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True); kb.add(KeyboardButton("❌ Отменить текущее")); return kb

def admin_panel_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(InlineKeyboardButton("⏳ Ожидающие", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:pending"))
    kb.add(InlineKeyboardButton("👥 Все пользователи", callback_data=f"{CB_PREFIX_USER_LIST}:show:p0:sf_all_status:rf_all_role:uid_all")) # унифицируем user list
    kb.add(InlineKeyboardButton("📋 Все задачи", callback_data=f"{CB_PREFIX_TASK_LIST}:show:p0:sf_all:uid_all")) # НОВЫЙ ФОРМАТ
    kb.add(InlineKeyboardButton("📬 Просмотреть отзывы", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:feedback"))
    kb.add(InlineKeyboardButton("📢 Рассылка (инфо)", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:broadcastinfo"))
    return kb

def user_list_filters_kb(current_status_filter: str, current_role_filter: str):
    kb = InlineKeyboardMarkup(row_width=2)
    csf = current_status_filter; crf = current_role_filter
    status_buttons_row = []; role_buttons_row = []
    for display, code in USER_STATUSES_FOR_FILTER.items():
        prefix = "✅ " if code == csf else ""
        status_buttons_row.append(InlineKeyboardButton(f"{prefix}{display}", callback_data=f"{CB_PREFIX_USER_LIST}:show:p0:sf_{code}:rf_{crf}:uid_all"))
    if status_buttons_row: kb.row(*status_buttons_row)
    for display, code in USER_ROLES_FOR_FILTER.items():
        prefix = "✅ " if code == crf else ""
        role_buttons_row.append(InlineKeyboardButton(f"{prefix}{display}", callback_data=f"{CB_PREFIX_USER_LIST}:show:p0:sf_{csf}:rf_{code}:uid_all"))
    if role_buttons_row: kb.row(*role_buttons_row)
    kb.add(InlineKeyboardButton("‹‹ К списку (тек. фильтры)", callback_data=f"{CB_PREFIX_USER_LIST}:show:p0:sf_{csf}:rf_{crf}:uid_all"))
    kb.add(InlineKeyboardButton("🏠 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    return kb

def user_list_pagination_kb(current_page: int, total_pages: int, status_filter: str, role_filter: str):
    kb = InlineKeyboardMarkup(row_width=3); nav_buttons = []
    cb_base = f"{CB_PREFIX_USER_LIST}:show:sf_{status_filter}:rf_{role_filter}:uid_all"
    if current_page > 0: nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"{cb_base}:p{current_page - 1}"))
    if total_pages > 0: nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data=f"{CB_PREFIX_NOOP}:userpage"))
    if current_page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"{cb_base}:p{current_page + 1}"))
    if nav_buttons: kb.row(*nav_buttons)
    return kb

def user_profile_actions_kb(target_user_id: int, current_status: str, current_role: str, current_page: int, status_filter: str, role_filter: str):
    kb = InlineKeyboardMarkup(row_width=2); pref = CB_PREFIX_USER_ACTION
    page_cb_suffix = f":p{current_page}:sf_{status_filter}:rf_{role_filter}" # Для возврата к списку
    if current_status == "active": kb.add(InlineKeyboardButton("🚫 Забанить", callback_data=f"{pref}:ban:{target_user_id}{page_cb_suffix}"))
    elif current_status == "banned": kb.add(InlineKeyboardButton("✅ Разбанить", callback_data=f"{pref}:unban:{target_user_id}{page_cb_suffix}"))
    if target_user_id not in ADMIN_IDS:
        if current_role == "user": kb.add(InlineKeyboardButton("👑 Сделать админом", callback_data=f"{pref}:setadmin:{target_user_id}{page_cb_suffix}"))
        elif current_role == "admin": kb.add(InlineKeyboardButton("👤 Сделать юзером", callback_data=f"{pref}:setuser:{target_user_id}{page_cb_suffix}"))
    kb.add(InlineKeyboardButton(f"📋 Задачи (ID {target_user_id})", callback_data=f"{pref}:viewtasks:{target_user_id}"))
    if target_user_id not in ADMIN_IDS:
        kb.add(InlineKeyboardButton("🗑️ Удалить юзера", callback_data=f"{pref}:confirmdelete:{target_user_id}{page_cb_suffix}"))
    kb.add(InlineKeyboardButton("🔙 К списку пользователей", callback_data=f"{CB_PREFIX_USER_LIST}:show:p{current_page}:sf_{status_filter}:rf_{role_filter}:uid_all"))
    return kb

def confirm_user_data_delete_kb(target_user_id: int):
    kb = InlineKeyboardMarkup(row_width=2); pref = CB_PREFIX_USER_ACTION
    kb.add(InlineKeyboardButton("🗑️ ДА, УДАЛИТЬ ЮЗЕРА!", callback_data=f"{pref}:dodelete:{target_user_id}"))
    kb.add(InlineKeyboardButton("Отмена (к профилю)", callback_data=f"{pref}:showprofile:{target_user_id}")) # Обратно к профилю
    return kb

def tasks_filter_kb(current_status_filter: str = "all", user_id_filter: int | None = None):
    kb = InlineKeyboardMarkup(row_width=2); uid_for_cb = user_id_filter if user_id_filter is not None else "all"
    base_cb_prefix = f"{CB_PREFIX_TASK_LIST}:show:p0:uid_{uid_for_cb}:sf" # НОВЫЙ ФОРМАТ
    buttons_in_row = []
    for display_name, code_name in TASK_STATUSES_FOR_FILTER.items():
        text = f"✅ {display_name}" if code_name == current_status_filter else display_name
        button = InlineKeyboardButton(text, callback_data=f"{base_cb_prefix}_{code_name}")
        buttons_in_row.append(button)
        if len(buttons_in_row) == 2: kb.row(*buttons_in_row); buttons_in_row = []
    if buttons_in_row: kb.row(*buttons_in_row)
    back_to_list_cb = f"{CB_PREFIX_TASK_LIST}:show:p0:sf_{current_status_filter}:uid_{uid_for_cb}"
    if user_id_filter: kb.add(InlineKeyboardButton(f"👤 К профилю юзера {user_id_filter}", callback_data=f"{CB_PREFIX_USER_ACTION}:showprofile:{user_id_filter}")) # Отправляем на профиль
    kb.add(InlineKeyboardButton("🔙 К списку задач", callback_data=back_to_list_cb))
    kb.add(InlineKeyboardButton("🏠 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    return kb

def tasks_pagination_kb(current_page: int, total_pages: int, current_filter: str = "all", user_id_filter: int | None = None):
    kb = InlineKeyboardMarkup(row_width=3); nav_buttons = []; uid_for_cb = user_id_filter if user_id_filter is not None else "all"
    base_cb_data = f"{CB_PREFIX_TASK_LIST}:show:sf_{current_filter}:uid_{uid_for_cb}" # НОВЫЙ ФОРМАТ
    if current_page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{base_cb_data}:p{current_page - 1}"))
    if total_pages > 0: nav_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data=f"{CB_PREFIX_NOOP}:taskpage"))
    if current_page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"{base_cb_data}:p{current_page + 1}"))
    if nav_buttons: kb.row(*nav_buttons)
    return kb

def task_info_actions_kb(task_id: int, task_status: str, results_exist: bool = False, user_id: int | None = None):
    kb = InlineKeyboardMarkup(row_width=1); pref = CB_PREFIX_TASK_ACTION
    if task_status in ["completed", "completed_with_warnings"] and results_exist:
        kb.add(InlineKeyboardButton("📊 Повторно скачать результаты", callback_data=f"{pref}:getresults:{task_id}"))
    if task_status not in ['processing', 'completed', 'completed_with_warnings', 'failed', 'failed_by_admin', 'cancelled']:
        kb.add(InlineKeyboardButton("🗑️ Удалить задачу", callback_data=f"{pref}:initdelete:{task_id}"))
    if user_id: kb.add(InlineKeyboardButton(f"👤 К профилю пользователя {user_id}", callback_data=f"{CB_PREFIX_USER_ACTION}:showprofile:{user_id}"))
    kb.add(InlineKeyboardButton("📋 К списку всех задач", callback_data=f"{CB_PREFIX_TASK_LIST}:show:p0:sf_all:uid_all"))
    return kb

def confirm_delete_task_kb(task_id: int):
    kb = InlineKeyboardMarkup(row_width=2); pref = CB_PREFIX_TASK_ACTION
    kb.add(InlineKeyboardButton("🗑️ Да, удалить задачу!", callback_data=f"{pref}:confirmdelete:{task_id}"))
    kb.add(InlineKeyboardButton("Нет (к инфо о задаче)", callback_data=f"{pref}:infocancel:{task_id}"))
    return kb

def mark_feedback_viewed_kb(feedback_id: int, user_id_from_feedback: int): # Добавляем user_id_from_feedback
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(f"🗣️ Ответить на отзыв #{feedback_id}", callback_data=f"{CB_PREFIX_FEEDBACK}:reply:{feedback_id}:{user_id_from_feedback}"))
    kb.add(InlineKeyboardButton(f"✅ Отметить отзыв #{feedback_id} как прочитанный", callback_data=f"{CB_PREFIX_FEEDBACK}:markviewed:{feedback_id}"))
    return kb