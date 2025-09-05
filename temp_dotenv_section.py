from pathlib import Path
import os
import logging # CHANGED: for PDF engine validation logging
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_CANDIDATES = [
    Path(os.path.expanduser('~/agentsuite/.env')),  # PythonAnywhere: ~/agentsuite/.env
    BASE_DIR / '.env',  # Local: project root
    BASE_DIR.parent / '.env',  # Local: repo root (if settings/ nested)
]

for env_path in ENV_CANDIDATES:
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[settings_pm] Loaded env from: {env_path}")
        break
else:
    load_dotenv()  # fallback (no-op if missing)
    print("[settings_pm] No .env found in common locations; relying on os.environ.")

ALLOWED_PDF_ENGINES = {"weasyprint", "xhtml2pdf", "pdfkit"}  # CHANGED
