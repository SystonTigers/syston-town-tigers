// scripts/scrape_fulltime.mjs
import fs from "node:fs/promises";
import puppeteer from "puppeteer";

const BASE = "https://systontigers.github.io/syston-town-tigers";
const TEAM_FIXTURES_URL = `${BASE}/team-fixtures.html`;
const TEAM_RESULTS_URL  = `${BASE}/team-results.html`;

// The FA widget usually renders into a DIV with id "lrep" + league/club code.
// Your pages use lrcode = '577104452', so we watch this container:
const WIDGET_SELECTOR = "#lrep455713059";

// Wait for the widget to render something table-ish
async function waitForWidget(page) {
  await page.waitForSelector(
    `${WIDGET_SELECTOR} table, ${WIDGET_SELECTOR} tbody tr, ${WIDGET_SELECTOR} .fixtures, ${WIDGET_SELECTOR} .results`,
    { timeout: 30000 }
  );
}

// Pull a matrix (array of row arrays) from the widget area
async function extractTable(page) {
  return await page.evaluate((sel) => {
    const box = document.querySelector(sel);
    if (!box) return [];
    const table = box.querySelector("table");
    if (!table) {
      const rows = [...box.querySelectorAll("tr, .row, li")];
      return rows.map(r => [...r.querySelectorAll("td, th, div, span")].map(c => c.textContent.trim()));
    }
    const rows = [...table.querySelectorAll("tr")];
    return rows.map(r => [...r.querySelectorAll("th, td")].map(c => c.textContent.trim()));
  }, WIDGET_SELECTOR);
}

function parseScore(s) {
  const m = String(s || "").match(/(\d+)\D+(\d+)/);
  return m ? { hs: Number(m[1]), as: Number(m[2]) } : { hs: "", as: "" };
}

function toGbDate(s) {
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(String(s))) return s;
  const parts = String(s).match(/(\d{1,2})[^\d](\d{1,2})[^\d](\d{2,4})/);
  if (!parts) return String(s);
  const dd = parts[1].padStart(2, "0");
  const mm = parts[2].padStart(2, "0");
  const yyyy = parts[3].length === 2 ? `20${parts[3]}` : parts[3];
  return `${dd}/${mm}/${yyyy}`;
}

function toFixturesJson(matrix) {
  const body = matrix.filter(row => row.some(cell => /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(cell) || /v|vs/i.test(cell)));
  const out = [];
  for (const row of body) {
    // Try common order: Date, Competition, Home, Away, KO, Venue
    let [date, comp, home, away, ko, venue] = row;
    if (!home || !away || !date) continue;
    out.push({
      date: toGbDate(date),
      matchType: comp || "League",
      home,
      away,
      venue: venue || "",
      ko: (ko || "").replace(/\s/g, "")
    });
  }
  return out;
}

function toResultsJson(matrix) {
  const out = [];
  const body = matrix.filter(row => row.some(cell => /\d{1,2}\/\d{1,2}\/\d{2,4}/.test(cell)));
  for (const row of body) {
    let date = row[0], comp = row[1], home = row[2], score = row[3], away = row[4];
    let venue = row[5] || "", ko = row[6] || "";
    if (!date || !home || !away) continue;
    const { hs, as } = parseScore(score || "");
    out.push({
      date: toGbDate(date),
      matchType: comp || "League",
      home, away, hs, as, venue,
      ko: (ko || "").replace(/\s/g, "")
    });
  }
  return out;
}

async function run() {
  const browser = await puppeteer.launch({ headless: "new" });
  const page = await browser.newPage();

  // Fixtures
  await page.goto(TEAM_FIXTURES_URL, { waitUntil: "domcontentloaded" });
  await waitForWidget(page);
  const fixMatrix = await extractTable(page);
  const fixtures = toFixturesJson(fixMatrix);

  // Results
  await page.goto(TEAM_RESULTS_URL, { waitUntil: "domcontentloaded" });
  await waitForWidget(page);
  const resMatrix = await extractTable(page);
  const results = toResultsJson(resMatrix);

  await browser.close();

  await fs.writeFile("fixtures.json", JSON.stringify(fixtures, null, 2), "utf8");
  await fs.writeFile("results.json",  JSON.stringify(results,  null, 2), "utf8");

  console.log(`Wrote fixtures.json (${fixtures.length}) and results.json (${results.length})`);
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
