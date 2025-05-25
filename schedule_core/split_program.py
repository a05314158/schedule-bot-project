# schedule_bot_project/schedule_core/split_program.py

import copy
import re


def split_by_shift(groups_data: dict) -> dict:
    if not groups_data:
        return {}

    updated_groups = {}
    for group_name, settings in groups_data.items():
        if not isinstance(settings, list) or len(settings) < 4:
            updated_groups[group_name] = settings
            continue

        current_free_times = settings[0]
        shift = settings[1]

        group_specific_free_times = {day: times[:] for day, times in current_free_times.items()}

        morning_slots_to_remove_for_shift2 = ["8:30-10:00", "10:20-11:50"]
        evening_slots_to_remove_for_shift1 = ["15:20-16:50", "17:00-18:30", "18:40-20:10"]

        slots_to_remove_current_shift = []
        if shift == 1:
            slots_to_remove_current_shift = evening_slots_to_remove_for_shift1
        elif shift == 2:
            slots_to_remove_current_shift = morning_slots_to_remove_for_shift2

        if slots_to_remove_current_shift:
            for day_key, time_slots_list in group_specific_free_times.items():
                group_specific_free_times[day_key] = [
                    time_slot for time_slot in time_slots_list
                    if time_slot not in slots_to_remove_current_shift
                ]

        new_settings = [group_specific_free_times] + settings[1:]
        updated_groups[group_name] = new_settings

    return updated_groups


def split_by_group_education_level(groups_data: dict,
                                   target_year_prefixes: list = None,
                                   required_first_digit_of_room: str = None) -> dict:
    if not groups_data:
        return {}
    if target_year_prefixes is None or required_first_digit_of_room is None:
        return groups_data

    updated_groups = {}
    for group_name, settings in groups_data.items():
        if not isinstance(settings, list) or len(settings) < 4:
            updated_groups[group_name] = settings
            continue

        applies_to_group = False
        for prefix in target_year_prefixes:
            if prefix in group_name:
                applies_to_group = True
                break

        if applies_to_group:
            current_rooms_with_tags = settings[2]
            filtered_rooms = []
            for room_info in current_rooms_with_tags:
                if isinstance(room_info, dict) and 'name' in room_info:
                    room_name_str = str(room_info['name'])

                    match = re.search(r'\d', room_name_str)
                    room_passes_filter = False
                    if match:
                        first_digit_in_room = room_name_str[match.start()]
                        if first_digit_in_room == required_first_digit_of_room:
                            room_passes_filter = True

                    if room_passes_filter:
                        filtered_rooms.append(room_info.copy())

            new_settings = settings[:2] + [filtered_rooms] + settings[3:]
            updated_groups[group_name] = new_settings
        else:
            updated_groups[group_name] = settings[:]

    return updated_groups