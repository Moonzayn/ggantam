import asyncio
import os
import platform
import json
import re
import time as time_module
from datetime import datetime
import sys

import nodriver as uc

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"email": "pangkassobo@gmail.com", "password": "198456z"}

def _find_chrome():
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
    else:
        candidates = ["/usr/bin/google-chrome-stable"]
    for p in candidates:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Chrome not found")

def _get_profile_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")

def solve_captcha(text):
    text = text.lower()
    m = re.search(r"(\d+)\s*(dikali|dikurangi|dijumlahkan|ditambah)\s*(\d+)", text)
    if m:
        a, b = int(m.group(1)), int(m.group(3))
        op = m.group(2)
        if "kali" in op:
            return a * b
        elif "kurang" in op:
            return a - b
        return a + b
    return 0

async def save_cookies(browser):
    try:
        cookies = await browser.cookies.get_all()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)
        print("[*] Cookies saved")
        return True
    except Exception as e:
        print(f"[!] Save cookies error: {e}")
        return False

async def load_cookies(browser):
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
        await browser.cookies.set_all(cookies)
        print("[*] Cookies loaded")
        return True
    except Exception as e:
        print(f"[!] Load cookies error: {e}")
        return False

async def wait_for_cloudflare(page, timeout=30):
    """Handle Cloudflare using nodriver's built-in cf_verify"""
    print("[*] Checking for Cloudflare...")
    try:
        await page.cf_verify(timeout=timeout)
        print("[+] Cloudflare cleared!")
        return True
    except Exception as e:
        print(f"[*] No Cloudflare challenge or already cleared: {e}")
        return True

async def wait_for_element(page, selector, timeout=30):
    """Wait for element to appear"""
    start = time_module.time()
    while time_module.time() - start < timeout:
        try:
            el = await page.select(selector)
            if el:
                return True
        except:
            pass
        await asyncio.sleep(1)
    return False

async def is_logged_in(page):
    try:
        html = await page.get_content()
        return "logout" in html.lower()
    except:
        return False

async def try_login(page, email, password, attempt_num):
    """Try to login once using nodriver native methods"""
    print(f"\n[*] Login attempt {attempt_num}")
    
    # Navigate to login page
    page = await page.browser.get("https://antrean.logammulia.com/login")
    await wait_for_cloudflare(page, timeout=30)
    
    # Wait for form to load
    print("[*] Waiting for login form...")
    try:
        username_el = await page.select('input[name="username"]', timeout=20)
    except:
        print("[!] Login form not found!")
        html = await page.get_content()
        print(f"[DEBUG] Page: {html[:500]}")
        return False
    
    # Get captcha
    captcha_answer = ""
    try:
        captcha_label = await page.find("aritmetika", best_match=True, timeout=3)
        if captcha_label:
            captcha_text = (await captcha_label.text).strip()
            print(f"[*] Captcha: {captcha_text}")
            captcha_answer = str(solve_captcha(captcha_text))
            print(f"[*] Answer: {captcha_answer}")
    except:
        pass
    
    # Fill form using nodriver native methods
    print("[*] Filling form...")
    await username_el.send_keys(email)
    await asyncio.sleep(0.5)
    
    password_el = await page.select('input[name="password"]', timeout=5)
    await password_el.send_keys(password)
    await asyncio.sleep(0.5)
    
    if captcha_answer:
        try:
            captcha_el = await page.select('input[name="aritmetika"]', timeout=5)
            await captcha_el.send_keys(captcha_answer)
        except:
            pass
        await asyncio.sleep(0.5)
    
    # Submit
    print("[*] Submitting...")
    try:
        submit_btn = await page.select('button[type="submit"]', timeout=5)
        await submit_btn.click()
    except:
        await page.evaluate('document.querySelector(\'button[type="submit"]\').click()')
    
    # Wait for response
    print("[*] Waiting for response...")
    for i in range(30):
        await asyncio.sleep(1)
        
        if await is_logged_in(page):
            print("[+] LOGIN SUCCESS!")
            return True
        
        # Check if Cloudflare appeared
        await wait_for_cloudflare(page, timeout=10)
        if await is_logged_in(page):
            print("[+] LOGIN SUCCESS!")
            return True
    
    print("[!] Login attempt failed")
    return False

async def main():
    print("\n" + "="*50)
    print("  ANTREAN BOT - LOGIN TEST")
    print("="*50 + "\n")
    
    config = load_config()
    email = config.get("email", "")
    password = config.get("password", "")
    
    print(f"[*] Email: {email}")
    print("[*] Starting Chrome...")
    
    try:
        browser = await uc.start(
            browser_executable_path=_find_chrome(),
            headless=False,
            user_data_dir=_get_profile_dir(),
        )
    except Exception as e:
        print(f"[!] Browser start error: {e}")
        return
    
    page = await browser.get("https://antrean.logammulia.com")
    print("[*] Initial page loaded")
    await asyncio.sleep(5)
    
    await wait_for_cloudflare(page, timeout=30)
    
    # Try load saved cookies
    await load_cookies(browser)
    await page.reload()
    await asyncio.sleep(5)
    await wait_for_cloudflare(page, timeout=30)
    
    if await is_logged_in(page):
        print("[+] Already logged in via cookies!")
        print("[*] SUCCESS!")
        await asyncio.sleep(5)
        browser.stop()
        return
    
    # Try login multiple times
    for attempt in range(1, 6):
        success = await try_login(page, email, password, attempt)
        if success:
            await save_cookies(browser)
            print("[*] Cookies saved. Next time will auto-login!")
            await asyncio.sleep(5)
            browser.stop()
            return
        
        if attempt < 5:
            print(f"[*] Retrying in 5 seconds...")
            await asyncio.sleep(5)
    
    print("[!] All login attempts failed")
    try:
        await page.save_screenshot("login_failed.png")
        print("[*] Screenshot saved to login_failed.png")
    except:
        pass
    browser.stop()

if __name__ == "__main__":
    asyncio.run(main())
