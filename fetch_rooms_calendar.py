# exemple
# python fetch_rooms_calendar.py --start_date "2026-03-18" --end_date "2026-03-19" --output="scraper_results_schedules_book_rooms_cources/rooms_calendar_19"

from joblib import Parallel, delayed
import shutil
import os
import requests
import time
from datetime import date, datetime
import argparse
from pathlib import Path

from fetch_rooms_calendar_utils import *
from utils import parse_date, print_summary, init_output_dir

OUTPUT_DIR = Path("room_schedule_per_site")

if __name__ == "__main__":
    start_time = time.time()
    parser = argparse.ArgumentParser(description="Script for extracting room schedule from orari.units.it")
    parser.add_argument("--start_date", type=parse_date, help="Start date in dd-mm-yyyy format",
                        default=date(datetime.now().year, 11, 6))
    parser.add_argument("--end_date", type=parse_date, help="End date in dd-mm-yyyy format",
                        default=date(datetime.now().year + 1, 2, 20))
    parser.add_argument("--num_sites", type=int,
                        help="For testing, consider only n sites instead of all; ignore to get all",
                        default=0)
    parser.add_argument("-o", "--output", type=str,
                        help="Output directory for the extracted data.", default=OUTPUT_DIR)
    parser.add_argument("--delay", type=float,
                        help="Delay between requests in seconds.", default=0.4)

    args = parser.parse_args()
    if args.output:
        OUTPUT_DIR = args.output

    init_output_dir(OUTPUT_DIR)

    start_date = args.start_date
    end_date = args.end_date
    num_sites = args.num_sites

    print_title(start_time, start_date, end_date)

    URL_sites_data = "https://orari.units.it/agendaweb/combo.php?sw=rooms_"

    resp = requests.get(URL_sites_data)
    resp.raise_for_status()
    data_from_units = resp.text

    sites = get_sites(data_from_units)
    if 0 < num_sites < len(sites):
        selected_sites = sites[:num_sites]
        print(f"Number of sites: {num_sites}")
    else:
        selected_sites = sites
        print(f"Number of sites: all ({len(sites)})")

    # Each worker writes its own converted JSON files directly into OUTPUT_DIR
    Parallel(n_jobs=4)(
        delayed(get_data)(site, start_date, end_date, OUTPUT_DIR, args.delay)
        for site in selected_sites
    )

    print_summary(start_time, OUTPUT_DIR, None, start_date, end_date)