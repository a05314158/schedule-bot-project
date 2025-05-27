from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import CommandStart, Command, Text
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup # <--- ИСПРАВЛЕНО
from aiogram.types import ReplyKeyboardRemove, BotCommand, ParseMode
from aiogram.utils.markdown import html_decoration as hd
import os

from bot.models import db
from bot.views import messages, keyboards
from bot.config import ADMIN_IDS
from bot.utils import file_manager # <--- ДОБАВЛЕНО

try:
    from .schedule_handlers import active_user_only
except ImportError:
    print("WARNING: active_user_only decorator not found in schedule_handlers, using a pass-through decorator in common_handlers.")
    def active_user_only(func):
        async def wrapper(*args, **kwargs): return await func(*args, **kwargs)
        return wrapper

async def cmd_start(message: types.Message, state: FSMContext, command: BotCommand = None):
    await state.finish()
    db.add_user(telegram_id=message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
    user_info = db.get_user(message.from_user.id)
    if not user_info: await message.answer(messages.ERROR_OCCURRED, reply_markup=ReplyKeyboardRemove()); return
    user_telegram_id, user_username, user_first_name, user_status, user_role, user_created_at = user_info
    is_admin_user = message.from_user.id in ADMIN_IDS
    if is_admin_user and (user_status != 'active' or user_role != 'admin'):
        db.update_user_status_role(message.from_user.id, status='active', role='admin')
        user_status, user_role = 'active', 'admin'
        await message.answer("👑 Вы автоматически активированы как администратор.")
    await message.answer(f"{messages.WELCOME_MESSAGE}\nВаш ID: {message.from_user.id}")
    if user_status == 'pending': await message.answer(messages.ACCESS_PENDING_MESSAGE, reply_markup=ReplyKeyboardRemove())
    elif user_status == 'banned': await message.answer(messages.ACCESS_DENIED_MESSAGE, reply_markup=ReplyKeyboardRemove())
    elif user_status == 'active': await message.answer("Вы можете создавать расписания или получить помощь.", reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user))

async def cmd_help(message: types.Message, command: BotCommand = None):
    user_info = db.get_user(message.from_user.id)
    is_admin = user_info and user_info[4] == 'admin' and message.from_user.id in ADMIN_IDS
    help_text = messages.ADMIN_HELP_MESSAGE if is_admin else messages.USER_HELP_MESSAGE
    try: await message.answer(help_text, parse_mode=ParseMode.HTML)
    except Exception: await message.answer(help_text)
    if user_info and user_info[3] == 'active': await message.answer("Выберите действие:", reply_markup=keyboards.main_menu_kb(is_admin=is_admin))

async def cmd_cancel(message: types.Message, state: FSMContext, command: BotCommand = None):
    current_state = await state.get_state()
    user_info = db.get_user(message.from_user.id)
    is_admin = user_info and user_info[4] == 'admin' and message.from_user.id in ADMIN_IDS
    reply_markup_after_cancel = ReplyKeyboardRemove()
    if user_info and user_info[3] == 'active': reply_markup_after_cancel = keyboards.main_menu_kb(is_admin=is_admin)
    if current_state is None:
        active_fsm_independent_task = db.get_user_active_task(message.from_user.id)
        if active_fsm_independent_task:
            task_to_cancel_id = active_fsm_independent_task[0]
            await message.answer(messages.CANCELLED_ACTION_GENERIC, reply_markup=reply_markup_after_cancel)
            return
        await message.answer(messages.NO_ACTIVE_TASK_TO_CANCEL, reply_markup=reply_markup_after_cancel)
        return
    await state.finish()
    await message.answer(messages.CANCELLED_ACTION, reply_markup=reply_markup_after_cancel)

