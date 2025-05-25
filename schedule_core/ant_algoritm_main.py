import random
import copy
import logging

logger = logging.getLogger(__name__)


class Ant:
    def __init__(self, lessons_to_schedule_for_ant: dict, group_available_times: dict, group_available_rooms: dict,
                 special_room_overrides: dict):
        self.lessons_to_schedule = copy.deepcopy(lessons_to_schedule_for_ant)
        self.group_available_times = copy.deepcopy(group_available_times)
        self.group_available_rooms = copy.deepcopy(group_available_rooms)
        self.special_room_overrides = special_room_overrides
        self.schedule = {}
        self.path = []
        self.fitness = float('inf')
        self.constraints_violated = 0

    def add_lesson_to_schedule(self, time_slot: str, group: str, lesson_info: dict, room_info: dict):
        if time_slot not in self.schedule: self.schedule[time_slot] = []
        self.schedule[time_slot].append({'group': group, 'lesson': lesson_info, 'room': room_info})
        self.path.append((group, lesson_info, time_slot, room_info))


class Scheduler:
    def __init__(self,
                 lessons_for_day_by_group: dict,
                 group_available_times_on_day: dict,
                 group_available_rooms_on_day: dict,
                 special_room_overrides: dict,
                 num_ants: int,
                 num_iterations: int,
                 evaporation_rate: float,
                 pheromone_deposit_amount: float,
                 alpha: float = 1.0,
                 beta: float = 1.0,
                 penalty_unplaced_lesson: int = 20,
                 penalty_window_slot: int = 5,
                 penalty_max_lessons_group_soft_coeff: int = 3,
                 soft_limit_max_lessons_group: int = 4,
                 penalty_slot_underutilization_coeff: int = 30,
                 slot_utilization_threshold: float = 0.6,
                 # Новый параметр для этого улучшения
                 max_consecutive_lessons_for_group: int = 2,
                 # Макс. пар подряд без штрафа (3я и далее будут штрафоваться)
                 penalty_consecutive_lessons: int = 7  # Штраф за каждую "лишнюю" пару подряд
                 ):
        self.lessons_for_day_by_group = lessons_for_day_by_group
        self.group_available_times_on_day = group_available_times_on_day
        self.group_available_rooms_on_day = group_available_rooms_on_day
        self.special_room_overrides = special_room_overrides
        self.num_ants = int(num_ants)
        self.num_iterations = num_iterations
        self.evaporation_rate = evaporation_rate
        self.pheromone_deposit_amount = pheromone_deposit_amount
        self.alpha = alpha
        self.beta = beta
        self.penalty_unplaced_lesson = penalty_unplaced_lesson
        self.penalty_window_slot = penalty_window_slot
        self.penalty_max_lessons_group_soft_coeff = penalty_max_lessons_group_soft_coeff
        self.soft_limit_max_lessons_group = soft_limit_max_lessons_group
        self.penalty_slot_underutilization_coeff = penalty_slot_underutilization_coeff
        self.slot_utilization_threshold = slot_utilization_threshold
        self.max_consecutive_lessons_for_group = max_consecutive_lessons_for_group
        self.penalty_consecutive_lessons = penalty_consecutive_lessons

        self.pheromone_matrix = {}
        self.ants = []
        self.best_schedule_for_day = {}
        self.best_fitness_for_day = float('inf')
        self._initialize_pheromones()

    def _initialize_pheromones(self):
        initial_pheromone_value = 1.0
        for group_name, lessons_list in self.lessons_for_day_by_group.items():
            available_times_for_group = self.group_available_times_on_day.get(group_name, [])
            available_rooms_for_group = self.group_available_rooms_on_day.get(group_name, [])
            if not available_times_for_group or not available_rooms_for_group: continue
            unique_lesson_names_in_group = set()
            for lesson_info in lessons_list: unique_lesson_names_in_group.add(lesson_info['name'])
            for lesson_name_str in unique_lesson_names_in_group:
                pheromone_key = (group_name, lesson_name_str)
                self.pheromone_matrix[pheromone_key] = {}
                for time_slot in available_times_for_group:
                    for room_info in available_rooms_for_group:
                        time_room_key = (time_slot, room_info['name'])
                        self.pheromone_matrix[pheromone_key][time_room_key] = initial_pheromone_value

    def _create_ants(self):
        self.ants = []
        for _ in range(self.num_ants):
            ant = Ant(lessons_to_schedule_for_ant=self.lessons_for_day_by_group,
                      group_available_times=self.group_available_times_on_day,
                      group_available_rooms=self.group_available_rooms_on_day,
                      special_room_overrides=self.special_room_overrides)
            self.ants.append(ant)

    def run_aco(self):
        for iteration in range(self.num_iterations):
            self._create_ants()
            for ant in self.ants:
                self._construct_schedule_for_ant(ant)
                ant.fitness = self._evaluate_schedule(ant.schedule, ant.constraints_violated)
                if ant.fitness < self.best_fitness_for_day:
                    self.best_fitness_for_day = ant.fitness
                    self.best_schedule_for_day = copy.deepcopy(ant.schedule)
            self._update_pheromones()
            if (iteration + 1) % 10 == 0 or iteration == self.num_iterations - 1:
                logger.debug(
                    f"ACO Daily Iteration {iteration + 1}/{self.num_iterations}, Best Fitness: {self.best_fitness_for_day:.2f}")
        if not self.best_schedule_for_day and any(self.lessons_for_day_by_group.values()):
            logger.warning(
                f"Не удалось составить расписание для дня (ACO Daily), хотя были уроки. Фитнес: {self.best_fitness_for_day}")
        return self.best_schedule_for_day

    def _is_placement_valid(self, current_ant_schedule: dict, group_to_place: str, time_slot: str,
                            room_info_to_place: dict, lesson_info_to_place: dict) -> bool:
        if time_slot in current_ant_schedule:
            for scheduled_item in current_ant_schedule[time_slot]:
                if scheduled_item['group'] == group_to_place: return False
        if time_slot in current_ant_schedule:
            for scheduled_item in current_ant_schedule[time_slot]:
                if scheduled_item['room']['name'] == room_info_to_place['name']: return False
        required_tags = lesson_info_to_place.get('required_tags', [])
        if not required_tags: return True
        available_room_tags = set(room_info_to_place.get('tags', []))
        if not all(req_tag in available_room_tags for req_tag in required_tags): return False
        return True

    def _get_target_room_for_special_override(self, lesson_name: str) -> (str | None):
        return self.special_room_overrides.get(lesson_name)

    def _construct_schedule_for_ant(self, ant: Ant):
        all_lessons_to_place_flat = []
        for group, lessons_list in ant.lessons_to_schedule.items():
            for lesson_info in lessons_list: all_lessons_to_place_flat.append((group, lesson_info))
        random.shuffle(all_lessons_to_place_flat)
        for group_name, lesson_info in all_lessons_to_place_flat:
            lesson_name_str = lesson_info['name']
            possible_time_room_choices = []
            override_room_name = self._get_target_room_for_special_override(lesson_name_str)
            target_room_info_from_override = None
            if override_room_name:
                for r_info in ant.group_available_rooms.get(group_name, []):
                    if r_info['name'] == override_room_name:
                        target_room_info_from_override = r_info;
                        break
                if not target_room_info_from_override:
                    ant.constraints_violated += 100;
                    continue
            available_times = ant.group_available_times.get(group_name, [])
            available_rooms = ant.group_available_rooms.get(group_name, [])
            pheromone_key_for_lesson = (group_name, lesson_name_str)
            pheromone_values_for_lesson = self.pheromone_matrix.get(pheromone_key_for_lesson, {})
            for time_slot_option in available_times:
                rooms_to_consider_for_time = [
                    target_room_info_from_override] if target_room_info_from_override else available_rooms
                for room_info_option in rooms_to_consider_for_time:
                    if self._is_placement_valid(ant.schedule, group_name, time_slot_option, room_info_option,
                                                lesson_info):
                        pheromone_val = pheromone_values_for_lesson.get((time_slot_option, room_info_option['name']),
                                                                        1.0)
                        heuristic_val = 1.0
                        prob_score = (pheromone_val ** self.alpha) * (heuristic_val ** self.beta)
                        possible_time_room_choices.append(((time_slot_option, room_info_option), prob_score))
            if not possible_time_room_choices:
                ant.constraints_violated += 10;
                continue
            total_prob_score = sum(score for _, score in possible_time_room_choices)
            chosen_time_slot, chosen_room_info = None, None
            if total_prob_score == 0:
                if possible_time_room_choices:
                    chosen_time_slot, chosen_room_info = \
                    random.choice([item for item, score in possible_time_room_choices])[0]
                else:
                    ant.constraints_violated += 10; continue
            else:
                rand_val = random.uniform(0, total_prob_score)
                current_sum = 0
                for (time_r_pair, score) in possible_time_room_choices:
                    current_sum += score
                    if current_sum >= rand_val: chosen_time_slot, chosen_room_info = time_r_pair; break
                if chosen_time_slot is None and possible_time_room_choices:
                    chosen_time_slot, chosen_room_info = possible_time_room_choices[-1][0]
                elif chosen_time_slot is None:
                    ant.constraints_violated += 10; continue
            ant.add_lesson_to_schedule(chosen_time_slot, group_name, lesson_info, chosen_room_info)

    def _get_time_slot_index(self, time_slot: str, all_day_slots_sorted: list) -> int:
        try:
            return all_day_slots_sorted.index(time_slot)
        except ValueError:
            return -1

    def _evaluate_schedule(self, schedule: dict, constraints_violated_penalty: int) -> float:
        fitness = float(constraints_violated_penalty)
        total_lessons_to_place = sum(len(l_list) for l_list in self.lessons_for_day_by_group.values())
        placed_lessons_count = sum(len(items_in_slot) for items_in_slot in schedule.values())
        unplaced_lessons = total_lessons_to_place - placed_lessons_count
        fitness += unplaced_lessons * self.penalty_unplaced_lesson

        unique_day_time_slots_set = set()
        for group_slots in self.group_available_times_on_day.values():
            unique_day_time_slots_set.update(group_slots)
        all_day_slots_sorted = sorted(list(unique_day_time_slots_set))

        for group_name in self.lessons_for_day_by_group.keys():
            group_lessons_indices = []
            for time_slot, lessons_at_time in schedule.items():
                for lesson_item in lessons_at_time:
                    if lesson_item['group'] == group_name:
                        slot_idx = self._get_time_slot_index(time_slot, all_day_slots_sorted)
                        if slot_idx != -1: group_lessons_indices.append(slot_idx)
            if not group_lessons_indices: continue
            group_lessons_indices.sort()

            window_penalty = 0
            consecutive_lessons_count = 0
            max_consecutive_run = 0

            if group_lessons_indices:  # Если у группы вообще есть пары
                consecutive_lessons_count = 1  # Начинаем с первой пары
                max_consecutive_run = 1
                for i in range(len(group_lessons_indices) - 1):
                    diff = group_lessons_indices[i + 1] - group_lessons_indices[i]
                    if diff > 1:  # Окно
                        window_penalty += (diff - 1) * self.penalty_window_slot
                        if consecutive_lessons_count > self.max_consecutive_lessons_for_group:
                            fitness += (
                                                   consecutive_lessons_count - self.max_consecutive_lessons_for_group) * self.penalty_consecutive_lessons
                        consecutive_lessons_count = 1  # Сбрасываем счетчик пар подряд
                    else:  # diff == 1, пары подряд
                        consecutive_lessons_count += 1
                    max_consecutive_run = max(max_consecutive_run, consecutive_lessons_count)

                # Проверяем последнюю серию пар подряд
                if consecutive_lessons_count > self.max_consecutive_lessons_for_group:
                    fitness += (
                                           consecutive_lessons_count - self.max_consecutive_lessons_for_group) * self.penalty_consecutive_lessons

            fitness += window_penalty

            if len(group_lessons_indices) > self.soft_limit_max_lessons_group:
                fitness += (
                                       len(group_lessons_indices) - self.soft_limit_max_lessons_group) * self.penalty_max_lessons_group_soft_coeff

        total_possible_placements = sum(len(times) for times in self.group_available_times_on_day.values())
        utilization_ratio = placed_lessons_count / total_possible_placements if total_possible_placements > 0 else 1.0
        if utilization_ratio < self.slot_utilization_threshold:
            fitness += (1.0 - utilization_ratio) * self.penalty_slot_underutilization_coeff

        for time_slot, scheduled_items_at_time in schedule.items():
            groups_at_time = set();
            rooms_at_time = set()
            for item in scheduled_items_at_time:
                if item['group'] in groups_at_time: fitness += 1000
                groups_at_time.add(item['group'])
                if item['room']['name'] in rooms_at_time: fitness += 1000
                rooms_at_time.add(item['room']['name'])
        return fitness

    def _update_pheromones(self):
        for pheromone_key, time_room_map in self.pheromone_matrix.items():
            for time_room_key, value in time_room_map.items():
                self.pheromone_matrix[pheromone_key][time_room_key] *= (1.0 - self.evaporation_rate)
        ants_to_deposit = sorted(self.ants, key=lambda ant: ant.fitness)
        num_best_ants = max(1, int(0.1 * self.num_ants))
        for ant in ants_to_deposit[:num_best_ants]:
            if ant.fitness == float('inf'): continue
            pheromone_add = self.pheromone_deposit_amount / (ant.fitness + 1e-9)
            for group_name, lesson_info, time_slot, room_info in ant.path:
                lesson_name_str = lesson_info['name']
                pheromone_key = (group_name, lesson_name_str)
                time_room_key = (time_slot, room_info['name'])
                if pheromone_key in self.pheromone_matrix and time_room_key in self.pheromone_matrix[pheromone_key]:
                    self.pheromone_matrix[pheromone_key][time_room_key] += pheromone_add