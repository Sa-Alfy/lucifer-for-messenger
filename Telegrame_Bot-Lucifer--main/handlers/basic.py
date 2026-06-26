import asyncio
import os
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services.ai_chat import get_ai_response, get_ai_response_stream
from state import API_STATE, FEATURE_FLAGS, track_user, track_command
from utils.logger import get_logger
from utils.format import prepare_telegram_html, clean_markdown_fallback
from utils.ux import ux_card
from utils.constants import MAX_HISTORY, DEVELOPER_NAME, GITHUB_URL, ASSET_PROFILE_PICTURE
from utils.decorators import enforce_moderation
from handlers.intent import detect_intent
from handlers.reminder import handle_reminder_text

logger = get_logger(__name__)


# ── Categorized Start Menu Builder ───────────────────────────
def _build_start_menu(user_first_name: str):
    """
    New button-based Control Panel for Lucifer.
    Focuses on 5 main categories for a clean interaction flow.
    """
    welcome_text = (
        f"<b>Welcome to Lucifer Control Panel</b>\n"
        f"Hello {user_first_name}! How can I assist you today?\n"
    )

    keyboard = [
        [
            InlineKeyboardButton("💬 Chat AI", callback_data="nav_chat"),
            InlineKeyboardButton("🎨 Image Generation", callback_data="nav_image"),
        ],
        [
            InlineKeyboardButton("🛒 Deal Finder", callback_data="nav_deals"),
            InlineKeyboardButton("🛠️ Tools", callback_data="nav_tools"),
        ],
        [
            InlineKeyboardButton("⚙️ Settings", callback_data="nav_settings"),
        ],
        [
            InlineKeyboardButton("👨‍💻 Developer", callback_data="developer_info"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    return welcome_text, reply_markup


# ── Category Content Definitions ─────────────────────────────
NAV_CONTENT = {
    "nav_chat": {
        "title": "💬 <b>Chat AI</b>",
        "desc": "Intelligent AI chat powered by Groq & Gemini.\n\nType naturally to chat, or use specific tools below:",
        "buttons": [
            ("🎭 Switch Persona", "/persona"),
            ("💡 Explain (Reply)", "/explain"),
            ("📋 Summarize (Reply)", "/summarize"),
            ("🗑️ Clear History", "/clear"),
        ],
    },
    "nav_image": {
        "title": "🎨 <b>Image Generation</b>",
        "desc": "Transform your ideas into high-quality art.",
        "buttons": [
            ("✨ Create New Image", "/image "),
            ("🖼️ Sticker Maker", "/sticker "),
        ],
    },
    "nav_deals": {
        "title": "🛒 <b>Deal Finder</b>",
        "desc": "Find the best deals and offers in Bangladesh.",
        "buttons": [
            ("🛍️ Daraz Deals", "/find "),
            ("📱 Mobile Offers", "/offers"),
        ],
    },
    "nav_tools": {
        "title": "🛠️ <b>Tools & Utilities</b>",
        "desc": "Everyday utility tools for productivity.",
        "buttons": [
            ("🌤️ Weather", "/weather Dhaka"),
            ("💱 Currency", "/convert "),
            ("🕌 Prayer Times", "/prayer"),
            ("⏰ Reminders", "/myreminders"),
            ("🎙️ Text-to-Speech", "/say "),
        ],
    },
    "nav_settings": {
        "title": "⚙️ <b>Settings & Profile</b>",
        "desc": "Manage your preferences and view stats.",
        "buttons": [
            ("📊 My Profile", "/me"),
            ("🛡️ Moderation", "/help_moderation"),
        ],
    },
}

def get_home_button():
    """Returns a minimal inline keyboard with just a Home button to reduce clutter."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]
    ])

def get_image_buttons():
    """Returns the specific action buttons for Image Generation."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Retry", callback_data="result_action_image_retry"),
            InlineKeyboardButton("✍️ Edit Input", callback_data="result_action_image_edit")
        ],
        [InlineKeyboardButton("🏠 Home", callback_data="back_to_start")]
    ])



