# antrean_bot.py - nodriver version (Step-by-step structured)
import asyncio
import json
import re
import os
import sys
from datetime import datetime

try:
    import nodriver as uc
except ImportError:
    print("[!] nodriver not installed!")
    print("Install: pip install nodriver")
    sys.exit(1)

CONFIG_FILE = "config.json"
CHECKPOINT_FILE = "checkpoint.json"

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
    """Solve arithmetic captcha"""
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

def save_checkpoint(data):
    data["timestamp"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

def print_step(step_num, message):
    """Print formatted step message"""
    print(f"\n{'='*55}")
    print(f"STEP {step_num}: {message}")
    print(f"{'='*55}")

async def wait_for_cloudflare(page, step_name="", timeout=60):
    """Wait for Cloudflare to clear"""
    print(f"[*] {step_name}: Waiting for Cloudflare challenge...")
    
    for i in range(timeout):
        try:
            content = await page.get_content()
            content_lower = content.lower()
            
            # Check if Cloudflare is present
            if "just a moment" in content_lower or "checking your browser" in content_lower:
                if i % 5 == 0:  # Print every 5 seconds
                    print(f"    [{i}s] Still in Cloudflare challenge...")
                await asyncio.sleep(1)
                continue
            
            # Check if page loaded successfully
            if len(content) > 1000:  # Page has content
                print(f"[✓] {step_name}: Cloudflare cleared! ({i}s)")
                return True
                
        except Exception as e:
            print(f"    [!] Error checking page: {e}")
        
        await asyncio.sleep(1)
    
    print(f"[!] {step_name}: Cloudflare timeout after {timeout}s")
    return False

async def verify_element_exists(page, selector, description, timeout=10):
    """Verify element exists and is visible"""
    print(f"[*] Verifying {description}...")
    try:
        element = await page.find(selector, timeout=timeout)
        if element:
            print(f"[✓] {description} found!")
            return element
        else:
            print(f"[!] {description} not found!")
            return None
    except Exception as e:
        print(f"[!] {description} error: {e}")
        return None

async def fill_input_safely(page, selector, value, description):
    """Fill input field with verification"""
    print(f"[*] Filling {description}...")
    try:
        input_elem = await page.find(selector, timeout=5)
        if not input_elem:
            print(f"[!] {description} field not found!")
            return False
        
        # Clear existing value
        await input_elem.click()
        await asyncio.sleep(0.2)
        
        # Send keys
        await input_elem.send_keys(value)
        await asyncio.sleep(0.3)
        
        # Verify value was entered
        actual_value = await page.evaluate(f'''
            document.querySelector('{selector}').value
        ''')
        
        if actual_value == value:
            print(f"[✓] {description} filled successfully: {value}")
            return True
        else:
            print(f"[!] {description} verification failed!")
            print(f"    Expected: {value}")
            print(f"    Got: {actual_value}")
            return False
            
    except Exception as e:
        print(f"[!] Error filling {description}: {e}")
        return False

async def run_bot(belm_key):
    config = load_config()
    email = config.get("email", "")
    password = config.get("password", "")
    belm = BELM_MAP.get(belm_key)
    
    if not belm:
        print(f"[!] BELM '{belm_key}' tidak dikenal!")
        sys.exit(1)
    
    print("\n" + "=" * 55)
    print(f"  ANTREAN BOT - {belm['name']} (ID: {belm['id']})")
    print("=" * 55)
    
    # ========== STEP 1: Start Browser ==========
    print_step(1, "Starting Undetected Browser")
    
    try:
        browser = await uc.start(
            headless=False,
            browser_args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized',
            ]
        )
        print("[✓] Browser started successfully!")
    except Exception as e:
        print(f"[!] Failed to start browser: {e}")
        return
    
    # ========== STEP 2: Open Login Page ==========
    print_step(2, "Opening Login Page")
    
    try:
        page = await browser.get("https://antrean.logammulia.com/login", new_tab=True)
        print("[✓] Login page loaded!")
        await asyncio.sleep(2)
    except Exception as e:
        print(f"[!] Failed to open login page: {e}")
        browser.stop()
        return
    
    # ========== STEP 3: Wait for Cloudflare (Login Page) ==========
    print_step(3, "Waiting for Cloudflare Challenge (Login)")
    
    cf_cleared = await wait_for_cloudflare(page, "Login Page", timeout=60)
    if not cf_cleared:
        print("[!] Cloudflare not cleared, but continuing...")
    
    await asyncio.sleep(2)
    
    # ========== STEP 4: Verify Login Form ==========
    print_step(4, "Verifying Login Form Elements")
    
    form = await verify_element_exists(page, 'form#formInput', "Login form", timeout=10)
    if not form:
        print("[!] Login form not found! Taking screenshot...")
        await page.save_screenshot("step4_form_not_found.png")
        browser.stop()
        return
    
    username_field = await verify_element_exists(page, 'input[name="username"]', "Username field")
    password_field = await verify_element_exists(page, 'input[name="password"]', "Password field")
    
    if not username_field or not password_field:
        print("[!] Required fields not found!")
        await page.save_screenshot("step4_fields_missing.png")
        browser.stop()
        return
    
    # ========== STEP 5: Check & Solve Captcha ==========
    print_step(5, "Checking for Arithmetic Captcha")
    
    captcha_answer = None
    try:
        captcha_label = await page.find('label[for="aritmetika"]', timeout=3)
        if captcha_label:
            captcha_text = await captcha_label.text
            print(f"[✓] Captcha found: {captcha_text}")
            
            captcha_answer = str(solve_captcha(captcha_text))
            print(f"[✓] Captcha solved: {captcha_answer}")
            
            # Verify captcha input field exists
            captcha_field = await verify_element_exists(page, 'input[name="aritmetika"]', "Captcha field")
            if not captcha_field:
                print("[!] Captcha field not found!")
                await page.save_screenshot("step5_captcha_field_missing.png")
                browser.stop()
                return
        else:
            print("[✓] No captcha required")
    except Exception as e:
        print(f"[✓] No captcha found (this is OK)")
    
    await asyncio.sleep(1)
    
    # ========== STEP 6: Fill Username ==========
    print_step(6, "Filling Username/Email")
    
    username_ok = await fill_input_safely(page, 'input[name="username"]', email, "Username")
    if not username_ok:
        print("[!] Failed to fill username!")
        await page.save_screenshot("step6_username_failed.png")
        browser.stop()
        return
    
    await asyncio.sleep(0.5)
    
    # ========== STEP 7: Fill Password ==========
    print_step(7, "Filling Password")
    
    password_ok = await fill_input_safely(page, 'input[name="password"]', password, "Password")
    if not password_ok:
        print("[!] Failed to fill password!")
        await page.save_screenshot("step7_password_failed.png")
        browser.stop()
        return
    
    await asyncio.sleep(0.5)
    
    # ========== STEP 8: Fill Captcha (if exists) ==========
    if captcha_answer:
        print_step(8, "Filling Captcha Answer")
        
        captcha_ok = await fill_input_safely(page, 'input[name="aritmetika"]', captcha_answer, "Captcha")
        if not captcha_ok:
            print("[!] Failed to fill captcha!")
            await page.save_screenshot("step8_captcha_failed.png")
            browser.stop()
            return
        
        await asyncio.sleep(0.5)
    else:
        print_step(8, "No Captcha to Fill (Skipped)")
    
    # ========== STEP 9: Verify All Fields Filled ==========
    print_step(9, "Verifying All Fields Are Filled")
    
    verification = await page.evaluate('''
        {
            username: document.querySelector('input[name="username"]')?.value || '',
            password: document.querySelector('input[name="password"]')?.value || '',
            captcha: document.querySelector('input[name="aritmetika"]')?.value || 'N/A'
        }
    ''')
    
    print(f"[*] Current values:")
    print(f"    Username: {verification['username'][:20]}{'...' if len(verification['username']) > 20 else ''}")
    print(f"    Password: {'*' * len(verification['password'])}")
    print(f"    Captcha: {verification['captcha']}")
    
    if not verification['username'] or not verification['password']:
        print("[!] Fields verification failed!")
        await page.save_screenshot("step9_verification_failed.png")
        browser.stop()
        return
    
    print("[✓] All required fields are filled!")
    await asyncio.sleep(1)
    
    # ========== STEP 10: Click Login Button ==========
    print_step(10, "Clicking Login Button")
    
    login_clicked = False
    
    # Method 1: Direct click
    try:
        print("[*] Attempting Method 1: Direct button click...")
        login_btn = await page.find('button#login', timeout=5)
        if login_btn:
            await login_btn.click()
            login_clicked = True
            print("[✓] Login button clicked (Method 1)!")
    except Exception as e:
        print(f"[!] Method 1 failed: {e}")
    
    # Method 2: JavaScript click
    if not login_clicked:
        try:
            print("[*] Attempting Method 2: JavaScript click...")
            result = await page.evaluate('''
                const btn = document.querySelector('#login');
                if (btn) {
                    btn.click();
                    true;
                } else {
                    false;
                }
            ''')
            if result:
                login_clicked = True
                print("[✓] Login button clicked (Method 2)!")
        except Exception as e:
            print(f"[!] Method 2 failed: {e}")
    
    # Method 3: Form submit
    if not login_clicked:
        try:
            print("[*] Attempting Method 3: Form submit...")
            result = await page.evaluate('''
                const form = document.querySelector('#formInput');
                if (form) {
                    form.submit();
                    true;
                } else {
                    false;
                }
            ''')
            if result:
                login_clicked = True
                print("[✓] Form submitted (Method 3)!")
        except Exception as e:
            print(f"[!] Method 3 failed: {e}")
    
    if not login_clicked:
        print("[!] All login click methods failed!")
        await page.save_screenshot("step10_click_failed.png")
        browser.stop()
        return
    
    await asyncio.sleep(2)
    
    # ========== STEP 11: Wait for Cloudflare (After Login) ==========
    print_step(11, "Waiting for Cloudflare Challenge (After Login)")
    
    cf_cleared = await wait_for_cloudflare(page, "After Login", timeout=60)
    
    await asyncio.sleep(3)
    
    # ========== STEP 12: Verify Login Success ==========
    print_step(12, "Verifying Login Success")
    
    login_success = False
    
    for attempt in range(30):
        try:
            content = await page.get_content()
            content_lower = content.lower()
            
            # Check for logout (means logged in)
            if "logout" in content_lower:
                print(f"[✓] LOGIN SUCCESS! (attempt {attempt + 1})")
                login_success = True
                break
            
            # Check for error messages
            if "salah" in content_lower or "incorrect" in content_lower or "invalid" in content_lower:
                print("[!] Login failed - Wrong credentials!")
                await page.save_screenshot("step12_wrong_credentials.png")
                browser.stop()
                return
            
            # Check if still in Cloudflare
            if "just a moment" in content_lower or "checking your browser" in content_lower:
                if attempt % 5 == 0:
                    print(f"    [{attempt}s] Still in Cloudflare after login...")
            
        except Exception as e:
            print(f"    [!] Error checking login: {e}")
        
        await asyncio.sleep(1)
    
    if not login_success:
        print("[!] Login verification timeout!")
        await page.save_screenshot("step12_login_timeout.png")
        browser.stop()
        return
    
    await asyncio.sleep(2)
    
    # ========== STEP 13: Navigate to Antrean Page ==========
    print_step(13, "Navigating to Antrean Page")
    
    try:
        page = await browser.get("https://antrean.logammulia.com/antrean")
        print("[✓] Antrean page loaded!")
        await asyncio.sleep(3)
    except Exception as e:
        print(f"[!] Failed to load antrean page: {e}")
        browser.stop()
        return
    
    # ========== STEP 14: Wait for Cloudflare (Antrean Page) ==========
    print_step(14, "Waiting for Cloudflare Challenge (Antrean)")
    
    cf_cleared = await wait_for_cloudflare(page, "Antrean Page", timeout=60)
    
    await asyncio.sleep(2)
    
    # ========== STEP 15: Select BELM Location ==========
    print_step(15, f"Selecting BELM: {belm['name']}")
    
    try:
        # Verify select element exists
        select_elem = await verify_element_exists(page, '#site', "BELM selector")
        if not select_elem:
            print("[!] BELM selector not found!")
            await page.save_screenshot("step15_selector_missing.png")
            browser.stop()
            return
        
        # Select option
        result = await page.evaluate(f'''
            const select = document.querySelector('#site');
            if (select) {{
                select.value = '{belm["id"]}';
                select.dispatchEvent(new Event('change', {{ bubbles: true }}));
                true;
            }} else {{
                false;
            }}
        ''')
        
        if result:
            print(f"[✓] BELM '{belm['name']}' selected!")
        else:
            print("[!] Failed to select BELM!")
            browser.stop()
            return
        
        await asyncio.sleep(1)
        
    except Exception as e:
        print(f"[!] Error selecting BELM: {e}")
        browser.stop()
        return
    
    # ========== STEP 16: Click Submit Button ==========
    print_step(16, "Clicking Submit Button")
    
    try:
        # Find and click button
        btn = await page.find('button[type="submit"]', timeout=5)
        if btn:
            await btn.click()
            print("[✓] Submit button clicked!")
        else:
            # Fallback to JS click
            await page.evaluate('document.querySelector("button").click()')
            print("[✓] Submit button clicked (JS)!")
        
        await asyncio.sleep(3)
        
    except Exception as e:
        print(f"[!] Error clicking submit: {e}")
        browser.stop()
        return
    
    # ========== STEP 17: Check Availability ==========
    print_step(17, "Checking Slot Availability")
    
    try:
        content = await page.get_content()
        
        if "Kuota Tidak Tersedia" in content or "tidak tersedia" in content.lower():
            print(f"\n{'='*55}")
            print(f"[!] {belm['name']}: KUOTA KOSONG / HABIS")
            print(f"{'='*55}\n")
            save_checkpoint({"status": "no_slot", "belm": belm_key})
            
            await asyncio.sleep(5)
            browser.stop()
            return
        
        print("[✓] Slot might be available!")
        
    except Exception as e:
        print(f"[!] Error checking availability: {e}")
    
    # ========== STEP 18: Take Antrean ==========
    print_step(18, "Taking Antrean Slot")
    
    try:
        # Find form
        form_exists = await page.evaluate('''
            !!document.querySelector('form[action*="masuk-pool"]')
        ''')
        
        if form_exists:
            print("[✓] Antrean form found!")
            
            # Submit form
            await page.evaluate('''
                const form = document.querySelector('form[action*="masuk-pool"]');
                if (form) {
                    form.submit();
                }
            ''')
            
            print("[✓] Antrean form submitted!")
            await asyncio.sleep(5)
            
        else:
            print("[!] No antrean form found")
            await page.save_screenshot("step18_no_form.png")
        
    except Exception as e:
        print(f"[!] Error taking antrean: {e}")
    
    # ========== STEP 19: Verify Antrean Number ==========
    print_step(19, "Verifying Antrean Number")
    
    try:
        result = await page.get_content()
        
        # Look for antrean number
        m = re.search(r'(?:NOMOR|No\.?\s*Antrean)[:\s]*(\d+)', result, re.IGNORECASE)
        if m:
            nomor = m.group(1)
            print("\n" + "=" * 55)
            print(f"   ✓✓✓ BERHASIL! ✓✓✓")
            print(f"   NOMOR ANTREAN: {nomor}")
            print(f"   Butik: {belm['name']}")
            print("=" * 55 + "\n")
            
            save_checkpoint({
                "status": "success",
                "belm": belm_key,
                "nomor": nomor,
                "location": belm['name']
            })
            
            await page.save_screenshot(f"success_{belm_key}_{nomor}.png")
        else:
            print("[?] Antrean submitted but number not found")
            print("[*] Check page manually")
            save_checkpoint({
                "status": "success_no_number",
                "belm": belm_key
            })
            
            await page.save_screenshot(f"success_no_number_{belm_key}.png")
        
    except Exception as e:
        print(f"[!] Error verifying antrean: {e}")
    
    # ========== STEP 20: Complete ==========
    print_step(20, "Process Complete")
    
    print("[*] Keeping browser open for 10 seconds...")
    await asyncio.sleep(10)
    
    print("[✓] All done! Closing browser...")
    browser.stop()

