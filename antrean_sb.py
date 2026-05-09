# antrean_bot.py
import asyncio
import json
import os
import re
import sys
from datetime import datetime

import botright

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
CONFIG_FILE    = "config.json"
CHECKPOINT_FILE = "checkpoint.json"
COOKIE_FILE    = "cookies.json"
BASE_URL       = "https://antrean.logammulia.com"

BELM_MAP = {
    "puri"      : {"id": "21", "name": "Puri Indah"},
    "setiabudi" : {"id": "8",  "name": "Setiabudi One"},
    "bintaro"   : {"id": "16", "name": "Bintaro"},
    "darmo"     : {"id": "13", "name": "Darmo"},
    "pakuwon"   : {"id": "14", "name": "Pakuwon"},
    "bandung"   : {"id": "1",  "name": "Bandung"},
    "bekasi"    : {"id": "19", "name": "Bekasi"},
    "bogor"     : {"id": "17", "name": "Bogor"},
}


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("[!] config.json rusak, pakai default")
    return {
        "email"   : "pangkassobo@gmail.com",
        "password": "198456z",
        "proxy"   : "",
    }


CONFIG   = load_config()
EMAIL    = CONFIG.get("email", "")
PASSWORD = CONFIG.get("password", "")


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def save_checkpoint(data: dict):
    data["timestamp"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[OK] Checkpoint: {data}")


def solve_captcha(text: str):
    """Solve simple arithmetic captcha."""
    t = text.lower().strip()
    patterns = [
        (r"(\d+)\s*(?:dikurang|kurang|minus|moins|\-)\s*(\d+)", lambda a, b: a - b),
        (r"(\d+)\s*(?:ditambah|tambah|plus|\+)\s*(\d+)",        lambda a, b: a + b),
        (r"(\d+)\s*(?:dikali|kali|times|×|x|\*)\s*(\d+)",       lambda a, b: a * b),
        (r"(\d+)\s*(?:dibagi|bagi|div|÷|/)\s*(\d+)",            lambda a, b: a // b if b else 0),
    ]
    for pat, op in patterns:
        m = re.search(pat, t)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            return op(a, b)
    print(f"[!] Captcha tidak dikenali: '{text}'")
    return None


# ─────────────────────────────────────────────
#  COOKIE HELPERS
# ─────────────────────────────────────────────
async def save_cookies(page):
    cookies = await page.context.cookies()
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f, indent=2)
    print(f"[OK] {len(cookies)} cookies disimpan")


async def load_cookies(page) -> bool:
    if not os.path.exists(COOKIE_FILE):
        return False
    try:
        with open(COOKIE_FILE, "r") as f:
            cookies = json.load(f)
        await page.context.add_cookies(cookies)
        print(f"[OK] {len(cookies)} cookies di-load")
        return True
    except Exception as e:
        print(f"[!] Gagal load cookies: {e}")
        return False


# ─────────────────────────────────────────────
#  PAGE HELPERS
# ─────────────────────────────────────────────
async def is_logged_in(page) -> bool:
    try:
        url  = page.url.lower()
        html = await page.content()
        html = html.lower()
    except Exception:
        return False

    if "/login" in url:
        return False
    if "logout" in html:
        return True
    if "/antrean" in url or "/antrian" in url or "/home" in url:
        return True
    return False


async def wait_for_page_ready(page, timeout: int = 30) -> bool:
    """Wait until Cloudflare / security check is gone."""
    CF_SIGNS = [
        "security verification",
        "performing security",
        "checking your browser",
        "just a moment",
        "cf-browser-verification",
    ]
    print("[*] Menunggu halaman siap...")
    for i in range(timeout):
        try:
            html = (await page.content()).lower()
        except Exception:
            await asyncio.sleep(1)
            continue

        if any(s in html for s in CF_SIGNS):
            if i % 5 == 0:
                print(f"  [!] Security check... ({i}s)")
            await asyncio.sleep(1)
            continue

        print(f"  [OK] Halaman siap ({i}s)")
        return True

    print(f"  [!] Timeout {timeout}s - lanjut")
    return True


async def safe_fill(page, selector: str, value: str, timeout: int = 10000):
    """Fill input with retry."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.fill(selector, value)
        return True
    except Exception as e:
        print(f"  [!] safe_fill({selector}): {e}")
        return False


async def safe_click(page, selector: str, timeout: int = 10000):
    """Click element with retry."""
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except Exception as e:
        print(f"  [!] safe_click({selector}): {e}")
        return False


# ─────────────────────────────────────────────
#  TURNSTILE / CAPTCHA WAIT
# ─────────────────────────────────────────────
async def wait_turnstile(page, timeout: int = 60) -> bool:
    """
    Botright handles Turnstile automatically.
    We just wait until the hidden input has a token value.
    """
    print("[*] Menunggu Turnstile selesai...")
    for i in range(timeout):
        try:
            # Turnstile injects a hidden input when solved
            token = await page.evaluate("""() => {
                const el = document.querySelector(
                    'input[name="cf-turnstile-response"]'
                );
                return el ? el.value : '';
            }""")
            if token and len(token) > 10:
                print(f"  [OK] Turnstile solved ({i}s)! Token: {token[:30]}...")
                return True
        except Exception:
            pass

        await asyncio.sleep(1)

    # Fallback: check if challenge gone
    html = (await page.content()).lower()
    if "verify you are human" not in html and "turnstile" not in html:
        print("  [OK] Turnstile tidak terdeteksi lagi")
        return True

    print(f"  [!] Turnstile timeout {timeout}s")
    return False


# ─────────────────────────────────────────────
#  LOGIN
# ─────────────────────────────────────────────
async def do_login(page, max_retries: int = 3) -> bool:
    for attempt in range(1, max_retries + 1):
        print(f"\n[LOGIN] Attempt {attempt}/{max_retries}")

        await page.goto(f"{BASE_URL}/login", wait_until="domcontentloaded")
        await asyncio.sleep(2)
        await wait_for_page_ready(page, timeout=30)

        # Already logged in?
        if await is_logged_in(page):
            print("[OK] Sudah login!")
            return True

        # Wait for login form
        try:
            await page.wait_for_selector(
                'input[name="username"]', timeout=15000
            )
        except Exception:
            print(f"  [!] Form login tidak muncul (attempt {attempt})")
            await page.screenshot(path=f"login_noform_{attempt}.png")
            continue

        # ── Turnstile? ──
        html = (await page.content()).lower()
        if "turnstile" in html or "verify you are human" in html:
            print("  [!] Turnstile terdeteksi, Botright sedang solve...")
            solved = await wait_turnstile(page, timeout=60)
            if not solved:
                print("  [!] Turnstile gagal solve — skip attempt ini")
                await page.screenshot(path=f"turnstile_fail_{attempt}.png")
                continue

        # ── Fill form ──
        await safe_fill(page, 'input[name="username"]', EMAIL)
        await asyncio.sleep(0.3)
        await safe_fill(page, 'input[name="password"]', PASSWORD)
        await asyncio.sleep(0.3)

        # ── Arithmetic captcha ──
        try:
            captcha_el = page.locator('label[for="aritmetika"]')
            if await captcha_el.count() > 0:
                captcha_text = await captcha_el.inner_text()
                print(f"  [*] Captcha: '{captcha_text}'")
                answer = solve_captcha(captcha_text)

                if answer is None:
                    manual = input("  [?] Jawaban captcha manual: ").strip()
                    answer = manual if manual else "0"

                print(f"  [*] Jawaban: {answer}")
                await safe_fill(
                    page, 'input[name="aritmetika"]', str(answer)
                )
            else:
                print("  [*] Tidak ada captcha aritmatika")
        except Exception as e:
            print(f"  [!] Captcha error: {e}")

        await asyncio.sleep(0.5)

        # ── Submit ──
        clicked = await safe_click(page, 'button[type="submit"]')
        if not clicked:
            try:
                await page.evaluate(
                    'document.querySelector("form").submit()'
                )
            except Exception:
                pass

        print("  [*] Submitted, menunggu redirect...")
        await asyncio.sleep(4)

        # ── reCAPTCHA after submit? ──
        html = (await page.content()).lower()
        if "recaptcha" in html or "verify you are human" in html:
            print("\n" + "!" * 50)
            print("  [!] reCAPTCHA / Turnstile MUNCUL setelah submit!")
            print("  [!] Solve MANUAL di browser!")
            print("!" * 50)

            for i in range(120):
                await asyncio.sleep(1)
                if await is_logged_in(page):
                    print(f"  [OK] Solved! ({i}s)")
                    break
                if i % 15 == 0 and i:
                    print(f"  [*] Menunggu... ({i}s)")
            else:
                print("  [!] Timeout menunggu solve manual")
                continue

        # ── Check result ──
        await asyncio.sleep(1)
        if await is_logged_in(page):
            print("\n[OK] LOGIN BERHASIL!")
            await save_cookies(page)
            return True

        # Print error jika ada
        try:
            html_raw = await page.content()
            for pat in [
                r'class="alert[^"]*"[^>]*>(.*?)</div>',
                r'class="error[^"]*"[^>]*>(.*?)</div>',
                r'<p[^>]*class="[^"]*danger[^"]*"[^>]*>(.*?)</p>',
            ]:
                m = re.search(pat, html_raw, re.DOTALL | re.IGNORECASE)
                if m:
                    print(f"  [!] Error: {m.group(1).strip()[:120]}")
                    break
        except Exception:
            pass

        print(f"  [!] Gagal attempt {attempt}")
        await page.screenshot(path=f"login_fail_{attempt}.png")
        await asyncio.sleep(2)

    print("\n[✗] LOGIN GAGAL semua attempt")
    return False


# ─────────────────────────────────────────────
#  NAVIGATE TO ANTRIAN
# ─────────────────────────────────────────────
async def navigate_to_antrian(page) -> bool:
    candidates = [
        f"{BASE_URL}/antrian",
        f"{BASE_URL}/antrean",
        f"{BASE_URL}/home",
        f"{BASE_URL}/",
    ]

    for url in candidates:
        print(f"  [*] Coba: {url}")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=15000)
        except Exception:
            continue
        await asyncio.sleep(2)
        await wait_for_page_ready(page, timeout=15)

        html = (await page.content()).lower()
        if "select" in html and any(
            kw in html for kw in ["site", "butik", "lokasi", "cabang"]
        ):
            print(f"  [OK] Halaman antrean ditemukan: {url}")
            return True

    # Cari link antrean dari halaman manapun
    try:
        links = await page.query_selector_all("a")
        for link in links:
            href = (await link.get_attribute("href") or "").lower()
            text = (await link.inner_text()).lower()
            if any(kw in href or kw in text for kw in ["antri", "antre", "ambil"]):
                print(f"  [*] Klik link: {text.strip()} -> {href}")
                await link.click()
                await asyncio.sleep(3)
                await wait_for_page_ready(page, timeout=15)
                return True
    except Exception as e:
        print(f"  [!] Link search error: {e}")

    return False


# ─────────────────────────────────────────────
#  SELECT BUTIK
# ─────────────────────────────────────────────
async def select_butik(page, belm_id: str) -> bool:
    selectors = [
        "#site",
        'select[name="site"]',
        'select[name="butik"]',
        'select[name="lokasi"]',
        'select[name="cabang"]',
        "select",
    ]

    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                print(f"  [*] Select ditemukan: {sel}")
                await el.select_option(value=belm_id)
                print(f"  [OK] Butik dipilih (value={belm_id})")
                return True
        except Exception:
            continue

    # Fallback: JavaScript
    try:
        await page.evaluate(f"""() => {{
            const selectors = ['#site','select[name="site"]','select[name="butik"]','select'];
            for (const s of selectors) {{
                const el = document.querySelector(s);
                if (el) {{
                    el.value = '{belm_id}';
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                    return true;
                }}
            }}
            return false;
        }}""")
        print(f"  [OK] Butik dipilih via JS (value={belm_id})")
        return True
    except Exception as e:
        print(f"  [!] JS select error: {e}")

    return False


# ─────────────────────────────────────────────
#  SUBMIT TAMPILKAN
# ─────────────────────────────────────────────
async def click_tampilkan(page) -> bool:
    candidates = [
        "button:has-text('Tampilkan')",
        "button:has-text('Cari')",
        "button:has-text('Submit')",
        'button[type="submit"]',
        'input[type="submit"]',
        ".btn-primary",
    ]
    for sel in candidates:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.click()
                print(f"  [OK] Klik: {sel}")
                return True
        except Exception:
            continue

    try:
        await page.evaluate('document.querySelector("form").submit()')
        return True
    except Exception:
        pass

    return False


# ─────────────────────────────────────────────
#  AMBIL ANTREAN
# ─────────────────────────────────────────────
async def submit_antrian(page) -> bool:
    form_selectors = [
        'form[action*="masuk-pool"]',
        'form[action*="ambil"]',
        'form[action*="antr"]',
    ]
    for sel in form_selectors:
        try:
            el = page.locator(sel)
            if await el.count() > 0:
                # Klik submit di dalam form
                submit_btn = el.locator('button[type="submit"]')
                if await submit_btn.count() > 0:
                    await submit_btn.click()
                else:
                    await page.evaluate(
                        f'document.querySelector(\'{sel}\').submit()'
                    )
                print(f"  [OK] Form submitted: {sel}")
                return True
        except Exception:
            continue

    # Cari tombol ambil antrean
    btn_texts = [
        "Ambil Antrean",
        "Ambil Antrian",
        "Daftar",
        "Masuk Antrean",
        "Join",
    ]
    for text in btn_texts:
        try:
            btn = page.locator(f"button:has-text('{text}')").first
            if await btn.count() > 0:
                await btn.click()
                print(f"  [OK] Klik: {text}")
                return True
        except Exception:
            continue

    return False


# ─────────────────────────────────────────────
#  MAIN BOT
# ─────────────────────────────────────────────
async def run_bot(belm_key: str):
    if belm_key not in BELM_MAP:
        print(f"[✗] BELM '{belm_key}' tidak dikenal!")
        print(f"    Pilihan: {', '.join(BELM_MAP.keys())}")
        sys.exit(1)

    belm = BELM_MAP[belm_key]

    print("\n" + "═" * 55)
    print(f"    ANTREAN BOT  —  {belm['name']}  (ID {belm['id']})")
    print("═" * 55 + "\n")

    proxy = CONFIG.get("proxy", "")

    # ── Init Botright ──
    async with botright.Botright(headless=False) as client:
        browser_opts = {}
        if proxy:
            browser_opts["proxy"] = {"server": proxy}
            print(f"[*] Proxy: {proxy[:40]}...")

        browser = await client.new_browser(**browser_opts)
        page    = await browser.new_page()

        # ── STEP 1: Login ──────────────────────────────────────
        print("[STEP 1] Login\n")

        # Coba cookies dulu
        if os.path.exists(COOKIE_FILE):
            await load_cookies(page)
            await page.goto(BASE_URL, wait_until="domcontentloaded")
            await asyncio.sleep(3)
            await wait_for_page_ready(page)

            if await is_logged_in(page):
                print("[OK] Login via cookies berhasil!")
            else:
                print("[*] Cookies expired, login ulang...")
                if not await do_login(page):
                    await page.screenshot(path="final_login_fail.png")
                    return
        else:
            if not await do_login(page):
                await page.screenshot(path="final_login_fail.png")
                return

        # ── STEP 2: Navigasi ───────────────────────────────────
        print("\n[STEP 2] Navigasi ke halaman antrean\n")

        if not await navigate_to_antrian(page):
            print("[✗] Halaman antrean tidak ditemukan!")
            await page.screenshot(path="no_antrian.png")
            return

        # ── STEP 3: Pilih butik ────────────────────────────────
        print(f"\n[STEP 3] Pilih butik: {belm['name']}\n")

        if not await select_butik(page, belm["id"]):
            print("[✗] Gagal pilih butik!")
            await page.screenshot(path="select_fail.png")
            return

        await asyncio.sleep(0.8)

        if not await click_tampilkan(page):
            print("[✗] Gagal klik Tampilkan!")

        await asyncio.sleep(3)
        await wait_for_page_ready(page, timeout=20)

        # ── STEP 4: Cek kuota ──────────────────────────────────
        print("\n[STEP 4] Cek ketersediaan kuota\n")

        html      = await page.content()
        html_low  = html.lower()
        print(f"[*] URL: {page.url}")

        NO_QUOTA = [
            "kuota tidak tersedia",
            "kuota habis",
            "tidak ada kuota",
            "sold out",
            "penuh",
            "quota not available",
        ]
        if any(kw in html_low for kw in NO_QUOTA):
            print(f"\n[✗] {belm['name']}: KUOTA KOSONG / HABIS")
            save_checkpoint({"status": "no_slot", "belm": belm_key})
            await page.screenshot(path="kuota_habis.png")
            print("[*] Coba lagi besok!\n")
            return

        # ── STEP 5: Ambil antrean ──────────────────────────────
        print("\n[STEP 5] Ambil antrean\n")

        if not await submit_antrian(page):
            print("[!] Tidak ada form / tombol ambil antrean")
            await page.screenshot(path="no_form.png")

            # Debug: print forms & buttons
            forms   = re.findall(r'<form[^>]*action="([^"]*)"', html)
            buttons = re.findall(r"<button[^>]*>(.*?)</button>", html, re.DOTALL)
            print(f"  Forms  : {forms}")
            print(f"  Buttons: {[b.strip()[:50] for b in buttons]}")
            save_checkpoint({"status": "no_form", "belm": belm_key})
            return

        await asyncio.sleep(5)
        await wait_for_page_ready(page, timeout=20)

        # ── STEP 6: Cek hasil ──────────────────────────────────
        print("\n[STEP 6] Cek hasil\n")

        result_html = await page.content()
        print(f"[*] URL: {page.url}")

        NOMOR_PATTERNS = [
            r"(?:NOMOR|No\.?\s*Antrean|Nomor\s*Antrian)[:\s<>/\w]*?(\d+)",
            r'class="[^"]*nomor[^"]*"[^>]*>\s*(\d+)',
            r"(?:antri(?:an|ean)|antrian)[:\s]*(\d+)",
        ]

        nomor = None
        for pat in NOMOR_PATTERNS:
            m = re.search(pat, result_html, re.IGNORECASE)
            if m:
                nomor = m.group(1)
                break

        if nomor:
            print("\n" + "═" * 55)
            print(f"     BERHASIL!")
            print(f"     Nomor Antrean : {nomor}")
            print(f"     Butik         : {belm['name']}")
            print(f"     Waktu         : {datetime.now():%H:%M:%S}")
            print("═" * 55 + "\n")
            save_checkpoint({
                "status": "success",
                "belm"  : belm_key,
                "nomor" : nomor,
            })
            await page.screenshot(path="success.png")

        elif any(
            kw in result_html.lower()
            for kw in ["berhasil", "sukses", "success", "selamat"]
        ):
            print("\n[OK] Sepertinya BERHASIL (tapi nomor tidak ditemukan)")
            save_checkpoint({"status": "success_no_number", "belm": belm_key})
            await page.screenshot(path="success_maybe.png")

        else:
            print("[!] Hasil tidak jelas")
            title = re.search(r"<title>(.*?)</title>", result_html)
            if title:
                print(f"    Page: {title.group(1)}")
            save_checkpoint({"status": "unclear", "belm": belm_key})
            await page.screenshot(path="result_unclear.png")


# ─────────────────────────────────────────────
#  STANDBY MODE
# ─────────────────────────────────────────────
async def standby_mode():
    print("\n" + "═" * 55)
    print("     ANTREAN BOT  —  STANDBY MODE")
    print("═" * 55)
    print("  Browser terbuka, login otomatis.")
    print("  Kamu bisa klik manual setelah login.")
    print("  Ctrl+C untuk keluar.\n")

    proxy = CONFIG.get("proxy", "")

    async with botright.Botright(headless=False) as client:
        opts = {}
        if proxy:
            opts["proxy"] = {"server": proxy}

        browser = await client.new_browser(**opts)
        page    = await browser.new_page()

        if not await do_login(page):
            print("[!] Login gagal. Solve manual di browser...")
            print("[*] Tekan Enter setelah login manual...")
            try:
                input()
            except EOFError:
                await asyncio.sleep(60)

        await navigate_to_antrian(page)

        print("\n" + "═" * 55)
        print(f"  [OK]  Browser siap!")
        print(f"  🌐  URL : {page.url}")
        print()
        print("  Pilih butik & ambil antrean MANUAL")
        print("  Ctrl+C untuk keluar")
        print("═" * 55 + "\n")

        try:
            while True:
                await asyncio.sleep(60)
                if not await is_logged_in(page):
                    print("[!] Session expired, re-login...")
                    await do_login(page)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\n[*] Keluar...")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
def print_help():
    print("═" * 55)
    print("    ANTREAN BOT  (Botright + Playwright)")
    print("═" * 55)
    print()
    print("  Usage:")
    print("    python antrean_bot.py standby   → Login, lalu manual")
    print("    python antrean_bot.py <butik>   → Auto ambil antrean")
    print()
    print("  Butik tersedia:")
    for k, v in BELM_MAP.items():
        print(f"    {k:12s} → {v['name']:20s} (ID {v['id']})")
    print()
    print("  Config (config.json):")
    print('    { "email": "...", "password": "...", "proxy": "" }')
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_help()
        sys.exit(0)

    mode = sys.argv[1].lower()

    if mode == "standby":
        asyncio.run(standby_mode())
    elif mode in BELM_MAP:
        asyncio.run(run_bot(mode))
    else:
        print(f"[✗] '{mode}' tidak dikenal!")
        print_help()
        sys.exit(1)