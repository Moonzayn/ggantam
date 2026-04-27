# Antrean Bot Logam Mulia

Bot otomatis untuk mengambil antrean online Butik Emas Logam Mulia (Antam).

## Fitur

- Auto login dengan Cloudflare Turnstile bypass
- Cek ketersediaan slot antrean
- Ambil antrean otomatis
- Simpan cookies untuk penggunaan ulang
- Multiple BELM support
- Jadwal otomatis (input jam)

## Install

```bash
pip install nodriver requests beautifulsoup4
```

## Config (`config.json`)

```json
{
    "email": "email@gmail.com",
    "password": "password",
    "belm": "bintaro"
}
```

## BELM Available

| Key | Nama |
|-----|------|
| bintaro | Bintaro |
| puri | Puri Indah |
| setiabudi | Setiabudi One |
| darmo | Surabaya 1 Darmo |
| pakuwon | Surabaya 2 Pakuwon |
| bandung | Bandung |
| bekasi | Bekasi |
| bogor | Bogor |

## Cara Pakai

### Cek Slot
```bash
python antrean.py bintaro
python antrean.py puri --cookie  # dengan cookies
```

### Ambil Antrean
```bash
python antrean.py bintaro --take
```

### Jadwal Otomatis
```bash
python antrean.py --schedule 07:00
```

## Usage

```
python antrean.py [belm_name] [options]

Arguments:
  belm_name          Nama BELM (bintaro, puri, darmo, dll)

Options:
  --take             Ambil antrean jika slot tersedia
  --cookie           Gunakan cookies yang ada
  --schedule HH:MM    Jadwal auto-run (bot jalan 2 menit sebelum)
```

## Note

- Jam membuka antrean biasanya 07:00-08:00 WIB
- Botsudah menggunakan Chrome nodriver (bukan Selenium)
- Cookies tersimpan di cookies.json