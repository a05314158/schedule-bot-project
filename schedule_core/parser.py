import pandas as pd
import re
import os
import logging

logger = logging.getLogger(__name__)  # Логгер для этого модуля


def create_free_times_from_df(df_weekdays: pd.DataFrame) -> dict | tuple[None, str]:
    free_times = {}
    try:
        day_col_name = df_weekdays.columns[0]
        time_col_name = df_weekdays.columns[1]
        for i in range(df_weekdays.shape[0]):
            day_name_raw = df_weekdays.iloc[i][day_col_name]
            times_str_raw = df_weekdays.iloc[i][time_col_name]
            if pd.isna(day_name_raw): continue
            day_name = str(day_name_raw).strip()
            if pd.isna(times_str_raw):
                free_times[day_name] = []
                logger.warning(f"Нет временных слотов для дня '{day_name}' в файле дней недели.")
            else:
                free_times[day_name] = [time.strip() for time in str(times_str_raw).split(",")]
        return free_times
    except IndexError:
        return None, "Файл дней недели должен содержать как минимум колонки 'день недели' и 'время пар'."
    except Exception as e:
        logger.error(f"Неожиданная ошибка в create_free_times_from_df: {e}")
        return None, f"Внутренняя ошибка при обработке временных слотов: {e}"


def get_common_available_rooms_with_tags(df_weekdays: pd.DataFrame) -> list | tuple[None, str]:
    rooms_data = []
    try:
        if df_weekdays.shape[0] == 0: return []  # Не ошибка, просто нет данных
        rooms_col_name = df_weekdays.columns[2]
        tags_col_name = df_weekdays.columns[3] if df_weekdays.shape[1] > 3 else None
        if pd.notna(df_weekdays.iloc[0][rooms_col_name]):
            rooms_str_list = [room.strip() for room in str(df_weekdays.iloc[0][rooms_col_name]).split(",")]
            tags_list_for_rooms_input = []
            if tags_col_name and pd.notna(df_weekdays.iloc[0][tags_col_name]):
                raw_tags_groups = [group.strip() for group in str(df_weekdays.iloc[0][tags_col_name]).split(',')]
                for group_tags_str in raw_tags_groups:
                    tags_list_for_rooms_input.append(
                        [tag.strip().lower() for tag in group_tags_str.split(';') if tag.strip()])

            if tags_col_name and rooms_str_list and tags_list_for_rooms_input and len(rooms_str_list) != len(
                    tags_list_for_rooms_input):
                logger.warning(
                    f"Количество аудиторий ({len(rooms_str_list)}) не совпадает с количеством групп тегов ({len(tags_list_for_rooms_input)}) в файле '{df_weekdays.attrs.get('filename', 'дней недели')}'.")

            for i, room_name in enumerate(rooms_str_list):
                room_tags = ['общая']
                if i < len(tags_list_for_rooms_input) and tags_list_for_rooms_input[i]:
                    room_tags = tags_list_for_rooms_input[i]
                rooms_data.append({'name': room_name, 'tags': room_tags})
        else:
            logger.warning(
                f"Не найден столбец или данные для доступных аудиторий в файле '{df_weekdays.attrs.get('filename', 'дней недели')}'.")
        return rooms_data
    except IndexError:
        return None, "Файл дней недели должен содержать как минимум 3 колонки ('день недели', 'время пар', 'доступные аудитории')."
    except Exception as e:
        logger.error(f"Неожиданная ошибка в get_common_available_rooms_with_tags: {e}")
        return None, f"Внутренняя ошибка при обработке аудиторий: {e}"


