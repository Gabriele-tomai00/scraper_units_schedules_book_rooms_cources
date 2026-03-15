import time
import os
import json
import requests
import re
from urllib.parse import urlencode
from datetime import datetime, timedelta
from collections import defaultdict
import html
from utils import extract_time_range, safe


def print_title(start_time, start_date, end_date):
    formatted_time = time.strftime("%H:%M:%S", time.localtime(start_time))
    print(f"Script started at {formatted_time}")
    print(f"First date: {start_date}, last date: {end_date}")
    print(f"Starting the process to get all room occupation URLs from orari.units.it...\n")


def write_json_to_file(content, directory, site, start_date, end_date):
    if content is None:
        return
        
    file_name = os.path.join(directory, f"{site}---{start_date}_to_{end_date}.json")

    data_to_write = content
    # If content is the wrapper dict produced by _convert_raw_events, extract the events list
    if isinstance(content, dict) and "events" in content and "site_code" in content:
        data_to_write = content["events"]

    with open(file_name, "w", encoding="utf-8") as f:
        json.dump(data_to_write, f, ensure_ascii=False, indent=2)


def clean_html_tags(text):
    if not text:
        return ""
    # Remove all HTML tags (e.g., <i ...> or </i>)
    clean_text = re.sub(r'<[^>]+>', '', text)
    # Convert HTML entities like &ograve; to real characters (ò)
    clean_text = html.unescape(clean_text)
    # Remove multiple spaces and trim
    return " ".join(clean_text.split()).strip()


def _convert_raw_events(raw_events):
    """
    Convert a flat list of raw event dicts (as returned by response_filter)
    into a list of per-site dicts:
        [{"site_code": ..., "site_name": ..., "events": [...]}, ...]

    Each event keeps separate time_start / time_end keys.
    """
    sites_events = defaultdict(list)
    sites_info = {}

    for event in raw_events:
        site_code = event.get("CodiceSede")
        site_name = event.get("NomeSede")
        room_code = event.get("CodiceAula")
        room_name = event.get("NomeAula")
        last_update = event.get("ultimo_aggiornamento", "")
        cancelled = "no" if event.get("Annullato", "0") == "0" else "yes"
        event_type = event.get("tipo") or event.get("type", "")

        # Clean the course name from any embedded HTML
        raw_course = event.get("name", "")
        course = clean_html_tags(raw_course)

        day = event.get("Giorno")
        time_slot = event.get("orario", "")
        teacher = event.get("utenti", "")

        if site_code not in sites_info:
            sites_info[site_code] = site_name

        # Split "HH:MM - HH:MM" into separate start/end strings
        time_start, time_end = extract_time_range(time_slot)

        event_dict = {
            "site_code":    safe(site_code),
            "room_code":    safe(room_code),
            "date":         safe(day),
            "last_update":  safe(last_update),
            "site_name":    safe(site_name),   
            "room_name":    safe(room_name),
            "start_time":   safe(time_start),
            "end_time":     safe(time_end),
            "name_event":   safe(course),
            "professors":   safe(teacher),
            "cancelled":    cancelled,
            "event_type":   safe(event_type),
        }

        if cancelled == "yes":
            event_dict["cancelled"] = cancelled

        sites_events[site_code].append(event_dict)

    result = []
    for site_code, events in sites_events.items():
        result.append({
            "site_code": site_code,
            "site_name": sites_info.get(site_code, ""),
            "events": events,
        })
    return result


def convert_json_structure(file_path):
    """Load a raw-events JSON file and return the converted per-site list."""
    with open(file_path, "r", encoding="utf-8") as f:
        raw_events = json.load(f)
    return _convert_raw_events(raw_events)


def get_sites(text):
    match = re.search(r"var\s+elenco_sedi\s*=\s*(\[.*?\])\s*;", text, re.S)
    if not match:
        raise ValueError("No sites list found")
    list_json = match.group(1)
    sites_list = json.loads(list_json)
    for site in sites_list:
        if 'valore' in site:
            site['value'] = site.pop('valore')  # rename key
    return sites_list


def get_rooms(text, site):
    match_rooms = re.search(r"var elenco_aule = (\{.*?\});", text, re.S)
    if not match_rooms:
        raise ValueError("No rooms list found")

    list_json = match_rooms.group(1)
    rooms_list = json.loads(list_json)

    if site not in rooms_list:
        raise ValueError(f"Site '{site}' not found")

    return rooms_list[site]


