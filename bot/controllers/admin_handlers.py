from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import InputFile, MediaGroup, ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.dispatcher import FSMContext
from aiogram.utils.markdown import html_decoration as hd
import os
import math
import asyncio
import re
from datetime import datetime

from bot.models import db
from bot.views import messages, keyboards
from bot.config import ADMIN_IDS
from bot.utils import file_manager

USERS_PER_PAGE = 10
TASKS_PER_PAGE = 5

CB_PREFIX_ADMIN_PANEL = keyboards.CB_PREFIX_ADMIN_PANEL
CB_PREFIX_USER_LIST = keyboards.CB_PREFIX_USER_LIST
CB_PREFIX_USER_ACTION = keyboards.CB_PREFIX_USER_ACTION
CB_PREFIX_TASK_LIST = keyboards.CB_PREFIX_TASK_LIST
CB_PREFIX_TASK_ACTION = keyboards.CB_PREFIX_TASK_ACTION
CB_PREFIX_FEEDBACK = keyboards.CB_PREFIX_FEEDBACK
CB_PREFIX_NOOP = keyboards.CB_PREFIX_NOOP


def admin_only(func):
    async def wrapper(message_or_call: types.Message | types.CallbackQuery, *args, **kwargs):
        user_id = message_or_call.from_user.id
        if user_id not in ADMIN_IDS:
            if isinstance(message_or_call, types.Message):
                await message_or_call.answer("❌ У вас нет прав.")
            elif isinstance(message_or_call, types.CallbackQuery):
                await message_or_call.answer("У вас нет прав.", show_alert=True)
            return
        return await func(message_or_call, *args, **kwargs)

    return wrapper


