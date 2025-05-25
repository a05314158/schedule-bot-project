import os
import copy
import random
import traceback
import logging
from aiogram.utils.markdown import html_decoration as hd
from .parser import load_and_parse_data
from .additional_functions import (load_subject_equipment_requirements_from_file,
                                   load_special_room_assignments_from_file, create_pairs_groups_data,
                                   create_group_workday_times_dict, create_group_rooms_dict, load_equipment_tag_weights)
from .split_program import split_by_shift, split_by_group_education_level
from .ant_algoritm_weekdays import distribute_lessons_by_days_aco_like, DAYS_OF_WEEK
from .ant_algoritm_main import Scheduler as DailySchedulerACO

try:
    from .transfer_to_table import create_schedule_excel
except ImportError:
    def create_schedule_excel(schedule_data, filename, day_name):
        logging.info(
            f"STUB_EXCEL: Экспорт для '{day_name}' в '{filename}'. Данных: {len(schedule_data) if schedule_data else 0} слотов.")
        pass

logger = logging.getLogger(__name__)


async def generate_full_schedule(
        groups_csv_path: str, weekdays_csv_path: str, output_dir: str,
        progress_callback: callable = None, task_id_for_progress: int = 0,
        filter_target_year_prefixes: list = None, filter_required_room_prefix: str = None,
        aco_weekdays_iterations: int = 100, aco_weekdays_target_daily_total: int = 30,
        aco_weekdays_max_weekday_lessons: int = 2, aco_weekdays_max_weekend_lessons: int = 3,
        aco_weekdays_fitness_variance_penalty: float = 0.1,
        aco_daily_num_ants: int = 10, aco_daily_num_iterations: int = 50,
        aco_daily_evaporation_rate: float = 0.1, aco_daily_pheromone_deposit: float = 100.0,
        aco_daily_alpha: float = 1.0, aco_daily_beta: float = 1.0,
        aco_daily_penalty_unplaced: int = 20, aco_daily_penalty_window: int = 5,
        aco_daily_penalty_max_lessons_coeff: int = 3, aco_daily_soft_limit_max_lessons: int = 4,
        aco_daily_penalty_slot_underutil_coeff: int = 30, aco_daily_slot_util_threshold: float = 0.6,
        default_tag_weight_for_priority_calc: int = 1,
        aco_daily_max_consecutive_lessons: int = 2,  # Новый параметр из предыдущего шага
        aco_daily_penalty_consecutive: int = 7  # Новый параметр из предыдущего шага
) -> dict:
    logger.info(f"Task_{task_id_for_progress}: Начало generate_full_schedule.")
    current_step_msg = "Инициализация..."
    try:
        total_major_steps = 6

        async def update_progress(step_num, message, sub_progress=None, sub_total=None):
            nonlocal current_step_msg;
            current_step_msg = message
            logger.debug(
                f"Task_{task_id_for_progress}: update_progress - step={step_num}, msg='{message}', sub={sub_progress}/{sub_total}")
            if progress_callback:
                progress_bar_fill = min(step_num, total_major_steps)
                progress_bar = "[" + "█" * progress_bar_fill + "░" * (total_major_steps - progress_bar_fill) + "]"
                emoji_map = {0: "⏳", 1: "📄", 2: "⚙️", 3: "🔍", 4: "📦", 5: "🗓️", 6: "📊"}
                step_emoji = emoji_map.get(step_num, "➡️")
                if "Ошибка" in message or "ВНИМАНИЕ" in message: step_emoji = "❗️"
                if "завершена" in message.lower() and step_num == total_major_steps and "ВНИМАНИЕ" not in message: step_emoji = "✅"
                safe_message = hd.quote(message)
                full_message = f"{step_emoji} Задача #{task_id_for_progress}\n{progress_bar} {safe_message}"
                if sub_progress is not None and sub_total is not None and sub_total > 0:
                    sub_bar_len = 10;
                    filled_sub_bar = int((sub_progress / sub_total) * sub_bar_len)
                    sub_bar = "[" + "■" * filled_sub_bar + "□" * (sub_bar_len - filled_sub_bar) + "]"
                    full_message += f"\nДни: {sub_bar} {sub_progress}/{sub_total}"
                await progress_callback(full_message)

        await update_progress(0, "Инициализация...")
        logger.info(f"Task_{task_id_for_progress}: Шаг 1 - Загрузка и парсинг данных.")
        parser_result = load_and_parse_data(groups_csv_path, weekdays_csv_path)
        if parser_result["status"] == "error":
            error_msg = f"Ошибка в файле '{parser_result.get('file_context', 'N/A')}': {parser_result['message']}"
            logger.error(f"Task_{task_id_for_progress}: {error_msg}");
            await update_progress(1, f"Ошибка: {parser_result['message']}")
            return {"status": "error", "message": error_msg}
        raw_groups_data = parser_result["data"]
        logger.info(f"Task_{task_id_for_progress}: Шаг 1 - Данные загружены, {len(raw_groups_data)} групп.")
        await update_progress(1, "Загрузка данных завершена.")
        logger.info(f"Task_{task_id_for_progress}: Шаг 2 - Загрузка конфигураций.")
        equipment_definitions = load_subject_equipment_requirements_from_file()
        special_room_overrides = load_special_room_assignments_from_file()
        tag_weights_map = load_equipment_tag_weights()
        logger.info(
            f"Task_{task_id_for_progress}: Шаг 2 - Конфигурации загружены (оборуд: {len(equipment_definitions)}, спец.ауд: {len(special_room_overrides)}, веса тегов: {len(tag_weights_map)})")
        await update_progress(2, "Загрузка конфигураций завершена.")
        logger.info(f"Task_{task_id_for_progress}: Шаг 3 - Применение фильтров.")
        groups_after_shift_split = split_by_shift(raw_groups_data)
        if filter_target_year_prefixes and filter_required_room_prefix:
            processed_groups_data = split_by_group_education_level(groups_after_shift_split,
                                                                   target_year_prefixes=filter_target_year_prefixes,
                                                                   required_first_digit_of_room=filter_required_room_prefix)
        else:
            processed_groups_data = groups_after_shift_split
        logger.info(f"Task_{task_id_for_progress}: Шаг 3 - Фильтры применены.")
        await update_progress(3, "Применение фильтров к группам завершено.")
        logger.info(f"Task_{task_id_for_progress}: Шаг 4 - Формирование пула уроков.")
        all_lessons_pool_per_group = create_pairs_groups_data(processed_groups_data, equipment_definitions,
                                                              tag_weights_map, default_tag_weight_for_priority_calc)
        total_lessons_to_schedule_overall = sum(len(gl) for gl in all_lessons_pool_per_group.values())
        logger.info(
            f"Task_{task_id_for_progress}: Шаг 4 - Пул уроков сформирован. Всего пар: {total_lessons_to_schedule_overall}")
        if total_lessons_to_schedule_overall == 0:
            await update_progress(total_major_steps, "Нет уроков для планирования.")
            return {"status": "warning", "message": "В загруженных файлах нет уроков для планирования.", "files": []}
        await update_progress(4, f"Пул из {total_lessons_to_schedule_overall} уроков сформирован.")
        logger.info(f"Task_{task_id_for_progress}: Шаг 5 - Распределение квот пар по дням.")
        daily_lessons_quota_distribution = distribute_lessons_by_days_aco_like(processed_groups_data,
                                                                               num_iterations=aco_weekdays_iterations,
                                                                               target_daily_total=aco_weekdays_target_daily_total,
                                                                               max_weekday_lessons_group=aco_weekdays_max_weekday_lessons,
                                                                               max_weekend_lessons_group=aco_weekdays_max_weekend_lessons,
                                                                               fitness_variance_penalty=aco_weekdays_fitness_variance_penalty)
        logger.info(f"Task_{task_id_for_progress}: Шаг 5 - Квоты пар по дням распределены.")
        await update_progress(5, "Распределение квот пар по дням недели завершено.")
        final_weekly_schedule = {};
        generated_excel_files = []
        mutable_lessons_pool = copy.deepcopy(all_lessons_pool_per_group)
        num_week_days = len(DAYS_OF_WEEK)
        logger.info(f"Task_{task_id_for_progress}: Шаг 6 - Начало цикла по дням недели ({num_week_days} дней)")
        for day_idx, day_name in enumerate(DAYS_OF_WEEK):
            logger.debug(f"Task_{task_id_for_progress}:  Планирование дня {day_idx + 1}/{num_week_days} - {day_name}")
            await update_progress(6, f"Планирование дня: {day_name}", sub_progress=day_idx + 1, sub_total=num_week_days)
            lessons_to_schedule_today = {};
            day_quotas = daily_lessons_quota_distribution.get(day_name, {});
            has_lessons_for_any_group_today = False
            if day_quotas:
                logger.debug(f"Task_{task_id_for_progress}:    Квоты на {day_name}: {str(day_quotas)[:200]}...")
                for group_name, num_lessons_quota in day_quotas.items():
                    if num_lessons_quota <= 0: lessons_to_schedule_today.pop(group_name, None); continue
                    group_total_lesson_pool = mutable_lessons_pool.get(group_name, [])
                    selected_lessons_for_group_today = []
                    if not group_total_lesson_pool: logger.warning(
                        f"Task_{task_id_for_progress}: Для группы {group_name} на {day_name} квота {num_lessons_quota}, но уроки в общем пуле закончились."); lessons_to_schedule_today.pop(
                        group_name, None); continue
                    priority_lessons = [];
                    regular_lessons = []
                    for lesson in group_total_lesson_pool:
                        if lesson['name'] in special_room_overrides or lesson.get('placement_priority', 0) > 0:
                            priority_lessons.append(lesson)
                        else:
                            regular_lessons.append(lesson)
                    priority_lessons.sort(key=lambda lsn: (not (lsn['name'] in special_room_overrides),
                                                           -lsn.get('placement_priority', 0)))
                    random.shuffle(regular_lessons)
                    num_to_select_from_priority = min(num_lessons_quota, len(priority_lessons))
                    for _ in range(num_to_select_from_priority):
                        if priority_lessons: selected_lessons_for_group_today.append(priority_lessons.pop(0))
                    remaining_quota = num_lessons_quota - len(selected_lessons_for_group_today)
                    num_to_select_from_regular = min(remaining_quota, len(regular_lessons))
                    for _ in range(num_to_select_from_regular):
                        if regular_lessons: selected_lessons_for_group_today.append(regular_lessons.pop(0))
                    new_pool_for_group = [];
                    new_pool_for_group.extend(priority_lessons);
                    new_pool_for_group.extend(regular_lessons)
                    mutable_lessons_pool[group_name] = new_pool_for_group
                    if selected_lessons_for_group_today:
                        lessons_to_schedule_today[group_name] = selected_lessons_for_group_today;
                        has_lessons_for_any_group_today = True
                        logger.debug(
                            f"Task_{task_id_for_progress}:      Для группы {group_name} на {day_name} выбрано {len(selected_lessons_for_group_today)}/{num_lessons_quota} уроков (приоритет учтен). В общем пуле осталось: {len(mutable_lessons_pool.get(group_name, []))}")
                    if len(
                        selected_lessons_for_group_today) < num_lessons_quota and num_lessons_quota > 0: logger.warning(
                        f"Task_{task_id_for_progress}: Для группы {group_name} на {day_name} квота {num_lessons_quota}, но удалось выбрать только {len(selected_lessons_for_group_today)}.")
            else:
                logger.info(f"Task_{task_id_for_progress}:    На {day_name} нет квот от недельного распределителя.")
            if not has_lessons_for_any_group_today:
                logger.info(f"Task_{task_id_for_progress}:    На {day_name} нет уроков для фактического планирования.")
                final_weekly_schedule[day_name] = {};
                excel_filename_for_day = os.path.join(output_dir, f"{day_name}.xlsx")
                create_schedule_excel({}, excel_filename_for_day, day_name);
                generated_excel_files.append(excel_filename_for_day)
                continue
            group_available_times_today = create_group_workday_times_dict(processed_groups_data, day_name)
            group_available_rooms_today = create_group_rooms_dict(processed_groups_data)
            logger.info(
                f"Task_{task_id_for_progress}:    Запуск DailySchedulerACO для {day_name} с {sum(len(lst) for lst in lessons_to_schedule_today.values())} уроками.")
            daily_scheduler = DailySchedulerACO(
                lessons_for_day_by_group=lessons_to_schedule_today,
                group_available_times_on_day=group_available_times_today,
                group_available_rooms_on_day=group_available_rooms_today,
                special_room_overrides=special_room_overrides,
                num_ants=aco_daily_num_ants,
                num_iterations=aco_daily_num_iterations,
                evaporation_rate=aco_daily_evaporation_rate,
                pheromone_deposit_amount=aco_daily_pheromone_deposit,
                alpha=aco_daily_alpha,
                beta=aco_daily_beta,
                penalty_unplaced_lesson=aco_daily_penalty_unplaced,
                penalty_window_slot=aco_daily_penalty_window,
                penalty_max_lessons_group_soft_coeff=aco_daily_penalty_max_lessons_coeff,
                soft_limit_max_lessons_group=aco_daily_soft_limit_max_lessons,
                penalty_slot_underutilization_coeff=aco_daily_penalty_slot_underutil_coeff,
                slot_utilization_threshold=aco_daily_slot_util_threshold,
                max_consecutive_lessons_for_group=aco_daily_max_consecutive_lessons,
                penalty_consecutive_lessons=aco_daily_penalty_consecutive
            )
            best_schedule_for_this_day = daily_scheduler.run_aco()
            final_weekly_schedule[day_name] = best_schedule_for_this_day
            os.makedirs(output_dir, exist_ok=True);
            excel_filename_for_day = os.path.join(output_dir, f"{day_name}.xlsx")
            create_schedule_excel(best_schedule_for_this_day, excel_filename_for_day, day_name)
            generated_excel_files.append(excel_filename_for_day)
            logger.info(
                f"Task_{task_id_for_progress}:    Расписание на {day_name} создано. Фитнес: {daily_scheduler.best_fitness_for_day if hasattr(daily_scheduler, 'best_fitness_for_day') else 'N/A'}")
        remaining_lessons_overall = sum(len(ll) for ll in mutable_lessons_pool.values() if ll)
        final_user_message = "Генерация успешно завершена!"
        if remaining_lessons_overall > 0:
            final_user_message = f"Генерация завершена. ВНИМАНИЕ: {remaining_lessons_overall} уроков не удалось распределить по дням (возможно, из-за конфликтов или нехватки слотов/аудиторий)."
            logger.warning(f"Task_{task_id_for_progress}: {final_user_message}")
        await update_progress(total_major_steps, final_user_message, sub_progress=num_week_days,
                              sub_total=num_week_days)
        logger.info(f"Task_{task_id_for_progress}: generate_full_schedule успешно завершается. {final_user_message}")
        return {"status": "success", "files": generated_excel_files, "data": final_weekly_schedule,
                "message": final_user_message}
    except Exception as e:
        tb_str = traceback.format_exc()
        error_message_for_user = f"Критическая ошибка на этапе '{current_step_msg}': {type(e).__name__}."
        logger.error(
            f"Task_{task_id_for_progress}: ИСКЛЮЧЕНИЕ в generate_full_schedule на этапе '{current_step_msg}': {e}\n{tb_str}")
        if progress_callback:
            try:
                await progress_callback(
                    f"Задача #{task_id_for_progress}\n[ОШИБКА] {hd.quote(current_step_msg)}: {hd.quote(type(e).__name__)}")
            except Exception:
                pass
        return {"status": "error", "message": error_message_for_user}