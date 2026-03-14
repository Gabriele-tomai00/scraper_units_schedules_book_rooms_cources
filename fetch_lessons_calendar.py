import shutil
from joblib import Parallel, delayed
import time
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import date, datetime
import argparse
from selenium.webdriver.chrome.service import Service
from pathlib import Path

from fetch_lessons_calendar_utils import *

from utils import print_summary, parse_date, init_output_dir

OUTPUT_DIR = Path("lessons_schedule_by_course")

if __name__ == "__main__":
    start_time = time.time()
    parser = argparse.ArgumentParser(description="Script for extracting schedule from orari.units.it")
    parser.add_argument("--start_date", type=parse_date, help="Start date in yyyy-mm-dd format", default=date(datetime.now().year, 11, 6))
    parser.add_argument("--end_date",   type=parse_date, help="End date in yyyy-mm-dd format",   default=date(datetime.now().year+1, 2, 20))    
    parser.add_argument("--num_departments", type=int, help="For testing, consider only n departments instead of all, ignore to get all", default=0)
    parser.add_argument("-o", "--output", type=str, help="Output file for the extracted data.", default=OUTPUT_DIR)
    parser.add_argument("--delay", type=float, help="Delay between requests in seconds.", default=0.5)
    parser.add_argument("--num_cores", type=int, help="Number of CPU cores to use for parallel processing.", default=4)

    args = parser.parse_args()

    if args.output:
        OUTPUT_DIR = args.output
    init_output_dir(OUTPUT_DIR)
    
    start_date = args.start_date
    end_date = args.end_date    # the request wants only one year as school year. EX 2023 for school year 2023/2024.
    num_departments = args.num_departments
    # so if the date is after August 15th, the school year is the year of the date, otherwise it is the previous year. 
    # It is assumed that requests after August 15th are for the school year starting in September (usually schedules for the new SY are not published before August 15th).
    school_year = start_date.year if start_date >= date(start_date.year, 8, 15) else start_date.year - 1

    ############### WebDriver Initialization ####################
    # Set headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=UNITS Links Crawler (network lab)")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    BASE_URL = "https://orari.units.it/agendaweb/index.php"
    URL_FORM = BASE_URL + "?view=easycourse&_lang=it&include=corso"
    URL_schedule_data = "https://orari.units.it/agendaweb/grid_call.php"

    driver = webdriver.Chrome(options=chrome_options)
    driver.get(URL_FORM)
    time.sleep(args.delay)
    departments = get_departments(driver)
    time.sleep(args.delay)
    if 0 < num_departments < len(departments):
        departments = departments[:num_departments]  # only for testing to speed up
    else:
        num_departments = 0
    print(f"num_departments considered: {'all' if num_departments == 0 else num_departments}")
    driver.quit()

    # num_cores = max(1, multiprocessing.cpu_count())
    results = Parallel(n_jobs=args.num_cores)(
        delayed(get_info_for_request)(dept, school_year, start_date, URL_FORM, args.delay) for dept in departments
    )

    final_blocks = []

    for block in results:
        final_blocks.extend(block)

    room_by_code, room_by_name = fetch_room_lookup()



    Parallel(n_jobs=8)(
        delayed(get_response_and_write_json_to_files)(course_schedule_info, OUTPUT_DIR, URL_schedule_data, BASE_URL, end_date, room_by_code=room_by_code, room_by_name=room_by_name) for course_schedule_info in final_blocks
    )

    print_summary(start_time, OUTPUT_DIR, num_departments, start_date, end_date)
