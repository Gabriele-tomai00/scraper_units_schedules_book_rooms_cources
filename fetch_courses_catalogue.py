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
OUTPUT_FILE = Path("courses_catalogue.json")


def fetch_courses(year: int) -> list[dict]:
    """Fetch the full course list from the catalogue API."""
    url = f"{BASE_URL}/corsi"
    params = {"anno": year, "minimal": "true"}

    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def flatten_courses(raw: list[dict]) -> list[dict]:
    """
    Flatten the nested structure:
        Area -> Subgroup -> CDS -> CDSSub
    into a flat list of course objects, each carrying all parent context.
    """
    courses = []

    for area in raw:
        area_info = {
            "area_cod": area.get("cod"),
            "area_des_it": area.get("des_it"),
            # "area_des_en": area.get("des_en"),
        }

        for subgroup in area.get("subgroups", []):
            subgroup_info = {
                "subgroup_cod": subgroup.get("cod"),
                "subgroup_des_it": subgroup.get("des_it"),
                # "subgroup_des_en": subgroup.get("des_en"),
            }

            for cds in subgroup.get("cds", []):
                cds_info = {
                    "cds_cod": cds.get("cdsCod"),
                    "cds_des_it": cds.get("des_it"),
                    # "cds_des_en": cds.get("des_en"),
                }

                for sub in cds.get("cdsSub", []):
                    # Build a flat record with all context merged in
                    record = {}
                    record.update(area_info)
                    record.update(subgroup_info)
                    record.update(cds_info)

                    # Core identifiers
                    record["id"] = sub.get("_id")
                    record["cod"] = sub.get("cod")
                    record["cds_cod"] = sub.get("cdsCod")
                    record["academic_year"] = sub.get("aa")

                    # Course names (prefer sub-level names, fall back to cds-level)
                    record["name_it"] = sub.get("des_it") or cds.get("des_it")
                    # record["name_en"] = sub.get("des_en") or cds.get("des_en")

                    # Language of instruction
                    record["language_cod"] = sub.get("lingua_cod")
                    # record["language_it"] = sub.get("lingua_des_it")
                    # record["language_en"] = sub.get("lingua_des_en")

                    # Campus / location
                    record["campus_cod"] = sub.get("sede_cod")
                    record["campus_it"] = sub.get("sede_des_it")
                    # record["campus_en"] = sub.get("sede_des_en")
                    # record["other_campuses"] = sub.get("altreSedi", [])

                    # Regulatory framework
                    record["regulation_cod"] = sub.get("normativa_cod")

                    # Teaching mode
                    record["teaching_mode_cod"] = sub.get("modalita_didattica_cod")
                    record["teaching_mode_it"] = sub.get("modalita_didattica_it")
                        # record["teaching_mode_en"] = sub.get("modalita_didattica_en")

                    # Admission type
                    record["admission_it"] = sub.get("accesso_it")
                    # record["admission_en"] = sub.get("accesso_en")
                    # record["admission_type"] = "free" if sub.get("tipoAccesso") == "L" else "programmed"

                    # Curriculum ordering
                    record["curriculum_year_start"] = sub.get("ordinamento_aa")
                    record["curriculum_status"] = sub.get("ordinamento_stato")  # A=active, C=ceased
                    record["curriculum_year_end"] = sub.get("ordinamento_aa_cess")  # 9999 = ongoing

                    # Degree type
                    record["degree_type_it"] = sub.get("tipo_corso_des_it")
                    # record["degree_type_en"] = sub.get("tipo_corso_des_en")

                    # Inter-class (joint degree class)
                    record["inter_class_cod"] = sub.get("interClasse_cod") or None
                    record["inter_class_it"] = sub.get("interClasse_it") or None
                    # record["inter_class_en"] = sub.get("interClasse_en") or None

                    # Consortium courses
                    record["consortium_courses"] = sub.get("corsiConsorziati", [])

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