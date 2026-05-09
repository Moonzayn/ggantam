# antrean_bot.py - Playwright version
import asyncio
import json
import re
import os
import sys
from datetime import datetime

from playwright.sync_api import sync_playwright
import time as time_module

CONFIG_FILE = "config.json"
CHECKPOINT_FILE = "checkpoint.json"
COOKIE_FILE = "cookies_pw.json"

BELM_MAP = {
    "puri": {"id": "21", "name": "Puri Indah"},
    "setiabudi": {"id": "8", "name": "Setiabudi One"},
    "bintaro": {"id": "16", "name": "Bintaro"},
    "darmo": {"id": "13", "name": "Darmo"},
    "pakuwon": {"id": "14", "name": "Pakuwon"},
    "bandung": {"id": "1", "name": "Bandung"},
    "bekasi": {"id": "19", "name": "Bekasi"},
    "bogor": {"id": "17", "name": "Bogor"},
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"email": "pangkassobo@gmail.com", "password": "198456z"}

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

def scrape_page(page, label="Page"):
    """Scrape page content and report to user"""
    try:
        content = page.content()
        url = page.url
        
        print(f"\n[DEBUG] {label} Report:")
        print(f"  URL: {url}")
        print(f"  Title: {page.title()}")
        
        # Check for key elements
        if "logout" in content.lower():
            print("  Status: LOGGED IN")
        else:
            print("  Status: NOT LOGGED IN")
        
        # Check for Cloudflare
        if "just a moment" in content.lower():
            print("  Cloudflare: ACTIVE")
        else:
            print("  Cloudflare: CLEARED")
        
        # Check for forms
        forms = re.findall(r'<form[^>]*action="([^"]*)"', content)
        if forms:
            print(f"  Forms found: {forms[:3]}")
        
        # Check for errors
        error_patterns = [
            r'class="alert[^"]*"[^>]*>(.*?)</div>',
            r'class="error[^"]*"[^>]*>(.*?)</div>',
            r'<p class="text-danger">(.*?)</p>',
        ]
        for pat in error_patterns:
            m = re.search(pat, content, re.DOTALL)
            if m:
                print(f"  Error: {m.group(1).strip()[:100]}")
                break
        
        return {
            "url": url,
            "title": page.title(),
            "content": content[:500],
            "is_logged_in": "logout" in content.lower()
        }
    except Exception as e:
        print(f"[!] Scrape error: {e}")
        return None

