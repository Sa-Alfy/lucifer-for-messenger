import re
import html

def clean_markdown_fallback(text: str) -> str:
    """Cleans markdown symbols so plain text fallback looks neat."""
    if not text:
        return ""
    # Remove Bold/Italic ** and __
    text = re.sub(r'(\*\*|__)', '', text)
    # Remove headers #
    text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
    # Remove single * used for italic/bold occasionally, safely
    # This might remove bullet points, but it's okay for clean fallback
    return text
def prepare_telegram_html(text: str) -> str:
    """Converts common Markdown from LLM into Telegram-safe HTML."""
    if not text:
        return ""
    
    # Escape HTML special characters first
    text = html.escape(text)

    # Code blocks: ```language\ncode\n```
    # Telegram supports <pre><code class="language="...">...</code></pre>
    def replace_code_block(match):
        language = match.group(1).strip()
        code = match.group(2)
        if language:
            return f'<pre><code class="language-{language}">{code}</code></pre>'
        return f'<pre><code>{code}</code></pre>'
        
    text = re.sub(r'```(?:([a-zA-Z0-9_-]+)\n)?(.*?)```', replace_code_block, text, flags=re.DOTALL)

    # Inline code: `code`
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)

    # Bold: **text**
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # Italic: *text* or _text_ (only match word boundaries for _ to avoid catching snake_case variables)
    text = re.sub(r'(?<![A-Za-z0-9_])\*(.*?)\*(?![A-Za-z0-9_])', r'<i>\1</i>', text)
    text = re.sub(r'(?<![A-Za-z0-9_])_(.*?)_(?![A-Za-z0-9_])', r'<i>\1</i>', text)

    # Links: [text](URL)
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    # Headers: ## Header
    text = re.sub(r'^#{1,6}\s*(.*)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Bullet lists: * item or - item
    text = re.sub(r'^[*-]\s+(.*)$', r'• \1', text, flags=re.MULTILINE)

    # Numbered lists: 1. item
    text = re.sub(r'^(\d+)\.\s+(.*)$', r'\1. \2', text, flags=re.MULTILINE)

    return text
