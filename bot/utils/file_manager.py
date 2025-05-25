import os
import shutil
from bot.config import UPLOADS_DIR, GENERATED_SCHEDULES_DIR
from aiogram import Bot
from aiogram.types import Document
import uuid

async def save_uploaded_file(document: Document, bot: Bot, user_id: int, task_id: int) -> dict:
    try:
        file_info = await bot.get_file(document.file_id)
        original_filename = document.file_name or "unknown_file"
        file_extension = os.path.splitext(original_filename)[1].lower()
        allowed_extensions = ['.csv', '.xlsx']
        if file_extension not in allowed_extensions:
            return {"status": "error", "message": f"Неподдерживаемый тип файла: {file_extension}. Допустимы: {', '.join(allowed_extensions)}"}
        unique_id = uuid.uuid4()
        user_task_uploaddir = os.path.join(UPLOADS_DIR, str(user_id), str(task_id))
        os.makedirs(user_task_uploaddir, exist_ok=True)
        safe_original_filename = "".join(c if c.isalnum() or c in ['.', '_', '-'] else '_' for c in original_filename)
        local_file_path = os.path.join(user_task_uploaddir, f"{unique_id}_{safe_original_filename}")
        await bot.download_file(file_info.file_path, local_file_path)
        return {"status": "success", "path": local_file_path}
    except Exception as e:
        return {"status": "error", "message": f"Ошибка при сохранении файла на сервере: {e}"}

def get_output_dir_for_task(user_id: int, task_id: int) -> str:
    task_output_dir = os.path.join(GENERATED_SCHEDULES_DIR, str(user_id), str(task_id))
    os.makedirs(task_output_dir, exist_ok=True)
    return task_output_dir

def cleanup_task_files(user_id: int, task_id: int):
    user_task_uploaddir = os.path.join(UPLOADS_DIR, str(user_id), str(task_id))
    user_task_generateddir = os.path.join(GENERATED_SCHEDULES_DIR, str(user_id), str(task_id))
    try:
        if os.path.exists(user_task_uploaddir):
            shutil.rmtree(user_task_uploaddir)
    except Exception: pass
    try:
        if os.path.exists(user_task_generateddir):
            shutil.rmtree(user_task_generateddir)
    except Exception: pass