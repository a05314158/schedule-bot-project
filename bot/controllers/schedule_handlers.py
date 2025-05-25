import os
import asyncio
from aiogram import types, Dispatcher
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher.filters import Command, Text
from aiogram.types import ContentType, InputFile, MediaGroup, ReplyKeyboardRemove, BotCommand, ParseMode
from aiogram.utils.markdown import html_decoration as hd

from bot.models import db, algorithm_runner
from bot.views import messages, keyboards
from bot.utils import file_manager
from bot.config import ADMIN_IDS  # Если потребуется для каких-то проверок здесь


class ScheduleCreationStates(StatesGroup):
    waiting_for_groups_file = State()
    waiting_for_weekdays_file = State()
    confirm_generation = State()


def active_user_only(func):
    async def wrapper(message_or_call: types.Message | types.CallbackQuery, *args, **kwargs):
        user_id = message_or_call.from_user.id
        user_info = db.get_user(user_id)
        if not user_info:
            db.add_user(user_id, message_or_call.from_user.username, message_or_call.from_user.first_name)
            user_info = db.get_user(user_id)
        if not user_info or user_info[3] != 'active':
            current_status = user_info[3] if user_info else "unknown"
            reply_message = messages.ACCESS_PENDING_MESSAGE if current_status == 'pending' else messages.ACCESS_DENIED_MESSAGE
            if isinstance(message_or_call, types.Message):
                await message_or_call.answer(reply_message, reply_markup=ReplyKeyboardRemove())
            elif isinstance(message_or_call, types.CallbackQuery):
                await message_or_call.answer(reply_message, show_alert=True)
            return
        return await func(message_or_call, *args, **kwargs)

    return wrapper


@active_user_only
async def cmd_new_schedule(message: types.Message, state: FSMContext, command: BotCommand = None, **kwargs):
    await state.finish()
    task_id = db.create_schedule_task(message.from_user.id)
    if not task_id:
        await message.answer(messages.TASK_CREATION_ERROR, reply_markup=keyboards.main_menu_kb())
        return
    await state.update_data(task_id=task_id)
    await ScheduleCreationStates.waiting_for_groups_file.set()
    await message.answer(messages.NEW_SCHEDULE_START, reply_markup=ReplyKeyboardRemove())
    await message.answer(messages.UPLOAD_GROUPS_FILE, reply_markup=keyboards.cancel_state_kb(),
                         parse_mode=ParseMode.HTML)


@active_user_only
async def process_groups_file(message: types.Message, state: FSMContext, **kwargs):
    if not message.document:
        await message.answer("Пожалуйста, отправьте файл.", reply_markup=keyboards.cancel_state_kb())
        return
    data = await state.get_data()
    task_id = data.get('task_id')
    if not task_id:
        await message.answer(messages.TASK_NOT_FOUND_ERROR.format(task_id="текущей") + " Начните заново /new_schedule.",
                             reply_markup=keyboards.main_menu_kb())
        await state.finish();
        return
    save_result = await file_manager.save_uploaded_file(message.document, message.bot, message.from_user.id, task_id)
    if save_result["status"] == "error":
        error_message = save_result.get("message", messages.FILE_UPLOAD_ERROR)
        await message.answer(error_message, reply_markup=keyboards.cancel_state_kb());
        return  # Остаемся в том же состоянии, чтобы пользователь мог попробовать снова
    file_path = save_result["path"]
    db.update_task_add_file(task_id, "groups", file_path)
    db.update_task_status(task_id, "pending_weekdays_file")
    await ScheduleCreationStates.waiting_for_weekdays_file.set()
    await message.answer(messages.UPLOAD_WEEKDAYS_FILE, reply_markup=keyboards.cancel_state_kb(),
                         parse_mode=ParseMode.HTML)


@active_user_only
async def process_weekdays_file(message: types.Message, state: FSMContext, **kwargs):
    if not message.document:
        await message.answer("Пожалуйста, отправьте файл.", reply_markup=keyboards.cancel_state_kb())
        return
    data = await state.get_data()
    task_id = data.get('task_id')
    if not task_id:
        await message.answer(messages.TASK_NOT_FOUND_ERROR.format(task_id="текущей") + " Начните заново /new_schedule.",
                             reply_markup=keyboards.main_menu_kb())
        await state.finish();
        return
    save_result = await file_manager.save_uploaded_file(message.document, message.bot, message.from_user.id, task_id)
    if save_result["status"] == "error":
        error_message = save_result.get("message", messages.FILE_UPLOAD_ERROR)
        await message.answer(error_message, reply_markup=keyboards.cancel_state_kb());
        return  # Остаемся в том же состоянии
    file_path = save_result["path"]
    db.update_task_add_file(task_id, "weekdays", file_path)
    db.update_task_status(task_id, "pending_files")
    await ScheduleCreationStates.confirm_generation.set()
    await message.answer(messages.FILES_UPLOADED_CONFIRM.format(task_id=task_id),
                         reply_markup=keyboards.confirm_schedule_generation_kb(task_id))
    await message.answer(messages.GENERATION_CONFIRM_PROMPT, reply_markup=ReplyKeyboardRemove(),
                         parse_mode=ParseMode.HTML)


