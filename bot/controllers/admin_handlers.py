from aiogram import types, Dispatcher
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import InputFile, MediaGroup, ParseMode, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.markdown import escape_md
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


class AdminReplyStates(StatesGroup):
    waiting_for_reply_text = State()


def admin_only(func):
    async def wrapper(message_or_call: types.Message | types.CallbackQuery, *args, **kwargs):
        user_id = message_or_call.from_user.id
        if user_id not in ADMIN_IDS:
            error_msg = messages.ACCESS_DENIED_MESSAGE
            if isinstance(message_or_call, types.Message):
                await message_or_call.answer(error_msg, parse_mode=ParseMode.MARKDOWN_V2)
            elif isinstance(message_or_call, types.CallbackQuery):
                await message_or_call.answer("У вас нет прав\\.", show_alert=True)
            return
        return await func(message_or_call, *args, **kwargs)

    return wrapper


async def try_edit_or_send_message(target_message_obj: types.Message | types.CallbackQuery, text: str,
                                   reply_markup: InlineKeyboardMarkup | None = None,
                                   parse_mode: str = ParseMode.MARKDOWN_V2):
    original_call = None
    actual_target_message = target_message_obj
    if isinstance(target_message_obj, types.CallbackQuery):
        original_call = target_message_obj
        actual_target_message = target_message_obj.message

    message_edited_or_sent = False
    try:
        await actual_target_message.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup,
                                              disable_web_page_preview=True)
        message_edited_or_sent = True
        if original_call: await original_call.answer()
    except Exception as e:
        if "message is not modified" in str(e).lower():
            if original_call: await original_call.answer()
            message_edited_or_sent = True
        else:
            print(f"ERROR editing message: {e}. Sending new one.")
            try:
                await actual_target_message.bot.send_message(actual_target_message.chat.id, text, parse_mode=parse_mode,
                                                             reply_markup=reply_markup, disable_web_page_preview=True)
                message_edited_or_sent = True
                if original_call: await original_call.answer("Сообщение обновлено (отправлено заново)\\.")
            except Exception as e2:
                print(f"ERROR sending new message after edit failed: {e2}")
                if original_call: await original_call.answer("Не удалось обновить информацию\\.", show_alert=True)

    if original_call and not getattr(original_call, '_answered', False) and not message_edited_or_sent:
        try:
            await original_call.answer()
        except:
            pass