def create_groups_from_df(df_groups: pd.DataFrame, df_weekdays: pd.DataFrame) -> dict | tuple[None, str]:
    groups = {}

    free_times_result = create_free_times_from_df(df_weekdays)
    if isinstance(free_times_result, tuple): return None, free_times_result[1]  # Ошибка из create_free_times_from_df
    free_times_map = free_times_result

    rooms_result = get_common_available_rooms_with_tags(df_weekdays)
    if isinstance(rooms_result, tuple): return None, rooms_result[1]  # Ошибка из get_common_available_rooms_with_tags
    common_rooms_with_tags = rooms_result

    try:
        group_col_name = df_groups.columns[0]
        shift_col_name = df_groups.columns[1]
        lessons_col_name = df_groups.columns[2]

        for i in range(df_groups.shape[0]):
            row_num_for_error = i + 2  # Номер строки в Excel/CSV (1-based + заголовок)
            group_name_raw = df_groups.iloc[i][group_col_name]
            shift_raw = df_groups.iloc[i][shift_col_name]
            lessons_str_raw = df_groups.iloc[i][lessons_col_name]

            if pd.isna(group_name_raw):
                logger.warning(f"Пропущена строка {row_num_for_error} в файле групп: отсутствует название группы.")
                continue
            group_name = str(group_name_raw).strip()

            try:
                shift = int(shift_raw)
            except ValueError:
                logger.warning(
                    f"Неверный формат смены '{shift_raw}' для группы '{group_name}' (строка {row_num_for_error}). Используется смена 0.")
                shift = 0

            lessons_count_map = {}
            if pd.notna(lessons_str_raw):
                lessons_str = str(lessons_str_raw).strip('"')
                raw_lesson_entries = lessons_str.split(',')
                processed_lesson_entries = []
                current_lesson_buffer = ""
                for entry_part in raw_lesson_entries:
                    current_lesson_buffer += entry_part
                    if re.search(r":\s*\d+\s*$", entry_part.strip()):
                        processed_lesson_entries.append(current_lesson_buffer.strip())
                        current_lesson_buffer = ""
                    else:
                        current_lesson_buffer += ","
                if current_lesson_buffer.strip():  # Обработка последнего элемента, если он не завершен запятой
                    if re.search(r":\s*\d+\s*$", current_lesson_buffer.strip()):
                        processed_lesson_entries.append(current_lesson_buffer.strip())
                    else:
                        logger.warning(
                            f"Не удалось полностью разобрать строку предметов для группы '{group_name}' (строка {row_num_for_error}): '{current_lesson_buffer.strip()}'")

                for lesson_entry_full in processed_lesson_entries:
                    match = re.search(r'^(.*):\s*(\d+)$', lesson_entry_full.strip())
                    if match:
                        lesson_full_name = match.group(1).strip()
                        count_str = match.group(2).strip()
                        try:
                            lessons_count_map[lesson_full_name] = int(count_str)
                        except ValueError:
                            logger.warning(
                                f"Неверное количество для предмета '{lesson_full_name}' группы '{group_name}' (строка {row_num_for_error}). Предмет пропущен.")
                    elif lesson_entry_full.strip():  # Если не пусто, но не соответствует
                        logger.warning(
                            f"Неверный формат записи предмета: '{lesson_entry_full}' для группы '{group_name}' (строка {row_num_for_error}). Предмет пропущен.")

            parametrs = [free_times_map.copy(), shift, [room.copy() for room in common_rooms_with_tags],
                         lessons_count_map]
            groups[group_name] = parametrs
        return groups
    except IndexError:
        return None, "Файл групп должен содержать как минимум колонки: 'группа', 'смена', 'предмет (преподаватель): кол-во в неделю'."
    except Exception as e:
        logger.error(f"Неожиданная ошибка в create_groups_from_df: {e}", exc_info=True)
        return None, f"Внутренняя ошибка при формировании данных групп: {e}"


