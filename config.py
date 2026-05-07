import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.environ["DISCORD_TOKEN"]
DB_PATH = os.getenv("DB_PATH", "files.db")
