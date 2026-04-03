"""
fetch_teachings.py
------------------
Downloads the list of teachings (insegnamenti) for one or all courses
from the UNITS course catalogue API and writes them all into a single JSON file.

Usage:
    # Single course by ID:
    python fetch_teachings.py --id 10775 -o output/subjects.json

    # Batch mode (reads all courses from courses.json):
    python fetch_teachings.py -o output/subjects.json --delay 0.15
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

API_BASE_URL = "https://units.coursecatalogue.cineca.it/api/v1/corso/2025"
INPUT_COURSES_FILE  = Path("scraper_results/courses.json")
OUTPUT_FILE  = Path("scraper_results/subjects.json")
DELAY_SEC    = 0.5


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
# Filtering
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
        "corso_cod"     : corso_cod,
        "year"          : anno,
        "cod"           : activity.get("cod"),
        "adCod"         : activity.get("adCod"),
        "name"          : activity.get("des_it"),
        "CFU"           : activity.get("crediti"),
        "type"          : activity.get("tipo_ins_des_it"),
        "semester"      : activity.get("periodo_didattico_it"),
        "professors"    : docenti,
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

def process_course(course_id: str) -> list[dict]:
    """
    Fetch and extract teachings for a single course ID.
    Returns the list of filtered teachings (does NOT write to disk).
    """
    print(f"  → Fetching course {course_id} ...", end=" ", flush=True)
    raw = fetch_raw_course(course_id)
    teachings = extract_teachings(raw)
    print(f"OK — {len(teachings)} teachings")
    return teachings


def save_all(teachings: list[dict], output_path: Path) -> None:
    """Write the full teachings list to a single JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(teachings, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(teachings)} total teachings → '{output_path}'")


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def run_single(course_id: str, output_path: Path) -> None:
    """Single-course mode."""
    try:
        teachings = process_course(course_id)
        save_all(teachings, output_path)
    except requests.HTTPError as e:
        print(f"HTTP error: {e}")
        sys.exit(1)
    except requests.RequestException as e:
        print(f"Network error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Data error: {e}")
        sys.exit(1)


def run_batch(input_path: Path, output_path: Path, delay: float, limit: int | None) -> None:
    """Batch mode: read courses.json and accumulate all teachings into one file."""
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

    all_teachings: list[dict] = []

    for idx, course in enumerate(courses, start=1):
        if limit is not None and idx > limit:
            break
        course_id = str(course.get("cod", "")).strip()
        if not course_id:
            print(f"  [{idx}/{total}] Skipping entry with missing 'cod'")
            continue

        print(f"  [{idx}/{total}]", end=" ")
        try:
            teachings = process_course(course_id)
            all_teachings.extend(teachings)
        except requests.HTTPError as e:
            print(f"HTTP error (skipping): {e}")
        except requests.RequestException as e:
            print(f"Network error (skipping): {e}")
        except ValueError as e:
            print(f"Data error (skipping): {e}")

        if idx < total:
            time.sleep(delay)

    save_all(all_teachings, output_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    start_time = time.time()

    parser = argparse.ArgumentParser(
        description="Fetch teachings (insegnamenti) from the UNITS course catalogue API."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=str(INPUT_COURSES_FILE),
        help=f"Input JSON file path (default: '{INPUT_COURSES_FILE}').",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=str(OUTPUT_FILE),
        help=f"Output JSON file path (default: '{OUTPUT_FILE}').",
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
        help="Stop after scraping N courses (useful for testing)",
    )

    args = parser.parse_args()
    output_path = Path(args.output)
    input_path = Path(args.input)

    if args.course_id:
        run_single(args.course_id, output_path)
    else:
        run_batch(input_path, output_path, args.delay, args.limit)

    elapsed = time.time() - start_time
    print(f"Elapsed: {elapsed:.1f}s")