from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import InputFile, MediaGroup, ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.dispatcher import FSMContext
from aiogram.utils.markdown import html_decoration as hd
import os, json, math, asyncio
from bot.models import db
from bot.views import messages, keyboards
from bot.config import ADMIN_IDS
from bot.utils import file_manager

TASKS_PER_PAGE = 5
USERS_PER_PAGE = 10

def admin_only(func):
    async def wrapper(message_or_call: types.Message | types.CallbackQuery, *args, **kwargs):
        user_id = message_or_call.from_user.id
        if user_id not in ADMIN_IDS:
            if isinstance(message_or_call, types.Message): await message_or_call.answer("❌ У вас нет прав для выполнения этой команды.")
            elif isinstance(message_or_call, types.CallbackQuery): await message_or_call.answer("У вас нет прав.", show_alert=True)
            return
        return await func(message_or_call, *args, **kwargs)
    return wrapper

async def _send_pending_users_list(message_to_reply: types.Message):
    pending_users = db.get_pending_users()
    if not pending_users: await message_to_reply.answer(messages.ADMIN_NO_PENDING_USERS); return
    await message_to_reply.answer(messages.ADMIN_PENDING_USERS_LIST_HEADER + "\n")
    for user_id, username, first_name in pending_users:
        user_display_name = first_name or username or "ID:"+str(user_id)
        await message_to_reply.answer(f"👤 {user_display_name} (ID: <code>{user_id}</code>)", reply_markup=keyboards.admin_approve_user_kb(user_id, username, first_name),parse_mode=ParseMode.HTML)

async def _send_task_list_page_internal(message_or_call_target: types.Message | types.CallbackQuery, page: int = 0, status_filter: str = "all", user_id_filter: int | None = None):
    actual_status_filter = None if status_filter == "all" else status_filter
    total_tasks = db.count_all_tasks(status_filter=actual_status_filter,user_id_filter=user_id_filter)
    total_pages = math.ceil(total_tasks / TASKS_PER_PAGE)
    if page < 0: page = 0
    if page >= total_pages and total_pages > 0: page = total_pages -1
    current_page_display = page + 1
    offset = page * TASKS_PER_PAGE
    tasks_on_page = db.get_all_tasks(limit=TASKS_PER_PAGE,offset=offset,status_filter=actual_status_filter,user_id_filter=user_id_filter)
    filter_display_name = "Все"
    for dn, code in keyboards.TASK_STATUSES_FOR_FILTER.items():
        if code == status_filter: filter_display_name = dn; break
    header_text = messages.ADMIN_TASK_LIST_HEADER
    if user_id_filter:
        user_info_for_header = db.get_user(user_id_filter)
        user_display_for_header = f" (для ID: {user_id_filter} - {hd.quote(user_info_for_header[2] or user_info_for_header[1] or '')})" if user_info_for_header else f" (для ID: {user_id_filter})"
        header_text = f"📑 <b>Задачи пользователя{user_display_for_header}</b> (Стр. {current_page_display}/{total_pages if total_pages > 0 else 1})\nФильтр: <i>{filter_display_name}</i>\n\n"
    else:
        header_text = messages.ADMIN_TASK_LIST_HEADER.format(current_page=current_page_display, total_pages=total_pages if total_pages > 0 else 1, filter_display_name=filter_display_name)
    response_text = header_text
    if not tasks_on_page: response_text += messages.ADMIN_TASK_LIST_EMPTY
    else:
        for tid,tuid,un,fn,st,ca in tasks_on_page:
            ud=fn or un or "N/A"; response_text += messages.ADMIN_TASK_LIST_ITEM.format(task_id=tid,user_display=hd.quote(ud),user_id=tuid,status=hd.quote(st),created_at=ca)
    pagination_callback_data_prefix = f"tasklist_user_{user_id_filter}_filter_{status_filter}" if user_id_filter else f"tasklist_filter_{status_filter}"
    reply_markup = InlineKeyboardMarkup(row_width=3)
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f"{pagination_callback_data_prefix}_page_{page - 1}"))
    if total_pages > 0 : nav_buttons.append(InlineKeyboardButton(f"{current_page_display}/{total_pages}", callback_data=f"{pagination_callback_data_prefix}_page_{page}"))
    if page < total_pages - 1: nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f"{pagination_callback_data_prefix}_page_{page + 1}"))
    if nav_buttons: reply_markup.row(*nav_buttons)
    if not user_id_filter: reply_markup.add(InlineKeyboardButton("⚙️ Фильтры статусов", callback_data="tasklist_show_filters"))
    if isinstance(message_or_call_target,types.Message): await message_or_call_target.answer(response_text,parse_mode=ParseMode.HTML,reply_markup=reply_markup)
    elif isinstance(message_or_call_target,types.CallbackQuery):
        try:
            if message_or_call_target.message.text!=response_text or message_or_call_target.message.reply_markup!=reply_markup: await message_or_call_target.message.edit_text(response_text,parse_mode=ParseMode.HTML,reply_markup=reply_markup)
            await message_or_call_target.answer()
        except Exception: await message_or_call_target.answer()

