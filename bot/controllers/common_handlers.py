from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import CommandStart, Command, Text
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, BotCommand, ParseMode, InputFile, MediaGroup, ContentType
from aiogram.utils.markdown import html_decoration as hd
import os

from bot.models import db
from bot.views import messages, keyboards
from bot.utils import file_manager
from bot.config import ADMIN_IDS
from bot.controllers import schedule_handlers, admin_handlers

class FeedbackState(StatesGroup):
    waiting_for_feedback_message = State()

async def cmd_start(message: types.Message, state: FSMContext, command: BotCommand = None):
    await state.finish()
    db.add_user(telegram_id=message.from_user.id, username=message.from_user.username, first_name=message.from_user.first_name)
    user_info = db.get_user(message.from_user.id)
    if not user_info: await message.answer(messages.ERROR_OCCURRED, reply_markup=ReplyKeyboardRemove()); return
    is_admin_user = message.from_user.id in ADMIN_IDS
    user_status, user_role = user_info[3], user_info[4]
    if is_admin_user and (user_status != 'active' or user_role != 'admin'):
        db.update_user_status_role(message.from_user.id, status='active', role='admin')
        user_status, user_role = 'active', 'admin'
        await message.answer("👑 Вы автоматически активированы как администратор.")
    await message.answer(f"{messages.WELCOME_MESSAGE}\nВаш ID: {message.from_user.id}", parse_mode=ParseMode.HTML)
    if user_status == 'pending': await message.answer(messages.ACCESS_PENDING_MESSAGE, reply_markup=ReplyKeyboardRemove())
    elif user_status == 'banned': await message.answer(messages.ACCESS_DENIED_MESSAGE, reply_markup=ReplyKeyboardRemove())
    elif user_status == 'active': await message.answer("Выберите действие из меню:", reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user))


async def cmd_help_wrapper(message: types.Message, command: BotCommand = None, state: FSMContext = None):
    user_id = message.from_user.id
    is_admin_user = user_id in ADMIN_IDS

    help_text_to_send = messages.ADMIN_HELP_MESSAGE if is_admin_user else messages.USER_HELP_MESSAGE

    try:
        await message.answer(help_text_to_send, parse_mode=ParseMode.HTML)
    except Exception:
        # В случае ошибки парсинга HTML, отправляем как простой текст (убрав теги)
        # Это очень грубый способ убрать теги, лучше иметь версии без тегов
        plain_text_help = help_text_to_send.replace("<br>", "\n").replace("<b>", "").replace("</b>", "").replace(
            "<code>", "").replace("</code>", "").replace("<i>", "").replace("</i>", "")
        plain_text_help = plain_text_help.replace("<", "<").replace(">", ">")
        await message.answer(plain_text_help)

    user_info = db.get_user(user_id)  # Повторно получаем, т.к. is_admin_user уже есть
    if user_info and user_info[3] == 'active':
        await message.answer("Что бы вы хотели сделать дальше?",
                             reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user))
async def cmd_cancel_wrapper(message: types.Message, state: FSMContext, command: BotCommand = None):
    user_id = message.from_user.id; current_fsm_state_name = await state.get_state()
    is_admin_user = user_id in ADMIN_IDS
    await state.finish(); reply_markup_after_cancel = ReplyKeyboardRemove()
    user_info = db.get_user(user_id)
    if user_info and user_info[3] == 'active': reply_markup_after_cancel = keyboards.main_menu_kb(is_admin=is_admin_user)
    if current_fsm_state_name == FeedbackState.waiting_for_feedback_message.state:
        await message.answer(messages.CANCELLED_ACTION_GENERIC, reply_markup=reply_markup_after_cancel); return
    active_task_id = db.get_task_id_by_user_and_status(user_id, ['pending_groups_file', 'pending_weekdays_file', 'pending_files'])
    if active_task_id:
        if db.cancel_task_by_id(active_task_id):
            file_manager.cleanup_task_files(user_id, active_task_id)
            await message.answer(messages.CANCELLED_TASK_SUCCESS.format(task_id=active_task_id), reply_markup=reply_markup_after_cancel); return
        else: await message.answer(messages.CANCELLED_TASK_FAILED, reply_markup=reply_markup_after_cancel); return
    elif current_fsm_state_name is not None: await message.answer(messages.CANCELLED_ACTION, reply_markup=reply_markup_after_cancel); return
    else: await message.answer(messages.NO_ACTIVE_TASK_TO_CANCEL, reply_markup=reply_markup_after_cancel); return

