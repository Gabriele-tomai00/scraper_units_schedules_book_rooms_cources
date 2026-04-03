from operator import truediv
import requests
import json
import argparse
from datetime import datetime
import os
from pathlib import Path

from utils import *

URL = "https://spweb.units.it/jsonapi/static/dad_grp.json"
OUTPUT_FILE = Path("teams_codes.json")

# Download and load JSON
def download_data():
    response = requests.get(URL)
    response.raise_for_status()
    # The API returns a dict with a "data" key which contains the list
    return response.json().get("data", [])

def process_data(data):
    timestamp = datetime.now().strftime("%d/%m/%Y")
    new_data = []
    for item in data:
        attrs = item.get("attributes", item)

        # 1. Mapping table (label, source_key)
        fields_to_process = [
            ("course_name",         "NOME_INS"),
            ("course_name_eng",     "NOME_INS_ENG"),
            ("course_code",         "AF_GEN_COD"),
            ("teams_code",          "JCD_O365"),
            ("degree_program",      "NOME_CORSO"),
            ("degree_program_code", "CDS_COD"),
            ("academic_year",       "ANNO_ACCADEMICO"),
            ("teacher",             "DOCENTE"),
            ("period",              "PERIODO_COD"),
        ]

        # 2. Extract and clean fields
        ordered_attrs = {}
        for label, key in fields_to_process:
            val = attrs.get(key)
            ordered_attrs[label] = "N/A" if val in ("", {}, None) else val

        # 3. Parse composite fields (after full extraction)
        course_name_clean  = clean_nome_insegnamento(ordered_attrs["course_name"])
        degree_name_clean  = clean_nome_corso(ordered_attrs["degree_program"])
        teacher_name, teacher_id = parse_docente(ordered_attrs["teacher"])

        # 4. Build metadata dict (nested, compatible with vector stores)
        metadata = {
            "course_code":          ordered_attrs["course_code"],
            "teams_code":           ordered_attrs["teams_code"],
            "degree_program_code":  ordered_attrs["degree_program_code"],
            "academic_year":        ordered_attrs["academic_year"],
            "teacher_name":         teacher_name,
            "teacher_id":           teacher_id,
            "period":               ordered_attrs["period"],
            "course_name":          course_name_clean,
            "degree_program":       degree_name_clean,
            "degree_program_eng":   clean_nome_corso(ordered_attrs["degree_program_eng"]),
            "last_update":          timestamp,
        }

        new_data.append(metadata)

    return new_data
    
def save_to_json(processed_data, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(f"{path_no_ext}.json")), exist_ok=True)
    
    with open(f"{path_no_ext}.json", "w", encoding="utf-8") as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=2)
    print(f"Data successfully saved to JSON: {f"{path_no_ext}.json"}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download Teams codes from UNITS")
    parser.add_argument("-o", "--output", help="Output file path (without extension", default=OUTPUT_FILE) 
    args = parser.parse_args()

    if args.output:
        OUTPUT_FILE = Path(args.output)

    init_output(OUTPUT_FILE)

    output_path = Path(os.path.abspath(args.output))
    os.makedirs(output_path.parent, exist_ok=True)

    timestamp = datetime.now().strftime("%d/%m/%Y")

    print("Downloading data...")
    try:
        raw_data = download_data()
        print(f"Downloaded {len(raw_data)} records.")
        
        processed_data = process_data(raw_data)
        
        # Determine base path and file name
        base_path = args.output if args.output else "teams_codes"
        path_no_ext = os.path.splitext(base_path)[0]


    # save to JSON
        os.makedirs(os.path.dirname(os.path.abspath(f"{path_no_ext}.json")), exist_ok=True)
        with open(f"{path_no_ext}.json", "w", encoding="utf-8") as f:
            json.dump(processed_data, f, ensure_ascii=False, indent=2)
        print(f"Data successfully saved to JSON: {f"{path_no_ext}.json"}")

            
    except Exception as e:
        print(f"An error occurred: {e}")