async def _send_unread_feedback(message_to_reply: types.Message):
    unread_feedback = db.get_unread_feedback(limit=5)
    if not unread_feedback: await message_to_reply.answer(messages.ADMIN_NO_UNREAD_FEEDBACK); return
    await message_to_reply.answer("📬 <b>Непрочитанные отзывы:</b>", parse_mode=ParseMode.HTML)
    for fb_id, uid, un, fn, msg_txt, rcv_at in unread_feedback:
        ud = fn or un or f"ID:{uid}"; response = f"<b>Отзыв #{fb_id}</b> от {hd.quote(ud)} ({uid}) [{rcv_at}]:\n<pre>{hd.quote(msg_txt)}</pre>"
        await message_to_reply.answer(response, parse_mode=ParseMode.HTML, reply_markup=keyboards.mark_feedback_viewed_kb(fb_id))

async def _send_user_profile(message_or_call: types.Message | types.CallbackQuery, target_user_id: int):
    user_data = db.get_user(target_user_id)
    if not user_data: await message_or_call.answer(messages.ADMIN_USER_NOT_FOUND.format(user_id=target_user_id)); return
    uid,un,fn,st,rl,cr_at = user_data[:6]
    ud=fn or un or "N/A"
    task_count = db.get_user_task_count(uid)
    response = messages.ADMIN_USER_PROFILE_HEADER + messages.ADMIN_USER_PROFILE_INFO.format(user_id=uid,username=un or "N/A",first_name=hd.quote(fn or "N/A"),status=st,role=rl,created_at=cr_at,task_count=task_count)
    kb = keyboards.user_profile_actions_kb(uid,st,rl)
    if isinstance(message_or_call, types.Message): await message_or_call.answer(response, parse_mode=ParseMode.HTML, reply_markup=kb)
    elif isinstance(message_or_call, types.CallbackQuery):
        try: await message_or_call.message.edit_text(response,parse_mode=ParseMode.HTML,reply_markup=kb)
        except: await message_or_call.bot.send_message(message_or_call.from_user.id, response, parse_mode=ParseMode.HTML, reply_markup=kb)
        await message_or_call.answer()

@admin_only
async def cmd_admin_panel(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs): await message.answer(messages.ADMIN_PANEL_MESSAGE, reply_markup=keyboards.admin_panel_kb(), parse_mode=ParseMode.HTML)
@admin_only
async def callback_admin_panel_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    action = call.data.split("admin_panel_")[-1]
    target_message_for_reply = call.message
    try: await call.message.delete()
    except: pass
    if action == "pending_users": await _send_pending_users_list(target_message_for_reply)
    elif action == "list_tasks": await _send_task_list_page_internal(target_message_for_reply)
    elif action == "view_feedback": await _send_unread_feedback(target_message_for_reply)
    elif action == "list_all_users_page_0": await _send_user_list_page(target_message_for_reply, 0, None, None)
    elif action == "broadcast_info": await target_message_for_reply.answer(messages.BROADCAST_INFO_ADMIN, parse_mode=ParseMode.HTML, reply_markup=keyboards.main_menu_kb(is_admin=True))
    else: await target_message_for_reply.answer("Неизвестное действие админ-панели.", reply_markup=keyboards.main_menu_kb(is_admin=True))
    await call.answer()

