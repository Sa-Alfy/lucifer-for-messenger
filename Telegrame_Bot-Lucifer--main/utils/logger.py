import logging
import sys
from logging.handlers import RotatingFileHandler

import os

# Configure logging: console only on Render, rotation on local
handlers = [logging.StreamHandler(sys.stdout)]
if not os.environ.get("RENDER"):
    handlers.append(
        RotatingFileHandler(
            "bot.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding='utf-8'
        )
    )

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=handlers
)

def get_logger(name):
    return logging.getLogger(name)
