"""
Scraper for all UniTS degree courses:
  - Lauree Magistrali
  - Lauree Triennali e a Ciclo Unico

Iterates over all paginated pages (?page=N) for each URL and saves
all results into a single JSON file.

Dependencies: requests, beautifulsoup4
Install with: pip install requests beautifulsoup4
"""

import json
import time
import requests
from bs4 import BeautifulSoup
import argparse
from pathlib import Path

from utils import safe, print_summary, init_output

# ==============================================================================
# CONFIGURATION
# ==============================================================================

OUTPUT_FILE = Path("full_degree_programs.json")

SOURCES = [
    {
        "categoria": "Laurea Magistrale",
        "url": (
            "https://portale.units.it/it/studiare/lauree-e-lauree-magistrali"
            "/corsi-di-laurea/lauree-magistrali"
        ),
    },
    {
        "categoria": "Laurea Triennale / Ciclo Unico",
        "url": (
            "https://portale.units.it/it/studiare/lauree-e-lauree-magistrali"
            "/corsi-di-laurea/lauree-triennali-e-ciclo-unico"
        ),
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "it-IT,it;q=0.9",
}

# ==============================================================================
# PARSING
# ==============================================================================

def parse_courses(soup: BeautifulSoup, categoria: str) -> list[dict]:
    """
    Extract all course cards from a parsed page.

    Each card has the structure:
        <div class="elenco-corsi__card">
            <div class="elenco-corsi__nome"><a href="...">COURSE NAME</a></div>
            <div class="elenco-corsi__dipart">Department</div>
            <div class="elenco-corsi__tipo">Type</div>
            ...
        </div>
    """
    courses = []

    for card in soup.select("div.elenco-corsi__card"):
        # Course name and link
        nome_tag = card.select_one("div.elenco-corsi__nome a")
        nome = nome_tag.get_text(strip=True) if nome_tag else ""
        link = nome_tag["href"] if nome_tag and nome_tag.has_attr("href") else ""

        # Department — the label <span> is empty, text follows directly
        dipart_tag = card.select_one("div.elenco-corsi__dipart")
        dipartimento = _extract_value(dipart_tag)

        # Type (e.g. "Corso di Laurea Magistrale")
        tipo_tag = card.select_one("div.elenco-corsi__tipo")
        tipo = _extract_labeled_value(tipo_tag, "Tipo:")

        # Duration — reuses class "elenco-corsi__dipart" (Drupal template quirk)
        durata = ""
        for tag in card.select("div.elenco-corsi__dipart"):
            label = tag.select_one("span.elenco-corsi__label")
            if label and "Durata" in label.get_text():
                durata = _extract_labeled_value(tag, "Durata:")
                break

        # Location
        sede_tag = card.select_one("div.elenco-corsi__sede")
        sede = _extract_labeled_value(sede_tag, "Sede:")

        # Language
        lingua_tag = card.select_one("div.elenco-corsi__lingua")
        lingua = _extract_labeled_value(lingua_tag, "Lingua:")

        # Normalize tipo: "Corso di Laurea" (any case) -> "corso di laurea triennale"
        tipo_normalized = (
            "corso di laurea triennale"
            if tipo.strip().lower() == "corso di laurea"
            else tipo
        )

        courses.append({
            "name":         safe(nome),
            "link":         safe(link),
            "category":     safe(categoria),
            "department":   safe(dipartimento),
            "type":         safe(tipo_normalized),
            "duration":     safe(durata),
            "location":     safe(sede),
            "language":     safe(lingua),
        })

    return courses


def _extract_value(tag) -> str:
    """
    Extract text from a tag after removing any child <span> label elements.
    Used for the department field, where the label span is empty.
    """
    if tag is None:
        return ""
    clone = BeautifulSoup(str(tag), "html.parser").find()
    for span in clone.select("span.elenco-corsi__label"):
        span.decompose()
    return clone.get_text(strip=True)


def _extract_labeled_value(tag, label_text: str) -> str:
    """
    Extract the value from a div that contains a <span> label prefix.
    Example: <div><span>Tipo:</span> Corso di Laurea Magistrale</div>
    Returns 'Corso di Laurea Magistrale'.
    """
    if tag is None:
        return ""
    full_text = tag.get_text(separator=" ", strip=True)
    if label_text in full_text:
        return full_text.split(label_text, 1)[-1].strip()
    return full_text


# ==============================================================================
# PAGINATION
# ==============================================================================

def has_next_page(soup: BeautifulSoup) -> bool:
    """Return True if a 'next page' link exists in the pagination widget."""
    return soup.select_one("li.pager__item--next a") is not None


def fetch_page(session: requests.Session, url: str, page: int) -> BeautifulSoup | None:
    """
    Fetch a single paginated page and return its parsed BeautifulSoup.
    Returns None on HTTP errors.
    """
    params = {"page": page} if page > 0 else {}
    try:
        response = session.get(url, params=params, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"[ERROR] {url} page {page}: {e}")
        return None


# ==============================================================================
# SCRAPING LOOP
# ==============================================================================

def scrape_source(session: requests.Session, source: dict, delay) -> list[dict]:
    """Scrape all pages of a single source URL and return the course list."""
    url       = source["url"]
    categoria = source["categoria"]
    all_courses: list[dict] = []
    page = 0

    print(f"\n[SOURCE] {categoria}")

    while True:
        print(f"  [PAGE {page}]...", end=" ")
        soup = fetch_page(session, url, page)

        if soup is None:
            print("fetch failed, stopping.")
            break

        courses = parse_courses(soup, categoria)
        print(f"{len(courses)} courses found.")

        if not courses:
            break

        all_courses.extend(courses)

        if not has_next_page(soup):
            break

        page += 1
        time.sleep(delay)

    return all_courses

def save_data(output_data):
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=4, ensure_ascii=False)
        print(f"Data successfully saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"Error while saving data to {OUTPUT_FILE}: {e}")



# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    start_time = time.time()
    parser = argparse.ArgumentParser(
        description="Script used to extract the Units courses (bachelor, master and years masters' degree)."
    )
    parser.add_argument("-o", "--output", type=str, help="Output file for the extracted data.", default=OUTPUT_FILE)
    parser.add_argument("--delay", type=float, help="Delay between requests.", default=1)


    args = parser.parse_args()
    if args.output:
        OUTPUT_FILE = Path(args.output)

    init_output(OUTPUT_FILE)

    all_courses: list[dict] = []

    with requests.Session() as session:
        for source in SOURCES:
            courses = scrape_source(session, source, args.delay)
            all_courses.extend(courses)

    # Deduplicate by (name, category) — keys updated to match English field names
    seen: set[tuple] = set()
    unique_courses: list[dict] = []
    for c in all_courses:
        key = (c["name"], c["category"])
        if key not in seen:
            seen.add(key)
            unique_courses.append(c)

    print(f"\n[DONE] Total unique courses scraped: {len(unique_courses)}")

    save_data(unique_courses)
    print_summary(start_time, OUTPUT_FILE)




