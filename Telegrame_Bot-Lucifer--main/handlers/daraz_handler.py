import asyncio
import uuid
from telegram import Update, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.daraz_service import get_best_daraz_deal
from state import API_STATE
from utils.decorators import rate_limit
from utils.logger import get_logger
from utils.cache import daraz_cache, DARAZ_TTL

logger = get_logger(__name__)

FALLBACK_IMAGE = "https://img.drz.lazcdn.com/static/bd/p/0f6c48ebc244f392375eb83c498f8a61.png"
PAGE_SIZE = 5


def _build_media_group(products: list) -> list:
    """Builds a list of InputMediaPhoto from a slice of products."""
    media_group = []
    for p in products:
        raw_name = p.get('name', 'Unknown product')
        name = raw_name[:60] + ("..." if len(raw_name) > 60 else "")
        price = p.get('price', 'N/A')
        rating = p.get('rating', '0')
        url = p.get('url', '#')
        label = p.get('_label', '📦 Option')
        image_url = p.get('image', '') or FALLBACK_IMAGE

        caption_html = (
            f"<b>{label}</b>\n"
            f"📦 {name}\n"
            f"💰 {price}   |   ⭐ {rating}\n"
            f"🔗 <a href='{url}'>Open in Daraz</a>"
        )
        media_group.append(InputMediaPhoto(media=image_url, caption=caption_html, parse_mode="HTML"))
    return media_group


def _build_action_bar(session_id: str, page: int, has_more: bool) -> InlineKeyboardMarkup:
    """Builds the Action Bar below the album."""
    buttons = []
    if has_more:
        buttons.append([InlineKeyboardButton("🔄 More Options", callback_data=f"daraz:more:{session_id}:{page + 1}")])
    buttons.append([InlineKeyboardButton("🔍 Search Another Item", callback_data="result_action_deals_retry")])
    buttons.append([InlineKeyboardButton("🏠 Home", callback_data="back_to_start")])
    return InlineKeyboardMarkup(buttons)


@rate_limit(seconds=10)
async def find_deal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler for the /find command.
    Searches Daraz and sends a Media Group (Album) of the Top 5 curated items.
    """
    if not API_STATE.get("daraz", True):
        await update.message.reply_text("🛒 Daraz Assistant is currently disabled by Admin.")
        return
        
    if not context.args:
        await update.message.reply_text(
            "🛒 <b>Daraz Shopping Assistant</b>\n\n"
            "Usage: <code>/find &lt;product name&gt;</code>\n\n"
            "Example: <code>/find smart watch</code>\n"
            "💡 <i>Tip: Be specific for better results!</i>",
            parse_mode="HTML"
        )
        return

    query = " ".join(context.args)
    sent_message = await update.message.reply_text(
        f"🔍 <b>Lucifer:</b> Searching Daraz for '{query}'...",
        parse_mode="HTML"
    )
    
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, get_best_daraz_deal, query)

    await sent_message.edit_text(f"📊 <b>Lucifer:</b> Analyzing best options for '{query}'...", parse_mode="HTML")

    if not result.get("success"):
        await sent_message.edit_text(f"😔 Error: {result.get('error', 'Unknown error.')}")
        return

    all_products = result.get("data", [])
    if not all_products:
        await sent_message.edit_text(f"😔 No relevant products found for '{query}'.")
        return

    # Cache the full results list and the action bar message id for auto-delete later
    session_id = str(uuid.uuid4())[:8]
    daraz_cache.set(session_id, {"query": query, "results": all_products, "action_bar_ids": []}, DARAZ_TTL)

    page = 0
    page_products = all_products[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    has_more = len(all_products) > PAGE_SIZE

    await sent_message.edit_text(f"✅ <b>Lucifer:</b> Showing top {len(page_products)} deals for '{query}'...", parse_mode="HTML")

    try:
        media_group = _build_media_group(page_products)
        sent_album = await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media_group)
        await sent_message.delete()

        # Send the Action Bar and save its message ID
        action_bar_msg = await update.message.reply_text(
            f"🛒 Showing curated picks (Page {page + 1}). Swipe the photos to compare!",
            reply_markup=_build_action_bar(session_id, page, has_more)
        )

        # Store message IDs for auto-delete on "More Options"
        album_ids = [m.message_id for m in sent_album]
        session = daraz_cache.get(session_id)
        if session:
            session["action_bar_ids"] = [action_bar_msg.message_id]
            session["album_ids"] = album_ids
            daraz_cache.set(session_id, session, DARAZ_TTL)

    except Exception as e:
        logger.error(f"Error sending Daraz media group: {e}")
        await sent_message.edit_text("❌ Failed to display the products. Please try again later.")


async def daraz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the 'More Options' button.
    Deletes the previous album and action bar, then sends the next page.
    """
    query = update.callback_query
    await query.answer()

    parts = query.data.split(":")
    if len(parts) < 4:
        return

    _, action, session_id, page_str = parts
    try:
        page = int(page_str)
    except ValueError:
        page = 1

    session = daraz_cache.get(session_id)
    if not session or "results" not in session:
        await query.message.edit_text("⏳ Session expired. Please search again with /find.")
        return

    all_products = session["results"]
    chat_id = query.message.chat_id

    # Phase 3 Auto-Delete: delete previous album photos
    for msg_id in session.get("album_ids", []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    # Delete previous action bar message
    for msg_id in session.get("action_bar_ids", []):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass

    page_products = all_products[page * PAGE_SIZE:(page + 1) * PAGE_SIZE]
    if not page_products:
        await query.message.reply_text("🏁 No more options available for this search.")
        return

    has_more = len(all_products) > (page + 1) * PAGE_SIZE

    try:
        media_group = _build_media_group(page_products)
        sent_album = await context.bot.send_media_group(chat_id=chat_id, media=media_group)

        action_bar_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"🛒 Showing more options (Page {page + 1}). Swipe the photos to compare!",
            reply_markup=_build_action_bar(session_id, page, has_more)
        )

        # Update stored IDs for the next potential auto-delete
        session["album_ids"] = [m.message_id for m in sent_album]
        session["action_bar_ids"] = [action_bar_msg.message_id]
        daraz_cache.set(session_id, session, DARAZ_TTL)

    except Exception as e:
        logger.error(f"Error in daraz_callback more options: {e}")
        await context.bot.send_message(chat_id=chat_id, text="❌ Failed to load more options. Please try again.")
