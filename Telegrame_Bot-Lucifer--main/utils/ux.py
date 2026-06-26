from utils.constants import DEVELOPER_NAME

def branded_footer():
    """Consistent attribution footer for Lucifer."""
    return f"\n\n⚡ <i>Lucifer Bot | Developed by {DEVELOPER_NAME}</i>"

def ux_card(body: str, title: str = None, footer: str = None, show_branding: bool = False):
    """
    Wraps content in a premium visual frame.
    """
    card = ""
    if title:
        card += f"<b>{title}</b>\n━━━━━━━━━━━━━━━━━━\n"
    
    card += body
    
    if footer:
        card += f"\n━━━━━━━━━━━━━━━━━━\n{footer}"
    elif show_branding:
        card += branded_footer()
        
    return card
