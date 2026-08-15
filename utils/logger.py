import logging
import csv
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone, timedelta 

KST = timezone(timedelta(hours=9))

#Initialize and configure the system logger.
def setup_logger(name="TurtleBot"):
    logger = logging.getLogger(name)

    #Prevent duplicate handlers if the logger is called multiple times
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        logging.Formatter.converter = lambda * args: datetime.now(KST).timetuple()

        # Configure rotating file handler: max 5MB per file, keep up to 3 backups
        file_handler = RotatingFileHandler('bot_status.log',maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        #Configure and attach the console stream handler
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
    # Return the fully configured logger instance
    return logger

logger = setup_logger()

LOG_FILE = "trade_history.csv"
# Export executed trade details to a CSV file.
def log_trade(ticker, action, qty, price, units, atr):
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        
        # Write header only if the file is newly created
        if not file_exists:
            writer.writerow(['datetime', 'ticker', 'action', 'qty', 'price', 'units', 'atr'])

        exit_date = datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')
        writer.writerow([
            exit_date,
            ticker,
            action,
            qty,
            f"{price:.2f}",
            units,
            f"{atr:.4f}"
        ])