async def cmd_task_status_wrapper(message: types.Message, command: BotCommand = None, state: FSMContext = None):
    user_id = message.from_user.id; args = message.get_args() if command else None
    task_id_to_check = None
    is_admin_user = user_id in ADMIN_IDS
    if args:
        try: task_id_to_check = int(args)
        except ValueError: await message.reply(messages.TASK_STATUS_USAGE, parse_mode=ParseMode.HTML); return
    else:
        task_id_to_check = db.get_user_last_task_id(user_id)
        if not task_id_to_check: await message.answer(messages.TASK_STATUS_NO_TASK_FOR_USER, reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user), parse_mode=ParseMode.HTML); return
    task_details = db.get_full_task_details(task_id_to_check)
    if not task_details: await message.answer(messages.TASK_STATUS_ID_NOT_FOUND.format(task_id=task_id_to_check), reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user)); return
    if task_details[1] != user_id and not is_admin_user:
         await message.answer(messages.TASK_STATUS_ID_NOT_FOUND.format(task_id=task_id_to_check) + " (Это не ваша задача)", reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user)); return
    (t_id,db_uid,un,fn,gf,wf,st,ca,rm)=task_details;ud=fn or un or f"ID:{db_uid}";gfb=os.path.basename(gf) if gf and isinstance(gf,str) else"N/A";wfb=os.path.basename(wf) if wf and isinstance(wf,str) else "N/A"
    resp=messages.TASK_STATUS_INFO_HEADER.format(task_id=t_id)+messages.TASK_STATUS_ITEM.format(user_display=hd.quote(ud),user_id=db_uid,created_at=ca,status=hd.quote(st),groups_file=hd.quote(gfb),weekdays_file=hd.quote(wfb),result_message=hd.quote(rm if rm else"Нет информации."))
    odf=file_manager.get_output_dir_for_task(db_uid,t_id); re=os.path.exists(odf) and any(f.endswith(('.xlsx','.xls')) for f in os.listdir(odf))
    rmu=keyboards.task_status_actions_kb(t_id,st,re)
    await message.answer(resp,parse_mode=ParseMode.HTML,reply_markup=rmu if rmu.inline_keyboard else None)

async def callback_resend_results(call: types.CallbackQuery, state: FSMContext = None):
    try: task_id = int(call.data.split("_")[-1])
    except: await call.answer("Ошибка ID.", show_alert=True); return
    td = db.get_full_task_details(task_id)
    if not td: await call.answer(messages.TASK_STATUS_ID_NOT_FOUND.format(task_id=task_id),show_alert=True); return
    is_admin_user = call.from_user.id in ADMIN_IDS
    if td[1]!=call.from_user.id and not is_admin_user: await call.answer("Это не ваша задача.",show_alert=True); return
    uid_owner=td[1]; odf=file_manager.get_output_dir_for_task(uid_owner,task_id); gfp=[]
    if os.path.exists(odf):
        for fn in sorted(os.listdir(odf)):
            if fn.endswith(('.xlsx','.xls')): gfp.append(os.path.join(odf,fn))
    if gfp:
        await call.message.answer(f"Повторно отправляю результаты для Задачи #{task_id}:")
        media=MediaGroup(); saf=False
        for i,fp in enumerate(gfp):
            if os.path.exists(fp) and len(media.media)<10: media.attach_document(InputFile(fp,filename=f"task{task_id}_{os.path.basename(fp)}")); saf=True
            elif os.path.exists(fp) and len(media.media)==10:
                try: await call.bot.send_media_group(chat_id=call.from_user.id,media=media)
                except: pass
                media=MediaGroup(); media.attach_document(InputFile(fp,filename=f"task{task_id}_{os.path.basename(fp)}"))
        if media.media:
            try: await call.bot.send_media_group(chat_id=call.from_user.id,media=media)
            except Exception as e: await call.message.answer(messages.FILES_SEND_ERROR.format(task_id=task_id,error=hd.quote(str(e))),parse_mode=ParseMode.HTML)
        if not saf and gfp: await call.message.answer(messages.NO_FILES_TO_SEND_WARNING.format(task_id=task_id))
        await call.answer()
    else: await call.answer("Сгенерированные файлы не найдены.",show_alert=True)

