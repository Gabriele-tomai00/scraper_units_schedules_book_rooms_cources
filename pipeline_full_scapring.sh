#!/bin/bash
set -e

# --- Default parameters -- dates in ISO format ---
START_DATE="2026-03-01"
END_DATE="2026-03-08"
OUTPUT_DIR="scraper_results_schedules_book_rooms_cources"

ENV_DIR="env"
REQUIREMENTS_FILE="requirements.txt"

echo "Using START_DATE = $START_DATE"
echo "Using END_DATE = $END_DATE"

# --- Check/Create Virtual Environment ---
if [[ ! -d "$ENV_DIR" ]]; then
    echo "Virtual environment not found. Creating it in '$ENV_DIR'..."
    python3 -m venv "$ENV_DIR"

    echo "Virtual environment created. Activating it and installing requirements..."
    source "$ENV_DIR/bin/activate"

    if [[ -f "$REQUIREMENTS_FILE" ]]; then
        pip install --upgrade pip
        pip install -r "$REQUIREMENTS_FILE"
    else
        echo "WARNING: requirements.txt not found. Continuing without installing packages."
    fi
else
    echo "Virtual environment already exists."

    if [[ -z "$VIRTUAL_ENV" ]]; then
        echo "Activating virtual environment..."
        source "$ENV_DIR/bin/activate"
    else
        echo "Virtual environment already active: $VIRTUAL_ENV"
    fi
fi

# --- Delete old scraper results ---
printf "\nCleaning up old results...\n"
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

printf "\n\n\nADDRESS BOOK SCRAPER\n"
python3 fetch_address_book.py --output="$OUTPUT_DIR/address_book.json"
# python fetch_address_book.py --output="scraper_results_schedules_book_rooms_cources/address_book.json" --limit 1

printf "\n\n\nTeams codes scraper\n"
python3 fetch_courses_with_teams_code.py -o "$OUTPUT_DIR/courses_with_teams_code.json"
# python fetch_courses_with_teams_code.py -o "scraper_results_schedules_book_rooms_cources/courses_with_teams_code.json"

printf "\n\n\bachelor, master and years masters' degree courses scraper\n"
python3 fetch_degrees_programs_bachelor_master.py -o "$OUTPUT_DIR/full_courses.json"
# python3 fetch_degrees_programs_bachelor_master.py -o "scraper_results_schedules_book_rooms_cources/full_degree_programs.json" --delay 0.15

printf "\n\n\nRooms info scraper\n"
python3 fetch_info_rooms.py -o "$OUTPUT_DIR/info_rooms.json"
# python fetch_info_rooms.py -o "scraper_results_schedules_book_rooms_cources/info_rooms.json" --limit 1

printf "\n\n\nROOMS CALENDAR\n"
python3 fetch_rooms_calendar.py --start_date "$START_DATE" --end_date "$END_DATE" --output="$OUTPUT_DIR/rooms_calendar"
# python fetch_rooms_calendar.py --start_date "2026-02-02" --end_date "2026-02-10" --output="scraper_results_schedules_book_rooms_cources/rooms_calendar" --num_sites 1

printf "\n\n\nLESSONS CALENDAR SCARPER\n"
python3 fetch_lessons_calendar.py --start_date "$START_DATE" --end_date "$END_DATE" --output="$OUTPUT_DIR/lessons_calendar"
# python fetch_lessons_calendar.py --start_date "2026-03-02" --end_date "2026-03-10" --output="scraper_results_schedules_book_rooms_cources/lessons_calendar" --num_departments 1

printf "\n\n\nSCRAPING ENDED\n"