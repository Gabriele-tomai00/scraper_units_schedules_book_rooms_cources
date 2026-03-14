import re
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from datetime import date, datetime, timedelta
import json
import requests
from urllib.parse import urlencode, quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils import format_iso_date_to_italian_long, get_day_of_week, extract_time_range, safe
from selenium.webdriver.chrome.options import Options

ROOMS_CALL_URL = "https://orari.units.it/agendaweb/rooms_call.php"


# ---------------------------------------------------------------------------
# Room name cleanup
# ---------------------------------------------------------------------------

def clean_room_name(room_name: str) -> str:
    """Remove trailing site info like '[Edificio H2bis]' from room_name."""
    if not room_name:
        return room_name
    return re.sub(r'\s*\[.*?\]\s*$', '', room_name).strip()


# ---------------------------------------------------------------------------
# Room lookup: fetch rooms_call.php and build two dicts for flexible matching
# ---------------------------------------------------------------------------

def fetch_room_lookup() -> tuple[dict, dict]:
    """
    Fetches rooms_call.php and builds two lookup dicts:
    - by_code: room_code (str)              -> room info dict
    - by_name: cleaned room_name (lowercase) -> room info dict

    The by_name dict is used as fallback when easycourse does not provide
    a room_code (i.e. 'codice aula' is empty or missing).
    Raw structure: { "area_rooms": { <area_code>: { <room_code>: {...} } } }
    """
    try:
        resp = requests.get(ROOMS_CALL_URL, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"WARNING: Could not fetch room data from {ROOMS_CALL_URL}: {e}")
        return {}, {}

    by_code = {}
    by_name = {}

    area_rooms = data.get("area_rooms", {})
    for area_code, rooms in area_rooms.items():
        for room_code, room_info in rooms.items():
            entry = {
                "room_id":    room_info.get("id"),
                "room_name":  clean_room_name(room_info.get("room_name", "")),
                "room_type":  room_info.get("type"),
                "area":       room_info.get("area"),
                "area_code":  room_info.get("area_code"),
                "area_group": room_info.get("area_group_code"),
                "address":    room_info.get("address"),
                "capacity":   room_info.get("capacity"),
                "aulastudio": room_info.get("aulastudio"),
                "visible":    room_info.get("visible"),
            }
            by_code[room_code] = entry

            # Index by cleaned lowercase name (last-write-wins on duplicates)
            cleaned_name = entry["room_name"].lower().strip()
            if cleaned_name:
                by_name[cleaned_name] = entry

    print(f"Room lookup built: {len(by_code)} rooms loaded from rooms_call.php")
    return by_code, by_name


def resolve_room(lesson: dict, by_code: dict, by_name: dict) -> dict:
    """
    Try to resolve room info from the lesson using two strategies:
    1. Match by 'codice aula' (room_code) — exact, fast
    2. Fallback: match by cleaned room name from 'aula' field
    Returns the room info dict, or {} if nothing is found.
    """
    # Strategy 1: lookup by room_code
    raw_code = lesson.get("codice_aula", "").strip()
    if raw_code:
        room = by_code.get(raw_code)
        if room:
            return room

    # Strategy 2: lookup by cleaned room name
    raw_aula = lesson.get("aula", "")
    cleaned = clean_room_name(raw_aula).lower().strip()
    if cleaned:
        room = by_name.get(cleaned)
        if room:
            return room

    return {}


############### Get and Set Functions ####################

def build_schedule_url(school_year, department, course, curriculum_code_and_year, date, base_url, lang="it"):
    params = {
        "view": "easycourse",
        "form-type": "corso",
        "include": "corso",
        "txtcurr": "",
        "anno": school_year,
        "scuola": department,
        "corso": course,
        "anno2[]": curriculum_code_and_year,
        "visualizzazione_orario": "cal",
        "date": date,
        "periodo_didattico": "",
        "_lang": lang,
        "list": "",
        "week_grid_type": "-1",
        "ar_codes_": "",
        "ar_select_": "",
        "col_cells": "0",
        "empty_box": "0",
        "only_grid": "0",
        "highlighted_date": "0",
        "all_events": "0",
        "faculty_group": "0",
    }
    return f"{base_url}?{urlencode(params, quote_via=quote)}"


def get_school_years(driver):
    select_school_year = driver.find_element(By.ID, "cdl_aa")
    return [
        {"value": opt.get_attribute("value"), "label": opt.text}
        for opt in select_school_year.find_elements(By.TAG_NAME, "option")
        if opt.get_attribute("value")
    ]


def set_school_year(year, driver):
    select_school_year = driver.find_element(By.ID, "cdl_aa")
    Select(select_school_year).select_by_value(year["value"])
    time.sleep(0.4)


