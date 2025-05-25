import pandas as pd
import os

def create_schedule_excel(schedule_data: dict, filename: str, day_name: str):
    if not schedule_data:
        try:
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                empty_df = pd.DataFrame([{"Информация": f"Нет запланированных пар на {day_name}"}])
                empty_df.to_excel(writer, sheet_name="Нет данных", index=False)
        except Exception:
            pass
        return

    try:
        output_dir = os.path.dirname(filename)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with pd.ExcelWriter(filename, engine='openpyxl') as writer:
            sorted_time_slots = sorted(schedule_data.keys())
            if not sorted_time_slots:
                empty_df = pd.DataFrame([{"Информация": f"Нет временных слотов с парами на {day_name}"}])
                empty_df.to_excel(writer, sheet_name="Нет данных", index=False)
                return

            for time_slot in sorted_time_slots:
                lessons_in_slot = schedule_data[time_slot]
                if not lessons_in_slot:
                    df_slot = pd.DataFrame([{"Информация": f"Нет пар в {time_slot}"}])
                else:
                    data_for_df = []
                    for item in lessons_in_slot:
                        group = item.get('group', 'N/A')
                        lesson_info = item.get('lesson', {})
                        room_info = item.get('room', {})
                        lesson_name = lesson_info.get('name', 'N/A')
                        lesson_req_tags = ", ".join(lesson_info.get('required_tags', [])) if lesson_info.get('required_tags') else "-"
                        room_name = room_info.get('name', 'N/A')
                        room_actual_tags = ", ".join(room_info.get('tags', [])) if room_info.get('tags') else "-"
                        data_for_df.append({
                            "Группа": group,
                            "Предмет (Преподаватель)": lesson_name,
                            "Требуемое оборудование": lesson_req_tags,
                            "Аудитория": room_name,
                            "Оборудование аудитории": room_actual_tags
                        })
                    df_slot = pd.DataFrame(data_for_df)
                sheet_name = time_slot.replace(":", "-")
                if len(sheet_name) > 31: sheet_name = sheet_name[:31]
                df_slot.to_excel(writer, sheet_name=sheet_name, index=False)
    except Exception:
        import traceback
        traceback.print_exc()