async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rich Welcome message with Branding Photo for Lucifer."""
    user = update.effective_user
    track_user(user.id)
    track_command("start")
    
    # Reset to HOME mode
    context.user_data["mode"] = "HOME"

    welcome_text, reply_markup = _build_start_menu(user.first_name)

    # Resolve character limit for photo captions (default is 1024)
    # Our welcome_text is well under that limit.
    
    photo_path = os.path.join(os.getcwd(), ASSET_PROFILE_PICTURE)
    
    if os.path.exists(photo_path):
        with open(photo_path, 'rb') as photo:
            await update.message.reply_photo(
                photo=photo,
                caption=welcome_text,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
    else:
        # Fallback to text only if the image is missing
        await update.message.reply_text(
            text=welcome_text,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )


@enforce_moderation()
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main message handler — routes input based on active User Mode."""
    
    # ── Step 0: Check Mode & Resolve Routing ──
    mode = context.user_data.get("mode", "HOME")
    user_text = update.message.caption if update.message.photo else update.message.text
    
    # If in a specific mode, some text inputs should trigger specific handlers
    if mode == "IMAGE_GEN" and user_text and not user_text.startswith("/"):
        from handlers.image_gen import generate_image_command
        context.args = user_text.split()
        return await generate_image_command(update, context)
        
    if mode == "SEARCH" and user_text and not user_text.startswith("/"):
        from handlers.daraz_handler import find_deal_command
        context.args = user_text.split()
        return await find_deal_command(update, context)

    # ── Step 0.1: Check if user is in reminder text input mode ──
    if update.message.text and await handle_reminder_text(update, context):
        return

    if not API_STATE.get("groq", True):
        await update.message.reply_text(
            "🤖 Groq AI Chat is currently disabled by the Admin. Please try again later."
        )
        return

    if not FEATURE_FLAGS.get("ai_chat", True):
        await update.message.reply_text(
            "💬 AI Chat is currently disabled by the Admin. Please try again later."
        )
        return

    track_command("ai_chat")

    image_bytes = None
    if update.message.photo:
        photo = update.message.photo[-1]
        photo_file = await context.bot.get_file(photo.file_id)
        image_bytes = await photo_file.download_as_bytearray()

    user_text = update.message.caption if update.message.photo else update.message.text

    if not user_text and image_bytes:
        user_text = "Please analyze this image."

    # ── Group Chat Handling ──
    is_group = update.effective_chat.type in ["group", "supergroup"]
    if is_group:
        bot_username = context.bot.username
        is_reply_to_bot = (
            update.message.reply_to_message 
            and update.message.reply_to_message.from_user.id == context.bot.id
        )
        is_mentioned = user_text and f"@{bot_username}" in user_text

        # If it's a group and we aren't mentioned or replied to, ignore it so we don't spam
        if not (is_reply_to_bot or is_mentioned):
            return
        
        # Clean up the mention from the text so the AI doesn't get confused
        if is_mentioned:
            user_text = user_text.replace(f"@{bot_username}", "").strip()
            if not user_text and not image_bytes:
                user_text = "Hello!"

    # ── Step 1: Natural Language Intent Detection ──
    # Only for text messages (not images), try to match known intents
    if user_text and not image_bytes:
        intent, intent_args = detect_intent(user_text)
        if intent:
            await _dispatch_intent(update, context, intent, intent_args)
            return

    # Typing indicator
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    # Get chat history and persona/game state
    chat_history = context.user_data.get("chat_history", [])
    persona = context.user_data.get("persona", "default")
    active_game = context.user_data.get("active_game")
    
    point_awarded_this_turn = False

    # ── IMAGE PATH: Non-streaming (Vision doesn't support streaming) ──
    if image_bytes:
        sent_message = await update.message.reply_text("🤔 Analyzing image...")
        response = await get_ai_response(
            user_text,
            image_bytes=image_bytes,
            chat_history=chat_history[-MAX_HISTORY:],
            persona=persona,
            game_mode=active_game,
        )
        
        # Point checking for non-streaming (image vision usually won't trigger games, but safe to check)
        if "[POINT_AWARDED]" in response:
            point_awarded_this_turn = True
            response = response.replace("[POINT_AWARDED]", "").strip()
            
        display_text = response
        if point_awarded_this_turn:
            display_text += "\n\n🎉 <b>You earned a point!</b>"
            
        try:
            await sent_message.edit_text(prepare_telegram_html(display_text), parse_mode="HTML")
        except Exception:
            try:
                await sent_message.edit_text(clean_markdown_fallback(display_text))
            except Exception:
                pass
    else:
        # ── TEXT PATH: Streaming response ──
        sent_message = await update.message.reply_text("🤔 Thinking...")
        
        accumulated = ""
        current_offset = 0
        last_edit = ""
        last_update_time = time.time()

        try:
            async for chunk in get_ai_response_stream(
                user_text,
                chat_history=chat_history[-MAX_HISTORY:],
                persona=persona,
                game_mode=active_game,
            ):
                accumulated += chunk
                
                # Check for hidden points
                if "[POINT_AWARDED]" in accumulated and not point_awarded_this_turn:
                    point_awarded_this_turn = True
                    # Initialize points if missing
                    context.user_data["game_points"] = context.user_data.get("game_points", 0) + 1

                # Paginate if the text exceeds Telegram's 4096 limit
                current_segment = accumulated[current_offset:]
                if len(current_segment) > 4000:
                    # Finalize the current message
                    last_space = current_segment.rfind(' ')
                    if last_space == -1: 
                        last_space = 4000
                        
                    final_segment = current_segment[:last_space].replace("[POINT_AWARDED]", "").strip()
                    try:
                        await sent_message.edit_text(prepare_telegram_html(final_segment), parse_mode="HTML")
                    except Exception:
                        try:
                            await sent_message.edit_text(clean_markdown_fallback(final_segment))
                        except Exception:
                            pass
                            
                    # Create a new overflow message
                    current_offset += last_space
                    current_segment = accumulated[current_offset:]
                    sent_message = await update.message.reply_text("...")
                    last_edit = ""
                    last_update_time = time.time()

                # Time-based update to perfectly dodge Telegram rate limits (approx 1 update per 0.5s-1s)
                current_time = time.time()
                if (current_time - last_update_time) > 0.8 and current_segment != last_edit:
                    display_text = current_segment.replace("[POINT_AWARDED]", "").strip()
                    if point_awarded_this_turn and current_offset == 0:  # Only show point popup if on first paginated chunk
                        display_text += "\n\n🎉 <b>You earned a point!</b>"

                    try:
                        last_edit = current_segment
                        last_update_time = current_time
                        await sent_message.edit_text(display_text + " ▌")
                    except Exception as e:
                        # Log but do not crash. If it's 400 Message is not modified, it's safe to ignore.
                        if "not modified" not in str(e).lower():
                            logger.error(f"Stream edit error: {e}")

            # Final edit with complete response (remove cursor)
            if accumulated:
                response = accumulated
                final_segment = accumulated[current_offset:]
                display_text = final_segment.replace("[POINT_AWARDED]", "").strip()
                if point_awarded_this_turn and current_offset == 0:
                    display_text += f"\n\n🎉 <b>You earned a point!</b> (Total Points: {context.user_data.get('game_points', 0)})"
            else:
                response = "🤔 I couldn't generate a response. Please try again."
                display_text = response

            try:
                # Wrap AI response in a UX Card
                card_text = ux_card(prepare_telegram_html(display_text))
                await sent_message.edit_text(
                    card_text, 
                    parse_mode="HTML",
                    reply_markup=get_home_button()
                )
            except Exception:
                try:
                    await sent_message.edit_text(
                        clean_markdown_fallback(display_text),
                        reply_markup=get_home_button()
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            response = f"🔧 Error: {str(e)}"
            await sent_message.edit_text(response)

    # Update conversation memory ONLY if it wasn't an API crash
    if not response.startswith("🔧 Error:") and not response.startswith("❌ All Chat models are currently down") and "Request too large" not in response:
        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": response})
        context.user_data["chat_history"] = chat_history[-MAX_HISTORY:]


async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clear the user's conversation history."""
    context.user_data.pop("chat_history", None)
    context.user_data.pop("quiz_score", None)
    context.user_data.pop("quiz_total", None)
    track_command("clear")

    await update.message.reply_text(
        "🗑️ Conversation history cleared!\n\n"
        "I've forgotten our previous chat. Start fresh! 🚀"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help button clicks from the inline keyboard."""
    query = update.callback_query
    await query.answer()

HELP_CONTENT = {
    "help_main": {
        "title": "📖 <b>Help Directory</b>",
        "desc": "Select a topic below to learn more about my features:",
        "buttons": [
            ("🤖 AI & Chat", "help_ai"),
            ("🎨 Images & Art", "help_image"),
            ("🛒 Shopping & Deals", "help_deals"),
            ("🛠️ Utilities & Tools", "help_tools"),
        ]
    },
    "help_ai": {
        "title": "🤖 <b>AI & Chat Help</b>",
        "desc": "I am powered by advanced LLMs (Groq & Gemini).\n\n"
                "• <b>Natural Chat:</b> Just type! I remember our context.\n"
                "• <code>/persona</code>: Switch my personality (e.g., Toxic, Friendly).\n"
                "• <code>/clear</code>: Reset our conversation memory.\n"
                "• <b>Replies:</b> Reply to any message with <code>/explain</code> or <code>/summarize</code>.",
    },
    "help_image": {
        "title": "🎨 <b>Images & Art Help</b>",
        "desc": "Create stunning visuals directly in chat.\n\n"
                "• <code>/image &lt;prompt&gt;</code>: Generate AI art.\n"
                "• <code>/sticker</code>: Reply to an image to convert it to a sticker.\n"
                "• <b>OCR:</b> Reply to an image with <code>/ocr</code> to extract text.",
    },
    "help_deals": {
        "title": "🛒 <b>Shopping & Deals Help</b>",
        "desc": "Find the best offers in Bangladesh.\n\n"
                "• <code>/find &lt;product&gt;</code>: Search Daraz for the best deals.\n"
                "• <code>/offers</code>: View latest mobile recharge & data offers.",
    },
    "help_tools": {
        "title": "🛠️ <b>Utilities & Tools Help</b>",
        "desc": "Useful everyday productivity features.\n\n"
                "• <code>/weather &lt;city&gt;</code>: Get live weather updates.\n"
                "• <code>/remind &lt;time&gt; &lt;task&gt;</code>: Set smart reminders.\n"
                "• <code>/convert</code>: Real-time currency exchange rates.\n"
                "• <code>/say</code>: Convert text to voice (TTS).",
    },
}

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help navigation and topic selection."""
    query = update.callback_query
    await query.answer()

    topic_key = query.data
    content = HELP_CONTENT.get(topic_key)

    if not content:
        # Fallback for older or unknown help keys
        topic_key = "help_main"
        content = HELP_CONTENT[topic_key]

    text = f"{content['title']}\n\n{content['desc']}"
    
    keyboard = []
    if "buttons" in content:
        # We are on the main help menu
        for label, data in content["buttons"]:
            keyboard.append([InlineKeyboardButton(label, callback_data=data)])
        keyboard.append([InlineKeyboardButton("🔙 Back to Home", callback_data="back_to_start")])
    else:
        # We are on a specific topic page
        keyboard.append([InlineKeyboardButton("🔙 Back to Help Menu", callback_data="help_main")])
        keyboard.append([InlineKeyboardButton("🏠 Home", callback_data="back_to_start")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if query.message.photo:
        await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")


async def nav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle category navigation button clicks from the Control Panel."""
    query = update.callback_query
    await query.answer()

    nav_key = query.data  # e.g. "nav_chat"
    
    # Map navigation keys to Modes
    mode_map = {
        "nav_chat": "AI_CHAT",
        "nav_image": "IMAGE_GEN",
        "nav_deals": "SEARCH",
        "nav_tools": "TOOLS",
        "nav_settings": "HOME"
    }
    context.user_data["mode"] = mode_map.get(nav_key, "HOME")

    content = NAV_CONTENT.get(nav_key)

    if not content:
        await query.edit_message_text("❌ Navigation error.")
        return

    text = f"{content['title']}\n\n{content['desc']}"

    keyboard = []
    for label, cmd in content["buttons"]:
        keyboard.append([InlineKeyboardButton(label, switch_inline_query_current_chat=cmd)])

    keyboard.append([
        InlineKeyboardButton("🔙 Back to Home", callback_data="back_to_start")
    ])
    reply_markup = InlineKeyboardMarkup(keyboard)

    if query.message.photo:
        await query.message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")


async def back_to_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle 'Back to Home' — edits existing message to return to control panel.
    Ensures zero flickering by avoiding delete/resend.
    """
    query = update.callback_query
    await query.answer()

    # Reset to HOME mode
    context.user_data["mode"] = "HOME"

    user = update.effective_user
    welcome_text, reply_markup = _build_start_menu(user.first_name)
    
    if query.message.photo:
        await query.message.edit_caption(
            caption=welcome_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    else:
        # If we somehow lost the photo context, we just edit text. 
        # But in Phase 1, we start with a photo so this is a fallback.
        await query.edit_message_text(
            text=welcome_text,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )

async def developer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show developer info and GitHub link."""
    query = update.callback_query
    await query.answer()
    
    dev_text = (
        f"👨‍💻 <b>Developer Profile</b>\n\n"
        f"<b>Name:</b> {DEVELOPER_NAME}\n"
        f"<b>Role:</b> Lead Architect & Developer\n\n"
        "Thank you for using Lucifer! This project is a labor of love dedicated to building "
        "the most intelligent and accessible AI companion for everyone.\n\n"
        "🚀 <b>Open Source:</b>\n"
        "Support the development by checking out the source code on GitHub. "
        "Leave a star if you like this project! ⭐\n\n"
        f"🔗 <a href='{GITHUB_URL}'>Visit Shariar's GitHub Profile</a>"
    )
    
    keyboard = [
        [InlineKeyboardButton("⭐ Follow on GitHub", url=GITHUB_URL)],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Developers like a clean UI, so we edit the text (or caption if it's a photo)
    if query.message.photo:
        await query.message.edit_caption(caption=dev_text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await query.edit_message_text(text=dev_text, reply_markup=reply_markup, parse_mode="HTML")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback help command — dispatches the interactive help menu."""
    user = update.effective_user
    welcome_text, reply_markup = _build_start_menu(user.first_name)
    
    # We send the start menu but could also jump directly to help_main if desired.
    # For now, let's keep it simple to fix the build.
    await update.message.reply_text(
        "📖 <b>Lucifer Help Menu</b>\nUse /start to explore all features or pick a topic below:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📖 Open Help Directory", callback_data="help_main")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="back_to_start")]
        ]),
        parse_mode="HTML"
    )