def check_date(date_str):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            input_date = datetime.strptime(date_str, fmt)
            break
        except ValueError:
            continue
    else:
        raise ValueError("Invalid date format. Use dd/mm/yyyy or dd-mm-yyyy.")

    target_date = datetime(2026, 1, 20)
    return input_date < target_date


def response_filter(data):
    last_update = data.get("file_date", "")
    try:
        last_update = last_update.split(" ", 1)[0]
    except Exception:
        pass

    event_keys = [
        "room", "NomeAula", "CodiceAula",
        "NomeSede", "CodiceSede", "name",
        "utenti", "orario", "Giorno", 
        "Annullato", "tipo", "type"
    ]
    events = data.get("events", [])
    if not isinstance(events, list):
        raise ValueError("The 'events' field must be a list")

    filtered_events = [
        {**{k: event[k] for k in event_keys if k in event}, "ultimo_aggiornamento": last_update}
        for event in events
    ]
    return filtered_events


def add_keys_and_reorder(filtered_data, sites, rooms, payload, URL_PORTAL):
    filtered_data["site"] = sites[0]['label']
    filtered_data["site_code"] = sites[0]['value']
    ordered_data = {
        "site": sites[0]['label'],
        "site_code": sites[0]['value'],
        "room": rooms[2]['label'],
        "room_code": rooms[2]['valore'],
        "week_date": filtered_data["data_settimana"],
        "url": build_units_url(payload, URL_PORTAL),
        **filtered_data,
    }
    return ordered_data


def build_units_url(payload, URL_PORTAL):
    query_string = urlencode(payload, doseq=True)
    separator = "&" if "?" in URL_PORTAL else "?"
    return URL_PORTAL + separator + query_string


def create_payload(site_code, week_date, room_value="all"):
    payload = {
        "form-type": "rooms",
        "view": "rooms",
        "include": "rooms",
        "aula": "",
        "sede_get[]": [site_code],
        "sede[]": [site_code],
        "aula[]": room_value,
        "date": week_date,
        "_lang": "it",
        "list": "",
        "week_grid_type": "-1",
        "ar_codes_": "",
        "ar_select_": "",
        "col_cells": "0",
        "empty_box": "0",
        "only_grid": "0",
        "highlighted_date": "0",
        "all_events": "0",
    }
    return payload


def get_response_from_request_with_payload(payload, retries=3, delay=1):
    url = "https://orari.units.it/agendaweb/rooms_call.php"
    headers = {
        "User-Agent": "UNITS Links Crawler (network lab)",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://orari.units.it",
        "Referer": "https://orari.units.it/agendaweb/index.php",
    }

    for attempt in range(retries):
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except (requests.ConnectionError, requests.Timeout) as e:
            print(f"[Retry {attempt+1}/{retries}] Connection error: {e}")
            time.sleep(delay)
        except requests.RequestException as e:
            print(f"Unhandled HTTP error: {e}")
            return None
    return None


def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = round(seconds % 60)
    if hours > 0:
        return f"{hours}h {minutes}m {secs}s"
    elif minutes > 0:
        return f"{minutes}m {secs}s"
    else:
        return f"{secs}s"


def get_data(site, start_date, end_date, output_dir, delay):
    """
    Fetch all events for a site over the date range, convert them,
    and write one JSON file per sub-site directly into output_dir.
    """
    print(f"Processing site: {site['label']} ({site['value']})...")
    raw_events = []
    days = [(start_date + timedelta(days=i)) for i in range((end_date - start_date).days + 1)]

    for day in days:
        payload = create_payload(site["value"], day)
        response_data = get_response_from_request_with_payload(payload)
        
        if response_data is None:
            print(
                f"Failed to retrieve data for {site['label']} on {day}. "
                f"URL: {build_units_url(payload, 'https://orari.units.it/agendaweb/index.php')}"
            )
            continue
        if isinstance(response_data["events"], list) and not response_data["events"]:
            continue
        raw_events.extend(response_filter(response_data))
        time.sleep(delay)

    converted = _convert_raw_events(raw_events)
    for file in converted:
        write_json_to_file(file, output_dir, file["site_code"], start_date, end_date)

    return raw_events


def parse_date(s):
    try:
        return datetime.strptime(s, "%d-%m-%Y").date()
    except ValueError:
        raise ValueError(f"Invalid date format: '{s}'. Use dd-mm-yyyy.")