@active_user_only
async def cmd_my_task_status(message: types.Message, state: FSMContext, command: types.BotCommand = None, **kwargs):
    await state.finish()
    user_id = message.from_user.id; args = message.get_args(); task_id_to_show = None
    if args and args.isdigit(): task_id_to_show = int(args)
    else: last_task_id = db.get_user_last_task_id(user_id); task_id_to_show = last_task_id
    is_admin_user = message.from_user.id in ADMIN_IDS
    if not task_id_to_show: await message.answer(messages.TASK_STATUS_NO_TASK_FOR_USER, reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user)); return
    task_details = db.get_full_task_details(task_id_to_show)
    if not task_details or (task_details[1] != user_id and not is_admin_user):
        await message.answer(messages.TASK_STATUS_ID_NOT_FOUND.format(task_id=task_id_to_show), reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user)); return
    t_id, uid_db, un_db, fn_db, gf_path, wf_path, st, ca_str, rm_str = task_details
    user_display = hd.quote(fn_db or un_db or f"ID:{uid_db}")
    groups_file_name = os.path.basename(gf_path) if gf_path and isinstance(gf_path, str) else "не загружен"
    weekdays_file_name = os.path.basename(wf_path) if wf_path and isinstance(wf_path, str) else "не загружен"
    result_message_display = hd.quote(rm_str or "Информация отсутствует.")
    response_text = messages.TASK_STATUS_INFO_HEADER.format(task_id=t_id)
    response_text += messages.TASK_STATUS_ITEM.format(user_display=user_display, user_id=uid_db, created_at=ca_str or "N/A", status=hd.quote(st), groups_file=hd.quote(groups_file_name), weekdays_file=hd.quote(weekdays_file_name), result_message=result_message_display)
    output_dir_for_task = file_manager.get_output_dir_for_task(uid_db, t_id)
    results_are_present = False
    if os.path.exists(output_dir_for_task) and any(f.endswith(('.xlsx', '.xls')) for f in os.listdir(output_dir_for_task)): results_are_present = True
    reply_markup = keyboards.task_info_actions_kb(task_id=t_id, task_status=st, results_exist=results_are_present, user_id=uid_db if is_admin_user else None)
    await message.answer(response_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)

class FeedbackStates(StatesGroup):
    waiting_for_feedback_text = State()

@active_user_only
async def cmd_leave_feedback_start(message: types.Message, state: FSMContext, command: types.BotCommand = None, **kwargs):
    await state.set_state(FeedbackStates.waiting_for_feedback_text.state)
    await message.answer(messages.FEEDBACK_PROMPT, reply_markup=keyboards.cancel_state_kb())

async def process_feedback_text(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 5:
        await message.reply(messages.FEEDBACK_EMPTY, reply_markup=keyboards.cancel_state_kb()); return
    user_id = message.from_user.id; user_info = db.get_user(user_id)
    username = user_info[1] if user_info else message.from_user.username
    first_name = user_info[2] if user_info else message.from_user.first_name
    is_admin = user_id in ADMIN_IDS
    if db.save_feedback(user_id, username, first_name, message.text.strip()):
        await message.answer(messages.FEEDBACK_RECEIVED, reply_markup=keyboards.main_menu_kb(is_admin=is_admin))
        feedback_id = db.get_last_feedback_id_for_user(user_id)
        if feedback_id:
            user_display = hd.quote(first_name or username or f"ID:{user_id}")
            for admin_id_notify in ADMIN_IDS:
                try: await message.bot.send_message(admin_id_notify, messages.FEEDBACK_FORWARDED_TO_ADMIN.format(user_display=user_display, user_id=user_id, feedback_text=hd.quote(message.text.strip()), feedback_id=feedback_id), parse_mode=ParseMode.HTML)
                except Exception: pass
    else: await message.answer(messages.ERROR_OCCURRED + " (не удалось сохранить отзыв)", reply_markup=keyboards.main_menu_kb(is_admin=is_admin))
    await state.finish()

def register_common_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, CommandStart(), state="*")
    dp.register_message_handler(cmd_help, Command(commands=['help']), state="*")
    dp.register_message_handler(cmd_help, Text(equals="❓ Помощь", ignore_case=True), state="*")
    dp.register_message_handler(cmd_cancel, Command(commands=['cancel']), state="*")
    dp.register_message_handler(cmd_cancel, Text(equals="❌ Отменить текущее", ignore_case=True), state="*")
    dp.register_message_handler(cmd_my_task_status, Command(commands=['my_task_status', 'task_status']), state="*")
    dp.register_message_handler(cmd_my_task_status, Text(equals="📊 Статус моей задачи", ignore_case=True), state="*")
    dp.register_message_handler(cmd_leave_feedback_start, Command(commands=['feedback', 'leave_feedback']), state="*")
    dp.register_message_handler(cmd_leave_feedback_start, Text(equals="📝 Оставить отзыв", ignore_case=True), state="*")
    dp.register_message_handler(process_feedback_text, state=FeedbackStates.waiting_for_feedback_text, content_types=types.ContentType.TEXT)