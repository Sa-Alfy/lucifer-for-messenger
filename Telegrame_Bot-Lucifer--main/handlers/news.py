import re
from telegram import Update
from telegram.ext import ContextTypes
from services.news_service import get_latest_news
from utils.decorators import rate_limit, api_enabled
from utils.cache import news_cache, NEWS_TTL
from state import track_command
from utils.format import prepare_telegram_html

@rate_limit(10)
@api_enabled("news")
async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Fetch the latest news.
    /news -> world news
    /news bangladesh or /news bd -> bangladesh news
    """
    track_command("news")
    
    args = context.args
    category = "world"
    title_display = "🌍 <b>World News Digest</b>"
    
    if args:
        query = " ".join(args).lower()
        if "bangladesh" in query or "bd" in query or "বাংলাদেশ" in query:
            category = "bangladesh"
            title_display = "🇧🇩 <b>Bangladesh News Digest</b>"
            
    sent_message = await update.message.reply_text(f"📰 Fetching {title_display}...", parse_mode="HTML")
    
    try:
        # Check cache first
        cached = news_cache.get(category)
        if cached:
            news_items = cached
        else:
            # Run synchronous RSS fetch in background to avoid blocking
            import asyncio
            loop = asyncio.get_event_loop()
            news_items = await loop.run_in_executor(None, lambda: get_latest_news(category, limit=5))
            if news_items:
                news_cache.set(category, news_items, NEWS_TTL)
        
        if not news_items:
            await sent_message.edit_text("❌ Could not fetch news at the moment. Please try again later.", parse_mode="HTML")
            return
            
        message = f"{title_display}\n\n"
        for i, item in enumerate(news_items, 1):
            title = prepare_telegram_html(item['title'])
            summary = prepare_telegram_html(item['summary'])
            link = prepare_telegram_html(item['link'])
            
            message += f"{i}. <b><a href='{link}'>{title}</a></b>\n"
            if summary:
                message += f"<i>{summary}</i>\n"
            message += "\n"
            
        await sent_message.edit_text(message, parse_mode="HTML", disable_web_page_preview=True)
        
    except Exception as e:
        await sent_message.edit_text(f"🔧 Error fetching news: {str(e)}")
