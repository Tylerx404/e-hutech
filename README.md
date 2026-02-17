<div align="center">

# e-HUTECH Telegram Bot

<img src="images/bot-preview.png" alt="HUTECH Bot Preview" width="320"/>

**Bot Telegram da chuc nang danh rieng cho sinh vien HUTECH**
**Truy cap thong tin hoc tap nhanh chong va thuan tien ngay tren Telegram.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Telegram Bot API](https://img.shields.io/badge/Telegram_Bot_API-26A5E4?style=for-the-badge&logo=telegram&logoColor=white)](https://core.telegram.org/bots/api)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-DC382D?style=for-the-badge&logo=redis&logoColor=white)](https://redis.io/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/Tylerx404/e-hutech?style=for-the-badge&logo=github)](https://github.com/Tylerx404/e-hutech/stargazers)
[![GitHub issues](https://img.shields.io/github/issues/Tylerx404/e-hutech?style=for-the-badge&logo=github)](https://github.com/Tylerx404/e-hutech/issues)
[![GitHub last commit](https://img.shields.io/github/last-commit/Tylerx404/e-hutech?style=for-the-badge&logo=github)](https://github.com/Tylerx404/e-hutech/commits/main)

---

</div>

## Gioi thieu

HUTECH Telegram Bot la cong cu ho tro sinh vien Dai hoc Cong nghe TP.HCM (HUTECH) truy cap nhanh cac thong tin hoc tap nhu **thoi khoa bieu**, **lich thi**, **diem so**, **diem danh** va nhieu tinh nang khac — tat ca ngay tren nen tang Telegram.

## Tinh nang

| Lenh | Chuc nang | Mo ta |
| :--- | :--- | :--- |
| `/dangnhap` | Dang nhap | Dang nhap vao he thong HUTECH |
| `/danhsach` | Danh sach | Xem danh sach tai khoan da dang nhap |
| `/vitri` | Vi tri | Cai dat vi tri diem danh mac dinh |
| `/diemdanh` | Diem danh | Diem danh cho tai khoan hien tai |
| `/diemdanhtatca` | Diem danh tat ca | Diem danh tat ca tai khoan cung luc |
| `/tkb` | Thoi khoa bieu | Xem TKB & xuat file iCalendar `.ics` |
| `/lichthi` | Lich thi | Xem lich thi cac mon sap toi |
| `/diem` | Diem so | Xem diem & xuat file Excel `.xlsx` |
| `/hocphan` | Hoc phan | Tra cuu hoc phan, danh sach lop, lich su diem danh |
| `/trogiup` | Tro giup | Hien thi thong tin tro giup chi tiet |
| `/dangxuat` | Dang xuat | Ngat ket noi tai khoan |

## Cai dat va Chay

### Yeu cau tien quyet

- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [Docker](https://www.docker.com/products/docker-desktop/) (khuyen khich)

### Buoc 1: Clone repository

```bash
git clone https://github.com/Tylerx404/e-hutech.git
cd e-hutech
```

### Buoc 2: Cau hinh moi truong

```bash
cp .env.example .env
```

Mo file `.env` va dien cac thong tin can thiet:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
POSTGRES_URL=postgresql://user:password@postgres:5432/db_name
REDIS_URL=redis://redis:6379/cache_name
```

> **Tip:** Lay `TELEGRAM_BOT_TOKEN` tu [@BotFather](https://t.me/BotFather) tren Telegram.

---

### Lua chon A: Docker (Khuyen khich)

```bash
# Build va khoi dong tat ca services
docker-compose up --build -d

# Kiem tra trang thai
docker-compose ps

# Xem logs
docker-compose logs -f hutech-bot

# Dung services
docker-compose down
```

Docker Compose se tu dong khoi dong **PostgreSQL**, **Redis** va **Bot** voi health check day du.

### Lua chon B: Chay local

> **Luu y:** Can cai dat va chay PostgreSQL va Redis tren may local truoc.

```bash
# Tao moi truong ao
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# .\venv\Scripts\activate  # Windows

# Cai dat dependencies
pip install -r requirements.txt

# Khoi chay bot
python bot.py
```

## Docker Services

| Service | Image | Port | Chuc nang |
| :--- | :--- | :--- | :--- |
| `hutech-bot` | Custom build | - | Telegram Bot chinh |
| `postgres` | `postgres:latest` | `5432` | Co so du lieu |
| `redis` | `redis:latest` | `6379` | Cache layer |

## Giay phep

Du an nay duoc cap phep theo **GNU General Public License v3.0** — xem chi tiet tai file [LICENSE](LICENSE).

---

<div align="center">

**Neu du an huu ich, hay cho mot** :star: **tren GitHub!**

Made with :heart: for HUTECH students

</div>
