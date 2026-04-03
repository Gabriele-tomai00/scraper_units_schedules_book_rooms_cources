"""
fetch_teachings.py
------------------
Downloads teachings (insegnamenti) and general degree info for one or all courses
from the UNITS course catalogue API.

Produces two output files:
    - subjects.json : flat list of all teachings across all courses
    - degrees.json  : flat list of general degree info for each course

Usage:
    # Single course by ID:
    python fetch_teachings.py --id 10775

    # Batch mode (reads all courses from course_list_ids.json):
    python fetch_teachings.py --delay 0.15 --limit 5
"""

import sys
import json
import time
import argparse
import requests
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

API_BASE_URL          = "https://units.coursecatalogue.cineca.it/api/v1/corso/2025"
INPUT_COURSES_FILE    = Path("scraper_results/course_list_ids.json")
OUTPUT_FILE_SUBJECTS  = Path("scraper_results/subjects.json")
OUTPUT_FILE_DEGREES   = Path("scraper_results/degrees.json")
DELAY_SEC             = 0.5


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def fetch_raw_course(course_id: str) -> dict:
    """Fetch the full course JSON from the API."""
    url = f"{API_BASE_URL}/{course_id}"
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, list):
        if not data:
            raise ValueError(f"Empty response for course id={course_id}")
        return data[0]
    return data


# ---------------------------------------------------------------------------
# Filtering — Degree info
# ---------------------------------------------------------------------------

def filter_degree(course: dict) -> dict:
    """
    Extract general degree-level info from the raw course response.

    Fields intentionally excluded (uncomment to restore):
        # "cod"          : course.get("cod"),
        # "classe_cod"   : course.get("classe_cod"),
        # "classe_it"    : course.get("classe_it"),
        # "accesso_it"   : course.get("accesso_it"),
        # "normativa_it" : course.get("normativa_it"),
        # "ruoli"        : [
        #     {"nome": f"{r.get('caricaNome','')} {r.get('caricaCognome','')}".strip(),
        #      "ruolo": r.get("carica", "")}
        #     for r in course.get("ruoli_it", [])
        # ],
    """
    return {
        "name"       : course.get("des_it"),
        "url"        : course.get("sitoweb"),
        "department" : course.get("dip_des_it"),
        "duration"   : course.get("durata_it"),
        "location"   : course.get("sede_des_it"),
        "language"   : course.get("lingua_des_it"),
        # they come from subgroup_des_it / classe_it in the course list.
        # Uncomment below if you enrich this dict with data from courses.json:
    }


# ---------------------------------------------------------------------------
# Filtering — Teachings
# ---------------------------------------------------------------------------

def filter_teaching(activity: dict, anno: int, corso_cod: str) -> dict:
    """
    Extract only the relevant fields from a single teaching (attività).

    Fields intentionally excluded (uncomment to restore):
        # "ore"         : activity.get("ore"),
        # "taf"         : activity.get("tafDes_it"),
        # "data_inizio" : activity.get("data_inizio_periodo_didattico"),
        # "data_fine"   : activity.get("data_fine_periodo_didattico"),
    """
    docenti = [d.get("des", "") for d in activity.get("docenti", []) if d.get("des")]

    return {
        "corso_cod"  : corso_cod,
        "year"       : anno,
        "cod"        : activity.get("cod"),
        "adCod"      : activity.get("adCod"),
        "name"       : activity.get("des_it"),
        "CFU"        : activity.get("crediti"),
        "type"       : activity.get("tipo_ins_des_it"),
        "semester"   : activity.get("periodo_didattico_it"),
        "professors" : docenti,
    }