async def cmd_feedback_wrapper(message: types.Message, state: FSMContext, command: BotCommand = None):
    feedback_text = message.get_args() if command else None
    is_admin_user = message.from_user.id in ADMIN_IDS
    if command and feedback_text:
        db.save_feedback(message.from_user.id, message.from_user.username, message.from_user.first_name, feedback_text)
        await message.reply(messages.FEEDBACK_RECEIVED, reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user))
        for admin_id in ADMIN_IDS:
            if admin_id == message.from_user.id : continue
            try: await message.bot.send_message(admin_id, messages.FEEDBACK_FORWARDED_TO_ADMIN.format(user_display=hd.quote(message.from_user.full_name), user_id=message.from_user.id, feedback_text=hd.quote(feedback_text), feedback_id="Новый (через команду)"), parse_mode=ParseMode.HTML)
            except Exception: pass
    else:
        await FeedbackState.waiting_for_feedback_message.set()
        await message.reply(messages.FEEDBACK_PROMPT, reply_markup=keyboards.cancel_state_kb(), parse_mode=ParseMode.HTML)

async def process_feedback_message(message: types.Message, state: FSMContext):
    is_admin_user = message.from_user.id in ADMIN_IDS
    if not message.text or message.text.startswith('/'):
        await message.reply(messages.FEEDBACK_EMPTY, reply_markup=keyboards.cancel_state_kb(), parse_mode=ParseMode.HTML); return
    feedback_text = message.text
    db.save_feedback(message.from_user.id, message.from_user.username, message.from_user.first_name, feedback_text)
    await state.finish()
    await message.reply(messages.FEEDBACK_RECEIVED, reply_markup=keyboards.main_menu_kb(is_admin=is_admin_user))
    for admin_id in ADMIN_IDS:
        if admin_id == message.from_user.id : continue
        try: await message.bot.send_message(admin_id, messages.FEEDBACK_FORWARDED_TO_ADMIN.format(user_display=hd.quote(message.from_user.full_name), user_id=message.from_user.id, feedback_text=hd.quote(feedback_text), feedback_id="Новый (через FSM)"), parse_mode=ParseMode.HTML)
        except Exception: pass

async def text_admin_panel_handler(message: types.Message, state: FSMContext):
    # Проверка прав теперь будет в admin_handlers.cmd_admin_panel через декоратор @admin_only
    await admin_handlers.cmd_admin_panel(message, state=state) # Передаем и message, и state

def register_common_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_start, CommandStart(), state="*")
    dp.register_message_handler(cmd_help_wrapper, Command(commands=['help']), state="*")
    dp.register_message_handler(cmd_help_wrapper, Text(equals="❓ Помощь", ignore_case=True), state="*")
    dp.register_message_handler(cmd_cancel_wrapper, Command(commands=['cancel']), state="*")
    dp.register_message_handler(cmd_cancel_wrapper, Text(equals="❌ Отменить текущее", ignore_case=True), state="*")
    dp.register_message_handler(cmd_task_status_wrapper, Command(commands=['task_status']), state="*")
    dp.register_message_handler(cmd_task_status_wrapper, Text(equals="📊 Статус моей задачи", ignore_case=True), state="*")
    dp.register_callback_query_handler(callback_resend_results, Text(startswith="resend_results_"), state="*")
    dp.register_message_handler(cmd_feedback_wrapper, Command(commands=['feedback']), state="*")
    dp.register_message_handler(cmd_feedback_wrapper, Text(equals="📝 Оставить отзыв", ignore_case=True), state="*")
    dp.register_message_handler(process_feedback_message, state=FeedbackState.waiting_for_feedback_message, content_types=ContentType.TEXT)
    dp.register_message_handler(text_admin_panel_handler, Text(equals="👑 Админ-панель", ignore_case=True), state="*")