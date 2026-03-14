"""
UniTS AgendaWeb - Classroom detail scraper
==========================================
Step 1: Fetch combo.php  →  get elenco_sedi + elenco_aule
Step 2: For each room    →  fetch vetrina_aule page and parse HTML details
Step 3: Write each room  →  incrementally to info_aule.json (never loses data)

Usage:
    pip install requests beautifulsoup4
    python scrape_aule.py            # scrape all rooms
    python scrape_aule.py --limit 10 # scrape only first 10 rooms (for testing)

JSON output — array of room objects with keys:
    room_name               str
    room_code               str
    site_name               str
    site_code               str
    address                 str
    floor                   str
    room_type               str
    capacity                int | null
    accessible              str
    maps_url                str   direct Google Maps link (openable in browser)
    maps_embed_url          str   original iframe embed URL
    occupancy_building_url  str
    occupancy_room_url      str
    equipment               list[{"name": str, "status": str}]
                            e.g. [{"name": "Proiettore", "status": "DISPONIBILE"}, ...]
                            empty list if no equipment info available
    scrape_ok               bool

String normalization:
    All string values are passed through normalize_str() which:
    - replaces smart/curly quotes and apostrophes with standard ASCII equivalents
    - replaces other problematic characters that break SQL queries
    - strips leading/trailing whitespace
"""

import argparse
import json
import re
import time
import logging
import sys
import unicodedata
from pathlib import Path
import requests
from bs4 import BeautifulSoup

from utils import print_summary, init_output

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

COMBO_URL   = "https://orari.units.it/agendaweb/combo.php?sw=rooms_&vetrina_risorse=&_=1773400225928"
DETAIL_URL  = "https://orari.units.it/agendaweb/index.php"
OUTPUT_FILE = Path("scraper_results_schedules_book_rooms_cources/info_aule.json")
DELAY_SEC   = 1
TIMEOUT_SEC = 15

DETAIL_PARAMS = {
    "form-type":        "vetrina_aule",
    "view":             "vetrina_aule",
    "include":          "vetrina_aule",
    "_lang":            "it",
    "list":             "",
    "week_grid_type":   "-1",
    "ar_codes_":        "",
    "ar_select_":       "",
    "col_cells":        "0",
    "empty_box":        "0",
    "only_grid":        "0",
    "highlighted_date": "0",
    "all_events":       "0",
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (research scraper; contact: your@email.com)",
    "Accept-Language": "it-IT,it;q=0.9",
})

# ── String normalization ──────────────────────────────────────────────────────

# Map of problematic Unicode characters to their safe ASCII replacements
_CHAR_MAP = str.maketrans({
    # Single quotes / apostrophes
    "\u2018": "'",   # left single quotation mark
    "\u2019": "'",   # right single quotation mark  ← most common culprit
    "\u201a": "'",   # single low-9 quotation mark
    "\u201b": "'",   # single high-reversed-9 quotation mark
    "\u02bc": "'",   # modifier letter apostrophe
    "\u0060": "'",   # grave accent used as apostrophe
    # Double quotes
    "\u201c": '"',   # left double quotation mark
    "\u201d": '"',   # right double quotation mark
    "\u201e": '"',   # double low-9 quotation mark
    "\u201f": '"',   # double high-reversed-9 quotation mark
    # Dashes that can break tokenization
    "\u2013": "-",   # en dash
    "\u2014": "-",   # em dash
    "\u2015": "-",   # horizontal bar
    # Non-breaking and zero-width spaces
    "\u00a0": " ",   # non-breaking space
    "\u200b": "",    # zero-width space
    "\u200c": "",    # zero-width non-joiner
    "\u200d": "",    # zero-width joiner
    "\ufeff": "",    # byte order mark
})


def normalize_str(value: str) -> str:
    """
    Normalize a string for safe use in SQL queries and embeddings:
    - Replace problematic Unicode characters (smart quotes, dashes, etc.)
      with their ASCII equivalents using the _CHAR_MAP table
    - Normalize Unicode to NFC (composed form) to avoid duplicate representations
    - Collapse multiple spaces into one
    - Strip leading/trailing whitespace
    """
    if not isinstance(value, str):
        return value
    value = unicodedata.normalize("NFC", value)
    value = value.translate(_CHAR_MAP)
    value = re.sub(r" {2,}", " ", value)
    return value.strip()


