🎬 OMDB + YTS Telegram Bot

A powerful movie search Telegram bot that fetches movie details from OMDB API and returns YTS magnet links instantly — clean, fast, and dockerized for easy deployment.

✨ Features

🔍 Search any movie by name

🎞 Fetch detailed movie info (Poster, Plot, Cast, Genre, Rating, Runtime etc.)

🧲 Get YTS Magnet Links (720p / 1080p / 2160p depending on availability)

🚀 Fast Telegram Bot Response (Async powered)

🐳 Docker Support — run anywhere

🔑 Secure API Keys via .env file

📦 Clean, modular code structure

🔧 Setup & Installation
1️⃣ Clone the Repository
git clone https://github.com/HARISARAN404/omdb-yts-telegram-bot.git
cd omdb-yts-telegram-bot

2️⃣ Create .env File

(Add your keys securely)

BOT_TOKEN=your_telegram_bot_token
OMDB_API_KEY=your_omdb_api_key

3️⃣ Install Requirements
pip install -r requirements.txt

4️⃣ Run the Bot
python bot/bot.py

🐳 Docker Deployment
Build Image
docker build -t omdb-yts-bot .

Run Container
docker run --env-file .env omdb-yts-bot

Using Docker Compose
docker compose up --build

🎯 Commands (Telegram)
Command	Description
/start	Welcome & Help
/search <movie>	Search movie + magnet links
/about	Bot information
🔗 APIs Used

🎥 OMDB API — Movie metadata

💚 YTS.mx — Torrent search (scraped)

🎥 Preview

Add screenshot or GIF here (optional)

[Insert bot chat preview image]

👨‍💻 Author

Harisaran V
🔗 GitHub: https://github.com/HARISARAN404

📧 Email: harisaran.official@gmail.com

📜 License

MIT License – feel free to use and modify!