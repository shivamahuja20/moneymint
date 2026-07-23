"""
Automates AMFI's official TER disclosure page to pull real expense ratios.
https://www.amfiindia.com/ter-of-mf-schemes

IMPORTANT — read before running:
This is a browser-automation script (uses Playwright to literally click through the page
like a person would), because AMFI's TER page has no simple downloadable file — only
an interactive form. This was written without being able to test it against the live
site (this environment can't reach amfiindia.com), so the first run may fail at some
step. If it does: it saves a screenshot (ter_debug.png) at the point of failure — send
that screenshot back and the exact error text, and the selectors below can be corrected.

One-time setup (only needed once):
    ./venv/bin/pip install playwright
    ./venv/bin/python -m playwright install chromium

Run:
    ./venv/bin/python -m app.ingestion.ter_scraper
"""
import sys, os, re, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from app.db import SessionLocal
from app import models

URL = "https://www.amfiindia.com/ter-of-mf-schemes"

# Map each fund to the exact dropdown values needed to find it on the TER page.
# Adjust "amc_dropdown_name" / "category_dropdown_name" if AMFI's exact wording differs
# from what's guessed here — check the actual dropdown options in the browser.
FUND_LOOKUP = {
    "hdfc-flexi-cap":    {"amc": "HDFC Mutual Fund", "scheme_match": "Flexi Cap"},
    "parag-parikh-flexi": {"amc": "PPFAS Mutual Fund", "scheme_match": "Flexi Cap"},
    "icici-tech":        {"amc": "ICICI Prudential Mutual Fund", "scheme_match": "Technology"},
    "sbi-banking-fin":   {"amc": "SBI Mutual Fund", "scheme_match": "Banking"},
    "nippon-pharma":     {"amc": "Nippon India Mutual Fund", "scheme_match": "Pharma"},
    "quant-infra":       {"amc": "Quant Mutual Fund", "scheme_match": "Infrastructure"},
    "hdfc-defence":      {"amc": "HDFC Mutual Fund", "scheme_match": "Defence"},
    "axis-realty":       {"amc": "Tata Mutual Fund", "scheme_match": "Housing"},
    "tata-fmcg":         {"amc": "Tata Mutual Fund", "scheme_match": "Consumer"},
    "dsp-energy":        {"amc": "DSP Mutual Fund", "scheme_match": "Natural Resources"},
}


def run():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright isn't installed yet. Run these two commands first:")
        print("  ./venv/bin/pip install playwright")
        print("  ./venv/bin/python -m playwright install chromium")
        return

    db = SessionLocal()
    results = {}

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Group funds by AMC so we only load each AMC's page once
        amcs = {}
        for fund_id, info in FUND_LOOKUP.items():
            amcs.setdefault(info["amc"], []).append((fund_id, info["scheme_match"]))

        for amc_name, fund_list in amcs.items():
            print(f"\n--- Fetching TER for {amc_name} ---")
            try:
                page.goto(URL, timeout=30000)
                page.wait_for_load_state("networkidle")

                # Select Fund Type = "Open Ended" (most common), Mutual Fund = the AMC name.
                # These clicks target visible text — likely to need adjustment on first real run.
                page.get_by_text("Fund Type", exact=False).first.click()
                page.get_by_text("Open Ended", exact=False).first.click()

                page.get_by_text("Mutual Fund", exact=False).last.click()
                page.get_by_text(amc_name, exact=False).first.click()

                page.get_by_role("button", name=re.compile("Go", re.IGNORECASE)).click()
                page.wait_for_load_state("networkidle")

                # Scrape the resulting table
                rows = page.locator("table tr").all()
                table_text = [r.inner_text() for r in rows]

                for fund_id, scheme_match in fund_list:
                    match_row = next((r for r in table_text if scheme_match.lower() in r.lower()), None)
                    if match_row:
                        # Look for a percentage figure in the matched row
                        pct_match = re.search(r"(\d+\.\d+)\s*%?", match_row)
                        if pct_match:
                            results[fund_id] = float(pct_match.group(1))
                            print(f"  Found {fund_id}: {results[fund_id]}%")
                        else:
                            print(f"  Matched a row for {fund_id} but couldn't extract a percentage: {match_row[:100]}")
                    else:
                        print(f"  No matching row found for {fund_id} (looked for '{scheme_match}')")

            except Exception as e:
                screenshot_path = f"ter_debug_{amc_name.replace(' ', '_')}.png"
                page.screenshot(path=screenshot_path)
                print(f"  Failed on {amc_name}: {e}")
                print(f"  Saved a screenshot to {screenshot_path} — send this back for debugging.")

        browser.close()

    # Apply whatever we successfully found
    updated = 0
    for fund_id, ter in results.items():
        fund = db.query(models.Fund).filter(models.Fund.id == fund_id).first()
        if fund:
            fund.expense_ratio = ter
            updated += 1
    db.commit()
    db.close()

    print(f"\nUpdated {updated} of {len(FUND_LOOKUP)} funds with real TER data.")
    if updated < len(FUND_LOOKUP):
        print("For any that failed, check the saved screenshot(s) and send them back to fix the selectors.")


if __name__ == "__main__":
    run()