def normalize_record(record: dict) -> dict:
    """
    Apply normalize_str() to all string values in a record dict,
    including strings nested inside the equipment list.
    Non-string values (int, float, bool, None, list) are left untouched.
    """
    result = {}
    for key, value in record.items():
        if isinstance(value, str):
            result[key] = normalize_str(value)
        elif key == "equipment" and isinstance(value, list):
            result[key] = [
                {"name": normalize_str(item["name"]), "status": normalize_str(item["status"])}
                for item in value
            ]
        else:
            result[key] = value
    return result


# ── Incremental JSON writer ───────────────────────────────────────────────────

class IncrementalJsonArrayWriter:
    """
    Writes a JSON array incrementally to a file.
    Opens the file immediately, writes '[', then appends each item
    as it arrives, and closes with ']' when done.
    Each record is flushed to disk immediately — crash-safe.
    """

    def __init__(self, path: Path):
        self._f = path.open("w", encoding="utf-8")
        self._f.write("[\n")
        self._first = True

    def write(self, record: dict) -> None:
        if not self._first:
            self._f.write(",\n")
        self._f.write(json.dumps(record, ensure_ascii=False, indent=2))
        self._f.flush()
        self._first = False

    def close(self) -> None:
        self._f.write("\n]\n")
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Step 1 – Fetch combo data ─────────────────────────────────────────────────

