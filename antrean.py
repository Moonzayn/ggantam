import asyncio
import os
import platform
import json
import re
from datetime import datetime

import nodriver as uc

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.json"
SLOT_FILE = "slot_info.json"

# Load config
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"email": "pangkassobo@gmail.com", "password": "198456z", "belm": "bintaro"}

CONFIG = load_config()
EMAIL = CONFIG.get("email", "pangkassobo@gmail.com")
PASSWORD = CONFIG.get("password", "198456z")
LOGIN_URL = "https://antrean.logammulia.com/login"

BELM_MAP = {
    "puri": {"id": "21", "name": "Butik Emas LM - Puri Indah"},
    "setiabudi": {"id": "8", "name": "Butik Emas LM - Setiabudi One"},
    "bintaro": {"id": "16", "name": "Butik Emas LM - Bintaro"},
    "darmo": {"id": "13", "name": "Butik Emas LM - Surabaya 1 Darmo"},
    "pakuwon": {"id": "14", "name": "Butik Emas LM - Surabaya 2 Pakuwon"},
    "bandung": {"id": "1", "name": "Butik Emas LM - Bandung"},
    "bekasi": {"id": "19", "name": "Butik Emas LM - Bekasi"},
    "bogor": {"id": "17", "name": "Butik Emas LM - Bogor"},
    "medan": {"id": "10", "name": "Butik Emas LM - Medan"},
    "makassar": {"id": "11", "name": "Butik Emas LM - Makassar"},
    "palembang": {"id": "12", "name": "Butik Emas LM - Palembang"},
    "yogyakarta": {"id": "9", "name": "Butik Emas LM - Yogyakarta"},
    "denpasar": {"id": "5", "name": "Butik Emas LM - Denpasar"},
}

def _find_chrome():
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]
    else:
        candidates = ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError("Chrome not found")

def _get_profile_dir():
    if os.environ.get("TS_PROFILE_DIR"):
        return os.environ["TS_PROFILE_DIR"]
    if platform.system() == "Windows":
        base = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Temp"
        return os.path.join(base, "antrean_profile")
    return "/tmp/antrean_profile"

def solve_captcha(text):
    text = text.lower()
    match = re.search(r"(\d+)\s*(dikali|dikurangi|dijumlahkan|ditambah)\s*(\d+)", text)
    if match:
        a = int(match.group(1))
        b = int(match.group(3))
        op = match.group(2)
        if "kali" in op:
            return a * b
        elif "kurang" in op:
            return a - b
        else:
            return a + b
    return 0

async def get_page_cookies(page):
    js_cookies = await page.evaluate('''JSON.stringify(document.cookie)''')
    cookies = []
    if js_cookies:
        for c in js_cookies.split("; "):
            if "=" in c:
                name, val = c.split("=", 1)
                cookies.append({"name": name, "value": val, "domain": "logammulia.com"})
    return cookies

async def check_slot(page, belm_key):
    belm = BELM_MAP.get(belm_key.lower(), BELM_MAP["setiabudi"])
    site_id = belm["id"]
    
    print(f"[*] Checking {belm['name']}...")
    
    # Reload antrean page to get fresh token
    await page.evaluate('window.location.href = "https://antrean.logammulia.com/antrean"')
    await asyncio.sleep(3)
    
    await page.evaluate(f'document.querySelector("#site").value = "{site_id}"')
    await asyncio.sleep(0.5)
    await page.evaluate('document.querySelector("button").click()')
    await asyncio.sleep(3)
    
    html = await page.evaluate('document.documentElement.outerHTML')
    
    # Save for debug
    with open(f"slot_{belm_key}.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    slot_info = {
        "belm_key": belm_key,
        "belm_id": site_id,
        "belm_name": belm["name"],
        "tanggal": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tersedia": False,
        "sisa": "0",
        "sesi": "",
        "rencana_stok": "",
    }
    
    # Check actual availability text
    if '<h2 class="text-primary">Kuota Tidak Tersedia</h2>' in html:
        match_sisa = re.search(r'Sisa.*?<span class="badge[^>]*>(\d+)</span>', html)
        match_sesi = re.search(r'Sesi waktu ambil antrean.*?:.*?([\d:]+.*?WIB)', html)
        match_stok = re.search(r'Rencana Stok.*?:.*?([\d|\s]+)<', html)
        
        slot_info["tersedia"] = False
        slot_info["sisa"] = match_sisa.group(1) if match_sisa else "0"
        slot_info["sesi"] = match_sesi.group(1).strip() if match_sesi else ""
        slot_info["rencana_stok"] = match_stok.group(1).strip() if match_stok else ""
        print(f"[-] {belm['name']}: Kuota Tidak Tersedia, Sisa: {slot_info['sisa']}")
    elif '<h2 class="text-primary">Kuota Tersedia</h2>' in html:
        slot_info["tersedia"] = True
        print(f"[+] {belm['name']}: ADA KUOTA! (Tersedia)")
    else:
        # Check for availability by form presence
        if 'action="/masuk-pool"' in html or 'masuk-pool' in html:
            slot_info["tersedia"] = True
            print(f"[+] {belm['name']}: Kuota Tersedia (bisa ambil)")
        else:
            print(f"[-] {belm['name']}: Kondisi tidak jelas")
    
    return slot_info