def extract_teachings(course: dict) -> list[dict]:
    """
    Walk the nested percorsi → anni → insegnamenti → attivita structure
    and return a flat list of filtered teachings.
    """
    teachings = []
    corso_cod = str(course.get("cod", ""))

    for percorso in course.get("percorsi", []):
        for year_block in percorso.get("anni", []):
            anno = year_block.get("anno")
            for group in year_block.get("insegnamenti", []):
                for activity in group.get("attivita", []):
                    teachings.append(filter_teaching(activity, anno, corso_cod))

    return teachings


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_course(course_id: str, category: str) -> tuple[dict, list[dict]]:
    """
    Fetch, extract degree info and teachings for a single course ID.
    Returns (degree_dict, teachings_list) — does NOT write to disk.
    """
    print(f"  → Fetching course {course_id} ...", end=" ", flush=True)
    raw = fetch_raw_course(course_id)
    degree = filter_degree(raw)
    degree["category"] = category 
    teachings = extract_teachings(raw)
    print(f"OK — {len(teachings)} teachings")
    return degree, teachings


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_json(data: list[dict], output_path: Path, label: str) -> None:
    """Write a list of dicts to a JSON file, creating parent dirs as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data)} {label} → '{output_path}'")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_single(
    course_id: str,
    subjects_path: Path,
    degrees_path: Path,
) -> None:
    """Single-course mode."""
    try:
        degree, teachings = process_course(course_id)
        save_json([degree], degrees_path, "degrees")
        save_json(teachings, subjects_path, "subjects")
    except requests.HTTPError as e:
        print(f"HTTP error: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Network error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Data error: {e}")
        sys.exit(1)


def run_batch(
    input_path: Path,
    subjects_path: Path,
    degrees_path: Path,
    delay: float,
    limit: int | None,
) -> None:
    """Batch mode: read course list and accumulate degrees + teachings."""
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            courses = json.load(f)
    except FileNotFoundError:
        print(f"Error: '{input_path}' not found in the current directory.")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: could not parse '{input_path}': {e}")
        sys.exit(1)

    total = len(courses)
    print(f"Batch mode: processing {total} courses from '{input_path}'")

    all_degrees:   list[dict] = []
    all_teachings: list[dict] = []

    for idx, course in enumerate(courses, start=1):
        if limit is not None and idx > limit:
            print(f"  Limit of {limit} courses reached, stopping.")
            break

        course_id = str(course.get("cod", "")).strip()
        category = str(course.get("category", "")).strip()
        if not course_id:
            print(f"  [{idx}/{total}] Skipping entry with missing 'cod'")
            continue

        print(f"  [{idx}/{total}]", end=" ")
        try:
            degree, teachings = process_course(course_id, category)
            all_degrees.append(degree)
            all_teachings.extend(teachings)
        except requests.HTTPError as e:
            print(f"HTTP error (skipping): {e}")
        except requests.RequestException as e:
            print(f"Network error (skipping): {e}")
        except ValueError as e:
            print(f"Data error (skipping): {e}")

        if idx < total:
            time.sleep(delay)

    print()
    save_json(all_degrees, degrees_path, "degrees")
    save_json(all_teachings, subjects_path, "subjects")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_time = time.time()

    parser = argparse.ArgumentParser(
        description="Fetch teachings and degree info from the UNITS course catalogue API."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(INPUT_COURSES_FILE),
        help=f"Input JSON file with course list (default: '{INPUT_COURSES_FILE}').",
    )
    parser.add_argument(
        "--output-subjects",
        type=str,
        default=str(OUTPUT_FILE_SUBJECTS),
        help=f"Output JSON file for subjects (default: '{OUTPUT_FILE_SUBJECTS}').",
    )
    parser.add_argument(
        "--output-degrees",
        type=str,
        default=str(OUTPUT_FILE_DEGREES),
        help=f"Output JSON file for degree info (default: '{OUTPUT_FILE_DEGREES}').",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DELAY_SEC,
        help=f"Delay in seconds between requests in batch mode (default: {DELAY_SEC}).",
    )
    parser.add_argument(
        "--id",
        type=str,
        default=None,
        dest="course_id",
        help="Single course ID to fetch. If omitted, batch mode is used.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after scraping N courses (useful for testing).",
    )

    args = parser.parse_args()
    subjects_path = Path(args.output_subjects)
    degrees_path  = Path(args.output_degrees)
    input_path    = Path(args.input)

    if args.course_id:
        run_single(args.course_id, subjects_path, degrees_path)
    else:
        run_batch(input_path, subjects_path, degrees_path, args.delay, args.limit)

    elapsed = time.time() - start_time
    print(f"Elapsed: {elapsed:.1f}s")