async def _send_user_list_page_internal(message_or_call: types.Message | types.CallbackQuery, page: int = 0,
                                        status_filter: str = "all_status", role_filter: str = "all_role"):
    print(
        f"DEBUG: _send_user_list_page_internal called with page={page}, status_filter={status_filter}, role_filter={role_filter}")
    actual_status_filter = None if status_filter == "all_status" else status_filter
    actual_role_filter = None if role_filter == "all_role" else role_filter
    total_users = db.count_all_users(role_filter=actual_role_filter, status_filter=actual_status_filter)
    total_pages = math.ceil(total_users / USERS_PER_PAGE)
    if page < 0: page = 0
    if total_pages == 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    current_page_display = page + 1 if total_users > 0 else 1
    total_pages_display = total_pages if total_pages > 0 else 1
    offset = page * USERS_PER_PAGE
    users_on_page = db.get_all_users_paginated(limit=USERS_PER_PAGE, offset=offset, role_filter=actual_role_filter,
                                               status_filter=actual_status_filter)
    sf_display = next((k for k, v in keyboards.USER_STATUSES_FOR_FILTER.items() if v == status_filter), "Все статусы")
    rf_display = next((k for k, v in keyboards.USER_ROLES_FOR_FILTER.items() if v == role_filter), "Все роли")
    header_text = messages.ADMIN_USER_LIST_HEADER.format(current_page=current_page_display,
                                                         total_pages=total_pages_display,
                                                         status_filter_display=hd.quote(sf_display),
                                                         role_filter_display=hd.quote(rf_display))
    response_text = header_text
    if not users_on_page:
        response_text += messages.ADMIN_USER_LIST_EMPTY
    else:
        for uid_db, un_db, fn_db, st_db, rl_db, cr_at_str_db in users_on_page:
            user_display = hd.quote(fn_db or un_db or f"ID:{uid_db}")
            response_text += messages.ADMIN_USER_LIST_ITEM.format(user_display=user_display, user_id=uid_db,
                                                                  status=hd.quote(st_db), role=hd.quote(rl_db),
                                                                  created_at=cr_at_str_db or "N/A")
    kb = keyboards.user_list_pagination_kb(current_page=page, total_pages=total_pages_display,
                                           status_filter=status_filter, role_filter=role_filter)
    kb.add(InlineKeyboardButton("⚙️ Фильтры пользователей",
                                callback_data=f"{CB_PREFIX_USER_LIST}:filters:sf_{status_filter}:rf_{role_filter}:uid_all"))
    kb.add(InlineKeyboardButton("🔙 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    target_message = message_or_call if isinstance(message_or_call, types.Message) else message_or_call.message
    try:
        current_text = getattr(target_message, 'text', None);
        current_markup = getattr(target_message, 'reply_markup', None)
        if current_text != response_text or current_markup != kb:
            await target_message.edit_text(response_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.answer()
    except Exception as e:
        print(f"ERROR in _send_user_list_page_internal editing/sending message: {e}")
        if isinstance(message_or_call, types.Message):
            await message_or_call.answer(response_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.answer("Не удалось обновить список.", show_alert=True)


async def _send_pending_users_list(message_to_reply: types.Message):
    pending_users = db.get_pending_users()
    if not pending_users: await message_to_reply.answer(messages.ADMIN_NO_PENDING_USERS); return
    await message_to_reply.answer(messages.ADMIN_PENDING_USERS_LIST_HEADER + "\n")
    for user_id, username, first_name in pending_users:
        await message_to_reply.answer(
            f"👤 {hd.quote(first_name or username or f'ID:{user_id}')} (ID: <code>{user_id}</code>)",
            reply_markup=keyboards.admin_approve_user_kb(user_id, username, first_name), parse_mode=ParseMode.HTML)


async def _send_task_list_page_internal(message_or_call_target: types.Message | types.CallbackQuery, page: int = 0,
                                        status_filter: str = "all",
                                        user_id_filter_str: str = "all"):  # user_id_filter теперь строка
    print(
        f"DEBUG: _send_task_list_page_internal called with page={page}, status_filter={status_filter}, user_id_filter_str={user_id_filter_str}")
    actual_status_filter = None if status_filter == "all" else status_filter
    actual_user_id_filter = None if user_id_filter_str == "all" else int(user_id_filter_str)
    total_tasks = db.count_all_tasks(status_filter=actual_status_filter, user_id_filter=actual_user_id_filter)
    total_pages = math.ceil(total_tasks / TASKS_PER_PAGE)
    if page < 0: page = 0
    if total_pages == 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1
    current_page_display = page + 1 if total_tasks > 0 else 1
    total_pages_display = total_pages if total_pages > 0 else 1
    offset = page * TASKS_PER_PAGE
    tasks_on_page = db.get_all_tasks(limit=TASKS_PER_PAGE, offset=offset, status_filter=actual_status_filter,
                                     user_id_filter=actual_user_id_filter)
    filter_display_name = "Все"
    for dn, code in keyboards.TASK_STATUSES_FOR_FILTER.items():
        if code == status_filter: filter_display_name = dn; break
    header_text = ""
    if actual_user_id_filter:
        user_info_for_header = db.get_user(actual_user_id_filter)
        user_name_for_header = hd.quote(user_info_for_header[2] or user_info_for_header[1] or str(
            actual_user_id_filter)) if user_info_for_header else str(actual_user_id_filter)
        header_text = f"📑 <b>Задачи пользователя {user_name_for_header}</b> (Стр. {current_page_display}/{total_pages_display})\nФильтр: <i>{hd.quote(filter_display_name)}</i>\n\n"
    else:
        header_text = messages.ADMIN_TASK_LIST_HEADER.format(current_page=current_page_display,
                                                             total_pages=total_pages_display,
                                                             filter_display_name=hd.quote(filter_display_name))
    response_text = header_text
    if not tasks_on_page:
        response_text += messages.ADMIN_TASK_LIST_EMPTY
    else:
        for tid, tuid, un, fn, st, ca_str in tasks_on_page:
            ud = hd.quote(fn or un or "N/A");
            response_text += messages.ADMIN_TASK_LIST_ITEM.format(task_id=tid, user_display=ud, user_id=tuid,
                                                                  status=hd.quote(st), created_at=ca_str or "N/A")
    kb = keyboards.tasks_pagination_kb(current_page=page, total_pages=total_pages_display, current_filter=status_filter,
                                       user_id_filter=actual_user_id_filter)
    kb.add(InlineKeyboardButton("⚙️ Фильтры статусов задач",
                                callback_data=f"{CB_PREFIX_TASK_LIST}:filters:sf_{status_filter}:uid_{user_id_filter_str}"))
    kb.add(InlineKeyboardButton("🔙 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    target_message = message_or_call_target if isinstance(message_or_call_target,
                                                          types.Message) else message_or_call_target.message
    try:
        current_text = getattr(target_message, 'text', None);
        current_markup = getattr(target_message, 'reply_markup', None)
        if current_text != response_text or current_markup != kb:
            await target_message.edit_text(response_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call_target, types.CallbackQuery):
            await message_or_call_target.answer()
    except Exception as e:
        print(f"ERROR in _send_task_list_page_internal editing/sending message: {e}")
        if isinstance(message_or_call_target, types.Message):
            await message_or_call_target.answer(response_text, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call_target, types.CallbackQuery):
            await message_or_call_target.answer("Не удалось обновить список задач.", show_alert=True)


async def _send_unread_feedback(message_to_reply: types.Message):
    unread_feedback = db.get_unread_feedback(limit=5)
    if not unread_feedback: await message_to_reply.answer(messages.ADMIN_NO_UNREAD_FEEDBACK); return
    await message_to_reply.answer("📬 <b>Непрочитанные отзывы:</b>", parse_mode=ParseMode.HTML)
    for fb_id, uid, un, fn, msg_txt, rcv_at_str in unread_feedback:
        ud = hd.quote(fn or un or f"ID:{uid}");
        response = f"<b>Отзыв #{fb_id}</b> от {ud} (ID:<code>{uid}</code>) [{rcv_at_str or 'N/A'}]:\n<pre>{hd.quote(msg_txt)}</pre>"
        await message_to_reply.answer(response, parse_mode=ParseMode.HTML,
                                      reply_markup=keyboards.mark_feedback_viewed_kb(fb_id))


async def _send_user_profile(message_or_call: types.Message | types.CallbackQuery, target_user_id: int,
                             from_page_info: dict | None = None):
    print(f"DEBUG: _send_user_profile for user {target_user_id}, from_page_info: {from_page_info}")
    user_data = db.get_user(target_user_id)
    if not user_data:
        msg_target = message_or_call if isinstance(message_or_call, types.Message) else message_or_call.message
        await msg_target.answer(messages.ADMIN_USER_NOT_FOUND.format(user_id=target_user_id))
        if isinstance(message_or_call, types.CallbackQuery): await message_or_call.answer()
        return
    uid, un, fn, st, rl, cr_at_str = user_data
    task_count = db.get_user_task_count(uid)
    response = messages.ADMIN_USER_PROFILE_HEADER + messages.ADMIN_USER_PROFILE_INFO.format(user_id=uid,
                                                                                            username=hd.quote(
                                                                                                un or "N/A"),
                                                                                            first_name=hd.quote(
                                                                                                fn or "N/A"),
                                                                                            status=hd.quote(st),
                                                                                            role=hd.quote(rl),
                                                                                            created_at=cr_at_str or "N/A",
                                                                                            task_count=task_count)
    page = from_page_info.get("page", 0) if from_page_info else 0
    status_f = from_page_info.get("status_filter", "all_status") if from_page_info else "all_status"
    role_f = from_page_info.get("role_filter", "all_role") if from_page_info else "all_role"
    kb = keyboards.user_profile_actions_kb(uid, st, rl, current_page=page, status_filter=status_f, role_filter=role_f)
    target_message = message_or_call if isinstance(message_or_call, types.Message) else message_or_call.message
    try:
        current_text = getattr(target_message, 'text', None);
        current_markup = getattr(target_message, 'reply_markup', None)
        if current_text != response or current_markup != kb:
            await target_message.edit_text(response, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.answer()
    except Exception as e:
        print(f"ERROR in _send_user_profile editing/sending message: {e}")
        if isinstance(message_or_call, types.Message):
            await message_or_call.answer(response, parse_mode=ParseMode.HTML, reply_markup=kb)
        elif isinstance(message_or_call, types.CallbackQuery):
            await message_or_call.bot.send_message(message_or_call.from_user.id, response, parse_mode=ParseMode.HTML,
                                                   reply_markup=kb)
            await message_or_call.answer("Обновлено новым сообщением.")


@admin_only
async def cmd_admin_panel(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    print(f"DEBUG: cmd_admin_panel triggered by {message.from_user.id}")
    await message.answer(messages.ADMIN_PANEL_MESSAGE, reply_markup=keyboards.admin_panel_kb(),
                         parse_mode=ParseMode.HTML)


@admin_only
async def callback_admin_panel_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    action_full = call.data
    print(f"DEBUG: callback_admin_panel_actions received: {action_full}")
    target_message_for_reply = call.message
    try:
        await call.message.delete()
    except:
        pass
    action_parts = action_full.split(":")
    action_prefix = action_parts[0]
    action_command = action_parts[1] if len(action_parts) > 1 else None

    if action_prefix != CB_PREFIX_ADMIN_PANEL:  # Этот хэндлер только для CB_PREFIX_ADMIN_PANEL
        print(f"DEBUG: callback_admin_panel_actions IGNORING {action_full}, not its prefix.")
        await call.answer()  # Просто отвечаем, чтобы убрать часики, но не обрабатываем
        return

    if action_command == "pending":
        print("DEBUG: Matched admin_panel_pending")
        await _send_pending_users_list(target_message_for_reply)
    elif action_command == "feedback":
        print("DEBUG: Matched admin_panel_feedback")
        await _send_unread_feedback(target_message_for_reply)
    elif action_command == "broadcastinfo":
        print("DEBUG: Matched admin_panel_broadcast_info")
        await target_message_for_reply.answer(messages.BROADCAST_INFO_ADMIN, parse_mode=ParseMode.HTML,
                                              reply_markup=keyboards.main_menu_kb(is_admin=True))
    elif action_command == "main":
        print("DEBUG: Matched admin_panel_main (back to panel)")
        await target_message_for_reply.answer(messages.ADMIN_PANEL_MESSAGE, reply_markup=keyboards.admin_panel_kb(),
                                              parse_mode=ParseMode.HTML)
    else:
        print(f"DEBUG: No match in callback_admin_panel_actions for: {action_full}")
        await target_message_for_reply.answer("Неизвестное действие в админ-панели (внутренняя ошибка).")
    await call.answer()


@admin_only
async def cmd_list_pending(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_pending_users_list(message)


@admin_only
async def callback_admin_user_action(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_admin_user_action received: {call.data}")
    # Формат: CB_PREFIX_USER_ACTION : action : user_id [:p_PAGE] [:sf_STATUS] [:rf_ROLE]
    parts = call.data.split(':');
    pref = parts[0];
    action = parts[1];
    target_user_id = int(parts[2])
    page_info_for_return = {"page": 0, "status_filter": "all_status", "role_filter": "all_role"}
    param_idx = 3
    while param_idx < len(parts):
        param_type = parts[param_idx][:2]  # p, sf, rf
        param_val = parts[param_idx][2:]
        if param_type == "p" and param_val.isdigit():
            page_info_for_return["page"] = int(param_val)
        elif param_type == "sf":
            page_info_for_return["status_filter"] = param_val
        elif param_type == "rf":
            page_info_for_return["role_filter"] = param_val
        param_idx += 1

    user_info = db.get_user(target_user_id)
    if not user_info: await call.answer("Пользователь не найден.", show_alert=True); return
    uid_db, un_db, fn_db, status_db, role_db, _ = user_info;
    user_display_name = hd.quote(fn_db or un_db or f"ID:{target_user_id}")
    action_performed_and_profile_refresh_needed = True
    if action == "approve":
        if status_db == 'active': await call.message.edit_text(
            messages.ADMIN_USER_ALREADY_ACTIVE.format(user_id=target_user_id,
                                                      user_display=user_display_name)); await call.answer(); return
        db.update_user_status_role(target_user_id, status='active')
        await call.message.edit_text(
            messages.ADMIN_USER_APPROVED.format(user_id=target_user_id, user_display=user_display_name));
        await call.answer("Пользователь активирован!")
        try:
            await call.bot.send_message(target_user_id, messages.ADMIN_NOTIFY_USER_ACTIVATED, parse_mode=ParseMode.HTML)
        except:
            await call.message.answer(messages.ADMIN_NOTIFY_USER_FAILED)
        return
    if action == "ban":
        db.update_user_status_role(target_user_id, status="banned"); await call.answer("Пользователь забанен.")
    elif action == "unban":
        db.update_user_status_role(target_user_id, status="active"); await call.answer("Пользователь разбанен.")
    elif action == "setadmin" and target_user_id not in ADMIN_IDS:
        db.update_user_status_role(target_user_id, role="admin"); await call.answer("Назначен администратором.")
    elif action == "setuser" and target_user_id not in ADMIN_IDS:
        db.update_user_status_role(target_user_id, role="user"); await call.answer("Назначен пользователем.")
    elif action == "viewtasks":
        try:
            await call.message.delete()
        except:
            pass
        await _send_task_list_page_internal(call.message, page=0, status_filter="all",
                                            user_id_filter_str=str(target_user_id));
        await call.answer("Просмотр задач пользователя");
        return
    elif action == "confirmdelete" and target_user_id not in ADMIN_IDS:
        await call.message.edit_text(
            messages.ADMIN_CONFIRM_USER_DATA_DELETE.format(user_display=user_display_name, user_id=target_user_id),
            parse_mode=ParseMode.HTML, reply_markup=keyboards.confirm_user_data_delete_kb(target_user_id));
        await call.answer();
        return
    elif action == "dodelete" and target_user_id not in ADMIN_IDS:
        file_manager.cleanup_task_files(target_user_id, "all_tasks_of_user")
        if db.delete_user_and_tasks(target_user_id):
            await call.message.edit_text(messages.ADMIN_USER_DATA_DELETED_SUCCESS.format(user_display=user_display_name,
                                                                                         user_id=target_user_id)); await call.answer(
                "Данные пользователя удалены.")
        else:
            await call.message.edit_text(messages.ADMIN_USER_DATA_DELETE_FAILED.format(user_display=user_display_name,
                                                                                       user_id=target_user_id)); await call.answer(
                "Ошибка удаления данных.", show_alert=True)
        return
    elif action == "canceldelete":
        await call.answer("Удаление отменено.")  # Профиль обновится
    elif action == "showprofile":
        await call.answer()  # Профиль обновится
    else:
        await call.answer(f"Неизвестное действие: {action}",
                          show_alert=True); action_performed_and_profile_refresh_needed = False
    if action_performed_and_profile_refresh_needed: await _send_user_profile(call, target_user_id,
                                                                             from_page_info=page_info_for_return)


@admin_only
async def cmd_task_info(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.get_args();
    if not args: await message.reply("Укажите ID задачи: /task_info <ID>"); return
    try:
        task_id_from_arg = int(args)
    except ValueError:
        await message.reply("ID задачи должен быть числом."); return
    task_details = db.get_full_task_details(task_id_from_arg)
    if not task_details: await message.reply(f"Задача с ID {task_id_from_arg} не найдена."); return
    t_id, uid, un, fn, gf, wf, st, ca_str, rm = task_details
    ud = hd.quote(fn or un or "N/A")
    gfb = os.path.basename(gf) if gf and isinstance(gf, str) else "N/A";
    wfb = os.path.basename(wf) if wf and isinstance(wf, str) else "N/A"
    gfe = os.path.exists(gf) if gf and isinstance(gf, str) else False;
    wfe = os.path.exists(wf) if wf and isinstance(wf, str) else False
    resp = (
        f"<b><u>Информация по Задаче #{t_id}</u></b>\n<b>Пользователь:</b> {ud} (ID: <code>{uid}</code>)\n<b>Создана:</b> {ca_str or 'N/A'}\n<b>Статус:</b> {hd.quote(st)}\n<b>Файл групп:</b> <code>{hd.quote(gfb)}</code> ({'✅' if gfe else '❌'})\n<b>Файл дней:</b> <code>{hd.quote(wfb)}</code> ({'✅' if wfe else '❌'})\n<b>Результат:</b> {hd.quote(rm) if rm else 'N/A'}\n")
    results_exist_for_kb = os.path.exists(file_manager.get_output_dir_for_task(uid, t_id)) and any(
        f.endswith(('.xlsx', '.xls')) for f in os.listdir(file_manager.get_output_dir_for_task(uid, t_id)))
    kb = keyboards.task_info_actions_kb(task_id=t_id, task_status=st, results_exist=results_exist_for_kb, user_id=uid)
    if gf and gfe: kb.insert(InlineKeyboardButton("📄 Группы",
                                                  callback_data=f"{CB_PREFIX_TASK_ACTION}:getfile:groups:{t_id}"))  # Изменен формат
    if wf and wfe: kb.insert(InlineKeyboardButton("🗓️ Дни",
                                                  callback_data=f"{CB_PREFIX_TASK_ACTION}:getfile:weekdays:{t_id}"))  # Изменен формат
    await message.answer(resp, parse_mode=ParseMode.HTML, reply_markup=kb)


@admin_only
async def callback_admin_task_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_admin_task_actions received: {call.data}")
    parts = call.data.split(":");
    pref = parts[0];
    action = parts[1];
    task_id_from_cb = int(parts[2] if len(parts) > 2 else 0)
    if pref != CB_PREFIX_TASK_ACTION: await call.answer("Неверный префикс для действия с задачей.",
                                                        show_alert=True); return

    task_data = db.get_full_task_details(task_id_from_cb)
    if not task_data and action not in ["infocancel"]: await call.answer("Задача не найдена.", show_alert=True);return

    if action == "getfile":
        file_kind = parts[3]  # groups или weekdays
        path_to_file = None;
        file_prefix = f"task{task_id_from_cb}_"
        if file_kind == "groups":
            path_to_file = task_data[4]; file_prefix += "groups_"
        elif file_kind == "weekdays":
            path_to_file = task_data[5]; file_prefix += "weekdays_"
        await send_file_to_admin(call, path_to_file, file_prefix)
    elif action == "getresults":
        user_id_of_task_owner = task_data[1];
        output_dir_for_results = file_manager.get_output_dir_for_task(user_id_of_task_owner, task_id_from_cb);
        generated_files_paths_list = []
        if os.path.exists(output_dir_for_results):
            for filename_in_dir in sorted(os.listdir(output_dir_for_results)):
                if filename_in_dir.endswith(('.xlsx', '.xls')): generated_files_paths_list.append(
                    os.path.join(output_dir_for_results, filename_in_dir))
        if generated_files_paths_list:
            media_group_to_send = MediaGroup();
            sent_count = 0;
            total_files_to_send = len(generated_files_paths_list)
            for i, file_p in enumerate(generated_files_paths_list):
                media_group_to_send.attach_document(
                    InputFile(file_p, filename=f"task{task_id_from_cb}_{os.path.basename(file_p)}"))
                if len(media_group_to_send.media) == 10 or (i == total_files_to_send - 1 and media_group_to_send.media):
                    try:
                        await call.bot.send_media_group(call.from_user.id, media_group_to_send); sent_count += len(
                            media_group_to_send.media)
                    except Exception as e:
                        await call.message.answer(f"Ошибка при отправке группы файлов: {e}"); break
                    media_group_to_send = MediaGroup()
            if sent_count > 0:
                await call.answer(f"Отправлено {sent_count} файлов результатов.")
            else:
                await call.answer("Не удалось отправить файлы.", show_alert=True)
        else:
            await call.answer("Файлы результатов не найдены.", show_alert=True)
    elif action == "initdelete":
        await call.message.edit_text(messages.ADMIN_DELETE_TASK_CONFIRM.format(task_id=task_id_from_cb),
                                     parse_mode=ParseMode.HTML,
                                     reply_markup=keyboards.confirm_delete_task_kb(task_id_from_cb))
        await call.answer()
    elif action == "confirmdelete":
        user_id_owner = task_data[1];
        file_manager.cleanup_task_files(user_id_owner, task_id_from_cb)
        if db.delete_task_from_db(task_id_from_cb):
            await call.message.edit_text(
                messages.ADMIN_TASK_DELETED_SUCCESS.format(task_id=task_id_from_cb)); await call.answer(
                "Задача удалена.")
        else:
            await call.message.edit_text(
                messages.ADMIN_TASK_DELETE_FAILED.format(task_id=task_id_from_cb)); await call.answer(
                "Ошибка удаления из БД.", show_alert=True)
    elif action == "canceldelete":  # Отмена удаления задачи
        await call.message.edit_text(f"Удаление Задачи #{task_id_from_cb} отменено.")
        await call.answer("Удаление отменено.")
    elif action == "infocancel":  # Возврат к информации о задаче после отмены удаления
        if call.message:
            try:
                await call.message.delete()
            except:
                pass
        temp_msg = types.Message(chat=types.Chat(id=call.from_user.id, type=types.ChatType.PRIVATE), message_id=0,
                                 from_user=call.from_user, date=datetime.now(), text=f"/task_info {task_id_from_cb}")
        temp_msg.get_args = lambda: str(task_id_from_cb)
        await cmd_task_info(temp_msg)  # Повторно вызываем cmd_task_info
        await call.answer("Удаление отменено.")
    else:
        await call.answer("Неизвестное действие с задачей.", show_alert=True)


@admin_only
async def cmd_list_tasks(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_task_list_page_internal(message, 0, "all", "all")  # uid_filter="all"


@admin_only
async def callback_task_list_action(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_task_list_action received: {call.data}")
    # Формат: tl:action:p0:sf_all:uid_all  ИЛИ tl:action:sf_all:uid_all
    parts = call.data.split(':')
    if len(parts) < 2 or parts[0] != CB_PREFIX_TASK_LIST:
        await call.answer("Неверный формат callback_data для списка задач", show_alert=True);
        return
    action = parts[1]
    page = 0;
    status_filter = "all";
    user_id_filter_str = "all"
    for i in range(2, len(parts)):
        param_val = parts[i]
        if param_val.startswith("p") and param_val[1:].isdigit():
            page = int(param_val[1:])
        elif param_val.startswith("sf_"):
            status_filter = param_val[3:]
        elif param_val.startswith("uid_"):
            user_id_filter_str = param_val[4:]

    user_id_filter = int(user_id_filter_str) if user_id_filter_str.isdigit() else None
    print(
        f"  [Task List Action] Parsed: action={action}, page={page}, status={status_filter}, user_id={user_id_filter_str}")

    if action == "show":
        await _send_task_list_page_internal(call, page=page, status_filter=status_filter,
                                            user_id_filter_str=user_id_filter_str)
    elif action == "filters":
        await call.message.edit_text(messages.ADMIN_TASK_FILTER_PROMPT,
                                     reply_markup=keyboards.tasks_filter_kb(current_status_filter=status_filter,
                                                                            user_id_filter=user_id_filter))
        await call.answer()
    elif action.startswith(CB_PREFIX_NOOP):  # Для noop_taskpage
        await call.answer()
    else:
        print(f"  [Task List Action] No specific action match for: {action}")
        await call.answer("Неизвестное действие для списка задач", show_alert=True)


@admin_only
async def cmd_force_cancel_task(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.text.split(maxsplit=2)
    if len(args) < 2: await message.reply(messages.ADMIN_FORCE_CANCEL_USAGE, parse_mode=ParseMode.HTML);return
    try:
        task_id_to_cancel = int(args[1])
    except ValueError:
        await message.reply("ID задачи должен быть числом.");return
    reason_for_cancel = args[2] if len(args) > 2 else "Причина не указана администратором";
    new_status_for_task = "failed_by_admin"
    task_details_to_cancel = db.get_full_task_details(task_id_to_cancel)
    if not task_details_to_cancel: await message.reply(
        messages.TASK_NOT_FOUND_ERROR.format(task_id=task_id_to_cancel));return
    current_task_status = task_details_to_cancel[6]
    if current_task_status in ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'failed_by_admin']:
        await message.reply(messages.ADMIN_TASK_NOT_CANCELLABLE_STATUS.format(task_id=task_id_to_cancel,
                                                                              current_status=current_task_status));
        return
    if db.force_update_task_status(task_id_to_cancel, new_status_for_task, admin_reason=reason_for_cancel):
        await message.reply(
            messages.ADMIN_TASK_STATUS_UPDATED.format(task_id=task_id_to_cancel, new_status=new_status_for_task),
            parse_mode=ParseMode.HTML)
        owner_id_of_task = task_details_to_cancel[1]
        if owner_id_of_task:
            try:
                await message.bot.send_message(owner_id_of_task,
                                               f"⚠️ Администратор изменил статус Задачи #{task_id_to_cancel} на '{new_status_for_task}'.\nПричина: {hd.quote(reason_for_cancel)}",
                                               parse_mode=ParseMode.HTML)
            except:
                pass
    else:
        await message.reply(messages.ADMIN_TASK_STATUS_UPDATE_FAILED.format(task_id=task_id_to_cancel))


@admin_only
async def cmd_broadcast(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    broadcast_text = message.get_args()
    if not broadcast_text: await message.reply("Укажите текст: /broadcast <текст>");return
    active_user_ids_list = db.get_active_user_ids()
    if not active_user_ids_list: await message.reply("Нет активных пользователей.");return
    await message.reply(messages.BROADCAST_STARTED.format(count=len(active_user_ids_list)))
    sent_successfully_count = 0;
    failed_to_send_count = 0
    for user_id_to_send in active_user_ids_list:
        try:
            await message.bot.send_message(user_id_to_send, broadcast_text,
                                           parse_mode=ParseMode.HTML); sent_successfully_count += 1
        except Exception:
            failed_to_send_count += 1
        await asyncio.sleep(0.05)
    await message.answer(
        messages.BROADCAST_STATS.format(sent_count=sent_successfully_count, failed_count=failed_to_send_count))


@admin_only
async def cmd_view_feedback(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_unread_feedback(message)


@admin_only
async def callback_mark_feedback_viewed(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_mark_feedback_viewed received: {call.data}")
    try:
        feedback_id_to_mark = int(call.data.split(f"{CB_PREFIX_FEEDBACK}:markviewed:")[-1])  # Изменен разделитель
    except:
        await call.answer("Ошибка ID отзыва.", show_alert=True);return
    if db.mark_feedback_as_viewed(feedback_id_to_mark):
        original_text = call.message.text;
        new_text = original_text + f"\n<i>(Отзыв #{feedback_id_to_mark} помечен как прочитанный)</i>"
        try:
            await call.message.edit_text(new_text, parse_mode=ParseMode.HTML, reply_markup=None)
        except Exception:
            await call.message.edit_reply_markup(reply_markup=None)
        await call.answer(f"Отзыв #{feedback_id_to_mark} прочитан.")
    else:
        await call.answer(messages.ADMIN_FEEDBACK_VIEW_ERROR.format(feedback_id=feedback_id_to_mark), show_alert=True)


@admin_only
async def cmd_list_all_users(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_user_list_page_internal(message, 0, "all_status", "all_role")


@admin_only
async def cmd_user_profile(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.get_args()
    if not args: await message.reply("Укажите ID пользователя: /user_profile <ID>"); return
    try:
        target_user_id = int(args)
    except ValueError:
        await message.reply("ID пользователя должен быть числом."); return
    await _send_user_profile(message, target_user_id,
                             from_page_info={"page": 0, "status_filter": "all_status", "role_filter": "all_role"})


@admin_only
async def callback_user_list_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_user_list_actions received: {call.data}")
    parts = call.data.split(':');
    action = parts[1] if len(parts) > 1 else None
    page = 0;
    status_f = "all_status";
    role_f = "all_role";
    # Разбор параметров из callback_data
    for i in range(2, len(parts)):
        param_part = parts[i]
        if param_part.startswith("p") and param_part[1:].isdigit():
            page = int(param_part[1:])
        elif param_part.startswith("sf_"):
            status_f = param_part[3:]
        elif param_part.startswith("rf_"):
            role_f = param_part[3:]

    print(f"  [User List Action] Parsed: action={action}, page={page}, status={status_f}, role={role_f}")
    if action == "show":
        await _send_user_list_page_internal(call, page, status_f, role_f)
    elif action == "filters":  # Был showfilters, теперь просто filters
        await call.message.edit_text(messages.ADMIN_USER_FILTER_PROMPT,
                                     reply_markup=keyboards.user_list_filters_kb(status_f, role_f))
        await call.answer()
    elif call.data.startswith(CB_PREFIX_NOOP):
        await call.answer()
    else:
        print(f"  [User List Action] No match for callback_data: {call.data}"); await call.answer(
            "Неизвестное действие для списка пользователей.", show_alert=True)


def register_admin_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_admin_panel, Command(commands=['admin']), state="*")
    dp.register_message_handler(cmd_admin_panel, Text(equals="👑 Админ-панель", ignore_case=True), state="*")
    dp.register_callback_query_handler(callback_admin_panel_actions, Text(startswith=CB_PREFIX_ADMIN_PANEL), state="*")
    dp.register_message_handler(cmd_list_pending, Command(commands=['pending_users']), state="*")
    dp.register_message_handler(cmd_task_info, Command(commands=['task_info']), state="*")
    dp.register_callback_query_handler(callback_admin_task_actions, Text(startswith=CB_PREFIX_TASK_ACTION), state="*")
    dp.register_message_handler(cmd_list_tasks, Command(commands=['list_tasks']), state="*")
    dp.register_callback_query_handler(callback_task_list_action, Text(startswith=CB_PREFIX_TASK_LIST), state="*")
    dp.register_message_handler(cmd_force_cancel_task, Command(commands=['force_cancel_task']), state="*")
    dp.register_message_handler(cmd_broadcast, Command(commands=['broadcast']), state="*")
    dp.register_message_handler(cmd_view_feedback, Command(commands=['view_feedback']), state="*")
    dp.register_callback_query_handler(callback_mark_feedback_viewed,
                                       Text(startswith=f"{CB_PREFIX_FEEDBACK}:markviewed:"),
                                       state="*")  # Изменен разделитель
    dp.register_message_handler(cmd_list_all_users, Command(commands=['list_all_users']), state="*")
    dp.register_message_handler(cmd_user_profile, Command(commands=['user_profile']), state="*")
    dp.register_callback_query_handler(callback_user_list_actions, Text(startswith=CB_PREFIX_USER_LIST), state="*")
    dp.register_callback_query_handler(callback_admin_user_action, Text(startswith=CB_PREFIX_USER_ACTION), state="*")
    dp.register_callback_query_handler(lambda call: call.answer(), Text(startswith=CB_PREFIX_NOOP), state="*")