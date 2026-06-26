from datetime import timezone, timedelta

# Bangladesh Standard Time (UTC+6)
BST = timezone(timedelta(hours=6))

def get_now_bst():
    """Returns the current time in Bangladesh Standard Time."""
    from datetime import datetime
    return datetime.now(BST)