def get_departments(driver):
    select_department = driver.find_element(By.ID, "cdl_scuola")
    return [
        {"value": opt.get_attribute("value"), "label": opt.text}
        for opt in select_department.find_elements(By.TAG_NAME, "option")
        if opt.get_attribute("value")
    ]


def set_department(department, driver):
    select_department = driver.find_element(By.ID, "cdl_scuola")
    Select(select_department).select_by_value(department["value"])
    time.sleep(0.4)


def get_study_courses(driver):
    select_course = driver.find_element(By.ID, "cdl_co")
    return [
        {"value": opt.get_attribute("value"), "label": opt.text}
        for opt in select_course.find_elements(By.TAG_NAME, "option")
        if opt.get_attribute("value")
    ]


def set_study_course(course, driver):
    select_course = driver.find_element(By.ID, "cdl_co")
    Select(select_course).select_by_value(course["value"])
    time.sleep(0.4)


def get_study_years_and_curriculum(driver):
    select_year_and_curriculum = driver.find_element(By.ID, "cdl_a2_multi")
    return [
        {"value": opt.get_attribute("value"), "label": opt.text}
        for opt in select_year_and_curriculum.find_elements(By.TAG_NAME, "option")
        if opt.get_attribute("value")
    ]


def set_study_year_and_curriculum(year, driver):
    select_year_and_curriculum = driver.find_element(By.ID, "cdl_a2_multi")
    Select(select_year_and_curriculum).select_by_value(year["value"])
    time.sleep(0.4)


def get_info_for_request(dept, school_year, start_date, URL_FORM, delay):
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=UNITS Links Crawler (network lab)")

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(URL_FORM)
    time.sleep(delay)

    school_years = get_school_years(driver)
    time.sleep(delay)
    if not school_years:
        print(f"No school year found for department {dept['label']}")
        return []
    latest_value = max(school_years, key=lambda x: int(x['value']))
    set_school_year(latest_value, driver)
    set_department(dept, driver)
    study_courses = get_study_courses(driver)

    blocks = []
    for course in study_courses:
        set_study_course(course, driver)
        study_years_and_curriculum = get_study_years_and_curriculum(driver)
        time.sleep(delay)
        for study_year in study_years_and_curriculum:
            set_study_year_and_curriculum(study_year, driver)

            log = "Getting " + dept["label"] + "  --  Course: " + course["label"] + "  --  Study year and curriculum: " + study_year["label"]
            print(f"{log}\n")

            if study_year["label"].strip().endswith("Comune"):
                study_year["label"] += " with all other curricula of that course"

            if course["label"].strip().endswith("(Laurea)"):
                course["label"] = course["label"][:-len("(Laurea)")] + "(Bachelor Degree)"

            block = {
                "school_year":                school_year,
                "department_code":            dept["value"],
                "course_code":                course["value"],
                "study_course":               course["label"],
                "curriculum_code_and_year":   study_year["value"],
                "course_year_and_curriculum": study_year["label"],
                "week_date":                  start_date
            }
            blocks.append(block)

    driver.quit()
    return blocks


def response_filter(data, cell_keys=None, output_key_cells="lessons_schedule"):
    print("RAW CELL KEYS:", data.get("celle", [{}])[0].keys() if data.get("celle") else "NO CELLE")
    print("SAMPLE CELL:", data.get("celle", [{}])[0] if data.get("celle") else "EMPTY")

    if cell_keys is None:
        cell_keys = [
            "codice_insegnamento",
            "nome_insegnamento",
            "data",
            "codice_aula",
            "codice sede",
            "aula",
            "orario",
            "Annullato",
            "codice_docente",
            "docente",
        ]

    filtered_cells = []
    for cell in data.get("celle", []):
        new_cell = {k: cell[k] for k in cell_keys if k in cell and k != "Annullato"}
        cancelled_val = str(cell.get("Annullato", "0")).strip()
        if cancelled_val == "1":
            new_cell["annullato"] = "yes"
        filtered_cells.append(new_cell)

    to_return = {}
    if "first_day_label" in data:
        to_return["week_start_day"] = data["first_day_label"]
    to_return[output_key_cells] = filtered_cells
    return to_return