def fetch_combo() -> tuple[dict, dict]:
    """
    Returns (sedi_by_code, elenco_aule).
        sedi_by_code : {sede_code: sede_label}
        elenco_aule  : {sede_code: [room_obj, ...]}
    """
    log.info("Fetching combo data ...")
    resp = SESSION.get(COMBO_URL, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    js = resp.text

    def extract_js_var(name: str):
        pattern = rf"var\s+{name}\s*=\s*(\{{.*?\}};|\[.*?\];)"
        m = re.search(pattern, js, re.DOTALL)
        if not m:
            raise ValueError(f"Variable '{name}' not found in combo response")
        return json.loads(m.group(1).rstrip(";"))

    sedi_list   = extract_js_var("elenco_sedi")
    elenco_aule = extract_js_var("elenco_aule")

    sedi_by_code = {item["valore"]: item["label"] for item in sedi_list}
    total_rooms  = sum(len(v) for v in elenco_aule.values())
    log.info("Combo fetched: %d buildings, %d rooms total", len(elenco_aule), total_rooms)
    return sedi_by_code, elenco_aule


# ── Step 2 – Parse detail page ────────────────────────────────────────────────

def parse_equipment(section: BeautifulSoup) -> list[dict]:
    """
    Parse the attrezzature popup into:
        [{"name": "Proiettore", "status": "DISPONIBILE"}, ...]

    The popup div (id="attrezzature-details-popup*") is the only reliable
    source of equipment data. The summary text in the main section
    ("Vedi dettagli Attrezzature...") is just a UI trigger link and is ignored.

    Returns [] if the popup is absent or empty.
    """
    popup = section.find("div", id=re.compile(r"^attrezzature-details-popup"))
    if not popup:
        return []

    items = []
    # Each item: <span style="font-weight:501">NAME</span>
    # followed immediately by a <div> containing the status (e.g. "DISPONIBILE")
    for span in popup.find_all("span", style=re.compile(r"font-weight")):
        name = span.get_text(strip=True)
        if not name:
            continue
        status_div = span.find_next_sibling("div")
        status = status_div.get_text(strip=True) if status_div else ""
        items.append({"name": name, "status": status})

    return items


def parse_detail_page(html: str) -> dict:
    """
    Parse the vetrina_aule HTML for one room.
    Returns {} if the page has no attendance-section (room not found).
    """
    soup = BeautifulSoup(html, "html.parser")

    section = soup.find("div", class_="attendance-section")
    if not section:
        return {}

    # Texts that appear as UI links inside field divs — not actual field values
    SKIP_TEXTS = {"apri link", "apri mappa", "vedi dettagli"}

    def find_field(label: str) -> str:
        """
        Finds <span class='custom-color-bold'>label</span> and returns
        the text content of its parent div, excluding the label itself
        and any UI link texts.
        """
        span = section.find(
            "span",
            class_="custom-color-bold",
            string=lambda s: s and label.lower() in s.lower(),
        )
        if not span:
            return ""
        parent = span.parent
        texts = []
        for child in parent.children:
            if hasattr(child, "get_text"):
                t = child.get_text(strip=True)
                if t and t != span.get_text(strip=True) and t.lower() not in SKIP_TEXTS:
                    texts.append(t)
            elif isinstance(child, str):
                t = child.strip()
                if t:
                    texts.append(t)
        return " ".join(texts).strip()

    result: dict = {}
    result["address"]   = find_field("Indirizzo")
    result["floor"]     = find_field("Piano")
    result["room_type"] = find_field("Tipo")
    result["accessible"]= False if find_field("Accessibile").upper() == "NO"  else True

    # Capacity: "20 posti" → 20
    cap_raw = find_field("Capacità")
    cap_match = re.search(r"\d+", cap_raw)
    result["capacity"] = int(cap_match.group()) if cap_match else None

    # Equipment: only from the popup — the main section just has a "Vedi dettagli" link
    result["equipment"] = parse_equipment(section)

    # Google Maps: extract lat/lng from the iframe embed URL
    # - maps_url:       direct link openable in any browser
    # - maps_embed_url: original iframe src (for embedding purposes)
    iframe = soup.find("iframe")
    embed_src = iframe["src"] if iframe and iframe.get("src") else ""
    lat_m = re.search(r"!3d(-?\d+\.\d+)", embed_src)
    lng_m = re.search(r"!2d(-?\d+\.\d+)", embed_src)
    if lat_m and lng_m:
        result["maps_url"]      = f"https://www.google.com/maps?q={lat_m.group(1)},{lng_m.group(1)}"
        result["maps_embed_url"]= embed_src
    else:
        result["maps_url"]      = ""
        result["maps_embed_url"]= ""

    # Occupancy links
    result["occupancy_building_url"] = ""
    result["occupancy_room_url"]     = ""
    for a in section.find_all("a", attrs={"target": "_blank"}):
        href = a.get("href", "")
        if "aula=" in href:
            result["occupancy_room_url"] = href
        elif "sede=" in href:
            result["occupancy_building_url"] = href

    return result


# ── Step 3 – Fetch detail for one room ───────────────────────────────────────

def fetch_room_detail(sede_code: str, room_code: str) -> tuple[dict, str]:
    params = {**DETAIL_PARAMS, "sede[]": sede_code, "aula[]": room_code}
    prepared = SESSION.prepare_request(requests.Request("GET", DETAIL_URL, params=params))
    room_url = prepared.url

    resp = SESSION.send(prepared, timeout=TIMEOUT_SEC)
    resp.raise_for_status()
    return parse_detail_page(resp.text), room_url




if __name__ == "__main__":
    start_time = time.time()
    parser = argparse.ArgumentParser(description="Scrape UniTS classroom details")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Stop after scraping N rooms (useful for testing)",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=OUTPUT_FILE,
        help="Output file for the extracted data.",
    )
    args = parser.parse_args()

    if args.output:
        OUTPUT_FILE = Path(args.output)

    init_output(OUTPUT_FILE)

    sedi, aule = fetch_combo()
    total_available = sum(len(v) for v in aule.values())
    total_to_scrape = min(args.limit, total_available) if args.limit else total_available

    if args.limit:
        log.info("Limiting scrape to %d rooms (of %d available)", total_to_scrape, total_available)

    idx = 0
    ok  = 0

    with IncrementalJsonArrayWriter(OUTPUT_FILE) as writer:
        for sede_code, room_list in aule.items():
            if idx >= total_to_scrape:
                break

            site_name = sedi.get(sede_code, sede_code)

            for room_obj in room_list:
                if idx >= total_to_scrape:
                    break

                idx += 1
                room_code      = room_obj["valore"]
                room_name      = room_obj["label"]
                capacity_combo = room_obj.get("capacity")

                log.info("[%d/%d] %s / %s", idx, total_to_scrape, site_name, room_name)

                record: dict = {
                    "room_name":               room_name,
                    "room_code":               room_code,
                    "site_name":           site_name,
                    "site_code":           sede_code,
                    "address":                 "",
                    "floor":                   "",
                    "room_type":               "",
                    "capacity":                capacity_combo,
                    "accessible":              "",
                    "maps_url":                "",
                    "maps_embed_url":          "",
                    "occupancy_building_url":  "",
                    "occupancy_room_url":      "",
                    "equipment":               [],
                    "scrape_ok":               False,
                    "room_url":                "",
                }

                try:
                    detail, room_url = fetch_room_detail(sede_code, room_code)
                    if detail:
                        record.update(detail)
                        if record["capacity"] is None:
                            record["capacity"] = capacity_combo
                        record["url"] = room_url
                        record["scrape_ok"] = True
                        ok += 1
                except Exception as exc:
                    log.warning("  failed: %s", exc)

                # Normalize all string fields before writing
                record = normalize_record(record)

                # Written and flushed to disk immediately — safe against crashes
                writer.write(record)
                time.sleep(DELAY_SEC)

    log.info("Done. %d/%d rooms scraped successfully -> %s", ok, idx, OUTPUT_FILE)

    print_summary(start_time, OUTPUT_FILE)
