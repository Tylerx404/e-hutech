<div align="center">

# e-HUTECH Telegram Bot

<img src="images/bot-preview.png" alt="HUTECH Bot Preview" width="320"/>

**Bot Telegram đa chức năng dành riêng cho sinh viên HUTECH**
**Truy cập thông tin học tập nhanh chóng và thuận tiện ngay trên Telegram.**

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

## Giới thiệu

e-HUTECH Telegram Bot là công cụ hỗ trợ sinh viên Đại học Công nghệ TP.HCM (HUTECH) truy cập nhanh các thông tin học tập như **thời khóa biểu**, **lịch thi**, **điểm số**, **điểm danh** và nhiều tính năng khác — tất cả ngay trên nền tảng Telegram.

## Tính năng

| Lệnh | Chức năng | Mô tả |
| :--- | :--- | :--- |
| `/dangnhap` | Đăng nhập | Đăng nhập vào hệ thống HUTECH |
| `/danhsach` | Danh sách | Xem danh sách tài khoản đã đăng nhập |
| `/vitri` | Vị trí | Cài đặt vị trí điểm danh mặc định |
| `/diemdanh` | Điểm danh | Điểm danh cho tài khoản hiện tại |
| `/diemdanhtatca` | Điểm danh tất cả | Điểm danh tất cả tài khoản cùng lúc |
| `/tkb` | Thời khóa biểu | Xem TKB & xuất file iCalendar `.ics` |
| `/lichthi` | Lịch thi | Xem lịch thi các môn sắp tới |
| `/diem` | Điểm số | Xem điểm & xuất file Excel `.xlsx` |
| `/hocphan` | Học phần | Tra cứu học phần, danh sách lớp, lịch sử điểm danh |
| `/trogiup` | Trợ giúp | Hiển thị thông tin trợ giúp chi tiết |
| `/dangxuat` | Đăng xuất | Ngắt kết nối tài khoản |

## Cài đặt và Chạy

### Yêu cầu tiên quyết

- [Python 3.10+](https://www.python.org/downloads/)
- [Git](https://git-scm.com/downloads)
- [Docker](https://www.docker.com/products/docker-desktop/) (khuyến khích)

### Bước 1: Clone repository

```bash
git clone https://github.com/Tylerx404/e-hutech.git
cd e-hutech
```

### Bước 2: Cấu hình môi trường

```bash
cp .env.example .env
```

Mở file `.env` và điền các thông tin cần thiết:

```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
POSTGRES_URL=postgresql://user:password@postgres:5432/db_name
REDIS_URL=redis://redis:6379/cache_name
LOG_LEVEL=INFO
LOG_JSON=false
```

> **Mẹo:** Lấy `TELEGRAM_BOT_TOKEN` từ [@BotFather](https://t.me/BotFather) trên Telegram.

---

### Lựa chọn A: Docker (Khuyến khích)

```bash
# Build và khởi động tất cả services
docker-compose up --build -d

# Kiểm tra trạng thái
docker-compose ps

# Xem logs
docker-compose logs -f hutech-bot

# Dừng services
docker-compose down
```

Docker Compose sẽ tự động khởi động **PostgreSQL**, **Redis** và **Bot** với health check đầy đủ.

### Lựa chọn B: Chạy local

> **Lưu ý:** Cần cài đặt và chạy PostgreSQL và Redis trên máy local trước.

```bash
# Tạo môi trường ảo
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# .\venv\Scripts\activate  # Windows

# Cài đặt dependencies
pip install -r requirements.txt

# Khởi chạy bot
python bot.py
```

## Docker Services

| Service | Image | Port | Chức năng |
| :--- | :--- | :--- | :--- |
| `hutech-bot` | Custom build | - | Telegram Bot chính |
| `postgres` | `postgres:latest` | `5432` | Cơ sở dữ liệu |
| `redis` | `redis:latest` | `6379` | Cache layer |

## Giấy phép

Dự án này được cấp phép theo **GNU General Public License v3.0** — xem chi tiết tại file [LICENSE](LICENSE).

---

<div align="center">

**Nếu dự án hữu ích, hãy cho một** :star: **trên GitHub!**

Made with :heart: for HUTECH students

</div>
