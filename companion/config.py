import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.8-flash")
UTILITY_MODEL = os.getenv("GEMINI_UTILITY_MODEL", "gemini-3.8-flash")
EMBEDDING_MODEL = os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIMENSIONS = int(os.getenv("EMBEDDING_DIMENSIONS", "768"))

DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "companion.sqlite3"
CHROMA_PATH = DATA_DIR / "chroma"
PERSONA_CARD_PATH = PROJECT_ROOT / "persona" / "card.md"

RETRIEVAL_TOP_K = 5
RECENT_TURNS = 8

FACT_COLLECTION = "facts"