def save_checkpoint(data):
    data["timestamp"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def run_bot(belm_key):
    config = load_config()
    email = config.get("email", "")
    password = config.get("password", "")
    PROXY = config.get("proxy", "")
    belm = BELM_MAP.get(belm_key)
    
    if not belm:
        print(f"[!] BELM '{belm_key}' tidak dikenal!")
        sys.exit(1)
    
    print("=" * 55)
    print(f"  ANTREAN BOT - {belm['name']} (ID: {belm['id']})")
    print("=" * 55 + "\n")
    
    with sync_playwright() as p:
        print("[*] Starting browser...")
        
        # Proxy config
        proxy_config = {}
        if PROXY:
            print(f"[*] Using proxy: {PROXY[:40]}...")
            proxy_config = {
                "server": PROXY,
            }
        
        browser = p.chromium.launch(
            headless=False,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-web-security',
            ]
        )
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            **proxy_config
        )
        
        # Load cookies if exists
        if os.path.exists(COOKIE_FILE):
            try:
                with open(COOKIE_FILE, "r") as f:
                    cookies = json.load(f)
                context.add_cookies(cookies)
                print("[*] Cookies loaded")
            except:
                pass
        
        page = context.new_page()
        
        # Go to site
        print("[*] Opening site...")
        try:
            page.goto("https://antrean.logammulia.com", timeout=60000)
            page.wait_for_load_state("domcontentloaded")
        except:
            print("[*] Timeout on load, continuing anyway...")
        
        # Wait for Cloudflare
        print("[*] Waiting for Cloudflare...")
        for i in range(30):
            if "just a moment" not in page.content().lower():
                break
            page.wait_for_timeout(1000)
        
        # Check if already logged in
        if "logout" in page.content().lower():
            print("[+] Already logged in via cookies!")
        else:
            print("[*] Not logged in, going to login...")
            try:
                page.goto("https://antrean.logammulia.com/login", timeout=60000)
                page.wait_for_load_state("domcontentloaded")
            except:
                print("[*] Timeout on load, continuing...")
            
            # Wait for Cloudflare
            print("[*] Waiting for Cloudflare...")
            for i in range(30):
                try:
                    if "just a moment" not in page.content().lower():
                        break
                except:
                    pass
                page.wait_for_timeout(1000)
            
            # Fill login form
            print("[*] Filling login form...")
            page.wait_for_timeout(2000)
            
            # Check captcha
            try:
                captcha_elem = page.query_selector('label[for="aritmetika"]')
                if captcha_elem:
                    captcha_text = captcha_elem.inner_text()
                    print(f"[*] Captcha: {captcha_text}")
                    answer = str(solve_captcha(captcha_text))
                    print(f"[*] Answer: {answer}")
                    
                    page.fill('input[name="username"]', email)
                    page.fill('input[name="password"]', password)
                    page.fill('input[name="aritmetika"]', answer)
                else:
                    page.fill('input[name="username"]', email)
                    page.fill('input[name="password"]', password)
            except:
                page.fill('input[name="username"]', email)
                page.fill('input[name="password"]', password)
            
            print("[*] Clicking login button...")
            page.wait_for_timeout(500)
            
            # Try multiple selectors for the login button
            login_clicked = False
            selectors = [
                'button#login',
                'button.btn-primary[type="submit"]',
                'button:has-text("Log in")',
                'div.form-button-group button[type="submit"]',
                'button[type="submit"]'
            ]
            
            for selector in selectors:
                try:
                    btn = page.query_selector(selector)
                    if btn and btn.is_visible():
                        print(f"[*] Found button with selector: {selector}")
                        btn.click()
                        login_clicked = True
                        break
                except Exception as e:
                    print(f"[!] Selector '{selector}' failed: {e}")
                    continue
            
            if not login_clicked:
                print("[!] Could not find login button!")
                page.screenshot(path="login_button_not_found.png")
                browser.close()
                return
            
            print("[*] Waiting for login response...")
            page.wait_for_timeout(5000)
            
            # Wait for Cloudflare after submit
            for i in range(60):
                if "logout" in page.content().lower():
                    print("[+] LOGIN SUCCESS!")
                    break
                if "challenges.cloudflare.com" in page.content():
                    print(f"    Cloudflare detected, waiting... ({i})")
                    page.wait_for_timeout(1000)
                page.wait_for_timeout(1000)
            else:
                print("[!] Login timeout!")
                page.screenshot(path="login_fail.png")
                browser.close()
                return
            
            # Save cookies
            cookies = context.cookies()
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f)
            print("[*] Cookies saved")
        
        # Go to antrean
        print("\n[*] Going to antrean page...")
        page.goto("https://antrean.logammulia.com/antrean", timeout=60000)
        page.wait_for_load_state("networkidle")
        
        # Select BELM
        print(f"[*] Selecting {belm['name']}...")
        page.select_option("#site", belm["id"])
        page.wait_for_timeout(500)
        page.click("button")
        page.wait_for_timeout(3000)
        
        # Check availability
        print("[*] Checking availability...")
        content = page.content()
        
        if "Kuota Tidak Tersedia" in content:
            print(f"\n[!] {belm['name']}: KUOTA KOSONG / HABIS")
            save_checkpoint({"status": "no_slot", "belm": belm_key})
            browser.close()
            return
        
        # Try to take antrean
        try:
            form = page.query_selector('form[action*="masuk-pool"]')
            if form:
                print("[+] ADA KUOTA! Taking antrean...")
                form.evaluate("form => form.submit()")
                page.wait_for_timeout(5000)
                
                # Check result
                result = page.content()
                m = re.search(r'(?:NOMOR|No.Antrean)[:\s]*(\d+)', result, re.IGNORECASE)
                if m:
                    nomor = m.group(1)
                    print("\n" + "=" * 55)
                    print(f"   BERHASIL! NOMOR ANTREAN: {nomor}")
                    print(f"   Butik: {belm['name']}")
                    print("=" * 55)
                    save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
                else:
                    print("[+] Maybe success (no number found)")
                    save_checkpoint({"status": "success_no_number", "belm": belm_key})
            else:
                print("[!] No form found to take antrean")
        except Exception as e:
            print(f"[!] Error taking antrean: {e}")
        
        page.wait_for_timeout(5000)
        browser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python antrean_bot.py <belm>")
        print("  python antrean_bot.py standby")
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    if mode == "standby":
        print("[*] Standby mode - browser will stay open...")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://antrean.logammulia.com")
            input("[*] Press Enter to close...")
            browser.close()
    elif mode in BELM_MAP:
        run_bot(mode)
    else:
        print(f"[!] Unknown mode: {mode}")
        sys.exit(1)