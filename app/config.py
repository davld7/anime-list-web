"""Application configuration for the anime-list-web frontend."""

import os
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_API_BASE_URL = "http://localhost:8000"

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_api_base_url() -> str:
    """Return the backend API base URL for the current environment."""
    return os.getenv("API_BASE_URL", DEFAULT_API_BASE_URL)
