from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from utils.admin_guard import is_admin
from state import MODERATION_STATE, FEATURE_FLAGS, save_state

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point for the admin panel."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ <b>Access Denied:</b> You are not authorized.", parse_mode="HTML")
        return

    # Store target user if replied
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        context.user_data["admin_target"] = {
            "id": target_user.id,
            "name": target_user.first_name
        }

    keyboard = [
        [InlineKeyboardButton("👥 User Controls", callback_data="admin_user_controls")],
        [InlineKeyboardButton("🧠 Feature Controls", callback_data="admin_feature_controls")],
        [InlineKeyboardButton("🛡 Moderation", callback_data="admin_moderation")],
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("⚡ System Tools", callback_data="admin_system_tools")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    target_text = ""
    if context.user_data.get("admin_target"):
        target_text = f"\n🎯 Target User: <code>{context.user_data['admin_target']['name']}</code> (<code>{context.user_data['admin_target']['id']}</code>)"

    await update.message.reply_text(
        f"⚙️ <b>Admin Panel</b>{target_text}\nSelect a configuration category below:",
        reply_markup=reply_markup,
        parse_mode="HTML"
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles callbacks for the admin panel and updates UI in-place."""
    query = update.callback_query
    await query.answer()
    
    if not is_admin(update.effective_user.id):
        await query.edit_message_text("⛔ <b>Access Denied:</b> You are not authorized.", parse_mode="HTML")
        return

    data = query.data

    target_user = context.user_data.get("admin_target")
    target_text = f"\n🎯 Target: <code>{target_user['name']}</code>" if target_user else "\n⚠️ No target selected (Reply to a user with /admin first)"

    if data == "admin_main":
        keyboard = [
            [InlineKeyboardButton("👥 User Controls", callback_data="admin_user_controls")],
            [InlineKeyboardButton("🧠 Feature Controls", callback_data="admin_feature_controls")],
            [InlineKeyboardButton("🛡 Moderation", callback_data="admin_moderation")],
            [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("⚡ System Tools", callback_data="admin_system_tools")]
        ]
        text = f"⚙️ <b>Admin Panel</b>\nSelect a configuration category below:"
        if target_user:
             text = f"⚙️ <b>Admin Panel</b>\n🎯 Target: <code>{target_user['name']}</code>\nSelect a configuration category below:"
        reply_markup = InlineKeyboardMarkup(keyboard)

    elif data == "admin_user_controls":
        keyboard = [
            [InlineKeyboardButton("🚫 Block User", callback_data="admin_act_block")],
            [InlineKeyboardButton("✅ Unblock User", callback_data="admin_act_unblock")],
            [InlineKeyboardButton("♻ Reset Cooldown", callback_data="admin_act_reset")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = f"👥 <b>User Controls</b>{target_text}\nSelect an action:"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    elif data.startswith("admin_act_"):
        action = data.split("_")[2] # block, unblock, reset
        if not target_user:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_user_controls")]]
            text = "❌ You must reply to a user's message with <code>/admin</code> first to select a target."
            reply_markup = InlineKeyboardMarkup(keyboard)
        else:
            # Confirmation Step
            keyboard = [
                [
                    InlineKeyboardButton("✅ Yes", callback_data=f"admin_confirm_{action}"),
                    InlineKeyboardButton("❌ No", callback_data="admin_user_controls")
                ]
            ]
            text = f"❓ Are you sure you want to <b>{action.upper()}</b> <code>{target_user['name']}</code>?"
            reply_markup = InlineKeyboardMarkup(keyboard)

    elif data.startswith("admin_confirm_"):
        action = data.split("_")[2]
        if not target_user:
            return
            
        tid = target_user["id"]
        if action == "block":
            MODERATION_STATE["blocked_users"].add(tid)
            save_state()
            text = f"✅ <code>{target_user['name']}</code> has been blocked."
        elif action == "unblock":
            if tid in MODERATION_STATE["blocked_users"]:
                MODERATION_STATE["blocked_users"].remove(tid)
                save_state()
            text = f"✅ <code>{target_user['name']}</code> has been unblocked."
        elif action == "reset":
            if tid in context.application.user_data:
                target_data = context.application.user_data[tid]
                keys_to_delete = [
                    k for k in target_data.keys() 
                    if k.startswith("_cooldown_") or k.startswith("_adaptive_")
                ]
                for k in keys_to_delete:
                    del target_data[k]
            text = f"✅ Cooldowns reset for <code>{target_user['name']}</code>."
            
        keyboard = [[InlineKeyboardButton("🔙 Back to Users", callback_data="admin_user_controls")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    elif data == "admin_feature_controls":
        keyboard = [
            [InlineKeyboardButton(f"🤖 AI Chat [{'✅' if FEATURE_FLAGS.get('ai_chat', True) else '❌'}]", callback_data="admin_toggle_ai_chat")],
            [InlineKeyboardButton(f"🎨 Image Gen [{'✅' if FEATURE_FLAGS.get('image_gen', True) else '❌'}]", callback_data="admin_toggle_image_gen")],
            [InlineKeyboardButton(f"📥 Downloader [{'✅' if FEATURE_FLAGS.get('downloader', True) else '❌'}]", callback_data="admin_toggle_downloader")],
            [InlineKeyboardButton(f"📰 News [{'✅' if FEATURE_FLAGS.get('news', True) else '❌'}]", callback_data="admin_toggle_news")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = "🧠 <b>Feature Controls</b>\n\nClick a feature to toggle it ON/OFF:"
        reply_markup = InlineKeyboardMarkup(keyboard)

    elif data.startswith("admin_toggle_"):
        feature = data.split("_", 2)[2] # ai_chat, downloader, news
        
        # If feature is somehow not in flags, default to True just in case
        if feature not in FEATURE_FLAGS:
            FEATURE_FLAGS[feature] = True
            
        FEATURE_FLAGS[feature] = not FEATURE_FLAGS[feature]
        save_state()
        
        # Regenerate the keyboard
        keyboard = [
            [InlineKeyboardButton(f"🤖 AI Chat [{'✅' if FEATURE_FLAGS.get('ai_chat', True) else '❌'}]", callback_data="admin_toggle_ai_chat")],
            [InlineKeyboardButton(f"🎨 Image Gen [{'✅' if FEATURE_FLAGS.get('image_gen', True) else '❌'}]", callback_data="admin_toggle_image_gen")],
            [InlineKeyboardButton(f"📥 Downloader [{'✅' if FEATURE_FLAGS.get('downloader', True) else '❌'}]", callback_data="admin_toggle_downloader")],
            [InlineKeyboardButton(f"📰 News [{'✅' if FEATURE_FLAGS.get('news', True) else '❌'}]", callback_data="admin_toggle_news")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = f"🧠 <b>Feature Controls</b>\n\nToggled <code>{feature}</code> to {'✅ ON' if FEATURE_FLAGS[feature] else '❌ OFF'}."
        reply_markup = InlineKeyboardMarkup(keyboard)

    elif data == "admin_moderation":
        keyboard = [
            [InlineKeyboardButton(f"🔇 Quiet Mode [{'✅' if MODERATION_STATE['quiet_mode'] else '❌'}]", callback_data="admin_mod_quiet_mode")],
            [InlineKeyboardButton(f"🚫 Anti-Spam [{'✅' if MODERATION_STATE['anti_spam'] else '❌'}]", callback_data="admin_mod_anti_spam")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = "🛡 <b>Moderation Limits</b>\n\nToggle global moderation settings:"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    elif data.startswith("admin_mod_"):
        mod_type = data[10:] # quiet_mode or anti_spam
        if mod_type in MODERATION_STATE:
            MODERATION_STATE[mod_type] = not MODERATION_STATE[mod_type]
            save_state()
            
        keyboard = [
            [InlineKeyboardButton(f"🔇 Quiet Mode [{'✅' if MODERATION_STATE['quiet_mode'] else '❌'}]", callback_data="admin_mod_quiet_mode")],
            [InlineKeyboardButton(f"🚫 Anti-Spam [{'✅' if MODERATION_STATE['anti_spam'] else '❌'}]", callback_data="admin_mod_anti_spam")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = f"🛡 <b>Moderation Limits</b>\n\nToggled <code>{mod_type}</code> to {'✅ ON' if MODERATION_STATE[mod_type] else '❌ OFF'}."
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    elif data == "admin_stats":
        stats = context.bot_data.get("global_stats", "No data")
        from state import get_stats_summary # We can fetch real stats
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]]
        text = f"📊 <b>Stats</b>\n\n{get_stats_summary()}"
        reply_markup = InlineKeyboardMarkup(keyboard)

    elif data == "admin_system_tools":
        keyboard = [
            [InlineKeyboardButton("🧹 Clear Cache", callback_data="admin_sys_clear_cache")],
            [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
        ]
        text = "⚡ <b>System Tools</b>\n\nSelect a system action:"
        reply_markup = InlineKeyboardMarkup(keyboard)
        
    elif data == "admin_sys_clear_cache":
        count = len(context.application.user_data)
        context.application.user_data.clear()
        text = f"✅ Cleared session cache for all {count} users."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_system_tools")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

    else:
        return

    try:
        if query.message.text != text or query.message.reply_markup != reply_markup:
            await query.edit_message_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode="HTML"
            )
    except Exception as e:
        # Ignore "Message is not modified" error
        pass

