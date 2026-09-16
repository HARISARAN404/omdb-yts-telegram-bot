
# 🎬 OMDB + YTS Telegram Bot

A movie search Telegram bot that fetches movie details from the OMDb API and returns YTS torrent links — clean, fast, and dockerized for easy deployment.

## ✨ Features

🔍 Search any movie by name

🎞 Movie details (Poster, Title, Year, Plot)

🧲 YTS torrent links per variant (720p / 1080p / 2160p, source, codec, size — depending on availability)

🚀 Fully async bot with a pooled HTTP client

🐳 Two small services (bot + checker) wired together with Docker Compose

🔑 Secrets via `.env` file

## 🧱 Project Structure

```
.
├── bot/                       # Telegram bot service
│   ├── bot.py                 # handlers & app entrypoint
│   ├── config.py              # env configuration
│   ├── omdb_client.py         # OMDb API client
│   ├── checker_client.py      # client for the checker service
│   ├── utils.py
│   ├── requirements.txt
│   └── Dockerfile
├── checker/                   # YTS checker microservice (Flask + gunicorn)
│   ├── yts_checker_service.py # POST /check, GET /health
│   ├── requirements.txt
│   └── Dockerfile
├── tests/
├── docker-compose.yml
└── .env.example
```

## 🔧 Setup & Installation

1️⃣ Clone the Repository

```bash
git clone https://github.com/HARISARAN404/omdb-yts-telegram-bot.git
cd omdb-yts-telegram-bot
```

2️⃣ Create `.env` File

```bash
cp .env.example .env
```

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OMDB_API_KEY=your_omdb_api_key
```

| Variable | Required | Default | Used by |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | bot |
| `OMDB_API_KEY` | ✅ | — | bot |
| `YTS_CHECKER_URL` | | `http://127.0.0.1:8000` | bot |
| `MAX_RESULTS` | | `8` | bot |
| `YTS_SITE_BASES` | | `https://www.yts-official.cc/movies` | checker (comma-separated) |
| `REQUEST_TIMEOUT` / `MAX_WORKERS` | | `8` / `8` | checker |

## 🐳 Docker Deployment (recommended)

```bash
docker compose up --build -d
```

The bot starts once the checker's health check passes. Logs: `docker compose logs -f bot`.

## 🐍 Run Locally (without Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# terminal 1 — checker
python checker/yts_checker_service.py

# terminal 2 — bot
python bot/bot.py
```

## 🧪 Development

```bash
ruff check . && ruff format --check .
pytest
```

CI runs lint, tests, and a Docker build on every push and pull request.

## 🔗 APIs Used

🎥 OMDb API — Movie metadata

💚 YTS — Torrent links (scraped)
