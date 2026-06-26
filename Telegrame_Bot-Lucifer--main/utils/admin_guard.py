from config import Config

def is_admin(user_id) -> bool:
    """
    Check if a user is the authorized admin.
    
    Args:
        user_id: The Telegram user ID (int or str)
        
    Returns:
        bool: True if the user is an admin, False otherwise.
    """
    if not Config.ADMIN_ID:
        return False
    return str(user_id) == str(Config.ADMIN_ID)