async def result_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle standardized result buttons (Retry, Edit, etc.)."""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "result_action_image_retry":
        prompt = context.user_data.get("last_image_prompt")
        if not prompt:
            await query.message.reply_text("I forgot what your last prompt was. Please type it again.")
            return
            
        await query.message.reply_text(f"Retrying image generation for: {prompt}")
        from handlers.image_gen import generate_image_command
        # Trigger the image generation with the saved prompt
        context.args = prompt.split()
        await generate_image_command(update, context)
        
    elif action == "result_action_image_edit":
        # Entering Image Gen mode automatically prompts for a new input
        context.user_data["mode"] = "IMAGE_GEN"
        await query.message.reply_text(
            "🎨 <b>Image Editor Mode</b>\n\n"
            "Please type your new image prompt below:",
            parse_mode="HTML",
            reply_markup=get_home_button()
        )
        
    elif action == "result_action_deals_retry":
        context.user_data["mode"] = "SEARCH"
        await query.message.reply_text(
            "🛒 <b>Daraz Shopping Mode</b>\n\n"
            "What would you like to search for today?",
            parse_mode="HTML",
            reply_markup=get_home_button()
        )
        
    else:
        # Fallback acknowledgment
        await query.message.reply_text("Action registered.")


# ── Intent Dispatcher ────────────────────────────────────────
async def _dispatch_intent(update: Update, context: ContextTypes.DEFAULT_TYPE, intent: str, args: str):
    """Dispatch a detected intent to the appropriate handler."""
    # Import handlers lazily to avoid circular imports
    from handlers.weather import weather_command
    from handlers.currency import convert_command, bdt_command
    from handlers.news import news_command
    from handlers.reminder import remind_command
    from handlers.prayer import prayer_command
    from handlers.mobile import mobile_command
    from handlers.vote import vote_command

    # Simulate context.args from extracted intent args
    context.args = args.split() if args else []

    intent_map = {
        "weather": weather_command,
        "weather_no_args": weather_command,
        "bdt_rate": bdt_command,
        "convert": convert_command,
        "news": news_command,
        "reminder": remind_command,
        "prayer": prayer_command,
        "mobile_offer": mobile_command,
        "vote": vote_command,
    }

    handler = intent_map.get(intent)
    if handler:
        await handler(update, context)
    else:
        logger.warning(f"Intent '{intent}' matched but no handler mapped.")