async def ambil_antrian(page, belm_key):
    belm = BELM_MAP.get(belm_key.lower(), BELM_MAP["setiabudi"])
    site_id = belm["id"]
    
    print(f"[*] Ambil antrian {belm['name']}...")
    
    # Go to antrean page
    await page.evaluate('window.location.href = "https://antrean.logammulia.com/antrean"')
    await asyncio.sleep(3)
    
    # Select BELM
    await page.evaluate(f'document.querySelector("#site").value = "{site_id}"')
    await asyncio.sleep(0.5)
    await page.evaluate('document.querySelector("button").click()')
    await asyncio.sleep(3)
    
    html = await page.evaluate('document.documentElement.outerHTML')
    await page.evaluate('document.body.innerHTML.length')  # Wait
    
    # Check if there's a form to take antrian
    if 'action="/masuk-pool"' in html or 'masuk-pool' in html:
        print("[*] Found antrian form, submitting...")
        
        # Submit the form directly
        form_result = await page.evaluate('''
            (() => {
                const form = document.querySelector('form[action*="masuk-pool"]');
                if (!form) return "no_form";
                
                const formData = new FormData(form);
                const params = new URLSearchParams(formData).toString();
                
                fetch(form.action, {
                    method: "POST",
                    body: params,
                    headers: {"Content-Type": "application/x-www-form-urlencoded"}
                })
                .then(r => r.text())
                .then(html => {
                    window._antrian_result = html;
                    return html;
                })
                .catch(e => "error:" + e.message);
            })()
        ''')
        await asyncio.sleep(5)
        
        result_html = await page.evaluate('window._antrian_result || document.documentElement.outerHTML')
        
        # Look for antrian number
        no_match = re.search(r'(?:NOMOR|No\.)[:\s]*(\d+)', result_html, re.IGNORECASE)
        if no_match:
            print(f"[+] BERHASIL! Nomor Antrean: {no_match.group(1)}")
            return {"success": True, "nomor": no_match.group(1)}
        
        if "sudah" in result_html.lower() or "ada" in result_html.lower():
            print("[-] Antrean sudah diambil hari ini")
            return {"success": False, "reason": "sudah_ada"}
        
        print("[-] Gagal ambil antrian, html length:", len(result_html))
        with open("antrian_error.html", "w") as f:
            f.write(result_html)
        return {"success": False, "reason": "unknown"}
    
    elif "Kuota Tidak Tersedia" in html:
        print("[-] Kuota tidak tersedia")
        return {"success": False, "reason": "no_quota"}
    
    else:
        print("[-] Kondisi tidak diketahui")
        with open("antrian_debug.html", "w") as f:
            f.write(html)
        return {"success": False, "reason": "unknown"}

