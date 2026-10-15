"""Vercel ASGI entrypoint; the application remains under apps/api for local use."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "apps" / "api"))

from app.main import app as app  # noqa: E402
