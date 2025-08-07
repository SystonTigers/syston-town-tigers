import requests
from bs4 import BeautifulSoup
import json
import datetime

# Replace with your actual FA Full-Time results URL
FA_RESULTS_URL = "https://fulltime.thefa.com/displayTeam.html?divisionseason=895836158&teamID=87654321"

def scrape_results():
    response = requests.get(FA_RESULTS_URL)
    soup = BeautifulSoup(response.text, "html.parser")

    results = []
    match_rows = soup.select(".match-details")

    for row in match_rows:
        date = row.select_one(".date").text.strip()
        teams = row.select_one(".teams").text.strip()
        score = row.select_one(".score").text.strip()
        location = row.select_one(".location").text.strip() if row.select_one(".location") else "Unknown"

        results.append({
            "date": date,
            "teams": teams,
            "score": score,
            "location": location,
        })

    filename = f"data/results_{datetime.datetime.now().strftime('%Y%m%d')}.json"
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)

if __name__ == "__main__":
    scrape_results()