async def full_login(page):
    print("[*] Loading login page...")
    page = await page.browser.get(LOGIN_URL)
    await asyncio.sleep(3)
    
    captcha_text = await page.evaluate('''(document.querySelector('label[for="aritmetika"]') || {}).innerText || "Error"''')
    print("[*] Captcha:", captcha_text)
    
    answer = solve_captcha(captcha_text)
    print("[*] Answer:", answer)
    
    print("[*] Solving Turnstile...")
    sitekey = "0x4AAAAAACJ3z-FPGdMU19nQ"
    
    await page.evaluate(f'''
        (() => {{
            if (document.getElementById('_ts_box')) return;
            window._tsToken = null;
            const wrap = document.createElement('div');
            wrap.id = '_ts_box';
            wrap.style = 'position:fixed;top:20px;left:20px;z-index:2147483647;';
            document.body.appendChild(wrap);
            window._tsLoad = function () {{
                turnstile.render('#_ts_box', {{
                    sitekey: '{sitekey}',
                    callback: function(token) {{ window._tsToken = token; }}
                }});
            }};
            const s = document.createElement('script');
            s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_tsLoad&render=explicit';
            s.async = true;
            document.head.appendChild(s);
        }})();
    ''')
    
    await asyncio.sleep(8)
    
    for attempt in range(5):
        ts_token = await page.evaluate('window._tsToken')
        if ts_token:
            break
        await asyncio.sleep(2)
    
    print("[*] Filling form...")
    await page.evaluate(f'document.querySelector(\'input[name="username"]\').value = "{EMAIL}"')
    await page.evaluate(f'document.querySelector(\'input[name="password"]\').value = "{PASSWORD}"')
    await page.evaluate(f'document.querySelector(\'input[name="aritmetika"]\').value = "{answer}"')
    
    await asyncio.sleep(1)
    
    print("[*] Clicking submit...")
    await page.evaluate('document.querySelector(\'button[type="submit"]\').click()')
    
    await asyncio.sleep(5)
    
    final_html = await page.evaluate('document.documentElement.outerHTML')
    
    if "logout" in final_html.lower():
        print("[+] LOGIN SUCCESS!")
        return True
    else:
        print("[-] Login failed")
        return False

async def check_multiple(belm_list):
    browser = await uc.start(
        browser_executable_path=_find_chrome(),
        headless=False,
        user_data_dir=_get_profile_dir(),
    )
    
    try:
        # Try cookie login first
        print("[*] Loading antrean page...")
        page = await browser.get("https://antrean.logammulia.com/antrean")
        await asyncio.sleep(3)
        
        cookies = await get_page_cookies(page)
        
        if not cookies or len(cookies) < 5:
            print("[*] No valid cookies, doing full login...")
            if not await full_login(page):
                return
            cookies = await get_page_cookies(page)
        
        # Save cookies
        with open(COOKIE_FILE, "w") as f:
            json.dump(cookies, f, indent=2)
        print(f"[*] Cookies saved")
        
        # Check slots
        results = []
        for belm in belm_list:
            info = await check_slot(page, belm)
            results.append(info)
        
        # Save all slot info
        with open(SLOT_FILE, "w") as f:
            json.dump(results, f, indent=2)
        
        print("\n" + "="*50)
        print("SLOT INFO SUMMARY")
        print("="*50)
        for r in results:
            status = "ADA" if r["tersedia"] else "KOSONG"
            print(f"{r['belm_name']}: {status}")
            if r["sesi"] != "N/A":
                print(f"   Sesi: {r['sesi']}, Sisa: {r['sisa']}")
        
        await asyncio.sleep(5)
        
    finally:
        try:
            browser.stop()
        except:
            pass

async def quick_check(belm_name):
    if not os.path.exists(COOKIE_FILE):
        print("[!] No cookies. Run first without --cookie flag")
        return
    
    print("[*] Loading cookies...")
    with open(COOKIE_FILE, "r") as f:
        cookie_str = f.read()
    
    browser = await uc.start(
        browser_executable_path=_find_chrome(),
        headless=False,
        user_data_dir=_get_profile_dir(),
    )
    
    try:
        page = await browser.get("https://antrean.logammulia.com/antrean")
        await asyncio.sleep(2)
        
        # Inject cookies
        cookies = json.loads(cookie_str)
        await page.evaluate('document.cookie = ' + json.dumps("; ".join([f"{c['name']}={c['value']}" for c in cookies])))
        
        await page.reload()
        await asyncio.sleep(2)
        
        html = await page.evaluate('document.documentElement.outerHTML')
        
        if "logout" not in html.lower():
            print("[!] Cookies expired! Need new login")
            return
        
        print(f"[*] Checking {belm_name}...")
        info = await check_slot(page, belm_name)
        
        with open(SLOT_FILE, "w") as f:
            json.dump(info, f, indent=2)
        
        print(f"\n{info['belm_name']}")
        if info["tersedia"]:
            print("SLOT TERSEDIA!")
        else:
            print("Kuota Tidak Tersedia")
            print(f"   Sesi: {info['sesi']}")
            print(f"   Sisa: {info['sisa']}")
        
        await asyncio.sleep(5)
        
    finally:
        try:
            browser.stop()
        except:
            pass

