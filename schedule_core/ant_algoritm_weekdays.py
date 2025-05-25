import random
import copy
import logging

logger = logging.getLogger(__name__)

DAYS_OF_WEEK = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
WEEKEND_DAYS = ["Суббота", "Воскресенье"]

def calculate_total_lessons_per_group(groups_data: dict) -> dict:
    group_total_lessons = {}
    if not groups_data: return group_total_lessons
    for group_name, settings in groups_data.items():
        if not isinstance(settings, list) or len(settings) < 4:
            group_total_lessons[group_name] = 0; continue
        lessons_count_map = settings[3]
        if not isinstance(lessons_count_map, dict):
            group_total_lessons[group_name] = 0; continue
        group_total_lessons[group_name] = sum(lessons_count_map.values())
    return group_total_lessons

def calculate_schedule_fitness_weekdays(daily_distribution: list, target_daily_sum: int, variance_penalty_factor: float = 0.1) -> float:
    fitness = 0.0
    num_days = len(DAYS_OF_WEEK)
    if len(daily_distribution) != num_days: return float('inf')
    daily_total_lessons_sum = [0.0] * num_days
    for day_index, day_schedule_map in enumerate(daily_distribution):
        if not isinstance(day_schedule_map, dict): continue
        current_day_total = sum(day_schedule_map.values())
        daily_total_lessons_sum[day_index] = current_day_total
        fitness += abs(current_day_total - target_daily_sum)
    if target_daily_sum > 0 and num_days > 0 :
        mean_daily_load = sum(daily_total_lessons_sum) / num_days
        variance = sum([(load - mean_daily_load) ** 2 for load in daily_total_lessons_sum]) / num_days
        fitness += variance * variance_penalty_factor
    return fitness

def create_random_daily_distribution(group_total_lessons_map: dict, days_list: list, max_weekday_lessons: int, max_weekend_lessons: int, weekend_days_list: list) -> list:
    num_days = len(days_list)
    daily_schedule_template = [{} for _ in range(num_days)]
    # remaining_lessons_per_group = copy.deepcopy(group_total_lessons_map) # Не используется, можно удалить
    for group_name, total_lessons_for_group in group_total_lessons_map.items():
        lessons_to_distribute_for_current_group = total_lessons_for_group
        for day_idx in range(num_days): daily_schedule_template[day_idx][group_name] = 0
        attempts_per_group = 0
        max_attempts_per_group = total_lessons_for_group * num_days * 3 # Увеличил немного для надежности
        while lessons_to_distribute_for_current_group > 0 and attempts_per_group < max_attempts_per_group:
            attempts_per_group += 1
            day_index_to_try = random.randint(0, num_days - 1)
            day_name_to_try = days_list[day_index_to_try]
            max_lessons_on_this_day_for_group = max_weekend_lessons if day_name_to_try in weekend_days_list else max_weekday_lessons
            current_lessons_on_day_for_group = daily_schedule_template[day_index_to_try].get(group_name, 0)
            if current_lessons_on_day_for_group < max_lessons_on_this_day_for_group:
                can_add_on_day = max_lessons_on_this_day_for_group - current_lessons_on_day_for_group
                num_to_add = min(can_add_on_day, lessons_to_distribute_for_current_group)
                if num_to_add > 0:
                    daily_schedule_template[day_index_to_try][group_name] += num_to_add
                    lessons_to_distribute_for_current_group -= num_to_add
        if lessons_to_distribute_for_current_group > 0:
            logger.warning(f"Не удалось полностью распределить {lessons_to_distribute_for_current_group} пар для группы {group_name} по дням.")
    return daily_schedule_template

def distribute_lessons_by_days_aco_like(
    groups_data: dict,
    num_iterations: int,
    target_daily_total: int,
    max_weekday_lessons_group: int,
    max_weekend_lessons_group: int,
    fitness_variance_penalty: float = 0.1
    ) -> dict:
    if not groups_data: return {}
    group_total_lessons = calculate_total_lessons_per_group(groups_data)
    if not group_total_lessons or all(v == 0 for v in group_total_lessons.values()):
        logger.info("distribute_lessons_by_days_aco_like: Нет уроков для распределения.")
        return {day: {} for day in DAYS_OF_WEEK}
    best_distribution_raw = None
    best_fitness = float('inf')
    logger.debug(f"distribute_lessons_by_days_aco_like: Запуск {num_iterations} итераций.")
    for iteration in range(num_iterations):
        current_distribution_raw = create_random_daily_distribution(group_total_lessons, DAYS_OF_WEEK, max_weekday_lessons_group, max_weekend_lessons_group, WEEKEND_DAYS)
        current_fitness = calculate_schedule_fitness_weekdays(current_distribution_raw, target_daily_total, fitness_variance_penalty)
        if current_fitness < best_fitness:
            best_fitness = current_fitness
            best_distribution_raw = current_distribution_raw
            logger.debug(f"distribute_lessons_by_days_aco_like: Итерация {iteration + 1}, новый лучший фитнес: {best_fitness:.2f}")
    final_distribution_map = {}
    if best_distribution_raw:
        for day_index, day_data_map in enumerate(best_distribution_raw):
            day_name = DAYS_OF_WEEK[day_index]
            final_distribution_map[day_name] = {group: count for group, count in day_data_map.items() if count > 0}
    else:
        logger.warning("distribute_lessons_by_days_aco_like: Не удалось найти распределение (best_distribution_raw is None).")
        final_distribution_map = {day: {} for day in DAYS_OF_WEEK}
    return final_distribution_map