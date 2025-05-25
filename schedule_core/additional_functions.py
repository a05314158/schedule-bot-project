import pandas as pd
import os
import copy
import logging

logger = logging.getLogger(__name__)
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'configs')

def load_subject_equipment_requirements_from_file(config_file_name="subject_equipment_map.csv") -> dict:
    requirements = {}
    file_path = os.path.join(CONFIG_DIR, config_file_name)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(file_path):
        logger.warning(f"Файл конфигурации требований '{file_path}' не найден. Используются пустые требования.")
        return requirements
    try:
        df_config = pd.read_csv(file_path)
        if df_config.empty or len(df_config.columns) == 0:
            logger.warning(f"Файл конфигурации '{file_path}' пуст или не содержит колонок."); return requirements
        key_col = df_config.columns[0]
        for _, row in df_config.iterrows():
            key_raw = row[key_col]
            if pd.isna(key_raw): continue
            key = str(key_raw).strip().lower()
            if not key: continue
            tags = []
            for i in range(1, len(df_config.columns)):
                tag_col_name = df_config.columns[i]
                tag_raw = row[tag_col_name]
                if pd.notna(tag_raw):
                    tag = str(tag_raw).strip().lower()
                    if tag: tags.append(tag)
            if tags: requirements[key] = tags
    except Exception as e:
        logger.error(f"Ошибка загрузки файла требований к оборудованию '{file_path}': {e}", exc_info=True)
        return {}
    return requirements

def load_special_room_assignments_from_file(config_file_name="special_room_assignments.csv") -> dict:
    assignments = {}
    file_path = os.path.join(CONFIG_DIR, config_file_name)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(file_path):
        logger.warning(f"Файл спец. назначений '{file_path}' не найден. Спец. назначения не будут применены.")
        return assignments
    try:
        df_config = pd.read_csv(file_path)
        if df_config.empty or len(df_config.columns) < 2:
            logger.warning(f"В файле '{file_path}' ожидается >= 2 колонок или файл пуст."); return assignments
        subject_col = df_config.columns[0]
        room_col = df_config.columns[1]
        for _, row in df_config.iterrows():
            subject_name_raw = row[subject_col]
            room_name_raw = row[room_col]
            if pd.isna(subject_name_raw) or pd.isna(room_name_raw): continue
            subject_name = str(subject_name_raw).strip()
            room_name = str(room_name_raw).strip()
            if subject_name and room_name: assignments[subject_name] = room_name
    except Exception as e:
        logger.error(f"Ошибка загрузки файла спец. назначений '{file_path}': {e}", exc_info=True)
        return {}
    return assignments

def load_equipment_tag_weights(config_file_name="equipment_tag_weights.csv") -> dict: # Эта функция была пропущена у вас
    tag_weights = {}
    file_path = os.path.join(CONFIG_DIR, config_file_name)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(file_path):
        logger.warning(f"Файл весов тегов оборудования '{file_path}' не найден. Будут использованы веса по умолчанию (1).")
        return tag_weights
    try:
        df_config = pd.read_csv(file_path)
        if df_config.empty or len(df_config.columns) < 2:
            logger.warning(f"Файл весов тегов '{file_path}' пуст или некорректен (ожидается 'tag_name', 'weight').")
            return tag_weights
        tag_col = df_config.columns[0]
        weight_col = df_config.columns[1]
        for _, row in df_config.iterrows():
            tag_name_raw = row[tag_col]
            weight_raw = row[weight_col]
            if pd.isna(tag_name_raw) or pd.isna(weight_raw): continue
            tag_name = str(tag_name_raw).strip().lower()
            try:
                weight = int(weight_raw)
                if tag_name: tag_weights[tag_name] = weight
            except ValueError:
                logger.warning(f"Некорректный вес '{weight_raw}' для тега '{tag_name}' в файле '{file_path}'.")
    except Exception as e:
        logger.error(f"Ошибка загрузки файла весов тегов оборудования '{file_path}': {e}", exc_info=True)
    return tag_weights

