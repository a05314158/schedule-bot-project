import asyncio
import logging
from schedule_core.main_timetable import generate_full_schedule
from bot.config import CORE_CONFIGS_DIR

logger = logging.getLogger(__name__)


async def run_schedule_generation_async(
        groups_file_path: str,
        weekdays_file_path: str,
        output_dir: str,
        task_id: int,
        progress_callback: callable = None,
        custom_params: dict | None = None
) -> dict:
    logger.debug(f"DEBUG_RUNNER: algorithm_runner вызван для task_id={task_id} с custom_params: {custom_params}")
    loop = asyncio.get_event_loop()
    default_algo_params = {
        "filter_target_year_prefixes": None, "filter_required_room_prefix": None,
        "aco_weekdays_iterations": 75, "aco_weekdays_target_daily_total": 30,
        "aco_weekdays_max_weekday_lessons": 2, "aco_weekdays_max_weekend_lessons": 3,
        "aco_weekdays_fitness_variance_penalty": 0.1,
        "aco_daily_num_ants": 10, "aco_daily_num_iterations": 30,
        "aco_daily_evaporation_rate": 0.1, "aco_daily_pheromone_deposit": 100.0,
        "aco_daily_alpha": 1.0, "aco_daily_beta": 1.0,
        "aco_daily_penalty_unplaced": 20, "aco_daily_penalty_window": 5,
        "aco_daily_penalty_max_lessons_coeff": 3, "aco_daily_soft_limit_max_lessons": 4,
        "aco_daily_penalty_slot_underutil_coeff": 30, "aco_daily_slot_util_threshold": 0.6,
        "default_tag_weight_for_priority_calc": 1,
        "aco_daily_max_consecutive_lessons": 2,  # Новый
        "aco_daily_penalty_consecutive": 7  # Новый
    }
    current_algo_params = default_algo_params.copy()
    if custom_params: current_algo_params.update(custom_params)
    try:
        logger.debug(f"DEBUG_RUNNER: Перед вызовом (await) generate_full_schedule с параметрами: {current_algo_params}")
        result = await generate_full_schedule(
            groups_file_path, weekdays_file_path, output_dir,
            progress_callback, task_id,
            filter_target_year_prefixes=current_algo_params["filter_target_year_prefixes"],
            filter_required_room_prefix=current_algo_params["filter_required_room_prefix"],
            aco_weekdays_iterations=current_algo_params["aco_weekdays_iterations"],
            aco_weekdays_target_daily_total=current_algo_params["aco_weekdays_target_daily_total"],
            aco_weekdays_max_weekday_lessons=current_algo_params["aco_weekdays_max_weekday_lessons"],
            aco_weekdays_max_weekend_lessons=current_algo_params["aco_weekdays_max_weekend_lessons"],
            aco_weekdays_fitness_variance_penalty=current_algo_params["aco_weekdays_fitness_variance_penalty"],
            aco_daily_num_ants=current_algo_params["aco_daily_num_ants"],
            aco_daily_num_iterations=current_algo_params["aco_daily_num_iterations"],
            aco_daily_evaporation_rate=current_algo_params["aco_daily_evaporation_rate"],
            aco_daily_pheromone_deposit=current_algo_params["aco_daily_pheromone_deposit"],
            aco_daily_alpha=current_algo_params["aco_daily_alpha"],
            aco_daily_beta=current_algo_params["aco_daily_beta"],
            aco_daily_penalty_unplaced=current_algo_params["aco_daily_penalty_unplaced"],
            aco_daily_penalty_window=current_algo_params["aco_daily_penalty_window"],
            aco_daily_penalty_max_lessons_coeff=current_algo_params["aco_daily_penalty_max_lessons_coeff"],
            aco_daily_soft_limit_max_lessons=current_algo_params["aco_daily_soft_limit_max_lessons"],
            aco_daily_penalty_slot_underutil_coeff=current_algo_params["aco_daily_penalty_slot_underutil_coeff"],
            aco_daily_slot_util_threshold=current_algo_params["aco_daily_slot_util_threshold"],
            default_tag_weight_for_priority_calc=current_algo_params["default_tag_weight_for_priority_calc"],
            aco_daily_max_consecutive_lessons=current_algo_params["aco_daily_max_consecutive_lessons"],  # Новый
            aco_daily_penalty_consecutive=current_algo_params["aco_daily_penalty_consecutive"]  # Новый
        )
        logger.debug(
            f"DEBUG_RUNNER: Прямой вызов (await) generate_full_schedule завершен. Результат: {result.get('status')}")
        return result
    except Exception as e:
        import traceback
        logger.error(f"DEBUG_RUNNER: ИСКЛЮЧЕНИЕ при вызове generate_full_schedule: {e}", exc_info=True)
        return {"status": "error", "message": f"Внутренняя ошибка runner: {type(e).__name__}"}