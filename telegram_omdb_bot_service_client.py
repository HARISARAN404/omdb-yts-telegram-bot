import os
import logging
import requests
from typing import List, Dict, Optional, Any

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

# ---------- CONFIG ----------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8449011306:AAEARUerozmGXj6DIuj4NF7ju95pomjoJtM")
OMDB_KEY = os.environ.get("OMDB_API_KEY", "f76584ec")
OMDB_URL = "http://www.omdbapi.com/"
CHECKER_SERVICE_BASE = os.environ.get("YTS_CHECKER_URL", "http://127.0.0.1:8000")
CHECKER_ENDPOINT = CHECKER_SERVICE_BASE.rstrip("/") + "/check"
MAX_RESULTS = 8
# ----------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram-omdb-clean")


# ----- helpers -----
def pretty_bytes(val: Optional[Any]) -> str:
    """
    Turn bytes (int or numeric string) into human-readable string.
    If val is None or not parseable, return 'unknown'.
    """
    if val is None:
        return "unknown"
    try:
        if isinstance(val, str):
            v = int(val.replace(",", "").strip())
        else:
            v = int(val)
    except Exception:
        return "unknown"

    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(v)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    if idx >= 2:
        return f"{size:.1f} {units[idx]}"
    else:
        return f"{int(size)} {units[idx]}"