async def ambil_antrian_auto(belm_name, use_existing_cookies=True):
    browser = await uc.start(
        browser_executable_path=_find_chrome(),
        headless=False,
        user_data_dir=_get_profile_dir(),
    )
    
    try:
        page = await browser.get("https://antrean.logammulia.com/antrean")
        await asyncio.sleep(3)
        
        cookies_js = await page.evaluate('document.cookie')
        
        if not cookies_js or "ci_session" not in cookies_js:
            print("[*] Need full login...")
            if not await full_login(page):
                return
            cookies_js = await page.evaluate('document.cookie')
            cookies = []
            for c in cookies_js.split("; "):
                if "=" in c:
                    name, val = c.split("=", 1)
                    cookies.append({"name": name, "value": val})
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f, indent=2)
                print(f"[*] Cookies saved")
        
        # Check slot first
        info = await check_slot(page, belm_name)
        
        if not info["tersedia"]:
            print(f"\n[INFO] {info['belm_name']}")
            print(f"   Kuota kosong")
            print(f"   Sesi: {info['sesi']}")
            print(f"   Sisa: {info['sisa']}")
            print(f"\n[!] Jalankan bot sebelum jam {info['sesi'].split('-')[0].strip()} untuk ambil antrian!")
            return
        
        # If tersedia, take antrian
        result = await ambil_antrian(page, belm_name)
        
        if result["success"]:
            print(f"\n[+] BERHASIL AMBIL ANTREAN!")
            print(f"   Nomor: {result['nomor']}")
        
        await asyncio.sleep(10)
        
    finally:
        try:
            browser.stop()
        except:
            pass

import re
import sys
from datetime import datetime, timedelta
import time

def run_schedule(belm_name, schedule_time_str):
    """Run bot automatically at scheduled time minus 2 minutes"""
    print(f"[*] Schedule mode: akan jalan 2 menit sebelum {schedule_time_str}")
    
    target_hour, target_min = map(int, schedule_time_str.split(":"))
    # Kurang 2 menit
    run_hour = target_hour
    run_min = target_min - 2
    if run_min < 0:
        run_hour -= 1
        run_min += 60
    
    print(f"[*] Akan dijalankan jam {run_hour:02d}:{run_min:02d}")
    print("[*] Menunggu...")
    
    while True:
        now = datetime.now()
        current_hour = now.hour
        current_min = now.minute
        
        # Cek apakah sudah waktunya
        if current_hour == run_hour and abs(current_min - run_min) < 2:
            print(f"\n[*] Waktu tercapai! Menjalankan bot...")
            asyncio.run(ambil_antrian_auto(belm_name, use_existing_cookies=False))
            break
        
        # Check jika sudah lewat hari
        if current_hour > run_hour or (current_hour == run_hour and current_min > run_min + 1):
            print("[!] Waktu sudah terlewat, besok lagi")
            break
        
        time.sleep(30)  # Check every 30 detik

def save_checkpoint(data, filename="checkpoint.json"):
    """Simpan checkpoint untuk rollback"""
    data["timestamp"] = datetime.now().isoformat()
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[*] Checkpoint saved: {filename}")

def load_checkpoint(filename="checkpoint.json"):
    """Load checkpoint untuk rollback"""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return json.load(f)
    return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python antrean.py [belm_name] [options]")
        print(f"Available: {list(BELM_MAP.keys())}")
        print("  --take          Ambil antrian otomatis jika tersedia")
        print("  --cookie       Gunakan cookies yang ada")
        print("  --schedule HH:MM  Jadwal auto-run (2 menit sebelum waktu)")
        sys.exit(1)
    
    belm = sys.argv[1].lower()
    take_antrian = "--take" in sys.argv
    use_cookies = "--cookie" in sys.argv
    
    # Check jadwal
    schedule_arg = None
    for arg in sys.argv:
        if arg.startswith("--schedule="):
            schedule_arg = arg.split("=")[1]
        elif arg == "--schedule" and sys.argv.index(arg) + 1 < len(sys.argv):
            schedule_arg = sys.argv[sys.argv.index(arg) + 1]
    
    if schedule_arg:
        run_schedule(belm, schedule_arg)
    elif take_antrian:
        asyncio.run(ambil_antrian_auto(belm, use_cookies))
    elif use_cookies:
        asyncio.run(quick_check(belm))
    else:
        asyncio.run(check_multiple([belm]))