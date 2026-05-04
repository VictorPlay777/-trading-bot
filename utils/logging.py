from loguru import logger
import os

def setup_logging(logs_dir: str):
    os.makedirs(logs_dir, exist_ok=True)
    logger.add(os.path.join(logs_dir, 'bot.log'), rotation='10 MB', retention='10 days')
    return logger
