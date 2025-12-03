
# 🎬 OMDB + YTS Telegram Bot

A powerful movie search Telegram bot that fetches movie details from OMDB API and returns YTS magnet links instantly — clean, fast, and dockerized for easy deployment.




## ✨ Features

🔍 Search any movie by name

🎞 Fetch detailed movie info (Poster, Plot, Cast, Genre, Rating, Runtime etc.)

🧲 Get YTS Magnet Links (720p / 1080p / 2160p depending on availability)

🚀 Fast Telegram Bot Response (Async powered)

🐳 Docker Support — run anywhere

🔑 Secure API Keys via .env file

📦 Clean, modular code structure


## 🔧 Setup & Installation

1️⃣ Clone the Repository

```bash
git clone https://github.com/HARISARAN404/omdb-yts-telegram-bot.git
cd omdb-yts-telegram-bot

```
2️⃣ Create .env File
```bash
BOT_TOKEN=your_telegram_bot_token
OMDB_API_KEY=your_omdb_api_key

```
3️⃣ Install Requirements
```bash
pip install -r requirements.txt
```
4️⃣ Run the Bot
```bash
python bot/bot.py

```

## 🐳 Docker Deployment

Build Image
```bash
docker build -t omdb-yts-bot .

```
Run Container
```bash
docker run --env-file .env omdb-yts-bot

```
Using Docker Compose
```bash
docker compose up --build

```
## 🔗 APIs Used

🎥 OMDB API — Movie metadata

💚 YTS.mx — Torrent search (scraped)