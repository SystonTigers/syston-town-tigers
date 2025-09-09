# .github/scripts/scrape_fa_results.py
import os, re, json, datetime, sys
import requests
from bs4 import BeautifulSoup

# -------- Inputs (set these URLs in the workflow env) ----------
FIXTURES_URL = os.getenv("FA_FIXTURES_URL", "").strip()
RESULTS_URL  = os.getenv("FA_RESULTS_URL", "").strip()

# Where to write JSON in the repo root
FIXTURES_JSON_PATH = "fixtures.json"
RESULTS_JSON_PATH  = "results.json"

# -------- Helpers ----------
UK_TZ = "Europe/London"

def to_ymd(date_str):
    """
    Accepts things like 'Sun 07 Sep 2025', '07/09/2025', '2025-09-07'
    and returns 'yyyy-mm-dd' or ''.
    """
    if not date_str:
        return ""
    s = str(date_str).strip()
    # Already ISO?
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # dd/mm/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        dd, mm, yyyy = m.groups()
        try:
            d = datetime.date(int(yyyy), int(mm), int(dd))
            return d.isoformat()
        except Exception:
            return ""
    # 'Sun 07 Sep 2025' etc.
    m = re.match(r"^\w{3}\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", s)
    if m:
        dd, mon, yyyy = m.groups()
        months = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,
                  "Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        try:
            d = datetime.date(int(yyyy), months[mon.title()], int(dd))
            return d.isoformat()
        except Exception:
            return ""
    return ""

def tidy(text):
    return re.sub(r"\s+", " ", (text or "")).strip()

def fetch_html(url):
    if not url:
        return ""
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    return r.text

# -------- Scrapers ----------
def scrape_fixtures(html):
    """
    Parse FA Full-Time fixtures snippet into list:
    {date, matchType, home, away, venue, ko}
    """
    out = []
    soup = BeautifulSoup(html, "html.parser")

    # This handles both table-based and card-based snippets fairly well.
    # 1) Table rows
    rows = soup.select("table tr")
    for tr in rows:
        tds = [tidy(td.get_text()) for td in tr.find_all("td")]
        if len(tds) < 5:
            continue
        # Heuristics: [Date, Type, Home, Away, Venue, KO?]
        date = to_ymd(tds[0])
        mtype = tds[1] if len(tds) > 1 else ""
        home  = tds[2] if len(tds) > 2 else ""
        away  = tds[3] if len(tds) > 3 else ""
        venue = tds[4] if len(tds) > 4 else ""
        ko    = tds[5] if len(tds) > 5 else ""
        if date and home and away:
            out.append({
                "date": date,
                "matchType": mtype,
                "home": home,
                "away": away,
                "venue": venue,
                "ko": ko
            })

    # 2) Card blocks (fallback)
    if not out:
        for card in soup.select("[class*=fixture], .match, .fixture"):
            text = tidy(card.get_text(" "))
            # Very tolerant regex
            m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\w{3}\s+\d{1,2}\s+\w{3}\s+\d{4})", text)
            date = to_ymd(m.group(1)) if m else ""
            m2 = re.search(r"(.+?)\s+v(?:s)?\s+(.+?)\b", text, re.I)
            home = tidy(m2.group(1)) if m2 else ""
            away = tidy(m2.group(2)) if m2 else ""
            ko_m = re.search(r"\b(\d{1,2}:\d{2})\b", text)
            ko = ko_m.group(1) if ko_m else ""
            if date and home and away:
                out.append({
                    "date": date, "matchType": "", "home": home,
                    "away": away, "venue": "", "ko": ko
                })
    return out

def scrape_results(html):
    """
    Parse FA Full-Time results snippet into list:
    {date, matchType, home, away, hs, as}
    """
    out = []
    soup = BeautifulSoup(html, "html.parser")

    # Table rows first
    rows = soup.select("table tr")
    for tr in rows:
        tds = [tidy(td.get_text()) for td in tr.find_all("td")]
        if len(tds) < 6:
            continue
        date = to_ymd(tds[0])
        mtype = tds[1]
        home  = tds[2]
        away  = tds[4] if len(tds) > 4 else ""
        # Score might be in tds[3] like "2 - 0" or split across HS/AS cols
        hs, as_ = "", ""
        sc = tds[3]
        m = re.search(r"(\d+)\s*[-–]\s*(\d+)", sc)
        if m:
            hs, as_ = m.group(1), m.group(2)
        elif len(tds) >= 6:
            hs, as_ = tds[3], tds[5]
        if date and home and away and hs != "" and as_ != "":
            out.append({
                "date": date,
                "matchType": mtype,
                "home": home,
                "away": away,
                "hs": int(hs),
                "as": int(as_)
            })

    # Card fallback
    if not out:
        for card in soup.select("[class*=result], .match, .result"):
            text = tidy(card.get_text(" "))
            date_m = re.search(r"(\d{1,2}/\d{1,2}/\d{4}|\w{3}\s+\d{1,2}\s+\w{3}\s+\d{4})", text)
            date = to_ymd(date_m.group(1)) if date_m else ""
            teams = re.search(r"(.+?)\s+(\d+)\s*[-–]\s*(\d+)\s+(.+)", text)
            if teams and date:
                home = tidy(teams.group(1))
                hs   = int(teams.group(2))
                as_  = int(teams.group(3))
                away = tidy(teams.group(4))
                out.append({
                    "date": date,
                    "matchType": "",
                    "home": home,
                    "away": away,
                    "hs": hs,
                    "as": as_
                })
    return out

# -------- Main ----------
def main():
    changed = False

    if FIXTURES_URL:
        f_html = fetch_html(FIXTURES_URL)
        f_list = scrape_fixtures(f_html)
        with open(FIXTURES_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(f_list, f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(f_list)} fixtures -> {FIXTURES_JSON_PATH}")
        changed = True

    if RESULTS_URL:
        r_html = fetch_html(RESULTS_URL)
        r_list = scrape_results(r_html)
        with open(RESULTS_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(r_list, f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(r_list)} results -> {RESULTS_JSON_PATH}")
        changed = True

    if not changed:
        print("Nothing to do: no FA URLs provided.")
        sys.exit(0)

if __name__ == "__main__":
    main()