def read_data_file(file_path: str) -> pd.DataFrame | tuple[None, str]:
    filename, file_extension = os.path.splitext(file_path)
    file_extension = file_extension.lower()
    df = None
    try:
        if file_extension == '.csv':
            df = pd.read_csv(file_path)
        elif file_extension == '.xlsx':
            df = pd.read_excel(file_path, engine='openpyxl')
        else:
            return None, f"Неподдерживаемое расширение файла: '{file_extension}'. Допустимы .csv и .xlsx."
        if df is not None:
            df.attrs['filename'] = os.path.basename(file_path)
            return df
        else:  # Should not happen if extension is correct and no exception
            return None, f"Не удалось прочитать файл {os.path.basename(file_path)} неизвестная ошибка."
    except FileNotFoundError:
        return None, f"Файл не найден: {os.path.basename(file_path)}"
    except pd.errors.EmptyDataError:
        return None, f"Файл {os.path.basename(file_path)} пуст."
    except ValueError as ve:  # Например, если XLSX поврежден или не Excel
        if "Excel file format cannot be determined" in str(ve) or "File is not a zip file" in str(ve):
            return None, f"Файл {os.path.basename(file_path)} не является корректным XLSX файлом или поврежден."
        return None, f"Ошибка значения при чтении файла {os.path.basename(file_path)}: {ve}"
    except Exception as e:
        logger.error(f"Ошибка при чтении файла {file_path}: {e}", exc_info=True)
        return None, f"Ошибка при чтении файла {os.path.basename(file_path)}: {type(e).__name__}."


def load_and_parse_data(groups_file_path: str, weekdays_file_path: str) -> dict:
    logger.info(f"Начало загрузки и парсинга файлов: Группы='{groups_file_path}', Дни='{weekdays_file_path}'")

    result_df_groups = read_data_file(groups_file_path)
    if isinstance(result_df_groups, tuple):  # Значит, вернулась ошибка (None, "сообщение")
        return {"status": "error", "message": result_df_groups[1], "file_context": os.path.basename(groups_file_path)}
    df_groups = result_df_groups

    result_df_weekdays = read_data_file(weekdays_file_path)
    if isinstance(result_df_weekdays, tuple):
        return {"status": "error", "message": result_df_weekdays[1],
                "file_context": os.path.basename(weekdays_file_path)}
    df_weekdays = result_df_weekdays

    expected_groups_cols = ['группа', 'смена', 'предмет (преподаватель): кол-во в неделю']
    min_expected_weekdays_cols = ['день недели', 'время пар', 'доступные аудитории']

    actual_groups_cols = [str(col).strip() for col in df_groups.columns]
    actual_weekdays_cols = [str(col).strip() for col in df_weekdays.columns]

    missing_groups_cols = [col for col in expected_groups_cols if col not in actual_groups_cols]
    if missing_groups_cols:
        return {"status": "error", "message": f"Отсутствуют обязательные колонки: {', '.join(missing_groups_cols)}.",
                "file_context": df_groups.attrs.get('filename')}

    missing_weekdays_cols = [col for col in min_expected_weekdays_cols if col not in actual_weekdays_cols]
    if missing_weekdays_cols:
        return {"status": "error", "message": f"Отсутствуют обязательные колонки: {', '.join(missing_weekdays_cols)}.",
                "file_context": df_weekdays.attrs.get('filename')}

    if len(actual_weekdays_cols) < 3:  # Эта проверка дублирует предыдущую, но оставим на всякий случай
        return {"status": "error", "message": "Файл дней недели должен содержать как минимум 3 колонки.",
                "file_context": df_weekdays.attrs.get('filename')}
    if len(actual_weekdays_cols) < 4:
        logger.warning(
            f"В файле дней недели ('{df_weekdays.attrs.get('filename')}') отсутствует колонка для тегов оборудования. Аудиториям будут присвоены теги 'общая'.")

    logger.info("Проверка колонок пройдена. Создание структуры групп...")
    parsed_groups_data_result = create_groups_from_df(df_groups, df_weekdays)

    if isinstance(parsed_groups_data_result, tuple):  # Ошибка из create_groups_from_df
        return {"status": "error", "message": parsed_groups_data_result[1], "file_context": "Оба файла (логика)"}

    parsed_groups_data = parsed_groups_data_result
    if not parsed_groups_data:  # Если create_groups_from_df вернул пустой словарь (маловероятно, если нет ошибок)
        logger.warning("Парсер не вернул данные групп, хотя ошибок не было.")
        return {"status": "error", "message": "Не удалось извлечь данные о группах, хотя файлы прочитаны.",
                "file_context": "Оба файла (логика)"}

    logger.info(f"Парсинг успешно завершен. Загружено {len(parsed_groups_data)} групп.")
    return {"status": "success", "data": parsed_groups_data}