@active_user_only
async def callback_run_generation(call: types.CallbackQuery, state: FSMContext, **kwargs):
    try:
        task_id = int(call.data.split("_")[-1])
    except (IndexError, ValueError):
        await call.answer("Ошибка в ID задачи.", show_alert=True);
        return
    try:
        await call.message.edit_text(f"Задача #{task_id}: Подготовка к запуску...", reply_markup=None)
    except Exception:
        pass
    await call.answer()
    await state.finish()
    task_info = db.get_task_info(task_id)
    if not task_info:
        await call.bot.send_message(call.from_user.id, messages.TASK_NOT_FOUND_ERROR.format(task_id=task_id),
                                    reply_markup=keyboards.main_menu_kb());
        return
    user_id, groups_file, weekdays_file, current_status = task_info
    if not groups_file or not weekdays_file:
        await call.bot.send_message(call.from_user.id, messages.FILES_MISSING_FOR_TASK_ERROR.format(task_id=task_id),
                                    reply_markup=keyboards.main_menu_kb(), parse_mode=ParseMode.HTML)
        db.update_task_status(task_id, "failed", "Отсутствуют входные файлы");
        return
    if current_status == 'processing':
        await call.bot.send_message(call.from_user.id, messages.TASK_ALREADY_PROCESSING_ERROR.format(task_id=task_id),
                                    reply_markup=keyboards.main_menu_kb());
        return
    db.update_task_status(task_id, "processing")
    output_dir = file_manager.get_output_dir_for_task(user_id, task_id)
    progress_status_message = await call.bot.send_message(call.from_user.id,
                                                          messages.USER_MESSAGE_GENERATION_STARTED.format(
                                                              task_id=task_id))
    last_update_time = asyncio.get_event_loop().time()

    async def send_progress_update(status_text: str):
        nonlocal last_update_time
        current_time = asyncio.get_event_loop().time()
        if current_time - last_update_time < 1.5 and "Завершено" not in status_text and "Ошибка" not in status_text and "ВНИМАНИЕ" not in status_text: return
        try:
            await progress_status_message.edit_text(status_text, parse_mode=ParseMode.HTML)
            last_update_time = current_time
        except Exception:
            pass

    result = await algorithm_runner.run_schedule_generation_async(groups_file, weekdays_file, output_dir,
                                                                  task_id=task_id,
                                                                  progress_callback=send_progress_update)
    try:
        await progress_status_message.delete()
    except Exception:
        pass

    reply_markup_after_generation = keyboards.main_menu_kb()

    if result.get("status") == "success":
        final_message_text = result.get("message", "Успешно завершено")
        db_status = "completed" if "ВНИМАНИЕ" not in final_message_text else "completed_with_warnings"
        db.update_task_status(task_id, db_status, final_message_text)
        user_message_template = messages.GENERATION_SUCCESS if db_status == "completed" else messages.GENERATION_WARNING
        safe_final_message = hd.quote(final_message_text)
        await call.bot.send_message(call.from_user.id,
                                    user_message_template.format(task_id=task_id, warning_message=safe_final_message),
                                    reply_markup=reply_markup_after_generation, parse_mode=ParseMode.HTML)
        generated_files_paths = result.get("files", [])
        if generated_files_paths:
            media = MediaGroup()
            sent_any_file = False
            for file_path in generated_files_paths:
                if os.path.exists(file_path) and len(media.media) < 10:
                    media.attach_document(InputFile(file_path));
                    sent_any_file = True
                elif os.path.exists(file_path) and len(media.media) == 10:
                    try:
                        await call.bot.send_media_group(chat_id=call.from_user.id, media=media)
                    except Exception:
                        pass
                    media = MediaGroup();
                    media.attach_document(InputFile(file_path))
            if media.media:
                try:
                    await call.bot.send_media_group(chat_id=call.from_user.id, media=media)
                except Exception as e:
                    await call.bot.send_message(call.from_user.id, messages.FILES_SEND_ERROR.format(task_id=task_id,
                                                                                                    error=hd.quote(
                                                                                                        str(e))),
                                                reply_markup=reply_markup_after_generation, parse_mode=ParseMode.HTML)
            elif not sent_any_file and generated_files_paths:
                await call.bot.send_message(call.from_user.id,
                                            messages.NO_FILES_TO_SEND_WARNING.format(task_id=task_id),
                                            reply_markup=reply_markup_after_generation)
        elif result.get("status") == "success":  # Успех, но нет файлов (например, пустой результат генерации)
            await call.bot.send_message(call.from_user.id, messages.NO_FILES_TO_SEND_WARNING.format(
                task_id=task_id) + " (Результат генерации пуст)", reply_markup=reply_markup_after_generation)

    elif result.get("status") == "error":
        error_msg_from_core = result.get("message", "Неизвестная ошибка ядра.")
        safe_error_msg = hd.quote(error_msg_from_core)
        db.update_task_status(task_id, "failed", error_msg_from_core)
        await call.bot.send_message(call.from_user.id,
                                    messages.GENERATION_FAILED.format(task_id=task_id, error_message=safe_error_msg),
                                    reply_markup=reply_markup_after_generation, parse_mode=ParseMode.HTML)

    elif result.get("status") == "warning":  # Если сам парсер или ядро вернули warning как основной статус
        warning_msg_from_core = result.get("message", "Неизвестное предупреждение ядра.")
        safe_warning_msg = hd.quote(warning_msg_from_core)
        db.update_task_status(task_id, "completed_with_warnings", warning_msg_from_core)
        await call.bot.send_message(call.from_user.id, messages.GENERATION_WARNING.format(task_id=task_id,
                                                                                          warning_message=safe_warning_msg),
                                    reply_markup=reply_markup_after_generation, parse_mode=ParseMode.HTML)
        # Логика отправки файлов, если они есть при warning от ядра
        generated_files_paths = result.get("files", [])
        if generated_files_paths:
            media = MediaGroup()
            sent_any_file = False
            for file_path in generated_files_paths:
                if os.path.exists(file_path) and len(media.media) < 10:
                    media.attach_document(InputFile(file_path));
                    sent_any_file = True
                elif os.path.exists(file_path) and len(media.media) == 10:
                    try:
                        await call.bot.send_media_group(chat_id=call.from_user.id, media=media)
                    except Exception:
                        pass
                    media = MediaGroup();
                    media.attach_document(InputFile(file_path))
            if media.media:
                try:
                    await call.bot.send_media_group(chat_id=call.from_user.id, media=media)
                except Exception:
                    pass
            elif not sent_any_file:
                await call.bot.send_message(call.from_user.id,
                                            messages.NO_FILES_TO_SEND_WARNING.format(task_id=task_id),
                                            reply_markup=reply_markup_after_generation)