async def _send_user_list_page_internal(message_or_call: types.Message | types.CallbackQuery, page: int = 0,
                                        status_filter: str = "all_status", role_filter: str = "all_role"):
    print(f"DEBUG: _send_user_list_page_internal: p{page} sf_{status_filter} rf_{role_filter}")
    actual_status_filter = None if status_filter == "all_status" else status_filter
    actual_role_filter = None if role_filter == "all_role" else role_filter
    total_users = db.count_all_users(role_filter=actual_role_filter, status_filter=actual_status_filter)
    total_pages = math.ceil(total_users / USERS_PER_PAGE);
    page = max(0, min(page, total_pages - 1 if total_pages > 0 else 0))
    current_page_display = page + 1 if total_users > 0 else 1;
    total_pages_display = total_pages if total_pages > 0 else 1
    offset = page * USERS_PER_PAGE
    users_on_page = db.get_all_users_paginated(limit=USERS_PER_PAGE, offset=offset, role_filter=actual_role_filter,
                                               status_filter=actual_status_filter)
    sf_display = escape_md(
        next((k for k, v in keyboards.USER_STATUSES_FOR_FILTER.items() if v == status_filter), "Все статусы"))
    rf_display = escape_md(
        next((k for k, v in keyboards.USER_ROLES_FOR_FILTER.items() if v == role_filter), "Все роли"))
    header_text = messages.ADMIN_USER_LIST_HEADER.format(current_page=current_page_display,
                                                         total_pages=total_pages_display,
                                                         status_filter_display=sf_display,
                                                         role_filter_display=rf_display)
    response_text = header_text
    if not users_on_page:
        response_text += messages.ADMIN_USER_LIST_EMPTY
    else:
        for uid_db, un_db, fn_db, st_db, rl_db, cr_at_str_db in users_on_page:
            user_display_md = escape_md(fn_db or un_db or f"ID:{uid_db}")
            status_md = escape_md(st_db);
            role_md = escape_md(rl_db);
            created_at_md = escape_md(cr_at_str_db or "N/A")
            response_text += messages.ADMIN_USER_LIST_ITEM.format(user_display=user_display_md, user_id=uid_db,
                                                                  status=status_md, role=role_md,
                                                                  created_at=created_at_md)
    kb = keyboards.user_list_pagination_kb(current_page=page, total_pages=total_pages_display,
                                           status_filter=status_filter, role_filter=role_filter)
    kb.add(InlineKeyboardButton("⚙️ Фильтры пользователей",
                                callback_data=f"{CB_PREFIX_USER_LIST}:filters:sf_{status_filter}:rf_{role_filter}:uid_all"))
    kb.add(InlineKeyboardButton("🔙 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    await try_edit_or_send_message(message_or_call, response_text, kb)


async def _send_pending_users_list(message_to_reply: types.Message):
    pending_users = db.get_pending_users()
    if not pending_users: await message_to_reply.answer(messages.ADMIN_NO_PENDING_USERS,
                                                        parse_mode=ParseMode.MARKDOWN_V2); return
    await message_to_reply.answer(messages.ADMIN_PENDING_USERS_LIST_HEADER + "\n", parse_mode=ParseMode.MARKDOWN_V2)
    for user_id, username, first_name in pending_users:
        display_name_md = escape_md(first_name or username or f"ID:{user_id}")
        await message_to_reply.answer(f"👤 {display_name_md} \\(ID: `{user_id}`\\)",
                                      reply_markup=keyboards.admin_approve_user_kb(user_id, username, first_name),
                                      parse_mode=ParseMode.MARKDOWN_V2)


async def _send_task_list_page_internal(message_or_call_target: types.Message | types.CallbackQuery, page: int = 0,
                                        status_filter: str = "all", user_id_filter_str: str = "all"):
    print(f"DEBUG: _send_task_list_page_internal: p{page} sf_{status_filter} uid_{user_id_filter_str}")
    actual_status_filter = None if status_filter == "all" else status_filter
    actual_user_id_filter = None if user_id_filter_str == "all" else int(user_id_filter_str)
    total_tasks = db.count_all_tasks(status_filter=actual_status_filter, user_id_filter=actual_user_id_filter)
    total_pages = math.ceil(total_tasks / TASKS_PER_PAGE);
    page = max(0, min(page, total_pages - 1 if total_pages > 0 else 0))
    current_page_display = page + 1 if total_tasks > 0 else 1;
    total_pages_display = total_pages if total_pages > 0 else 1
    offset = page * TASKS_PER_PAGE
    tasks_on_page = db.get_all_tasks(limit=TASKS_PER_PAGE, offset=offset, status_filter=actual_status_filter,
                                     user_id_filter=actual_user_id_filter)
    filter_display_name_md = escape_md(
        next((k for k, v in keyboards.TASK_STATUSES_FOR_FILTER.items() if v == status_filter), "Все"))
    header_text = ""
    if actual_user_id_filter:
        user_info_for_header = db.get_user(actual_user_id_filter)
        user_name_for_header = escape_md(user_info_for_header[2] or user_info_for_header[1] or str(
            actual_user_id_filter)) if user_info_for_header else str(actual_user_id_filter)
        header_text = f"📑 *Задачи пользователя {user_name_for_header}* \\(Стр\\. {current_page_display}/{total_pages_display}\\)\nФильтр: _{filter_display_name_md}_\n\n"
    else:
        header_text = messages.ADMIN_TASK_LIST_HEADER.format(current_page=current_page_display,
                                                             total_pages=total_pages_display,
                                                             filter_display_name=filter_display_name_md)
    response_text = header_text
    if not tasks_on_page:
        response_text += messages.ADMIN_TASK_LIST_EMPTY
    else:
        for tid, tuid, un, fn, st, ca_str in tasks_on_page:
            ud_md = escape_md(fn or un or "N/A");
            status_md = escape_md(st);
            created_at_md = escape_md(ca_str or "N/A")
            response_text += messages.ADMIN_TASK_LIST_ITEM.format(task_id=tid, user_display=ud_md, user_id=tuid,
                                                                  status=status_md, created_at=created_at_md)
    kb = keyboards.tasks_pagination_kb(current_page=page, total_pages=total_pages_display, current_filter=status_filter,
                                       user_id_filter=actual_user_id_filter)
    kb.add(InlineKeyboardButton("⚙️ Фильтры статусов задач",
                                callback_data=f"{CB_PREFIX_TASK_LIST}:filters:sf_{status_filter}:uid_{user_id_filter_str}"))
    kb.add(InlineKeyboardButton("🔙 В Админ-панель", callback_data=f"{CB_PREFIX_ADMIN_PANEL}:main"))
    await try_edit_or_send_message(message_or_call_target, response_text, kb)


async def _send_unread_feedback(message_to_reply: types.Message):
    unread_feedback = db.get_unread_feedback(limit=5)
    if not unread_feedback: await message_to_reply.answer(messages.ADMIN_NO_UNREAD_FEEDBACK,
                                                          parse_mode=ParseMode.MARKDOWN_V2); return
    await message_to_reply.answer("📬 *Непрочитанные отзывы:*\n", parse_mode=ParseMode.MARKDOWN_V2)
    for fb_id, uid_author, un_author, fn_author, msg_txt, rcv_at_str in unread_feedback:
        ud_md = escape_md(fn_author or un_author or f"ID:{uid_author}")
        msg_txt_md = msg_txt  # Текст отзыва не экранируем здесь, а заключаем в блок кода
        rcv_at_md = escape_md(rcv_at_str or "N/A")
        response = f"*Отзыв \\#{fb_id}* от {ud_md} \\(ID:`{uid_author}`\\) \\[{rcv_at_md}\\]:\n```\n{escape_md(msg_txt_md)}\n```"  # Экранируем только перед вставкой в блок
        await message_to_reply.answer(response, parse_mode=ParseMode.MARKDOWN_V2,
                                      reply_markup=keyboards.mark_feedback_viewed_kb(fb_id, uid_author))


async def _send_user_profile(message_or_call: types.Message | types.CallbackQuery, target_user_id: int,
                             from_page_info: dict | None = None):
    print(f"DEBUG: _send_user_profile for user {target_user_id}, from_page_info: {from_page_info}")
    user_data = db.get_user(target_user_id)
    if not user_data:
        msg_target = message_or_call if isinstance(message_or_call, types.Message) else message_or_call.message
        await msg_target.answer(messages.ADMIN_USER_NOT_FOUND.format(user_id=target_user_id),
                                parse_mode=ParseMode.MARKDOWN_V2)
        if isinstance(message_or_call, types.CallbackQuery): await message_or_call.answer()
        return
    uid_db, un_db, fn_db, st_db, rl_db, cr_at_str_db = user_data
    task_count = db.get_user_task_count(uid_db)
    username_md = escape_md(un_db or "N/A").replace("@", "\\@")
    response = messages.ADMIN_USER_PROFILE_HEADER + messages.ADMIN_USER_PROFILE_INFO.format(
        user_id=uid_db, username=username_md,
        first_name=escape_md(fn_db or "N/A"), status=escape_md(st_db),
        role=escape_md(rl_db), created_at=escape_md(cr_at_str_db or "N/A"), task_count=task_count
    )
    page = from_page_info.get("page", 0) if from_page_info else 0
    status_f = from_page_info.get("status_filter", "all_status") if from_page_info else "all_status"
    role_f = from_page_info.get("role_filter", "all_role") if from_page_info else "all_role"
    kb = keyboards.user_profile_actions_kb(uid_db, st_db, rl_db, current_page=page, status_filter=status_f,
                                           role_filter=role_f)
    await try_edit_or_send_message(message_or_call, response, kb)


@admin_only
async def cmd_admin_panel(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    print(f"DEBUG: cmd_admin_panel triggered by {message.from_user.id}")
    await message.answer(messages.ADMIN_PANEL_MESSAGE, reply_markup=keyboards.admin_panel_kb(),
                         parse_mode=ParseMode.MARKDOWN_V2)


@admin_only
async def callback_admin_panel_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    action_full = call.data
    print(f"DEBUG: callback_admin_panel_actions received: {action_full}")
    target_message_for_reply = call.message
    try:
        await call.message.delete()
    except:
        pass
    parts = action_full.split(':');
    prefix = parts[0];
    action = parts[1] if len(parts) > 1 else None
    if prefix != CB_PREFIX_ADMIN_PANEL: await call.answer(); return
    if action == "pending":
        await _send_pending_users_list(target_message_for_reply)
    elif action == "feedback":
        await _send_unread_feedback(target_message_for_reply)
    elif action == "broadcastinfo":
        await target_message_for_reply.answer(messages.BROADCAST_INFO_ADMIN, parse_mode=ParseMode.MARKDOWN_V2,
                                              reply_markup=keyboards.main_menu_kb(is_admin=True))
    elif action == "main":
        await target_message_for_reply.answer(messages.ADMIN_PANEL_MESSAGE, reply_markup=keyboards.admin_panel_kb(),
                                              parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await target_message_for_reply.answer(messages.ERROR_OCCURRED + " \\(Неизвестное действие админ\\-панели\\)",
                                              parse_mode=ParseMode.MARKDOWN_V2)
    await call.answer()


@admin_only
async def cmd_list_pending(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_pending_users_list(message)


@admin_only
async def callback_admin_user_action(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_admin_user_action received: {call.data}")
    parts = call.data.split(':');
    pref = parts[0];
    action = parts[1];
    target_user_id = int(parts[2])
    if pref != CB_PREFIX_USER_ACTION: await call.answer("Ошибка маршрутизации user_action\\.", show_alert=True); return
    page_info_for_return = {"page": 0, "status_filter": "all_status", "role_filter": "all_role"}
    for i in range(3, len(parts)):
        part = parts[i]
        if part.startswith("p") and part[1:].isdigit():
            page_info_for_return["page"] = int(part[1:])
        elif part.startswith("sf_"):
            page_info_for_return["status_filter"] = part[3:]
        elif part.startswith("rf_"):
            page_info_for_return["role_filter"] = part[3:]
    user_info = db.get_user(target_user_id)
    if not user_info: await call.answer("Пользователь не найден\\.", show_alert=True); return
    uid_db, un_db, fn_db, status_db, role_db, _ = user_info;
    user_display_name = escape_md(fn_db or un_db or f"ID:{target_user_id}")
    refresh_profile = True
    if action == "approve":
        if status_db == 'active': await call.message.edit_text(
            messages.ADMIN_USER_ALREADY_ACTIVE.format(user_id=target_user_id, user_display=user_display_name),
            parse_mode=ParseMode.MARKDOWN_V2); await call.answer(); return
        db.update_user_status_role(target_user_id, status='active')
        await call.message.edit_text(
            messages.ADMIN_USER_APPROVED.format(user_id=target_user_id, user_display=user_display_name),
            parse_mode=ParseMode.MARKDOWN_V2);
        await call.answer("Пользователь активирован\\!")
        try:
            await call.bot.send_message(target_user_id, messages.ADMIN_NOTIFY_USER_ACTIVATED,
                                        parse_mode=ParseMode.MARKDOWN_V2)
        except:
            await call.message.answer(messages.ADMIN_NOTIFY_USER_FAILED, parse_mode=ParseMode.MARKDOWN_V2)
        return
    if action == "ban":
        db.update_user_status_role(target_user_id, status="banned"); await call.answer("Пользователь забанен\\.")
    elif action == "unban":
        db.update_user_status_role(target_user_id, status="active"); await call.answer("Пользователь разбанен\\.")
    elif action == "setadmin" and target_user_id not in ADMIN_IDS:
        db.update_user_status_role(target_user_id, role="admin"); await call.answer("Назначен администратором\\.")
    elif action == "setuser" and target_user_id not in ADMIN_IDS:
        db.update_user_status_role(target_user_id, role="user"); await call.answer("Назначен пользователем\\.")
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
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboards.confirm_user_data_delete_kb(target_user_id));
        await call.answer();
        return
    elif action == "dodelete" and target_user_id not in ADMIN_IDS:
        file_manager.cleanup_task_files(target_user_id, "all_tasks_of_user")
        if db.delete_user_and_tasks(target_user_id):
            await call.message.edit_text(
                messages.ADMIN_USER_DATA_DELETED_SUCCESS.format(user_display=user_display_name, user_id=target_user_id),
                parse_mode=ParseMode.MARKDOWN_V2); await call.answer("Данные пользователя удалены\\.")
        else:
            await call.message.edit_text(
                messages.ADMIN_USER_DATA_DELETE_FAILED.format(user_display=user_display_name, user_id=target_user_id),
                parse_mode=ParseMode.MARKDOWN_V2); await call.answer("Ошибка удаления данных\\.", show_alert=True)
        return
    elif action == "canceldelete":
        await call.answer("Удаление отменено\\.")
    elif action == "showprofile":
        await call.answer()
    else:
        await call.answer(f"Неизвестное действие: {escape_md(action)}", show_alert=True); refresh_profile = False
    if refresh_profile: await _send_user_profile(call, target_user_id, from_page_info=page_info_for_return)


@admin_only
async def cmd_task_info(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.get_args();
    if not args: await message.reply(messages.TASK_STATUS_USAGE, parse_mode=ParseMode.MARKDOWN_V2); return
    try:
        task_id_from_arg = int(args)
    except ValueError:
        await message.reply("ID задачи должен быть числом\\.", parse_mode=ParseMode.MARKDOWN_V2); return
    task_details = db.get_full_task_details(task_id_from_arg)
    if not task_details: await message.reply(messages.TASK_NOT_FOUND_ERROR.format(task_id=task_id_from_arg),
                                             parse_mode=ParseMode.MARKDOWN_V2); return
    t_id, uid, un, fn, gf, wf, st, ca_str, rm = task_details
    ud_md = escape_md(fn or un or "N/A");
    gfb_md = escape_md(os.path.basename(gf) if gf and isinstance(gf, str) else "N/A");
    wfb_md = escape_md(os.path.basename(wf) if wf and isinstance(wf, str) else "N/A")
    gfe = os.path.exists(gf) if gf and isinstance(gf, str) else False;
    wfe = os.path.exists(wf) if wf and isinstance(wf, str) else False
    status_md = escape_md(st);
    created_at_md = escape_md(ca_str or "N/A");
    result_msg_md = escape_md(rm or "N/A")
    resp = messages.TASK_STATUS_INFO_HEADER.format(task_id=t_id) + messages.TASK_STATUS_ITEM.format(user_display=ud_md,
                                                                                                    user_id=uid,
                                                                                                    created_at=created_at_md,
                                                                                                    status=status_md,
                                                                                                    groups_file=gfb_md,
                                                                                                    weekdays_file=wfb_md,
                                                                                                    result_message=result_msg_md)
    results_exist_for_kb = os.path.exists(file_manager.get_output_dir_for_task(uid, t_id)) and any(
        f.endswith(('.xlsx', '.xls')) for f in os.listdir(file_manager.get_output_dir_for_task(uid, t_id)))
    kb = keyboards.task_info_actions_kb(task_id=t_id, task_status=st, results_exist=results_exist_for_kb, user_id=uid)
    if gf and gfe: kb.insert(
        InlineKeyboardButton("📄 Группы", callback_data=f"{CB_PREFIX_TASK_ACTION}:getfile:groups:{t_id}"))
    if wf and wfe: kb.insert(
        InlineKeyboardButton("🗓️ Дни", callback_data=f"{CB_PREFIX_TASK_ACTION}:getfile:weekdays:{t_id}"))
    await message.answer(resp, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=kb, disable_web_page_preview=True)


@admin_only
async def callback_admin_task_actions(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_admin_task_actions received: {call.data}")
    parts = call.data.split(":");
    pref = parts[0];
    action = parts[1] if len(parts) > 1 else None;
    task_id_from_cb = int(parts[2] if len(parts) > 2 and parts[2].isdigit() else 0)
    if pref != CB_PREFIX_TASK_ACTION: await call.answer("Неверный префикс для действия с задачей\\.",
                                                        show_alert=True); return
    if action == "getfile":
        if len(parts) < 4: await call.answer("Неверный формат getfile\\.", show_alert=True); return
        file_kind = parts[3];  # ID задачи уже в task_id_from_cb (parts[2])
    elif action in ["initdelete", "confirmdelete", "canceldelete", "getresults", "infocancel"]:
        if len(parts) < 3: await call.answer(f"Неверный формат {escape_md(action)}\\.", show_alert=True); return
        task_id_from_cb = int(parts[2])
    if not task_id_from_cb and action not in ["infocancel"]: await call.answer("Ошибка: ID задачи не найден\\.",
                                                                               show_alert=True); return
    task_data = db.get_full_task_details(task_id_from_cb) if task_id_from_cb else None
    if not task_data and action not in ["infocancel"]: await call.answer("Задача не найдена\\.", show_alert=True);return
    if action == "getfile":
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
                        await call.message.answer(f"Ошибка при отправке группы файлов: {escape_md(str(e))}",
                                                  parse_mode=ParseMode.MARKDOWN_V2); break
                    media_group_to_send = MediaGroup()
            if sent_count > 0:
                await call.answer(f"Отправлено {sent_count} файлов результатов\\.")
            else:
                await call.answer("Не удалось отправить файлы\\.", show_alert=True)
        else:
            await call.answer("Файлы результатов не найдены\\.", show_alert=True)
    elif action == "initdelete":
        await call.message.edit_text(messages.ADMIN_DELETE_TASK_CONFIRM.format(task_id=task_id_from_cb),
                                     parse_mode=ParseMode.MARKDOWN_V2,
                                     reply_markup=keyboards.confirm_delete_task_kb(task_id_from_cb))
        await call.answer()
    elif action == "confirmdelete":
        user_id_owner = task_data[1];
        file_manager.cleanup_task_files(user_id_owner, task_id_from_cb)
        if db.delete_task_from_db(task_id_from_cb):
            await call.message.edit_text(messages.ADMIN_TASK_DELETED_SUCCESS.format(task_id=task_id_from_cb),
                                         parse_mode=ParseMode.MARKDOWN_V2); await call.answer("Задача удалена\\.")
        else:
            await call.message.edit_text(messages.ADMIN_TASK_DELETE_FAILED.format(task_id=task_id_from_cb),
                                         parse_mode=ParseMode.MARKDOWN_V2); await call.answer(
                "Ошибка удаления из БД\\.", show_alert=True)
    elif action == "canceldelete":
        await call.message.edit_text(f"Удаление Задачи \\#{task_id_from_cb} отменено\\.",
                                     parse_mode=ParseMode.MARKDOWN_V2)
        await call.answer("Удаление отменено\\.")
    elif action == "infocancel":
        if call.message:
            try:
                await call.message.delete()
            except:
                pass
        temp_msg = types.Message(chat=types.Chat(id=call.from_user.id, type=types.ChatType.PRIVATE), message_id=0,
                                 from_user=call.from_user, date=datetime.now(), text=f"/task_info {task_id_from_cb}")
        temp_msg.get_args = lambda: str(task_id_from_cb)
        await cmd_task_info(temp_msg)
        await call.answer("Удаление отменено\\.")
    else:
        await call.answer("Неизвестное действие с задачей\\.", show_alert=True)


@admin_only
async def cmd_list_tasks(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_task_list_page_internal(message, 0, "all", "all")


@admin_only
async def callback_task_list_action(call: types.CallbackQuery, state: FSMContext = None, **kwargs):
    print(f"DEBUG: callback_task_list_action received: {call.data}")
    parts = call.data.split(':');
    action = parts[1] if len(parts) > 1 else None
    page = 0;
    status_filter = "all";
    user_id_filter_str = "all"
    for i in range(2, len(parts)):
        param_part = parts[i]
        if param_part.startswith("p") and param_part[1:].isdigit():
            page = int(param_part[1:])
        elif param_part.startswith("sf_"):
            status_filter = param_part[3:]
        elif param_part.startswith("uid_"):
            user_id_filter_str = param_part[4:]
    user_id_filter = int(user_id_filter_str) if user_id_filter_str.isdigit() else None
    print(
        f"  [Task List Action] Parsed: action={action}, page={page}, status={status_filter}, user_id_filter_str={user_id_filter_str}")
    if action == "show":
        await _send_task_list_page_internal(call, page=page, status_filter=status_filter,
                                            user_id_filter_str=user_id_filter_str)
    elif action == "filters":
        await call.message.edit_text(messages.ADMIN_TASK_FILTER_PROMPT,
                                     reply_markup=keyboards.tasks_filter_kb(current_status_filter=status_filter,
                                                                            user_id_filter=user_id_filter),
                                     parse_mode=ParseMode.MARKDOWN_V2); await call.answer()
    elif call.data.startswith(CB_PREFIX_NOOP):
        await call.answer()
    else:
        print(f"  [Task List Action] No match for callback_data: {call.data}"); await call.answer(
            "Неизвестное действие для списка задач\\.", show_alert=True)


@admin_only
async def cmd_force_cancel_task(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.text.split(maxsplit=2)
    if len(args) < 2: await message.reply(messages.ADMIN_FORCE_CANCEL_USAGE, parse_mode=ParseMode.MARKDOWN_V2);return
    try:
        task_id_to_cancel = int(args[1])
    except ValueError:
        await message.reply("ID задачи должен быть числом\\.", parse_mode=ParseMode.MARKDOWN_V2);return
    reason_for_cancel = args[2] if len(args) > 2 else "Причина не указана администратором";
    new_status_for_task = "failed_by_admin"
    task_details_to_cancel = db.get_full_task_details(task_id_to_cancel)
    if not task_details_to_cancel: await message.reply(messages.TASK_NOT_FOUND_ERROR.format(task_id=task_id_to_cancel),
                                                       parse_mode=ParseMode.MARKDOWN_V2);return
    current_task_status = task_details_to_cancel[6]
    if current_task_status in ['completed', 'completed_with_warnings', 'failed', 'cancelled', 'failed_by_admin']:
        await message.reply(messages.ADMIN_TASK_NOT_CANCELLABLE_STATUS.format(task_id=task_id_to_cancel,
                                                                              current_status=escape_md(
                                                                                  current_task_status)),
                            parse_mode=ParseMode.MARKDOWN_V2);
        return
    if db.force_update_task_status(task_id_to_cancel, new_status_for_task, admin_reason=reason_for_cancel):
        await message.reply(messages.ADMIN_TASK_STATUS_UPDATED.format(task_id=task_id_to_cancel,
                                                                      new_status=escape_md(new_status_for_task)),
                            parse_mode=ParseMode.MARKDOWN_V2)
        owner_id_of_task = task_details_to_cancel[1]
        if owner_id_of_task:
            try:
                await message.bot.send_message(owner_id_of_task,
                                               f"⚠️ Администратор изменил статус Задачи \\#{task_id_to_cancel} на '{escape_md(new_status_for_task)}'\\.\nПричина: {escape_md(reason_for_cancel)}",
                                               parse_mode=ParseMode.MARKDOWN_V2)
            except:
                pass
    else:
        await message.reply(messages.ADMIN_TASK_STATUS_UPDATE_FAILED.format(task_id=task_id_to_cancel),
                            parse_mode=ParseMode.MARKDOWN_V2)


@admin_only
async def cmd_broadcast(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    broadcast_text = message.get_args()
    if not broadcast_text: await message.reply("Укажите текст: `/broadcast текст сообщения`",
                                               parse_mode=ParseMode.MARKDOWN_V2);return
    active_user_ids_list = db.get_active_user_ids()
    if not active_user_ids_list: await message.reply("Нет активных пользователей\\.",
                                                     parse_mode=ParseMode.MARKDOWN_V2);return
    await message.reply(messages.BROADCAST_STARTED.format(count=len(active_user_ids_list)),
                        parse_mode=ParseMode.MARKDOWN_V2)
    sent_successfully_count = 0;
    failed_to_send_count = 0
    for user_id_to_send in active_user_ids_list:
        try:
            await message.bot.send_message(user_id_to_send, broadcast_text,
                                           parse_mode=ParseMode.MARKDOWN_V2); sent_successfully_count += 1
        except Exception:
            failed_to_send_count += 1
        await asyncio.sleep(0.05)
    await message.answer(
        messages.BROADCAST_STATS.format(sent_count=sent_successfully_count, failed_count=failed_to_send_count),
        parse_mode=ParseMode.MARKDOWN_V2)


@admin_only
async def cmd_view_feedback(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_unread_feedback(message)


@admin_only
async def callback_feedback_actions(call: types.CallbackQuery, state: FSMContext = None,
                                    **kwargs):  # Объединенный хэндлер
    print(f"DEBUG: callback_feedback_actions received: {call.data}")
    parts = call.data.split(':');
    pref = parts[0];
    action = parts[1] if len(parts) > 1 else None
    if pref != CB_PREFIX_FEEDBACK: await call.answer("Неверный префикс для отзыва.", show_alert=True); return

    feedback_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if not feedback_id: await call.answer("Ошибка ID отзыва.", show_alert=True); return

    if action == "markviewed":
        if db.mark_feedback_as_viewed(feedback_id):
            original_text = call.message.text
            new_text = original_text + f"\n_{escape_md(f'(Отзыв #{feedback_id} помечен как прочитанный)')}_"
            try:
                await call.message.edit_text(new_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=None)
            except Exception:
                await call.message.edit_reply_markup(reply_markup=None)
            await call.answer(f"Отзыв \\#{feedback_id} прочитан\\.")
        else:
            await call.answer(messages.ADMIN_FEEDBACK_VIEW_ERROR.format(feedback_id=feedback_id), show_alert=True,
                              parse_mode=ParseMode.MARKDOWN_V2)
    elif action == "reply":
        if len(parts) < 4 or not parts[3].isdigit(): await call.answer("Недостаточно данных для ответа (user_id).",
                                                                       show_alert=True); return
        user_id_to_reply = int(parts[3])
        await state.set_state(AdminReplyStates.waiting_for_reply_text.state)
        await state.update_data(reply_to_user_id=user_id_to_reply, context_feedback_id=feedback_id)
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except:
            pass
        await call.message.answer(
            f"📝 Введите ваш ответ для пользователя ID `{user_id_to_reply}` \\(на отзыв \\#{feedback_id}\\)\\.\nДля отмены: /cancel",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboards.cancel_state_kb())
        await call.answer()
    else:
        await call.answer("Неизвестное действие с отзывом.", show_alert=True)


@admin_only
async def process_admin_reply_text(message: types.Message, state: FSMContext, **kwargs):
    print(f"DEBUG: process_admin_reply_text received for state {await state.get_state()}")
    data = await state.get_data();
    user_id_to_reply = data.get('reply_to_user_id');
    context_feedback_id = data.get('context_feedback_id')
    is_admin_sender = message.from_user.id in ADMIN_IDS  # Для main_menu_kb
    if not user_id_to_reply or not message.text:
        await message.reply("Ошибка: не найден ID пользователя или текст ответа пуст\\. Попробуйте снова\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                            reply_markup=keyboards.main_menu_kb(is_admin=is_admin_sender));
        await state.finish();
        return

    # Формируем текст ответа. Текст самого админа (message.text) не экранируем,
    # так как админ может сам захотеть использовать Markdown.
    # Экранируем только ту часть, которую генерирует бот.
    reply_text_from_admin = f"Ответ от администрации на ваш отзыв \\(\\#{context_feedback_id}\\):\n\n{message.text}"

    try:
        await message.bot.send_message(user_id_to_reply, reply_text_from_admin, parse_mode=ParseMode.MARKDOWN_V2)
        await message.reply(f"✅ Ответ успешно отправлен пользователю ID `{user_id_to_reply}`\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                            reply_markup=keyboards.main_menu_kb(is_admin=is_admin_sender))
    except Exception as e:
        await message.reply(
            f"❌ Не удалось отправить ответ пользователю ID `{user_id_to_reply}`\\. Ошибка: {escape_md(str(e))}",
            parse_mode=ParseMode.MARKDOWN_V2, reply_markup=keyboards.main_menu_kb(is_admin=is_admin_sender))
    await state.finish()


@admin_only
async def cmd_reply_to_user(message: types.Message, state: FSMContext, command: BotCommand = None, **kwargs):
    await state.finish()
    args = command.args if command and command.args is not None else message.get_args()
    if not args: await message.reply("🚫 Укажите ID и текст\\.\nПример: `/reply 123456 Текст\\.`",
                                     parse_mode=ParseMode.MARKDOWN_V2); return
    parts = args.split(maxsplit=1)
    if not parts[0].isdigit() or len(parts) < 2: await message.reply(
        "🚫 Неверный формат\\.\nПример: `/reply 123456 Текст`", parse_mode=ParseMode.MARKDOWN_V2); return
    user_id_to_reply = int(parts[0]);
    text_to_send = parts[1]
    try:
        await message.bot.send_message(user_id_to_reply, f"Сообщение от администрации:\n\n{text_to_send}",
                                       parse_mode=ParseMode.MARKDOWN_V2)
        await message.reply(f"✅ Сообщение отправлено ID `{user_id_to_reply}`\\.", parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки ID `{user_id_to_reply}`: {escape_md(str(e))}",
                            parse_mode=ParseMode.MARKDOWN_V2)


@admin_only
async def cmd_list_all_users(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    await _send_user_list_page_internal(message, 0, "all_status", "all_role")


@admin_only
async def cmd_user_profile(message: types.Message, command: BotCommand = None, state: FSMContext = None, **kwargs):
    args = message.get_args()
    if not args: await message.reply("Укажите ID пользователя: `/user_profile ID`",
                                     parse_mode=ParseMode.MARKDOWN_V2); return
    try:
        target_user_id = int(args)
    except ValueError:
        await message.reply("ID пользователя должен быть числом\\.", parse_mode=ParseMode.MARKDOWN_V2); return
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
    elif action == "filters":
        await call.message.edit_text(messages.ADMIN_USER_FILTER_PROMPT,
                                     reply_markup=keyboards.user_list_filters_kb(status_f, role_f),
                                     parse_mode=ParseMode.MARKDOWN_V2); await call.answer()
    elif call.data.startswith(CB_PREFIX_NOOP):
        await call.answer()
    else:
        print(f"  [User List Action] No match for callback_data: {call.data}"); await call.answer(
            "Неизвестное действие для списка пользователей\\.", show_alert=True)


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
    dp.register_callback_query_handler(callback_feedback_actions, Text(startswith=CB_PREFIX_FEEDBACK),
                                       state="*")  # Объединенный
    dp.register_message_handler(process_admin_reply_text, state=AdminReplyStates.waiting_for_reply_text,
                                content_types=types.ContentType.TEXT)
    dp.register_message_handler(cmd_reply_to_user, Command(commands=['reply']), state="*")
    dp.register_message_handler(cmd_list_all_users, Command(commands=['list_all_users']), state="*")
    dp.register_message_handler(cmd_user_profile, Command(commands=['user_profile']), state="*")
    dp.register_callback_query_handler(callback_user_list_actions, Text(startswith=CB_PREFIX_USER_LIST), state="*")
    dp.register_callback_query_handler(callback_admin_user_action, Text(startswith=CB_PREFIX_USER_ACTION), state="*")
    dp.register_callback_query_handler(lambda call: call.answer(), Text(startswith=CB_PREFIX_NOOP), state="*")