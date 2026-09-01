import asyncio
import json
import os
import random
import subprocess
from playwright.async_api import async_playwright

# HARDCODED CREDENTIALS
ACCOUNTS = [
    {"email": "saipavan7748@gmail.com", "password": "Sai@1234"},
    {"email": "skywalker774826@gmail.com", "password": "Sky@1234"},
    {"email": "adupasrivankumar@gmail.com", "password": "Srivan@1234"},
]

LOGIN_URL = "https://app.chartacademy.com/login"
WATCH_DURATION_MINUTES = 33
STATE_FILE = "state.json"

# Masterclasses and duration in days
# Format: ("URL", days_to_stay)
MASTERCLASS_SCHEDULE = [
    ("https://app.chartacademy.com/masterclasses/562/video/595", 4),  # 1st Masterclass: 3 Days
    ("https://app.chartacademy.com/masterclasses/463/video/496", 4),  # 2nd Masterclass: 4 Days
    ("https://app.chartacademy.com/masterclasses/299/video/303", 4),  # 3rd Masterclass: 3 Days
    ("https://app.chartacademy.com/masterclasses/608/video/675", 2),
    ("https://app.chartacademy.com/masterclasses/607/video/660", 2),
    ("https://app.chartacademy.com/masterclasses/465/video/503", 8),
    ("https://app.chartacademy.com/masterclasses/430/video/463", 4)
]


def load_state():
    """Reads current progress from state.json."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[State Manager] Error reading state.json: {e}")
    return {"masterclass_index": 0, "day_count": 0}


def save_and_commit_state(state):
    """Saves updated state and pushes changes to the GitHub repository."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

    # Automatically commit changes back to GitHub when running inside GitHub Actions
    if os.getenv("GITHUB_ACTIONS"):
        try:
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
            subprocess.run(["git", "add", STATE_FILE], check=True)
            subprocess.run(["git", "commit", "-m", "Automated state update [skip ci]"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("[State Manager] State updated and pushed to GitHub successfully.")
        except Exception as e:
            print(f"[State Manager] Failed to push updated state to GitHub: {e}")


def get_current_target_url():
    """Determines target Masterclass URL based on state.json counter."""
    state = load_state()
    index = state["masterclass_index"]

    if index >= len(MASTERCLASS_SCHEDULE):
        index = len(MASTERCLASS_SCHEDULE) - 1

    target_url, required_days = MASTERCLASS_SCHEDULE[index]
    current_day = state["day_count"] + 1
    print(f"[State Manager] Active Masterclass #{index + 1} | Day {current_day} of {required_days}")
    print(f"[State Manager] Playing Target URL: {target_url}")
    return target_url


def increment_counter():
    """Increments state values after a successful watch session."""
    state = load_state()
    index = state["masterclass_index"]
    day_count = state["day_count"] + 1

    if index < len(MASTERCLASS_SCHEDULE):
        _, required_days = MASTERCLASS_SCHEDULE[index]
    else:
        required_days = MASTERCLASS_SCHEDULE[-1][1]

    if day_count >= required_days:
        state["masterclass_index"] += 1
        state["day_count"] = 0
        print("[State Manager] Masterclass completed! Transitioning to next link on next run.")
    else:
        state["day_count"] = day_count
        print(f"[State Manager] Incremented day count to {day_count}/{required_days}.")

    save_and_commit_state(state)


async def watch_account(account_label, username, password, target_url, browser):
    print(f"[{account_label}] Initializing context for: {username}")
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720},
    )
    page = await context.new_page()

    async def ensure_logged_in_and_watching():
        print(f"[{account_label}] Opening login page...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        print(f"[{account_label}] Logging in...")
        await page.fill("input[name='email'], input[type='email'], #email", username)
        await page.fill("input[name='password'], input[type='password'], #password", password)
        await page.click("button[type='submit'], input[type='submit'], button:has-text('Login')")
        await page.wait_for_load_state("networkidle")

        print(f"[{account_label}] Opening target masterclass video...")
        await page.goto(target_url, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        await try_play_video()

    async def try_play_video():
        try:
            video = page.locator("video").first
            if await video.is_visible():
                is_paused = await video.evaluate("v => v.paused")
                if is_paused:
                    await video.click(force=True)
                    print(f"[{account_label}] Clicked video element to resume playback.")
            else:
                await page.mouse.click(640, 360)
        except Exception as e:
            print(f"[{account_label}] Video playback notice: {e}")

    try:
        await ensure_logged_in_and_watching()

        total_seconds = WATCH_DURATION_MINUTES * 60
        elapsed_seconds = 0
        interval = 60

        print(f"[{account_label}] Monitoring video playback for {WATCH_DURATION_MINUTES} minutes...")

        while elapsed_seconds < total_seconds:
            await asyncio.sleep(interval)
            elapsed_seconds += interval

            try:
                video = page.locator("video").first
                if await video.is_visible():
                    is_paused = await video.evaluate("v => v.paused")
                    is_ended = await video.evaluate("v => v.ended")

                    if is_ended or is_paused:
                        print(f"[{account_label}] Video paused/ended. Resuming...")
                        await try_play_video()
                    else:
                        print(f"[{account_label}] Check ok ({elapsed_seconds // 60}m) - Video actively playing.")
                else:
                    print(f"[{account_label}] Video element missing. Reloading target URL...")
                    await page.goto(target_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    await try_play_video()
            except Exception as e:
                print(f"[{account_label}] Error during playback check: {e}")

            # Anti-idle mouse activity every 10 minutes
            if elapsed_seconds % 600 == 0:
                rx, ry = random.randint(100, 1000), random.randint(100, 600)
                await page.mouse.move(rx, ry)
                await page.mouse.wheel(0, 100)
                await page.mouse.wheel(0, -100)
                print(f"[{account_label}] Anti-idle activity executed.")

        print(f"[{account_label}] Session completed successfully.")

    except Exception as e:
        print(f"[{account_label}] Critical error: {e}")
    finally:
        await context.close()


async def main():
    target_url = get_current_target_url()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
        )

        tasks = [
            watch_account(
                f"Account-{i+1}", acc["email"], acc["password"], target_url, browser
            )
            for i, acc in enumerate(ACCOUNTS)
        ]

        await asyncio.gather(*tasks)
        await browser.close()

    # Update counter state and commit back to GitHub after session finishes
    increment_counter()


if __name__ == "__main__":
    asyncio.run(main())
