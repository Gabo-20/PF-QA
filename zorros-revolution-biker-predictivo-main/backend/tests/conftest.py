"""Hace importable el paquete `app` al correr pytest desde backend/."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
