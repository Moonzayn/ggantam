import asyncio
import os
import platform
import json
import re
from datetime import datetime
import sys

import nodriver as uc

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.json"

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
    return {"email": "pangkassobo@gmail.com", "password": "198456z", "belm": "bintaro"}

CONFIG = load_config()
EMAIL = CONFIG.get("email")
PASSWORD = CONFIG.get("password")
PROXY = CONFIG.get("proxy", "")
CHECKPOINT_FILE = "checkpoint.json"

def save_checkpoint(data):
    data["timestamp"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _find_chrome():
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    if platform.system() == "Windows":
        cand = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")
        ]
    else:
        cand = ["/usr/bin/google-chrome-stable"]
    for p in cand:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Chrome not found")

def _get_profile_dir():
    if os.environ.get("TS_PROFILE_DIR"):
        return os.environ["TS_PROFILE_DIR"]
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome_profile")

def solve_captcha(text):
    """Solve math captcha like 'Berapa hasil perhitungan dari 5 ditambah 3 ?'"""
    text = text.lower()
    m = re.search(r'(\d+)\s+(dikali|dikurangi|dijumlahkan|ditambah)\s+(\d+)', text)
    if m:
        a, b = int(m.group(1)), int(m.group(3))
        op = m.group(2)
        print(f"[*] Math: {a} {op} {b}")
        if "kali" in op:
            return a * b
        elif "kurang" in op or "dikurangi" in op:
            return a - b
        else:
            return a + b
    print(f"[!] Could not parse captcha: {text}")
    return 0

async def do_login(page, browser):
    """Handle login process. Returns True on success, False on failure."""
    print("[*] Filling login form...")

    # Wait for form to load
    print("[*] Waiting for login form...")
    max_wait = 30
    for i in range(max_wait):
        await asyncio.sleep(1)
        html = await page.get_content()
        if 'username' in html.lower() or 'password' in html.lower():
            print("[+] Login form loaded!")
            break
        if i % 5 == 4:
            print(f"    Waiting for form... ({i+1}/{max_wait}s)")
    else:
        print("[!] Login form not found!")
        return False

    # Solve captcha
    captcha_answer = ""
    match = re.search(r'<label[^>]*for="aritmetika"[^>]*>(.*?)</label>', html, re.IGNORECASE | re.DOTALL)
    if match:
        captcha_text = re.sub(r'<[^>]+>', ' ', match.group(1)).strip()
        print(f"[*] Captcha: {captcha_text}")
        captcha_answer = str(solve_captcha(captcha_text))
        print(f"[*] Answer: {captcha_answer}")
    else:
        print("[!] Could not find captcha")

    # Fill fields using nodriver's element selection
    print("[*] Filling username...")
    try:
        username_field = await page.find('input[name="username"]', best_match=True)
        if username_field:
            await username_field.send_keys(EMAIL)
        else:
            # Fallback to JS
            await page.evaluate(f"document.querySelector('input[name=username]').value = {json.dumps(EMAIL)}")
    except Exception as e:
        print(f"[!] Error filling username: {e}")
        await page.evaluate(f"document.querySelector('input[name=username]').value = {json.dumps(EMAIL)}")
    await asyncio.sleep(0.5)

    print("[*] Filling password...")
    try:
        password_field = await page.find('input[name="password"]', best_match=True)
        if password_field:
            await password_field.send_keys(PASSWORD)
        else:
            await page.evaluate(f"document.querySelector('input[name=password]').value = {json.dumps(PASSWORD)}")
    except Exception as e:
        print(f"[!] Error filling password: {e}")
        await page.evaluate(f"document.querySelector('input[name=password]').value = {json.dumps(PASSWORD)}")
    await asyncio.sleep(0.5)

    if captcha_answer:
        print(f"[*] Filling captcha: {captcha_answer}")
        try:
            captcha_field = await page.find('input[name="aritmetika"]', best_match=True)
            if captcha_field:
                await captcha_field.send_keys(captcha_answer)
            else:
                await page.evaluate(f"document.querySelector('input[name=aritmetika]').value = {json.dumps(captcha_answer)}")
        except Exception as e:
            print(f"[!] Error filling captcha: {e}")
            await page.evaluate(f"document.querySelector('input[name=aritmetika]').value = {json.dumps(captcha_answer)}")
        await asyncio.sleep(0.5)

    # Wait for Turnstile
    print("[*] Waiting for Turnstile (60s)...")
    print("[*] Please click the checkbox!")
    solved = False
    for i in range(60):
        await asyncio.sleep(1)
        solved = await page.evaluate("document.querySelector('[name=cf-turnstile-response]')?.value?.length > 0")
        if solved:
            print("[+] Turnstile solved!")
            break
        if i % 10 == 9:
            print(f"    Waiting... ({i+1}/60)")

    if not solved:
        print("[!] Turnstile not solved in time!")
        return False

    # Bypass jQuery validation
    print("[*] Bypassing validation...")
    await page.evaluate("""
        if (window.jQuery) {
            const v = $("#formInput").data("validator");
            if (v) v.destroy();
        }
    """)
    await asyncio.sleep(1)

    # Submit
    print("[*] Submitting...")
    await page.evaluate("document.getElementById('formInput').submit()")

    # Wait for navigation
    print("[*] Waiting for login result...")
    await asyncio.sleep(5)

    # Check result
    html = await page.get_content()
    if "logout" not in html.lower():
        print("\n[!] LOGIN GAGAL!")
        with open("login_failed.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("[*] HTML saved to login_failed.html")
        return False

    print("\n[+] LOGIN BERHASIL!")

    # Save cookies
    try:
        cookies = await browser.cookies.get_all()
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f)
        print("[*] Cookies saved")
    except Exception as e:
        print(f"[!] Failed to save cookies: {e}")

    return True

