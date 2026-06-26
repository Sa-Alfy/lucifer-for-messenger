import urllib.request
import xml.etree.ElementTree as ET

from utils.logger import get_logger

logger = get_logger(__name__)

# Official free RSS feeds
FEEDS = {
    "world": [
        "http://feeds.bbci.co.uk/news/world/rss.xml",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.a.dj.com/rss/RSSWorldNews.xml" # Wall Street Journal
    ],
    "bangladesh": [
        "https://www.thedailystar.net/frontpage/rss.xml",
        "https://www.thedailystar.net/top-news/rss.xml"
    ]
}

import re

def clean_html(raw_html):
    """Remove HTML tags from descriptions using regex."""
    if not raw_html:
        return ""
    clean = re.sub(r'<[^>]+>', '', raw_html)
    clean = clean.replace('&nbsp;', ' ').replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&')
    if len(clean) > 200:
        clean = clean[:197] + "..."
    return clean.strip()

def get_latest_news(category: str = "world", limit: int = 5) -> list:
    """
    Fetches the latest news from RSS feeds based on the category.
    Returns a list of dicts: [{'title': x, 'link': y, 'summary': z}, ...]
    """
    feed_urls = FEEDS.get(category, FEEDS["world"])
    news_items = []
    
    for url in feed_urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            response = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(response)
            
            for item in root.findall('.//item'):
                title_elem = item.find('title')
                link_elem = item.find('link')
                desc_elem = item.find('description')
                
                title_text = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
                link_text = "".join(link_elem.itertext()).strip() if link_elem is not None else ""
                desc_text = "".join(desc_elem.itertext()).strip() if desc_elem is not None else ""
                
                # Some feeds put the link in an href attribute inside the link element or a nested a tag
                if not link_text.startswith("http"):
                    a_tag = item.find('.//a')
                    if a_tag is not None and 'href' in a_tag.attrib:
                        link_text = a_tag.attrib['href']
                        if link_text.startswith('/'):
                            link_text = "https://www.thedailystar.net" + link_text
                
                if title_text and link_text:
                    clean_title = clean_html(title_text)
                    clean_summary = clean_html(desc_text)
                    
                    # Avoid duplicates
                    if not any(n['title'] == clean_title for n in news_items):
                        news_items.append({
                            'title': clean_title,
                            'link': link_text,
                            'summary': clean_summary
                        })
                
                # If we have enough items, return
                if len(news_items) >= limit:
                    return news_items

        except Exception as e:
            logger.error(f"Failed to fetch RSS from {url}: {e}")
            continue # Try next fallback URL
            
    return news_items
