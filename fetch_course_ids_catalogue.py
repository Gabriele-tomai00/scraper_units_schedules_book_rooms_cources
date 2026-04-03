"""
Scraper for the UNITS (University of Trieste) course catalogue API.
Fetches all courses and flattens the nested structure into a list of course objects.
"""

import argparse
import json
import requests
from pathlib import Path

# --- Configuration ---
BASE_URL = "https://units.coursecatalogue.cineca.it/api/v1"
YEAR = 2025
OUTPUT_FILE = Path("course_list_ids.json")

def parse_category(des_it: str | None) -> str:
    """Parse the course category from the Italian description."""
    if not des_it:
        return "Unknown"
    des_it = des_it.lower()
    if "lauree magistrali a ciclo unico" in des_it:
        return "Laurea a Ciclo Unico"
    elif "lauree magistrali" in des_it:
        return "Laurea Magistrale"
    elif "lauree" in des_it:
        return "Laurea Triennale"
    elif "dottorati di ricerca" in des_it:
        return "Dottorato di Ricerca"
    else:
        return des_it
        
def fetch_courses(year: int) -> list[dict]:
    """Fetch the full course list from the catalogue API."""
    url = f"{BASE_URL}/corsi"
    params = {"anno": year, "minimal": "true"}

    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def flatten_courses(raw: list[dict]) -> list[dict]:
    courses = []
    for area in raw:
        for subgroup in area.get("subgroups", []):
            for cds in subgroup.get("cds", []):
                for sub in cds.get("cdsSub", []):
                    category = parse_category(subgroup.get("des_it"))
                    name = sub.get("des_it") or cds.get("des_it")
                    record = {"cod": sub.get("cod"), "name_it": name, "category": category}
                    courses.append(record)
    return courses


def save_json(data: list[dict], output_path: Path) -> None:
    """Serialize data to a JSON file with indentation."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(data)} courses to '{output_path}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape the UNITS course catalogue and export to JSON."
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        help="Output file for the extracted data.",
        default=OUTPUT_FILE,
    )
    parser.add_argument(
        "-y", "--year",
        type=int,
        help="Academic year to fetch (default: %(default)s).",
        default=YEAR,
    )
    args = parser.parse_args()

    output_path = Path(args.output)

    print(f"Fetching courses for year {args.year}...")
    raw_data = fetch_courses(args.year)

    print("Flattening nested structure...")
    courses = flatten_courses(raw_data)

    save_json(courses, output_path)