#!/usr/bin/env python3
"""Checks StädteRegion Aachen for a 'Umschreibung ausländische Fahrerlaubnis' slot
in Würselen and pushes an alert to iPhone (ntfy) + Mac when one appears.
Setup: pip3 install playwright && python3 -m playwright install chromium
Run:   NTFY_TOPIC=your-secret-topic python3 termin_watch.py
"""
import asyncio, os, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright

BASE = "https://termine.staedteregion-aachen.de"
TOPIC = os.environ.get("NTFY_TOPIC")  # pick something unguessable, topics are public
NONE_TEXT = "alle Termine vergeben"

# --burst: the times new slots reportedly get released (German local time)
BERLIN = ZoneInfo("Europe/Berlin")
DROPS = [(0, 0), (7, 0), (8, 0)]
DROP_DELAY = 20     # first check this many seconds after the drop
WINDOW = 300        # keep checking this long after the first check
INTERVAL = 30
MAX_WAIT = 30 * 60  # cron fires ~20 min early; skip if no drop is this close


def notify(title, msg, urgent=True):
    print(f"{title}: {msg}")
    if TOPIC:
        req = urllib.request.Request(f"https://ntfy.sh/{TOPIC}", data=msg.encode(), headers={
            "Title": title,
            "Priority": "urgent" if urgent else "low",
            "Tags": "rotating_light" if urgent else "warning",
            "Click": BASE + "/select2?md=2",
        })
        urllib.request.urlopen(req, timeout=15)
    if sys.platform == "darwin":
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "{title}" sound name "Glass"'])
        if urgent:
            subprocess.run(["say", "Führerschein Termin verfügbar"])


async def check():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.set_default_timeout(20000)
        await page.goto(BASE + "/select2?md=2")                 # Führerscheinstelle Würselen
        if await page.locator("#cookie_msg_btn_no").is_visible():
            await page.click("#cookie_msg_btn_no")
        await page.click("#header_concerns_accordion-58645")     # open the accordion
        await page.click("#button-plus-1357")                    # 1 x Umschreibung ausländische FE
        await page.click("#WeiterButton")
        await page.wait_for_timeout(1500)
        if await page.locator("#OKButton").is_visible():         # info modal, if shown
            await page.click("#OKButton")
        await page.wait_for_load_state()
        await page.click("#WeiterButton")                        # only location: Würselen
        await page.wait_for_load_state()
        text = await page.inner_text("body")
        await browser.close()
        return text


def run_once():
    """One check. Returns 'none', 'found' or 'unexpected'; raises if the site/browser fails."""
    text = asyncio.run(check())
    if NONE_TEXT in text:
        print("no slots")
        return "none"
    if "Schritt 4" in text:
        notify("TERMIN FREI!", "Führerscheinstelle Würselen hat Termine. Jetzt buchen!")
        return "found"
    notify("Termin watcher: unexpected page", text[:150], urgent=False)
    return "unexpected"


def next_drop(now):
    """Start of the earliest drop window that hasn't ended yet."""
    starts = []
    for day in (0, 1):
        d = now + timedelta(days=day)
        for h, m in DROPS:
            t = datetime(d.year, d.month, d.day, h, m, DROP_DELAY, tzinfo=BERLIN)
            if t + timedelta(seconds=WINDOW) > now:
                starts.append(t)
    return min(starts)


def burst():
    """Wait for the next drop time, then poll every INTERVAL seconds for WINDOW seconds."""
    now = datetime.now(BERLIN)
    start = next_drop(now)
    wait = (start - now).total_seconds()
    if wait > MAX_WAIT:
        print(f"next drop {start:%H:%M:%S} Berlin is {wait / 60:.0f} min away, skipping")
        return
    if wait > 0:
        print(f"waiting {wait:.0f}s until {start:%H:%M:%S} Berlin", flush=True)
        time.sleep(wait)
    end = start + timedelta(seconds=WINDOW)
    error = None
    checked = False
    while True:
        print(f"{datetime.now(BERLIN):%H:%M:%S} Berlin: ", end="", flush=True)
        try:
            if run_once() != "none":
                return
            checked = True
        except Exception as e:  # one flaky load shouldn't end the burst
            error = e
            print(f"check failed: {type(e).__name__}: {e}")
        if datetime.now(BERLIN) + timedelta(seconds=INTERVAL) > end:
            break
        time.sleep(INTERVAL)
    if not checked:
        notify("Termin watcher broken", f"{type(error).__name__}: {str(error)[:120]}", urgent=False)
        sys.exit(1)


def main():
    if "--burst" in sys.argv:
        return burst()
    try:
        run_once()
    except Exception as e:
        # ponytail: one low-priority ping per failure; add a failure counter if the site flakes a lot
        notify("Termin watcher broken", f"{type(e).__name__}: {str(e)[:120]}", urgent=False)
        sys.exit(1)


if __name__ == "__main__":
    main()
