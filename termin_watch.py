#!/usr/bin/env python3
"""Checks StädteRegion Aachen for a 'Umschreibung ausländische Fahrerlaubnis' slot
in Würselen and pushes an alert to iPhone (ntfy) + Mac when one appears.
Setup: pip3 install playwright && python3 -m playwright install chromium
Run:   NTFY_TOPIC=your-secret-topic python3 termin_watch.py
"""
import asyncio, os, subprocess, sys, urllib.request
from playwright.async_api import async_playwright

BASE = "https://termine.staedteregion-aachen.de"
TOPIC = os.environ.get("NTFY_TOPIC")  # pick something unguessable, topics are public
NONE_TEXT = "alle Termine vergeben"


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


def main():
    try:
        text = asyncio.run(check())
    except Exception as e:
        # ponytail: one low-priority ping per failure; add a failure counter if the site flakes a lot
        notify("Termin watcher broken", f"{type(e).__name__}: {str(e)[:120]}", urgent=False)
        sys.exit(1)
    if NONE_TEXT in text:
        print("no slots")
    elif "Schritt 4" in text:
        notify("TERMIN FREI!", "Führerscheinstelle Würselen hat Termine. Jetzt buchen!")
    else:
        notify("Termin watcher: unexpected page", text[:150], urgent=False)


if __name__ == "__main__":
    main()