def get_lesson_required_tags_from_definitions(lesson_name: str, equipment_definitions: dict) -> list:
    lesson_name_lower = lesson_name.lower()
    found_tags = set()
    if lesson_name in equipment_definitions:
        req = equipment_definitions[lesson_name]
        if isinstance(req, list): found_tags.update(tag.lower() for tag in req)
        else: found_tags.add(req.lower())
        return list(found_tags)
    elif lesson_name_lower in equipment_definitions:
        req = equipment_definitions[lesson_name_lower]
        if isinstance(req, list): found_tags.update(tag.lower() for tag in req)
        else: found_tags.add(req.lower())
        return list(found_tags)
    sorted_keywords = sorted([k for k in equipment_definitions.keys() if k != lesson_name and k != lesson_name_lower], key=len, reverse=True)
    for keyword in sorted_keywords:
        if keyword in lesson_name_lower:
            tag_or_tags = equipment_definitions[keyword]
            if isinstance(tag_or_tags, list): found_tags.update(t.lower() for t in tag_or_tags)
            else: found_tags.add(tag_or_tags.lower())
    return list(found_tags)

def calculate_lesson_placement_priority(required_tags: list, tag_weights: dict, default_tag_weight: int = 1) -> int: # Эта функция была пропущена
    priority = 0
    if not required_tags: return 0
    for tag in required_tags:
        priority += tag_weights.get(tag.lower(), default_tag_weight)
    return priority

def create_pairs_groups_data(group_data: dict, equipment_definitions_for_tags: dict, tag_weights: dict, default_tag_weight_for_calc: int = 1) -> dict: # Изменена сигнатура
    pairs_groups_data = {}
    if not group_data: return pairs_groups_data
    for group, settings in group_data.items():
        group_pairs_list = []
        lessons_data = settings[3]
        if not isinstance(lessons_data, dict):
            pairs_groups_data[group] = group_pairs_list; continue
        for lesson_name, count in lessons_data.items():
            if not isinstance(count, int) or count < 0: continue
            required_tags = get_lesson_required_tags_from_definitions(lesson_name, equipment_definitions_for_tags)
            placement_priority = calculate_lesson_placement_priority(required_tags, tag_weights, default_tag_weight_for_calc) # Используем новую функцию
            for _ in range(count):
                group_pairs_list.append({'name': lesson_name, 'required_tags': required_tags[:], 'placement_priority': placement_priority})  # Добавлен placement_priority
        pairs_groups_data[group] = group_pairs_list
    return pairs_groups_data

def create_group_workday_times_dict(group_data: dict, target_weekday: str) -> dict:
    group_available_times_on_day = {}
    if not group_data: return group_available_times_on_day
    for group, settings in group_data.items():
        if not isinstance(settings, list) or len(settings) < 1:
            group_available_times_on_day[group] = []; continue
        group_free_times_all_days = settings[0]
        if not isinstance(group_free_times_all_days, dict):
            group_available_times_on_day[group] = []; continue
        if target_weekday in group_free_times_all_days:
            group_available_times_on_day[group] = group_free_times_all_days[target_weekday][:]
        else: group_available_times_on_day[group] = []
    return group_available_times_on_day

def create_group_rooms_dict(group_data: dict) -> dict:
    group_available_rooms_map = {}
    if not group_data: return group_available_rooms_map
    for group, settings in group_data.items():
        if not isinstance(settings, list) or len(settings) < 3:
            group_available_rooms_map[group] = []; continue
        rooms_list = settings[2]
        if not isinstance(rooms_list, list):
            group_available_rooms_map[group] = []; continue
        copied_rooms_list = []
        for room_item in rooms_list:
            if isinstance(room_item, dict): copied_rooms_list.append(room_item.copy())
        group_available_rooms_map[group] = copied_rooms_list
    return group_available_rooms_map