"""
Diagnostic only — figures out the real clickable structure of AMFI's TER page dropdowns
before we try to automate the full flow again.

Run:
    ./venv/bin/python app/ingestion/ter_diagnostic.py

It will save a few screenshots and print whatever option text it can find, so we can
build the real scraper based on facts instead of guesses.
"""
from playwright.sync_api import sync_playwright

URL = "https://www.amfiindia.com/ter-of-mf-schemes"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(URL, timeout=30000)
    page.wait_for_load_state("networkidle")

    print("Step 1: clicking the 'Select Fund Type' box (not the label above it)...")
    try:
        # Target the placeholder text inside the box, not the label above it
        page.get_by_text("Select Fund Type", exact=True).click()
        page.wait_for_timeout(800)  # give any dropdown animation time to render
        page.screenshot(path="diag_1_fundtype_opened.png")
        print("Saved diag_1_fundtype_opened.png")

        # Try a few common ways a dropdown's options might be structured
        for selector in ["li", "[role='option']", "div[class*='option']", "ul li", "div[class*='menu'] div"]:
            items = page.locator(selector).all_inner_texts()
            items = [i.strip() for i in items if i.strip()]
            if items:
                print(f"Selector '{selector}' found {len(items)} items: {items[:15]}")
    except Exception as e:
        print(f"Step 1 failed: {e}")
        page.screenshot(path="diag_1_failed.png")

    print("\nStep 2: dumping the full page HTML for the dropdown area (first 3000 chars)...")
    try:
        html = page.content()
        # find the area mentioning "Fund Type" and print surrounding HTML
        idx = html.find("Fund Type")
        print(html[max(0, idx-200):idx+1500])
    except Exception as e:
        print(f"Step 2 failed: {e}")

    browser.close()

print("\nDone. Send back: this printed output, plus diag_1_fundtype_opened.png")