async def get_url(page):
    """Get current URL properly handling nodriver v0.44 tuple return."""
    try:
        # Try page.url first
        url = page.url
        if url:
            return url
    except:
        pass

    # Fallback to evaluate with tuple handling
    result = await page.evaluate('window.location.href')
    if isinstance(result, tuple):
        return result[0].value
    elif hasattr(result, 'value'):
        return result.value
    return str(result)

async def take_antrean(page, browser, belm_key):
    """Take antrean for selected BELM. Returns True on success, False on failure."""
    belm = BELM_MAP[belm_key]

    # Go to antrean page
    print(f"\n[2] Ke halaman antrean...")
    page = await browser.get("https://antrean.logammulia.com/antrean")

    # Wait for page to load
    print("[*] Waiting for page to load...")
    await asyncio.sleep(5)

    current_url = await get_url(page)
    print(f"[DEBUG] Current URL after navigation: {current_url}")

    html = await page.get_content()

    # Check if we're on the right page
    if 'site' not in html.lower() and 'pilih' not in html.lower():
        print("[!] Not on antrean page, got wrong page!")
        print(f"[DEBUG] HTML snippet: {html[:500]}")
        return False

    print("[+] On antrean page, proceeding...")

    # Select BELM
    print(f"[*] Selecting BELM: {belm['name']} (ID: {belm['id']})...")
    js_code = f"document.querySelector('#site').value = {json.dumps(belm['id'])}"
    await page.evaluate(js_code)
    await asyncio.sleep(1)

    # Click "Tampilkan Butik" button
    print("[*] Clicking 'Tampilkan Butik'...")
    click_result = await page.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const btn of btns) {
            if (btn.textContent.includes('Tampilkan') || btn.textContent.includes('Butik')) {
                btn.click();
                return 'Clicked: ' + btn.textContent;
            }
        }
        const firstBtn = document.querySelector('button');
        if (firstBtn) {
            firstBtn.click();
            return 'Clicked first button';
        }
        return 'Button not found';
    }""")
    print(f"[*] {click_result}")

    # Wait for page to reload with site parameter
    print("[*] Waiting for page to reload with site parameter...")
    max_wait = 30
    for i in range(max_wait):
        await asyncio.sleep(1)
        current_url = await get_url(page)
        if '?site=' in current_url or f"site={belm['id']}" in current_url:
            print(f"[+] Page reloaded. URL: {current_url}")
            break
        if i % 5 == 4:
            print(f"    Waiting for URL update... ({i+1}/{max_wait}s)")
    else:
        print("[!] Page did not reload with ?site= within 30s")
        print(f"[DEBUG] Current URL: {await get_url(page)}")
        return False

    # Wait for content to load
    await asyncio.sleep(3)

    # Check slot availability
    print("\n[3] Cek ketersediaan...")
    print("-" * 30)

    html = await page.get_content()
    current_url = await get_url(page)
    print(f"[DEBUG] URL: {current_url}")
    print(f"[DEBUG] HTML length: {len(html)} chars")

    if 'Kuota Tidak Tersedia' in html or 'Kosong' in html:
        print(f"\n[!] {belm['name']}: KUOTA KOSONG")
        save_checkpoint({"status": "no_slot", "belm": belm_key})
        return False

    if 'masuk-pool' in html or 'Ambil Antrean' in html:
        print(f"[+] {belm['name']}: ADA KUOTA!")
        print("[*] Mengambil antrian...")

        # Submit the form to take antrean
        result = await page.evaluate("""() => {
            const form = document.querySelector('form[action*="masuk-pool"]');
            if (form) {
                form.submit();
                return 'Form submitted';
            }
            return 'Form not found';
        }""")
        print(f"[*] {result}")

        # Wait for result
        print("[*] Waiting for result...")
        await asyncio.sleep(5)

        # Check result
        result_html = await page.get_content()
        m = re.search(r'(?:NOMOR|No\.?Antrean)[:\s]*(\d+)', result_html, re.IGNORECASE)
        if m:
            nomor = m.group(1)
            print("\n" + "="*50)
            print(f"   [!] BERHASIL! NOMOR: {nomor}")
            print("="*50)
            print(f"\n[*] Silakan ke {belm['name']} ya!")
            save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
            return True
        else:
            print("\n[!] Gagal mengambil antrian: queue number not found")
            with open("antrean_failed.html", "w", encoding="utf-8") as f:
                f.write(result_html)
            print("[*] HTML saved to antrean_failed.html")
            return False
    else:
        print("\n[!] Unexpected page content")
        print(f"[DEBUG] HTML snippet: {html[:500]}")
        with open("antrean_failed.html", "w", encoding="utf-8") as f:
            f.write(html)
        return False

async def run_bot(belm_key):
    """Main bot flow"""
    print(f"\n{'='*50}")
    print(f"  ANTREAN BOT - {BELM_MAP[belm_key]['name']}")
    print(f"{'='*50}\n")

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

    page = await browser.get("https://antrean.logammulia.com/login")
    print("[*] Page loaded, waiting 5s for Cloudflare...")
    await asyncio.sleep(5)
    
    # Check current URL to see if redirected (already logged in)
    current_url = await get_url(page)
    print(f"[*] Current URL: {current_url}")
    
    if '/login' in current_url:
        print("[*] On login page, need to login...")
        login_success = await do_login(page, browser)
        if not login_success:
            print("[!] Login failed, exiting...")
            try:
                await browser.stop()
            except:
                pass
            return
    else:
        print("[+] Already logged in! (redirected to /users or /antrean)")
    
    # Take antrean
    success = await take_antrean(page, browser, belm_key)

    await asyncio.sleep(3)
    try:
        await browser.stop()
    except:
        pass

    if success:
        print("\n[+] Bot completed successfully!")
    else:
        print("\n[!] Bot completed with errors.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python antrean.py <belm>")
        print("Available BELM: puri, setiabudi, bintaro, darmo, pakuwon, bandung, bekasi, bogor")
        sys.exit(1)
    belm = sys.argv[1].lower()
    if belm not in BELM_MAP:
        print(f"Invalid BELM: {belm}")
        print("Available BELM: puri, setiabudi, bintaro, darmo, pakuwon, bandung, bekasi, bogor")
        sys.exit(1)
    asyncio.run(run_bot(belm))
