from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

class Settings:
    """Application settings with environment overrides."""

    APP_NAME: str = "NIRBHAR"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "nirbhar.db"))
    CHROMA_PATH: str = os.getenv("CHROMA_PATH", str(BASE_DIR / "data" / "chroma"))
    OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")
    OLLAMA_EMBED_MODEL: str = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    RETRIEVER_MODE: str = os.getenv("RETRIEVER_MODE", "auto")
    SOP_PACKS: tuple[str, ...] = ("campus", "factory")
    ACTIVE_PACK: str = os.getenv("ACTIVE_PACK", "campus")


settings = Settings()