@admin_only
async def cmd_list_pending(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs): await _send_pending_users_list(message)
@admin_only
async def callback_approve_user(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    try: user_to_approve_id = int(call.data.split("_")[-1])
    except: await call.answer(messages.ADMIN_APPROVE_ERROR, show_alert=True); return
    user_info = db.get_user(user_to_approve_id)
    if not user_info: await call.message.edit_text(messages.ADMIN_USER_NOT_FOUND.format(user_id=user_to_approve_id)); await call.answer(); return
    _,un,fn,cs,_=user_info[:5]; ud=fn or un or "N/A"
    if cs=='active': await call.message.edit_text(messages.ADMIN_USER_ALREADY_ACTIVE.format(user_id=user_to_approve_id,user_display=ud)); await call.answer(); return
    db.update_user_status_role(user_to_approve_id,status='active')
    await call.message.edit_text(messages.ADMIN_USER_APPROVED.format(user_id=user_to_approve_id,user_display=ud)); await call.answer("Пользователь активирован!")
    try: await call.bot.send_message(user_to_approve_id,messages.ADMIN_NOTIFY_USER_ACTIVATED,parse_mode=ParseMode.HTML)
    except: await call.message.answer(messages.ADMIN_NOTIFY_USER_FAILED)

@admin_only
async def cmd_task_info(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args=message.get_args();
    if not args: await message.reply("Пожалуйста, укажите ID задачи: /task_info <ID>"); return
    try: task_id_from_arg = int(args)
    except ValueError: await message.reply("ID задачи должен быть числом."); return
    task_details = db.get_full_task_details(task_id_from_arg)
    if not task_details: await message.reply(f"Задача с ID {task_id_from_arg} не найдена."); return
    (t_id,uid,un,fn,gf,wf,st,ca,rm)=task_details; ud=fn or un or "N/A"; gfb=os.path.basename(gf) if gf and isinstance(gf,str) else "N/A"; wfb=os.path.basename(wf) if wf and isinstance(wf,str) else "N/A"; gfe=os.path.exists(gf) if gf else False; wfe=os.path.exists(wf) if wf else False
    resp=(f"<b><u>Информация по Задаче #{t_id}</u></b>\n<b>Пользователь:</b> {hd.quote(ud)} (ID: {uid})\n<b>Создана:</b> {ca}\n<b>Статус:</b> {hd.quote(st)}\n<b>Файл групп:</b> <code>{hd.quote(gfb)}</code> ({gfe})\n<b>Файл дней:</b> <code>{hd.quote(wfb)}</code> ({wfe})\n<b>Результат:</b> {hd.quote(rm) if rm else 'N/A'}\n")
    kb=InlineKeyboardMarkup(row_width=2); odf=file_manager.get_output_dir_for_task(uid,t_id)
    if gf and gfe: kb.add(InlineKeyboardButton("📄 Группы",callback_data=f"admin_getfile_groups_{t_id}"))
    if wf and wfe: kb.add(InlineKeyboardButton("🗓️ Дни",callback_data=f"admin_getfile_weekdays_{t_id}"))
    if os.path.exists(odf) and any(f.endswith(('.xlsx','.xls')) for f in os.listdir(odf)): kb.add(InlineKeyboardButton("📊 Результаты",callback_data=f"admin_getresults_{t_id}"))
    kb.add(InlineKeyboardButton("🗑️ Удалить эту задачу", callback_data=f"admin_init_delete_task_{t_id}")) # Кнопка удаления
    await message.answer(resp,parse_mode=ParseMode.HTML,reply_markup=kb if kb.inline_keyboard else None)

async def send_file_to_admin(call:types.CallbackQuery,fp:str|None,pfx:str=""):
    if fp and os.path.exists(fp):
        try: await call.bot.send_document(call.from_user.id,InputFile(fp,filename=f"{pfx}{os.path.basename(fp)}")); await call.answer()
        except Exception as e: await call.answer(f"Ошибка: {str(e)[:180]}",show_alert=True)
    else: await call.answer("Файл не найден.",show_alert=True)
@admin_only
async def callback_admin_get_file(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    try:pts=call.data.split("_");fk=pts[2];tid=int(pts[3])
    except: await call.answer("Ошибка данных.",show_alert=True);return
    td=db.get_full_task_details(tid)
    if not td: await call.answer("Задача не найдена.",show_alert=True);return
    path=None;pfx=f"task{tid}_"
    if fk=="groups":path=td[4];pfx+="groups_"
    elif fk=="weekdays":path=td[5];pfx+="weekdays_"
    await send_file_to_admin(call,path,pfx)
@admin_only
async def callback_admin_get_results(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    try:tid=int(call.data.split("_")[-1])
    except: await call.answer("Ошибка ID.",show_alert=True);return
    td=db.get_full_task_details(tid)
    if not td: await call.answer("Задача не найдена.",show_alert=True);return
    uid=td[1];odf=file_manager.get_output_dir_for_task(uid,tid);gfp=[]
    if os.path.exists(odf):
        for fn in sorted(os.listdir(odf)):
            if fn.endswith(('.xlsx','.xls')):gfp.append(os.path.join(odf,fn))
    if gfp:
        media=MediaGroup();sc=0;tf=len(gfp)
        for i,fp in enumerate(gfp):
            media.attach_document(InputFile(fp,filename=f"task{tid}_{os.path.basename(fp)}"))
            if len(media.media)==10 or(i==tf-1 and media.media):
                try:await call.bot.send_media_group(call.from_user.id,media)
                except Exception as e:await call.message.answer(f"Ошибка группы: {e}"); break
                media=MediaGroup()
            sc+=1
        if sc>0:await call.answer(f"Отправлено {sc} файлов.")
        else:await call.answer("Не удалось отправить.",show_alert=True)
    else:await call.answer("Результаты не найдены.",show_alert=True)
@admin_only
async def cmd_list_tasks(message:types.Message,command:BotCommand=None,state:FSMContext=None,**kwargs):await _send_task_list_page_internal(message)
@admin_only
async def callback_task_list_action(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    dp=call.data.split("_");act=dp[1]
    user_id_filter_for_tasks = None
    status_filter_for_tasks = "all"
    page_num = 0
    if act=="show"and dp[2]=="filters":await call.message.edit_text(messages.ADMIN_TASK_FILTER_PROMPT,reply_markup=keyboards.tasks_filter_kb()); await call.answer(); return
    if act == "filter":
        if len(dp) >=3: status_filter_for_tasks = dp[2]
        if len(dp) >=5 and dp[3] == "page":
            try: page_num = int(dp[4])
            except ValueError: page_num = 0
    elif act == "user":
        if len(dp) >=3 and dp[2].isdigit(): user_id_filter_for_tasks = int(dp[2])
        if len(dp) >=5 and dp[3] == "filter": status_filter_for_tasks = dp[4]
        if len(dp) >=7 and dp[5] == "page":
            try: page_num = int(dp[6])
            except ValueError: page_num = 0
    else: await call.answer("Неизвестное действие для tasklist.",show_alert=True); return
    await _send_task_list_page_internal(call, page=page_num, status_filter=status_filter_for_tasks, user_id_filter=user_id_filter_for_tasks)

@admin_only
async def cmd_force_cancel_task(message:types.Message,command:BotCommand=None,state:FSMContext=None,**kwargs):
    args=message.text.split(maxsplit=2)
    if len(args)<2:await message.reply(messages.ADMIN_FORCE_CANCEL_USAGE,parse_mode=ParseMode.HTML);return
    try:tid=int(args[1])
    except ValueError:await message.reply("ID задачи число.");return
    reason=args[2]if len(args)>2 else"Причина не указана";ns="failed_by_admin"
    td=db.get_full_task_details(tid)
    if not td:await message.reply(messages.TASK_NOT_FOUND_ERROR.format(task_id=tid));return
    cs=td[6]
    if cs in['completed','completed_with_warnings','failed','cancelled','failed_by_admin']:await message.reply(messages.ADMIN_TASK_NOT_CANCELLABLE_STATUS.format(task_id=tid,current_status=cs));return
    if db.force_update_task_status(tid,ns,admin_reason=reason):
        await message.reply(messages.ADMIN_TASK_STATUS_UPDATED.format(task_id=tid,new_status=ns),parse_mode=ParseMode.HTML)
        owner_id=td[1]
        if owner_id:
            try:await message.bot.send_message(owner_id,f"⚠️ Администратор изменил статус Задачи #{tid} на '{ns}'.\nПричина: {hd.quote(reason)}",parse_mode=ParseMode.HTML)
            except:pass
    else:await message.reply(messages.ADMIN_TASK_STATUS_UPDATE_FAILED.format(task_id=tid))

@admin_only
async def callback_admin_init_delete_task(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    try: task_id = int(call.data.split("admin_init_delete_task_")[-1])
    except: await call.answer("Ошибка ID.",show_alert=True);return
    task_details = db.get_full_task_details(task_id)
    if not task_details: await call.message.edit_text(messages.TASK_NOT_FOUND_ERROR.format(task_id=task_id)); await call.answer(); return
    await call.message.answer(messages.ADMIN_DELETE_TASK_CONFIRM.format(task_id=task_id),parse_mode=ParseMode.HTML,reply_markup=keyboards.confirm_delete_task_kb(task_id))
    await call.answer()

@admin_only
async def callback_confirm_delete_task(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    try:tid=int(call.data.split("admin_confirm_delete_task_")[-1])
    except:await call.answer("Ошибка ID.",show_alert=True);return
    td=db.get_full_task_details(tid)
    if not td:await call.message.edit_text(messages.TASK_NOT_FOUND_ERROR.format(task_id=tid));await call.answer();return
    uid=td[1];file_manager.cleanup_task_files(uid,tid)
    if db.delete_task_from_db(tid):await call.message.edit_text(messages.ADMIN_TASK_DELETED_SUCCESS.format(task_id=tid));await call.answer("Задача удалена.")
    else:await call.message.edit_text(messages.ADMIN_TASK_DELETE_FAILED.format(task_id=tid));await call.answer("Ошибка удаления из БД.",show_alert=True)
@admin_only
async def callback_cancel_delete_task(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    try:tid=int(call.data.split("admin_cancel_delete_task_")[-1]);await call.message.edit_text(f"Удаление Задачи #{tid} отменено.")
    except:await call.message.edit_text("Удаление отменено.")
    await call.answer("Удаление отменено.")
@admin_only
async def cmd_broadcast(message:types.Message,command:BotCommand=None,state:FSMContext=None,**kwargs):
    bt=message.get_args()
    if not bt:await message.reply("Укажите текст: /broadcast <текст>");return
    aui=db.get_active_user_ids()
    if not aui:await message.reply("Нет активных пользователей.");return
    await message.reply(messages.BROADCAST_STARTED.format(count=len(aui)))
    sc=0;fc=0
    for uid in aui:
        try:await message.bot.send_message(uid,bt,parse_mode=ParseMode.HTML);sc+=1
        except:fc+=1
        await asyncio.sleep(0.1)
    await message.answer(messages.BROADCAST_STATS.format(sent_count=sc,failed_count=fc))
@admin_only
async def cmd_view_feedback(message:types.Message,command:BotCommand=None,state:FSMContext=None,**kwargs): await _send_unread_feedback(message)
@admin_only
async def callback_mark_feedback_viewed(call:types.CallbackQuery,state:FSMContext=None,**kwargs):
    try:fid=int(call.data.split("_")[-1])
    except:await call.answer("Ошибка ID отзыва.",show_alert=True);return
    if db.mark_feedback_as_viewed(fid):
        await call.message.edit_text(call.message.text+f"\n<i>(Отзыв #{fid} помечен как прочитанный)</i>",parse_mode=ParseMode.HTML,reply_markup=None)
        await call.answer(f"Отзыв #{fid} прочитан.")
    else:await call.answer(messages.ADMIN_FEEDBACK_VIEW_ERROR.format(feedback_id=fid),show_alert=True)

@admin_only
async def cmd_list_all_users(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs): await _send_user_list_page(message, 0, None, None)
@admin_only
async def cmd_user_profile(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.get_args()
    if not args: await message.reply("Укажите ID пользователя: /user_profile <ID>"); return
    try: target_user_id = int(args)
    except ValueError: await message.reply("ID пользователя должен быть числом."); return
    await _send_user_profile(message, target_user_id)
@admin_only
async def callback_user_list_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    data = call.data.split("_")
    if data[1]=="show"and data[2]=="filters":
        sf=data[4]if len(data)>4 and data[3]=="status"else None;rf=data[6]if len(data)>6 and data[5]=="role"else None
        await call.message.edit_text(messages.ADMIN_USER_FILTER_PROMPT,reply_markup=keyboards.user_list_filters_kb(sf,rf));await call.answer();return
    if data[1]=="filter"and len(data)>=8 and data[2]=="status" and data[4]=="role" and data[6]=="page":
        sf=data[3]if data[3]!="all_status"else None;rf=data[5]if data[5]!="all_role"else None;page=int(data[7])
        await _send_user_list_page(call,page,sf,rf)
    await call.answer()
@admin_only
async def callback_user_profile_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    parts=call.data.split("_"); action=parts[2]; target_user_id=int(parts[3])
    user_info=db.get_user(target_user_id);
    if not user_info: await call.answer("Пользователь не найден.", show_alert=True); return
    ud=user_info[2]or user_info[1]or f"ID:{target_user_id}"
    if action=="ban":db.update_user_status_role(target_user_id,status="banned");await call.message.edit_text(messages.ADMIN_USER_BANNED_SUCCESS.format(user_display=ud,user_id=target_user_id));await call.answer("Забанен")
    elif action=="unban":db.update_user_status_role(target_user_id,status="active");await call.message.edit_text(messages.ADMIN_USER_UNBANNED_SUCCESS.format(user_display=ud,user_id=target_user_id));await call.answer("Разбанен")
    elif action=="setadmin":db.update_user_status_role(target_user_id,role="admin");await call.message.edit_text(messages.ADMIN_USER_ROLE_UPDATED.format(user_display=ud,user_id=target_user_id,new_role="admin"));await call.answer("Сделан админом")
    elif action=="setuser":db.update_user_status_role(target_user_id,role="user");await call.message.edit_text(messages.ADMIN_USER_ROLE_UPDATED.format(user_display=ud,user_id=target_user_id,new_role="user"));await call.answer("Сделан юзером")
    elif action=="viewtasks":
        await call.message.delete()
        await _send_task_list_page_internal(call.message, page=0, status_filter="all", user_id_filter=target_user_id)
        await call.answer("Задачи пользователя"); return
    elif action=="confirmdelete":await call.message.edit_text(messages.ADMIN_CONFIRM_USER_DATA_DELETE.format(user_display=ud,user_id=target_user_id),parse_mode=ParseMode.HTML,reply_markup=keyboards.confirm_user_data_delete_kb(target_user_id)); await call.answer(); return
    elif action=="dodelete":
        file_manager.cleanup_task_files(target_user_id,"all_tasks_of_user")
        if db.delete_user_and_tasks(target_user_id):await call.message.edit_text(messages.ADMIN_USER_DATA_DELETED_SUCCESS.format(user_display=ud,user_id=target_user_id));await call.answer("Пользователь удален")
        else:await call.message.edit_text(messages.ADMIN_USER_DATA_DELETE_FAILED.format(user_display=ud,user_id=target_user_id));await call.answer("Ошибка удаления",show_alert=True)
        return
    elif action=="canceldelete":await call.message.edit_text(f"Удаление данных пользователя {ud} (ID:{target_user_id}) отменено.");await call.answer("Отменено"); return
    await _send_user_profile(call, target_user_id)

def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_admin_panel, Command(commands=['admin']))
    dp.register_callback_query_handler(callback_admin_panel_actions, Text(startswith="admin_panel_"))
    dp.register_message_handler(cmd_list_pending, Command(commands=['pending_users']))
    dp.register_callback_query_handler(callback_approve_user, Text(startswith='admin_approve_'))
    dp.register_message_handler(cmd_task_info, Command(commands=['task_info']))
    dp.register_callback_query_handler(callback_admin_get_file, Text(startswith="admin_getfile_"))
    dp.register_callback_query_handler(callback_admin_get_results, Text(startswith="admin_getresults_"))
    dp.register_message_handler(cmd_list_tasks, Command(commands=['list_tasks']))
    dp.register_callback_query_handler(callback_task_list_action, Text(startswith="tasklist_"))
    dp.register_message_handler(cmd_force_cancel_task, Command(commands=['force_cancel_task']))
    # dp.register_message_handler(cmd_delete_task_data, Command(commands=['delete_task_data'])) # Удалено, теперь через /task_info
    dp.register_callback_query_handler(callback_admin_init_delete_task, Text(startswith="admin_init_delete_task_")) # Новый для кнопки из task_info
    dp.register_callback_query_handler(callback_confirm_delete_task, Text(startswith="admin_confirm_delete_task_"))
    dp.register_callback_query_handler(callback_cancel_delete_task, Text(startswith="admin_cancel_delete_task_"))
    dp.register_message_handler(cmd_broadcast, Command(commands=['broadcast']))
    dp.register_message_handler(cmd_view_feedback, Command(commands=['view_feedback']))
    dp.register_callback_query_handler(callback_mark_feedback_viewed, Text(startswith="admin_mark_fb_viewed_"))
    dp.register_message_handler(cmd_list_all_users, Command(commands=['list_all_users']))
    dp.register_message_handler(cmd_user_profile, Command(commands=['user_profile']))
    dp.register_callback_query_handler(callback_user_list_actions, Text(startswith="admin_userlist_"))
    dp.register_callback_query_handler(callback_user_profile_actions, Text(startswith="admin_useract_"))