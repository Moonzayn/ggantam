import asyncio
import os
import platform
import json
import re
from datetime import datetime
import time

import nodriver as uc

CONFIG_FILE = "config.json"
COOKIE_FILE = "cookies.json"
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
    return {"email": "pangkassobo@gmail.com", "password": "198456z", "belm": "bintaro"}

CONFIG = load_config()
EMAIL = CONFIG.get("email")
PASSWORD = CONFIG.get("password")

def _find_chrome():
    if os.environ.get("CHROME_PATH"):
        return os.environ["CHROME_PATH"]
    if platform.system() == "Windows":
        cand = [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
    else:
        cand = ["/usr/bin/google-chrome-stable"]
    for p in cand:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("Chrome not found")

def _get_profile_dir():
    if os.environ.get("TS_PROFILE_DIR"):
        return os.environ["TS_PROFILE_DIR"]
    base = os.environ.get("TEMP") or os.environ.get("TMP") or r"C:\Temp"
    return os.path.join(base, "antrean_bot")

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

def save_checkpoint(data):
    data["timestamp"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

async def run_bot(belm_key):
    """Langsung jalan - login + ambil antrian dlm 1 browser"""
    print("\n" + "="*50)
    print(f"  ANTREAN BOT - {BELM_MAP[belm_key]['name']}")
    print("="*50 + "\n")
    
    # Start browser
    print("[*] Starting Chrome...")
    browser = await uc.start(
        browser_executable_path=_find_chrome(),
        headless=False,
        user_data_dir=_get_profile_dir(),
    )
    
    print("[1] Loading login page...")
    page = await browser.get("https://antrean.logammulia.com/login")
    await asyncio.sleep(3)
    
    # Get captcha
    captcha = await page.evaluate('''(document.querySelector('label[for="aritmetika"]') || {}).innerText || "Error"''')
    if "Error" in captcha:
        print("[*] Already logged in")
    else:
        print(f"[*] Captcha: {captcha}")
        answer = solve_captcha(captcha)
        print(f"[*] Jawaban: {answer}")
        
        # Inject Turnstile
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
                        callback: function(token) {{ window._tsToken = token; console.log('Token:', token); }}
                    }});
                }};
                const s = document.createElement('script');
                s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?onload=_tsLoad&render=explicit';
                document.head.appendChild(s);
            }})();
        ''')
        await asyncio.sleep(8)
        
        # Fill form
        await page.evaluate(f'document.querySelector(\'input[name="username"]\').value = "{EMAIL}"')
        await page.evaluate(f'document.querySelector(\'input[name="password"]\').value = "{PASSWORD}"')
        await page.evaluate(f'document.querySelector(\'input[name="aritmetika"]\').value = "{answer}"')
        await asyncio.sleep(1)
        print("[*] Submitting...")
        await page.evaluate('document.querySelector(\'button[type="submit"]\').click()')
        await asyncio.sleep(5)
    
    # Check login
    html = await page.evaluate('document.documentElement.outerHTML')
    if "logout" in html.lower():
        print("[+] LOGIN BERHASIL!\n")
    else:
        print("[*] Continuing...\n")
    
    # Save cookies
    cookies = await page.evaluate('document.cookie')
    with open(COOKIE_FILE, "w") as f:
        f.write(cookies)
    print("[*] Cookies saved\n")
    
    # Go to antrean
    print("[2] Ke halaman antrean...")
    await page.evaluate('window.location.href = "https://antrean.logammulia.com/antrean"')
    await asyncio.sleep(3)
    
    # Select BELM
    belm = BELM_MAP[belm_key]
    await page.evaluate(f'document.querySelector("#site").value = "{belm["id"]}"')
    await asyncio.sleep(0.5)
    await page.evaluate('document.querySelector("button").click()')
    await asyncio.sleep(3)
    
    # Check slot
    print("[3] Cek ketersediaan...")
    print("-"*30)
    html = await page.evaluate('document.documentElement.outerHTML')
    
    if 'class="text-primary">Kuota Tidak Tersedia</h2>' in html:
        m = re.search(r'Sisa.*?<span class="badge[^>]*>(\d+)</span>', html)
        sisa = m.group(1) if m else "0"
        print(f"\n[!] {belm['name']}: KUOTA KOSONG")
        print(f"    Sisa: {sisa}")
        save_checkpoint({"status": "no_slot", "belm": belm_key, "sisa": sisa})
        browser.stop()
        print("\n[*] Coba lagi besok ya!\n")
        return
    
    if 'action="/masuk-pool"' in html:
        print(f"[+] {belm['name']}: ADA KUOTA!")
        print("[*] Mengambil antrian...")
        
        await page.evaluate('''
            (() => {
                const form = document.querySelector('form[action*="masuk-pool"]');
                if (!form) return;
                const fd = new FormData(form);
                const params = new URLSearchParams(fd).toString();
                fetch(form.action, {
                    method: "POST",
                    body: params,
                    headers: {"Content-Type": "application/x-www-form-urlencoded"}
                }).then(r => r.text()).then(html => window._result = html);
            })()
        ''')
        await asyncio.sleep(5)
        
        result_html = await page.evaluate('window._result || document.documentElement.outerHTML')
        
        m = re.search(r'(?:NOMOR|No.Antrean)[:\s]*(\d+)', result_html, re.IGNORECASE)
        if m:
            nomor = m.group(1)
            print("\n" + "="*50)
            print(f"   [!] BERHASIL! NOMOR: {nomor}")
            print("="*50)
            print(f"\n[*] Silica ke {belm['name']} ya!")
            save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
            browser.stop()
            return
    
    print("\n[!] Gagal mengambil antrian")
    save_checkpoint({"status": "failed", "belm": belm_key})
    browser.stop()

async def run_schedule(target_hour, target_min, belm_key):
    """Schedule mode: 2 menit sebelum login"""
    run_hour = target_hour
    run_min = target_min - 2
    if run_min < 0:
        run_hour -= 1
        run_min += 60
    
    print("\n" + "="*50)
    print("  ANTREAN BOT - SCHEDULE MODE")
    print("="*50)
    print(f"  BELM: {BELM_MAP[belm_key]['name']}")
    print(f"  Login:  {run_hour:02d}:{run_min:02d}")
    print(f"  Target: {target_hour:02d}:{target_min:02d}")
    print("="*50 + "\n")
    
    # Phase 1: Tunggu
    print("[*] Menunggu login time...")
    while True:
        now = datetime.now()
        ch, cm = now.hour, now.minute
        if ch == run_hour and cm >= run_min:
            break
        if ch > run_hour or (ch == run_hour and cm > run_min + 1):
            print("\n[!] Waktu sudah terlewat!")
            return
        if now.second < 2:
            print(f"  [{ch:02d}:{cm:02d}] Menunggu...")
        time.sleep(30)
    
    # Phase 1: Login dan stay alive
    print(f"\n[*] {run_hour:02d}:{run_min:02d} - LOGIN & STAY ALIVE...")
    print("-"*30)
    
    browser = await uc.start(
        browser_executable_path=_find_chrome(),
        headless=False,
        user_data_dir=_get_profile_dir(),
    )
    
    page = await browser.get("https://antrean.logammulia.com/login")
    await asyncio.sleep(3)
    
    captcha = await page.evaluate('''(document.querySelector('label[for="aritmetika"]') || {}).innerText || "Error"''')
    print(f"[*] Captcha: {captcha}")
    answer = solve_captcha(captcha)
    print(f"[*] Jawaban: {answer}")
    
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
            document.head.appendChild(s);
        }})();
    ''')
    await asyncio.sleep(8)
    
    await page.evaluate(f'document.querySelector(\'input[name="username"]\').value = "{EMAIL}"')
    await page.evaluate(f'document.querySelector(\'input[name="password"]\').value = "{PASSWORD}"')
    await page.evaluate(f'document.querySelector(\'input[name="aritmetika"]\').value = "{answer}"')
    await asyncio.sleep(1)
    print("[*] Submitting...")
    await page.evaluate('document.querySelector(\'button[type="submit"]\').click()')
    await asyncio.sleep(5)
    
    html = await page.evaluate('document.documentElement.outerHTML')
    if "logout" in html.lower():
        print("[+] LOGIN BERHASIL!")
        save_checkpoint({"status": "logged_in", "belm": belm_key, "step": "waiting"})
    else:
        print("[-] Login gagal")
        browser.stop()
        return
    
    # Phase 2: Tunggu target time
    print("\n[*] Browser stay alive...")
    while True:
        now = datetime.now()
        ch, cm = now.hour, now.minute
        if ch == target_hour and cm >= target_min:
            break
        if ch > target_hour or (ch == target_hour and cm > target_min + 1):
            print("\n[!] Waktu sudah terlewat!")
            browser.stop()
            return
        if now.second < 2:
            print(f"  [{ch:02d}:{cm:02d}] Waiting...")
        time.sleep(30)
    
    # Phase 2: Ambil antrian
    print(f"\n[*] {target_hour:02d}:{target_min:02d} - AMBIL ANTREAN!")
    print("-"*30)
    
    await page.evaluate('window.location.href = "https://antrean.logammulia.com/antrean"')
    await asyncio.sleep(3)
    
    belm = BELM_MAP[belm_key]
    await page.evaluate(f'document.querySelector("#site").value = "{belm["id"]}"')
    await asyncio.sleep(0.5)
    await page.evaluate('document.querySelector("button").click()')
    await asyncio.sleep(3)
    
    html = await page.evaluate('document.documentElement.outerHTML')
    
    if 'class="text-primary">Kuota Tidak Tersedia</h2>' in html:
        print(f"\n[!] {belm['name']}: KUOTA KOSONG")
        print("\n[*] Coba lagi besok ya!\n")
        save_checkpoint({"status": "no_slot", "belm": belm_key})
        browser.stop()
        return
    
    if 'action="/masuk-pool"' in html:
        print("[+] ADA KUOTA! Mengambil...")
        
        await page.evaluate('''
            (() => {
                const form = document.querySelector('form[action*="masuk-pool"]');
                if (!form) return;
                const fd = new FormData(form);
                const params = new URLSearchParams(fd).toString();
                fetch(form.action, {
                    method: "POST",
                    body: params,
                    headers: {"Content-Type": "application/x-www-form-urlencoded"}
                }).then(r => r.text()).then(html => window._result = html);
            })()
        ''')
        await asyncio.sleep(5)
        
        result_html = await page.evaluate('window._result || document.documentElement.outerHTML')
        
        m = re.search(r'(?:NOMOR|No.Antrean)[:\s]*(\d+)', result_html, re.IGNORECASE)
        if m:
            nomor = m.group(1)
            print("\n" + "="*50)
            print(f"   [!] BERHASIL! NOMOR: {nomor}")
            print("="*50)
            save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
            browser.stop()
            return
    
    print("\n[!] Gagal")
    save_checkpoint({"status": "failed", "belm": belm_key})
    browser.stop()
    
    await page.evaluate('window.location.href = "https://antrean.logammulia.com/antrean"')
    await asyncio.sleep(3)
    
    belm = BELM_MAP[belm_key]
    await page.evaluate(f'document.querySelector("#site").value = "{belm["id"]}"')
    await asyncio.sleep(0.5)
    await page.evaluate('document.querySelector("button").click()')
    await asyncio.sleep(3)
    
    html = await page.evaluate('document.documentElement.outerHTML')
    
    if 'class="text-primary">Kuota Tidak Tersedia</h2>' in html:
        print(f"[-] Kuota tidak tersedia")
        save_checkpoint({"status": "no_slot", "belm": belm_key})
        browser.stop()
        return
    
    if 'action="/masuk-pool"' in html:
        print("[+] KUOTA TERSEDIA! Submit...")
        
        await page.evaluate('''
            (() => {
                const form = document.querySelector('form[action*="masuk-pool"]');
                if (!form) return;
                const fd = new FormData(form);
                const params = new URLSearchParams(fd).toString();
                fetch(form.action, {
                    method: "POST",
                    body: params,
                    headers: {"Content-Type": "application/x-www-form-urlencoded"}
                }).then(r => r.text()).then(html => window._result = html);
            })()
        ''')
        await asyncio.sleep(5)
        
        result_html = await page.evaluate('window._result || document.documentElement.outerHTML')
        
        m = re.search(r'(?:NOMOR|No.Antrean)[:\s]*(\d+)', result_html, re.IGNORECASE)
        if m:
            nomor = m.group(1)
            print(f"\n[+] BERHASIL! Nomor: {nomor}")
            save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
            browser.stop()
            return
    
    print("[-] Gagal")
    save_checkpoint({"status": "failed", "belm": belm_key})
    browser.stop()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2 or sys.argv[1] == "--help":
        print("""
ANTREAN BOT
==========
Usage:
    python antrean.py --test HH:MM [belm]  # Test jadwal
    python antrean.py belm              # Langsung jalan
    python antrean.py --checkpoint     # Cek checkpoint
""")
        sys.exit(1)
    
    if sys.argv[1] == "--test" and len(sys.argv) >= 3:
        try:
            th, tm = map(int, sys.argv[2].split(":"))
        except:
            print("[-] Format HH:MM")
            sys.exit(1)
        belm = sys.argv[3] if len(sys.argv) > 3 else "bintaro"
        asyncio.run(run_schedule(th, tm, belm))
        sys.exit(1)
    
    if sys.argv[1] == "--checkpoint":
        if os.path.exists(CHECKPOINT_FILE):
            with open(CHECKPOINT_FILE, "r") as f:
                print(f.read())
        else:
            print("No checkpoint")
        sys.exit(1)
    
    belm = sys.argv[1].lower()
    asyncio.run(run_bot(belm))