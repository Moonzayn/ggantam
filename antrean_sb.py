from seleniumbase import SB
import sys
import json
import re
from datetime import datetime

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
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except:
        return {"email": "pangkassobo@gmail.com", "password": "198456z"}

CONFIG = load_config()
EMAIL = CONFIG.get("email")
PASSWORD = CONFIG.get("password")

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

def run_bot(belm_key):
    """Bypass Cloudflare with SeleniumBase UC Mode"""
    belm = BELM_MAP[belm_key]
    
    print("\n" + "="*50)
    print(f"  ANTREAN BOT - {belm['name']}")
    print("="*50 + "\n")
    
    # UC Mode = Undetected ChromeDriver
    with SB(uc=True, headless=False) as sb:
        print("[1] Login ke antrean.logammulia.com...")
        
        sb.open("https://antrean.logammulia.com/login")
        sb.sleep(5)  # Wait for Cloudflare
        
        # Check if already logged in
        try:
            logout = sb.wait_for_element_visible("a:contains('Logout')", timeout=3)
            if logout:
                print("[+] Already logged in!")
        except:
            pass
        
        # Get captcha
        try:
            captcha = sb.wait_for_element_present('label[for="aritmetika"]', timeout=5)
            if captcha:
                text = sb.get_text('label[for="aritmetika"]')
                print(f"[*] Captcha: {text}")
                answer = solve_captcha(text)
                print(f"[*] Jawaban: {answer}")
                
                sb.type('input[name="username"]', EMAIL)
                sb.type('input[name="password"]', PASSWORD)
                sb.type('input[name="aritmetika"]', str(answer))
                sb.sleep(1)
                
                print("[*] Submitting...")
                sb.click('button[type="submit"]')
                sb.sleep(8)
        except Exception as e:
            print(f"[*] Captcha error: {e}")
        
        # Check login
        try:
            sb.wait_for_element_visible("a:contains('Logout')", timeout=5)
            print("[+] LOGIN BERHASIL!\n")
        except:
            print("[*] Continuing...\n")
        
        # Save cookies
        cookies = sb.get_cookies()
        with open("cookies_sb.txt", "w") as f:
            for c in cookies:
                f.write(f"{c['name']}={c['value']}\n")
        print("[*] Cookies saved\n")
        
        # Go to antrean
        print("[2] Ke halaman antrean...")
        sb.open("https://antrean.logammulia.com/antrean")
        sb.sleep(3)
        
        # Select BELM
        sb.select_option_by_value('#site', belm["id"])
        sb.sleep(0.5)
        sb.click("button:contains('Tampilkan')")
        sb.sleep(3)
        
        # Check slot
        print("[3] Cek ketersediaan...")
        print("-"*30)
        
        if sb.is_text_visible("Kuota Tidak Tersedia"):
            print(f"\n[!] {belm['name']}: KUOTA KOSONG")
            save_checkpoint({"status": "no_slot", "belm": belm_key})
            print("\n[*] Coba lagi besok ya!\n")
            return
        
        if sb.is_element_present('form[action*="masuk-pool"]'):
            print(f"[+] {belm['name']}: ADA KUOTA!")
            sb.submit('form')
            sb.sleep(5)
            
            # Check result
            page_text = sb.get_page_source()
            m = re.search(r'(?:NOMOR|No\. Antrean)[:\s<]*(\d+)', page_text, re.IGNORECASE)
            if m:
                nomor = m.group(1)
                print("\n" + "="*50)
                print(f"   [!] BERHASIL! NOMOR: {nomor}")
                print("="*50)
                save_checkpoint({"status": "success", "belm": belm_key, "nomor": nomor})
                return
        
        print("\n[!] Gagal atau tidak ada quota")
        save_checkpoint({"status": "failed", "belm": belm_key})

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python antrean_sb.py bintaro")
        sys.exit(1)
    
    belm = sys.argv[1].lower()
    run_bot(belm)