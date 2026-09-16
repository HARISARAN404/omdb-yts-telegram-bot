"""Telegram bot: search OMDb, then list torrent variants found by the YTS checker service."""

import logging
from contextlib import suppress
from html import escape

import httpx
from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import checker_client
import omdb_client
from config import cfg
from utils import pretty_bytes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # don't log every poll URL (it contains the bot token)
logger = logging.getLogger("telegram-bot")

CANCEL_ROW = [InlineKeyboardButton("Cancel", callback_data="CANCEL")]


def http(context: ContextTypes.DEFAULT_TYPE) -> httpx.AsyncClient:
    return context.application.bot_data["http"]


async def safe_delete(message: Message) -> None:
    with suppress(TelegramError):
        await message.delete()


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎬 Movies", callback_data="MENU_MOVIES")]])
    await update.message.reply_text(
        "Welcome! Click <b>Movies</b> to start movie search flow, then send a movie name.",
        reply_markup=keyboard,
        parse_mode=ParseMode.HTML,
    )
    context.user_data.pop("awaiting_movie", None)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    if not context.user_data.get("awaiting_movie"):
        await update.message.reply_text(
            "Please click the <b>Movies</b> button from the menu first. Use /start to open the menu.",
            parse_mode=ParseMode.HTML,
        )
        return

    query_text = update.message.text.strip()
    progress = await update.message.reply_text(
        f"🔎 Searching OMDb for <code>{escape(query_text)}</code>", parse_mode=ParseMode.HTML
    )
    try:
        data = await omdb_client.omdb_search(http(context), query_text)
        if not data or data.get("Response", "False") == "False":
            await update.message.reply_text("No results or error from OMDb.")
            return

        results = data.get("Search", [])[: cfg.MAX_RESULTS]
        if not results:
            await update.message.reply_text("No results returned.")
            return

        payload = {
            "items": [
                {"imdbID": it.get("imdbID", ""), "title": it.get("Title", ""), "year": it.get("Year", "")}
                for it in results
            ]
        }
        checker_resp = await checker_client.post_to_checker(http(context), payload)
        checker_results = (checker_resp or {}).get("results", {})

        keyboard = []
        for it in results:
            imdbid = it.get("imdbID", "")
            torrents = (checker_results.get(imdbid) or {}).get("torrents", [])
            label = f"{it.get('Title', '')} ({it.get('Year', '')})"
            if torrents:
                label += f" ✅[{len(torrents)}]"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"IMDB_{imdbid}")])
        keyboard.append(CANCEL_ROW)

        await update.message.reply_text(
            "Select a result (shows number of torrent variants found):",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        context.user_data["checker_results"] = checker_results
        context.user_data.pop("awaiting_movie", None)
    finally:
        await safe_delete(progress)


async def on_cancel(query: CallbackQuery) -> None:
    try:
        await query.edit_message_text("Cancelled.")
    except TelegramError:
        await query.message.reply_text("Cancelled.")


async def on_menu_movies(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["awaiting_movie"] = True
    try:
        await query.edit_message_text(
            "🎬 Movie mode activated. Now send me the movie name (e.g. <code>Inception</code>) and I'll search OMDb.",
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        await query.message.reply_text("🎬 Movie mode activated. Now send me the movie name and I'll search OMDb.")


async def on_movie_selected(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, imdbid: str) -> None:
    movie = await omdb_client.omdb_get_by_id(http(context), imdbid)
    if not movie:
        await query.message.reply_text("Failed to fetch movie details from OMDb.")
        return

    title = escape(movie.get("Title", "N/A"))
    year = escape(movie.get("Year", "N/A"))
    plot = escape(movie.get("Plot", "N/A"))
    poster = movie.get("Poster", "")

    with suppress(TelegramError):
        await query.edit_message_text(f"Selected: <b>{title}</b> ({year})", parse_mode=ParseMode.HTML)

    detail_text = f"<b>{title}</b> ({year})\n\n<b>Plot:</b> {plot}\n"
    try:
        if not poster or poster == "N/A":
            raise TelegramError("no poster")
        await query.message.reply_photo(photo=poster, caption=detail_text, parse_mode=ParseMode.HTML)
    except TelegramError:
        await query.message.reply_text(detail_text, parse_mode=ParseMode.HTML)

    checker_results = context.user_data.get("checker_results") or {}
    torrents = (checker_results.get(imdbid) or {}).get("torrents", [])
    if not torrents:
        await query.message.reply_text("No torrent links found on configured sites.")
        return

    torrent_map = context.user_data.setdefault("torrent_map", {})
    keyboard = []
    for idx, t in enumerate(torrents):
        q = t.get("quality", "unknown")
        src = t.get("source", "unknown")
        codec = t.get("codec", "unknown")
        validation = t.get("validation") or {}
        cbid = f"TORR_{imdbid}_{idx}"
        torrent_map[cbid] = {
            "url": validation.get("final_url") or t.get("torrent_url"),
            "meta": {"quality": q, "source": src, "codec": codec},
            "validation": validation,
        }
        label = f"{q} / {src} / {codec} — {pretty_bytes(validation.get('content_length'))}"
        if len(label) > 64:
            label = label[:61] + "."
        keyboard.append([InlineKeyboardButton(label, callback_data=cbid)])
    keyboard.append(CANCEL_ROW)

    await query.message.reply_text("Select torrent variant to get link:", reply_markup=InlineKeyboardMarkup(keyboard))


async def on_torrent_selected(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE, cbid: str) -> None:
    entry = context.user_data.get("torrent_map", {}).get(cbid)
    if not entry:
        await query.message.reply_text("Sorry — torrent entry not found (it may have expired). Try searching again.")
        return

    meta = entry.get("meta", {})
    validation = entry.get("validation") or {}
    variant = " / ".join(escape(meta.get(k, "unknown")) for k in ("quality", "source", "codec"))
    msg = "\n".join(
        [
            f"<b>Torrent ({variant})</b>",
            f"size: <b>{pretty_bytes(validation.get('content_length'))}</b>",
            f"status: <code>{escape(str(validation.get('status') or 'unknown'))}</code>",
            f"content-type: <code>{escape(validation.get('content_type') or 'unknown')}</code>",
            "",
            escape(entry.get("url") or ""),
        ]
    )
    await query.message.reply_text(msg, parse_mode=ParseMode.HTML)

    with suppress(TelegramError):
        await query.edit_message_text("Torrent link sent. Use /start to search again.")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()
    data = query.data or ""

    if data == "CANCEL":
        await on_cancel(query)
    elif data == "MENU_MOVIES":
        await on_menu_movies(query, context)
    elif data.startswith("IMDB_"):
        await on_movie_selected(query, context, data.removeprefix("IMDB_"))
    elif data.startswith("TORR_"):
        await on_torrent_selected(query, context, data)
    else:
        await query.message.reply_text("Unknown action.")


async def post_init(app: Application) -> None:
    # One pooled HTTP client shared by all handlers (OMDb + checker calls).
    app.bot_data["http"] = httpx.AsyncClient(follow_redirects=True)


async def post_shutdown(app: Application) -> None:
    if client := app.bot_data.pop("http", None):
        await client.aclose()


def main() -> None:
    missing = [name for name in ("TELEGRAM_BOT_TOKEN", "OMDB_API_KEY") if not getattr(cfg, name)]
    if missing:
        raise SystemExit(f"Error: set {', '.join(missing)} environment variable(s)")

    app = ApplicationBuilder().token(cfg.TELEGRAM_BOT_TOKEN).post_init(post_init).post_shutdown(post_shutdown).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(callback_handler))

    logger.info("Bot started.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