async def standby_mode():
    """Standby mode - just open browser for manual testing"""
    print("\n" + "=" * 55)
    print("  STANDBY MODE - Browser for Manual Testing")
    print("=" * 55 + "\n")
    
    browser = await uc.start(headless=False)
    page = await browser.get("https://antrean.logammulia.com")
    
    print("[*] Browser is open.")
    print("[*] Press Ctrl+C to close...")
    
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Closing browser...")
        browser.stop()

def main():
    if len(sys.argv) < 2:
        print("\n" + "=" * 55)
        print("  ANTREAN BOT - Usage")
        print("=" * 55)
        print("\nUsage:")
        print("  python antrean_bot.py <belm>")
        print("  python antrean_bot.py standby")
        print("\nAvailable BELM:")
        for key, val in BELM_MAP.items():
            print(f"  - {key:12} : {val['name']}")
        print("\nExamples:")
        print("  python antrean_bot.py puri")
        print("  python antrean_bot.py setiabudi")
        print("  python antrean_bot.py standby")
        print()
        sys.exit(1)
    
    mode = sys.argv[1].lower()
    
    if mode == "standby":
        uc.loop().run_until_complete(standby_mode())
    elif mode in BELM_MAP:
        uc.loop().run_until_complete(run_bot(mode))
    else:
        print(f"\n[!] Unknown mode: {mode}")
        print(f"[*] Available: {', '.join(BELM_MAP.keys())}, standby")
        sys.exit(1)

if __name__ == "__main__":
    main()