def next_week(d: date) -> date:
    days_ahead = 7 - d.weekday()
    if days_ahead == 0:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def write_json_to_file(file_name, new_content):
    data = []
    if os.path.exists(file_name) and os.path.getsize(file_name) > 0:
        with open(file_name, "r", encoding="utf-8") as f:
            data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Existing JSON is not a list, cannot append.")
    if isinstance(new_content, list):
        data = new_content + data
    else:
        data = [new_content] + data
    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_response_and_write_json_to_files(
    course_schedule_info, OUTPUT_DIR, url, BASE_URL, end_date,
    room_by_code: dict, room_by_name: dict
):
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('https://', adapter)

    while course_schedule_info["week_date"] <= end_date:
        print("Request for:", course_schedule_info["week_date"])
        try:
            school_year               = course_schedule_info["school_year"]
            department_code           = course_schedule_info["department_code"]
            course_code               = course_schedule_info["course_code"]
            study_course              = course_schedule_info["study_course"]
            curriculum_code_and_year  = course_schedule_info["curriculum_code_and_year"]
            course_year_and_curriculum = course_schedule_info["course_year_and_curriculum"]
            week_date                 = course_schedule_info["week_date"]
        except Exception as e:
            print(f"Error parsing json: {e}")
            break

        specific_url = build_schedule_url(
            school_year, department_code, course_code,
            curriculum_code_and_year, week_date, BASE_URL, lang="it"
        )

        payload = {
            "view": "easycourse",
            "form-type": "corso",
            "include": "corso",
            "anno": school_year,
            "scuola": department_code,
            "corso": course_code,
            "anno2[]": curriculum_code_and_year,
            "visualizzazione_orario": "cal",
            "date": week_date,
            "_lang": "it",
            "col_cells": "0",
            "only_grid": "0",
            "all_events": "0"
        }

        headers = {
            "User-Agent": "UNITS Links Crawler (network lab)",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://orari.units.it",
            "Referer": BASE_URL
        }

        try:
            time.sleep(0.2)
            response = session.post(url, data=payload, headers=headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"Error in request: {e}")
            break

        schedule_json = response_filter(response.json())
        lessons = schedule_json.get("lessons_schedule", [])

        if not lessons:
            print(f"WARNING Empty schedule for {course_code} on date {week_date}")

        rag_ready_lessons = []

        for lesson in lessons:
            if not lesson.get("nome_insegnamento"):
                continue

            iso_date   = safe(datetime.strptime(lesson.get('data'), "%d-%m-%Y").strftime("%Y-%m-%d"))
            start_time = safe(extract_time_range(lesson.get("orario"))[0])
            end_time   = safe(extract_time_range(lesson.get("orario"))[1])

            # --- Room resolution: try by code first, then by name ---
            room_info     = resolve_room(lesson, room_by_code, room_by_name)
            raw_room_code = lesson.get("codice_aula", "").strip()

            room_name     = safe(room_info.get("room_name") or clean_room_name(lesson.get("aula", "")))
            site_name = safe(room_info.get("area"))
            site_code = safe(room_info.get("area_code"))
            area_group    = safe(room_info.get("area_group"))
            address       = safe(room_info.get("address"))
            capacity      = room_info.get("capacity")
            room_type     = safe(room_info.get("room_type"))

            # Reconstruct full_location (kept for backward compat)
            if site_name and site_name != "N/A" and room_name and room_name != "N/A":
                full_location = f"{site_name} - {room_name}"
            else:
                full_location = safe(clean_room_name(lesson.get("aula", "")))

            flat_lesson = {
                    # --- Course info ---
                    "department":          safe(department_code),
                    "degree_program_code": safe(course_code),
                    "degree_program_name": safe(study_course),
                    "subject_code":        safe(lesson.get("codice_insegnamento")),
                    "subject_name":        safe(lesson.get("nome_insegnamento")),
                    "study_year_code":     safe(curriculum_code_and_year),
                    "curriculum":          safe(course_year_and_curriculum),
                    # --- Time info ---
                    "date":                safe(iso_date),
                    "start_time":          safe(start_time),
                    "end_time":            safe(end_time),
                    # --- Location (split) ---
                    "room_code":           safe(raw_room_code),
                    "room_name":           room_name,
                    "site_name":           site_name,
                    "site_code":           site_code,
                    # "area_group":          area_group,
                    "address":             address,
                    # "capacity":            capacity,
                    # --- Other ---
                    "professors":           safe(lesson.get("docente")),
                    # "professor_code":      safe(lesson.get("codice_docente")),
                    "lesson_type":         safe(lesson.get("tipo")),
                    "cancelled":           lesson.get("annullato", "no"),
                    "url":                 safe(specific_url),
            }
            rag_ready_lessons.append(flat_lesson)

        if not rag_ready_lessons:
            course_schedule_info["week_date"] = next_week(week_date)
            continue

        file_name = os.path.join(
            OUTPUT_DIR,
            f"{course_code}---{curriculum_code_and_year.replace('|', '_')}---{week_date}.json"
        )
        with open(file_name, "w", encoding="utf-8") as f:
            json.dump(rag_ready_lessons, f, ensure_ascii=False, indent=2)

        course_schedule_info["week_date"] = next_week(week_date)