def omdb_search(query: str) -> Optional[Dict]:
    params = {"apikey": OMDB_KEY, "s": query}
    try:
        r = requests.get(OMDB_URL, params=params, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("omdb_search failed")
        return None


def omdb_get_by_id(imdbid: str) -> Optional[Dict]:
    params = {"apikey": OMDB_KEY, "i": imdbid, "plot": "short"}
    try:
        r = requests.get(OMDB_URL, params=params, timeout=8)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("omdb_get_by_id failed")
        return None


def build_checker_payload(results: List[Dict]) -> Dict:
    items = []
    for it in results:
        items.append({"imdbID": it.get("imdbID", ""), "title": it.get("Title", ""), "year": it.get("Year", "")})
    return {"items": items}


def post_to_checker(payload: Dict) -> Optional[Dict]:
    try:
        r = requests.post(CHECKER_ENDPOINT, json=payload, timeout=20)
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.exception("post_to_checker failed")
        return None


# ----- Telegram handlers -----
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Hi — send a movie name and I'll search OMDb and check torrent links on configured sites.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    query_text = update.message.text.strip()
    progress = await update.message.reply_text(f"🔎 Searching OMDb for `{query_text}`", parse_mode="MarkdownV2")

    data = omdb_search(query_text)
    if not data or data.get("Response", "False") == "False":
        await update.message.reply_text("No results or error from OMDb.")
        try:
            await progress.delete()
        except Exception:
            pass
        return

    results = data.get("Search", [])[:MAX_RESULTS]
    if not results:
        await update.message.reply_text("No results returned.")
        try:
            await progress.delete()
        except Exception:
            pass
        return

    # send to checker service
    payload = build_checker_payload(results)
    checker_resp = post_to_checker(payload)
    checker_results = (checker_resp or {}).get("results", {})

    # build inline keyboard with basic indicator (count of torrents)
    keyboard = []
    for it in results:
        imdbid = it.get("imdbID", "")
        title = it.get("Title", "")
        year = it.get("Year", "")
        chk = checker_results.get(imdbid, {})
        torrents = chk.get("torrents", []) if chk else []
        found = len(torrents) > 0
        btn_label = f"{title} ({year})"
        if found:
            btn_label += f" ✅[{len(torrents)}]"
        keyboard.append([InlineKeyboardButton(btn_label, callback_data=f"IMDB_{imdbid}")])

    keyboard.append([InlineKeyboardButton("Cancel", callback_data="CANCEL")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a result (shows number of torrent variants found):", reply_markup=reply_markup)

    # cache the checker results for later
    context.user_data["checker_results"] = checker_results
    try:
        await progress.delete()
    except Exception:
        pass


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""

    # Cancel handler
    if data == "CANCEL":
        try:
            await query.edit_message_text("Cancelled.")
        except Exception:
            await query.message.reply_text("Cancelled.")
        return

    # IMDB selection -> show details + torrent buttons
    if data.startswith("IMDB_"):
        imdbid = data.split("_", 1)[1]
        movie = omdb_get_by_id(imdbid)
        if not movie:
            await query.message.reply_text("Failed to fetch movie details from OMDb.")
            return

        title = movie.get("Title", "N/A")
        year = movie.get("Year", "N/A")
        plot = movie.get("Plot", "N/A")
        poster = movie.get("Poster", "")

        try:
            await query.edit_message_text(f"Selected: *{title}* ({year})", parse_mode="Markdown")
        except Exception:
            pass

        detail_text = f"*{title}* ({year})\n\n*Plot:* {plot}\n"
        if poster and poster != "N/A":
            try:
                await query.message.reply_photo(photo=poster, caption=detail_text, parse_mode="Markdown")
            except Exception:
                await query.message.reply_text(detail_text, parse_mode="Markdown")
        else:
            await query.message.reply_text(detail_text, parse_mode="Markdown")

        # Show torrent buttons gathered earlier from checker_results
        checker_results = context.user_data.get("checker_results", {})
        chk = checker_results.get(imdbid, {}) or {}
        torrents = chk.get("torrents", []) if chk else []

        if not torrents:
            await query.message.reply_text("No torrent links found on configured sites.")
            return

        # Prepare mapping in user_data for callback lookup:
        torrent_map = context.user_data.setdefault("torrent_map", {})

        t_keyboard = []
        for idx, t in enumerate(torrents):
            q = t.get("quality", "unknown")
            src = t.get("source", "unknown")
            codec = t.get("codec", "unknown")
            validation = t.get("validation", {}) or {}
            clen = validation.get("content_length") or validation.get("Content-Length") or validation.get("content-length")
            size_readable = pretty_bytes(clen)
            # label includes size if available
            label = f"{q} / {src} / {codec} — {size_readable}"
            # callback id
            cbid = f"TORR_{imdbid}_{idx}"
            torrent_url = (validation.get("final_url") or t.get("torrent_url"))
            # store mapping with extra metadata to show later
            torrent_map[cbid] = {
                "url": torrent_url,
                "meta": {"quality": q, "source": src, "codec": codec},
                "validation": validation,
            }
            # create button (truncate label if too long)
            if len(label) > 64:
                label = label[:61] + "..."
            t_keyboard.append([InlineKeyboardButton(label, callback_data=cbid)])

        # add cancel button
        t_keyboard.append([InlineKeyboardButton("Cancel", callback_data="CANCEL")])
        t_markup = InlineKeyboardMarkup(t_keyboard)
        await query.message.reply_text("Select torrent variant to get link:", reply_markup=t_markup)
        return

    # User picked a torrent button (TORR_<imdbid>_<idx>)
    if data.startswith("TORR_"):
        mapping = context.user_data.get("torrent_map", {})
        entry = mapping.get(data)
        if not entry:
            await query.message.reply_text("Sorry — torrent entry not found (it may have expired). Try searching again.")
            return

        torrent_url = entry.get("url")
        meta = entry.get("meta", {})
        validation = entry.get("validation", {}) or {}
        q = meta.get("quality", "unknown")
        src = meta.get("source", "unknown")
        codec = meta.get("codec", "unknown")

        status = validation.get("status") or validation.get("http_status") or "unknown"
        ctype = validation.get("content_type") or validation.get("Content-Type") or "unknown"
        clen = validation.get("content_length") or validation.get("Content-Length") or validation.get("content-length")
        size_readable = pretty_bytes(clen)

        # send the torrent URL as a message (safe and explicit)
        msg_lines = [
            f"*Torrent ({q} / {src} / {codec})*",
            f"size: *{size_readable}*",
            f"status: `{status}`",
            f"content-type: `{ctype}`",
            "",
            f"{torrent_url}"
        ]
        msg = "\n".join(msg_lines)
        await query.message.reply_text(msg, parse_mode="Markdown")

        # Optionally, after sending, remove the inline keyboard (edit the message)
        try:
            await query.edit_message_text("Torrent link sent. Use /start to search again.")
        except Exception:
            pass
        return

    # Unknown callback
    await query.message.reply_text("Unknown action.")


def main():
    if not BOT_TOKEN:
        print("Error: set TELEGRAM_BOT_TOKEN environment variable")
        return
    if not OMDB_KEY:
        print("Error: set OMDB_API_KEY environment variable")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