@active_user_only
async def process_any_document_without_state(message: types.Message, state: FSMContext, **kwargs):
    await message.reply(messages.WAITING_FOR_FILE_REMINDER, reply_markup=keyboards.main_menu_kb(),
                        parse_mode=ParseMode.HTML)


def register_schedule_handlers(dp: Dispatcher):
    dp.register_message_handler(cmd_new_schedule, Command(commands=['new_schedule']), state="*")
    dp.register_message_handler(cmd_new_schedule, Text(equals="📅 Новое расписание", ignore_case=True), state="*")
    dp.register_message_handler(process_groups_file, state=ScheduleCreationStates.waiting_for_groups_file,
                                content_types=ContentType.DOCUMENT)
    dp.register_message_handler(process_weekdays_file, state=ScheduleCreationStates.waiting_for_weekdays_file,
                                content_types=ContentType.DOCUMENT)
    dp.register_message_handler(
        lambda msg: msg.answer(messages.WAITING_FOR_FILE_REMINDER, reply_markup=keyboards.cancel_state_kb(),
                               parse_mode=ParseMode.HTML),
        state=[ScheduleCreationStates.waiting_for_groups_file, ScheduleCreationStates.waiting_for_weekdays_file],
        content_types=ContentType.ANY)
    dp.register_callback_query_handler(callback_run_generation, Text(startswith="run_task_"),
                                       state=ScheduleCreationStates.confirm_generation)
    dp.register_callback_query_handler(callback_run_generation, Text(startswith="run_task_"), state=None)
    dp.register_message_handler(process_any_document_without_state, content_types=ContentType.DOCUMENT, state=None)