# bot.py
import asyncio
import logging
from typing import List, Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from config import cfg
import omdb_client
import checker_client
from utils import pretty_bytes

# basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("telegram-bot")

MAX_RESULTS = cfg.MAX_RESULTS


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🎬 Movies", callback_data="MENU_MOVIES")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Welcome! Click *Movies* to start movie search flow, then send a movie name.",
        reply_markup=reply_markup,
        parse_mode="Markdown",
    )
    context.user_data.pop("awaiting_movie", None)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    if not context.user_data.get("awaiting_movie"):
        await update.message.reply_text("Please click the *Movies* button from the menu first. Use /start to open the menu.", parse_mode="Markdown")
        return

    query_text = update.message.text.strip()
    progress = await update.message.reply_text(f"🔎 Searching OMDb for `{query_text}`", parse_mode="MarkdownV2")

    # Call blocking omdb_search in a thread
    data = await asyncio.to_thread(omdb_client.omdb_search, query_text)
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

    # Prepare payload and call checker in thread
    payload = {"items": [{"imdbID": it.get("imdbID", ""), "title": it.get("Title", ""), "year": it.get("Year", "")} for it in results]}
    checker_resp = await asyncio.to_thread(checker_client.post_to_checker, payload)
    checker_results = (checker_resp or {}).get("results", {})

    # build result keyboard
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

    context.user_data["checker_results"] = checker_results
    context.user_data.pop("awaiting_movie", None)
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

    if data == "CANCEL":
        try:
            await query.edit_message_text("Cancelled.")
        except Exception:
            await query.message.reply_text("Cancelled.")
        return

    if data == "MENU_MOVIES":
        context.user_data["awaiting_movie"] = True
        try:
            await query.edit_message_text("🎬 Movie mode activated. Now send me the movie name (e.g. `Inception`) and I'll search OMDb.", parse_mode="Markdown")
        except Exception:
            await query.message.reply_text("🎬 Movie mode activated. Now send me the movie name and I'll search OMDb.")
        return

    if data.startswith("IMDB_"):
        imdbid = data.split("_", 1)[1]
        # fetch OMDb details in thread
        movie = await asyncio.to_thread(omdb_client.omdb_get_by_id, imdbid)
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

        checker_results = context.user_data.get("checker_results", {}) or {}
        chk = checker_results.get(imdbid, {}) or {}
        torrents = chk.get("torrents", []) if chk else []

        if not torrents:
            await query.message.reply_text("No torrent links found on configured sites.")
            return

        torrent_map = context.user_data.setdefault("torrent_map", {})

        t_keyboard = []
        for idx, t in enumerate(torrents):
            q = t.get("quality", "unknown")
            src = t.get("source", "unknown")
            codec = t.get("codec", "unknown")
            validation = t.get("validation", {}) or {}
            clen = validation.get("content_length") or validation.get("Content-Length") or validation.get("content-length")
            size_readable = pretty_bytes(clen)
            label = f"{q} / {src} / {codec} — {size_readable}"
            cbid = f"TORR_{imdbid}_{idx}"
            torrent_url = (validation.get("final_url") or t.get("torrent_url"))
            torrent_map[cbid] = {
                "url": torrent_url,
                "meta": {"quality": q, "source": src, "codec": codec},
                "validation": validation,
            }
            if len(label) > 64:
                label = label[:61] + "."
            t_keyboard.append([InlineKeyboardButton(label, callback_data=cbid)])

        t_keyboard.append([InlineKeyboardButton("Cancel", callback_data="CANCEL")])
        t_markup = InlineKeyboardMarkup(t_keyboard)
        await query.message.reply_text("Select torrent variant to get link:", reply_markup=t_markup)
        return

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

        try:
            await query.edit_message_text("Torrent link sent. Use /start to search again.")
        except Exception:
            pass
        return

    await query.message.reply_text("Unknown action.")


def main():
    if not cfg.TELEGRAM_BOT_TOKEN:
        print("Error: set TELEGRAM_BOT_TOKEN environment variable")
        return
    if not cfg.OMDB_API_KEY:
        print("Error: set OMDB_API_KEY environment variable")
        return

    app = ApplicationBuilder().token(cfg.TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Bot started.")
    app.run_polling()


if __name__ == "__main__":
    main()
