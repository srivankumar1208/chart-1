import asyncio
import json
import os
import sys
import random
from playwright.async_api import async_playwright

LOGIN_URL = "https://app.chartacademy.com/login"
INITIAL_VIDEO_URL = "https://app.chartacademy.com/masterclasses/465/video/500"
WATCH_DURATION_MINUTES = 35


async def watch_account(account_label, username, password, browser):
    print(f"[{account_label}] Initializing session for: {username}")
    
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 720}
    )
    page = await context.new_page()

    async def ensure_logged_in_and_watching():
        """Navigates, logs in, and ensures video playback is active."""
        print(f"[{account_label}] Opening login page...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # Fill credentials (adjust selectors if site uses different input names/IDs)
        print(f"[{account_label}] Logging in...")
        await page.fill("input[name='email'], input[type='email'], #email", username)
        await page.fill("input[name='password'], input[type='password'], #password", password)
        await page.click("button[type='submit'], input[type='submit'], button:has-text('Login')")
        await page.wait_for_load_state("networkidle")

        # Navigate directly to the video URL if not redirected
        print(f"[{account_label}] Navigating to video page...")
        await page.goto(INITIAL_VIDEO_URL, wait_until="domcontentloaded")
        await asyncio.sleep(3)

        # Attempt to trigger video playback if paused
        await try_play_video()

    async def try_play_video():
        try:
            # Check HTML5 video elements or video frame click overlays
            video = page.locator("video").first
            if await video.is_visible():
                is_paused = await video.evaluate("v => v.paused")
                if is_paused:
                    await video.click(force=True)
                    print(f"[{account_label}] Clicked video element to start playback.")
            else:
                # Fallback click in the center of the video area
                await page.mouse.click(640, 360)
        except Exception as e:
            print(f"[{account_label}] Video play check notice: {e}")

    try:
        await ensure_logged_in_and_watching()

        total_seconds = WATCH_DURATION_MINUTES * 60
        elapsed_seconds = 0
        interval = 60  # Check state every 1 minute

        print(f"[{account_label}] Active monitoring started for {WATCH_DURATION_MINUTES} minutes...")

        while elapsed_seconds < total_seconds:
            await asyncio.sleep(interval)
            elapsed_seconds += interval

            # 1. Check video playback state every 1 minute
            try:
                video = page.locator("video").first
                if await video.is_visible():
                    is_paused = await video.evaluate("v => v.paused")
                    is_ended = await video.evaluate("v => v.ended")
                    
                    if is_ended:
                        print(f"[{account_label}] Video ended. Waiting for auto-next transition...")
                        await asyncio.sleep(5)
                        await try_play_video()
                    elif is_paused:
                        print(f"[{account_label}] Video is paused. Attempting to resume...")
                        await try_play_video()
                        # If still paused after click, refresh page
                        if await video.evaluate("v => v.paused"):
                            print(f"[{account_label}] Playback recovery failed. Refreshing page...")
                            await page.reload(wait_until="domcontentloaded")
                            await asyncio.sleep(3)
                            await try_play_video()
                    else:
                        print(f"[{account_label}] Check ok (Elapsed: {elapsed_seconds // 60}m) - Video playing.")
                else:
                    print(f"[{account_label}] Video element missing/transitioning. Refreshing...")
                    await page.reload(wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    await try_play_video()
            except Exception as e:
                print(f"[{account_label}] Error checking state: {e}. Refreshing page...")
                await page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(3)
                await try_play_video()

            # 2. Trigger anti-idle mouse movement every 10 minutes
            if elapsed_seconds % 600 == 0:
                rx = random.randint(100, 1000)
                ry = random.randint(100, 600)
                await page.mouse.move(rx, ry)
                await page.mouse.wheel(0, 100)
                await page.mouse.wheel(0, -100)
                print(f"[{account_label}] Anti-idle activity triggered (Mouse moved to {rx}, {ry}).")

        print(f"[{account_label}] 35-minute watch session completed successfully.")

    except Exception as e:
        print(f"[{account_label}] Critical error during task: {e}")
    finally:
        await context.close()


async def main():
    accounts_json = os.getenv("ACCOUNTS_JSON")
    if not accounts_json:
        print("Error: ACCOUNTS_JSON secret is missing.")
        sys.exit(1)

    accounts = json.loads(accounts_json)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--autoplay-policy=no-user-gesture-required",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )

        tasks = [
            watch_account(f"Account-{i+1}", acc["email"], acc["password"], browser)
            for i, acc in enumerate(accounts)
        ]

        await asyncio.gather(*tasks)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
