"""
Agentsuite Django settings

CHANGE LOG
----------
2026-02-21 • RENDER FIX: Stop forcing 'anymail' into INSTALLED_APPS (not used).                    # CHANGED:
           • Allow app-guard to run so missing 'apps.*' are skipped instead of crashing.          # CHANGED:
           • DB: Use DATABASE_URL when present (Render Postgres), else fallback to SQLite.        # CHANGED:
           • MIDDLEWARE: Skip optional middleware if its module can't import (Render-safe).       # CHANGED:

2026-01-23 • PPA CACHE: Add shared FileBasedCache to fix translate polling job_not_found across workers. # CHANGED:
           • Uses BASE_DIR/ppa_cache (or env PPA_CACHE_DIR) and auto-creates dir safely.               # CHANGED:
           • Falls back to LocMemCache if dir isn't writable (never crashes startup).                 # CHANGED:

2025-12-26 • PPA EMAIL: Remove hardcoded email constants and wire env-driven provider config.         # CHANGED:
           • Uses postpress_ai.email_config.get_email_settings() (Mailgun via Anymail).              # CHANGED:
           • Keeps existing behavior for non-PPA apps; no CORS/auth/Stripe changes.                  # CHANGED:

2025-10-24 • Guard INSTALLED_APPS against missing optional monorepo apps on PA  # CHANGED:
- Dynamically skip absent modules (e.g., 'apps.*') to prevent ModuleNotFoundError. # CHANGED:
- Emits [settings_pm] warning listing any skipped apps.                             # CHANGED:

2025-08-25 • Added THERAPYLIB_PDF_ENGINE config                                    # CHANGED:
- Loads default PDF engine from env (THERAPYLIB_PDF_ENGINE).                       # CHANGED:
- Validates against {'weasyprint','xhtml2pdf','pdfkit'}.                           # CHANGED:
- Falls back to 'xhtml2pdf' if invalid, logs a warning.                            # CHANGED:

2025-08-16 • Logging encoding → settings-level (UTF-8)
- Added encoding='utf-8' to the RotatingFileHandler in LOGGING.handlers['file'] to
  prevent NUL bytes during rotation and make greps stable.
- Added a defensive post-processing block that ensures any RotatingFileHandler in
  LOGGING gets encoding='utf-8' if not explicitly set.
"""

from pathlib import Path
import os
import logging  # CHANGED: for PDF engine validation logging
from dotenv import load_dotenv
import environ  # CHANGED: DATABASE_URL parsing (Render Postgres)

# ========= Base / Env =========
BASE_DIR = Path(__file__).resolve().parent.parent

# ## PPA: load .env (minimal)
try:
    from pathlib import Path as _PPAPath
    import os as _PPAOS
    _ppa_env = (_PPAPath(__file__).resolve().parent.parent / ".env")
    if _ppa_env.exists():
        for _line in _ppa_env.read_text(encoding="utf-8").splitlines():
            _s = _line.strip()
            if not _s or _s.startswith("#") or "=" not in _s:
                continue
            _k, _v = _s.split("=", 1)
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k and _k not in _PPAOS.environ:
                _PPAOS.environ[_k] = _v
except Exception:
    pass
# ## /PPA

ENV_CANDIDATES = [
    Path(os.path.expanduser('~/agentsuite/.env')),
    BASE_DIR / '.env',
    BASE_DIR.parent / '.env',
]
for _env in ENV_CANDIDATES:
    if _env.exists():
        load_dotenv(_env)
        print(f"[settings_pm] Loaded env from: {_env}")
        break
else:
    load_dotenv()
    print("[settings_pm] No .env found in common locations; relying on os.environ.")

# ========= PDF Engine (TherapyLib) =========
ALLOWED_PDF_ENGINES = {"weasyprint", "xhtml2pdf", "pdfkit"}  # CHANGED
_pdf_engine = os.getenv("THERAPYLIB_PDF_ENGINE", "xhtml2pdf").lower()  # CHANGED
if _pdf_engine not in ALLOWED_PDF_ENGINES:  # CHANGED
    print("[WARNING]"
        f"Invalid THERAPYLIB_PDF_ENGINE '{_pdf_engine}' detected. "
        "Falling back to 'xhtml2pdf'. Allowed values: weasyprint, xhtml2pdf, pdfkit."
    )
    _pdf_engine = "xhtml2pdf"  # CHANGED
THERAPYLIB_PDF_ENGINE = _pdf_engine  # CHANGED

# ========= Secret Key =========
DJANGO_SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not DJANGO_SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY must be set in environment")
SECRET_KEY = DJANGO_SECRET_KEY

DEBUG = os.getenv("DEBUG", "False") == "True"

# ========= Hosts / CSRF / Security =========
def _split_csv_env(name: str) -> list[str]:  # CHANGED:
    raw = os.getenv(name, "")  # CHANGED:
    if not raw:  # CHANGED:
        return []  # CHANGED:
    return [x.strip() for x in raw.split(",") if x.strip()]  # CHANGED:

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "apps.techwithwayne.com",
    "techwithwayne.pythonanywhere.com",
    "testserver",
    "ppa-api.techwithwayne.com",
] + _split_csv_env("ADDITIONAL_HOSTS")  # CHANGED:

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# ========= Installed apps =========
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "webdoctor",
    "captcha",

    # Apps being built
    "therapylib",
    "personal_mentor",
    "promptopilot",

    "website_analyzer",
    "barista_assistant",
    "barista_assistant.menu",
    "barista_assistant.orders",
    "content_strategy_generator_agent",
    "rest_framework",
    "django_extensions",

    "humancapital",

    "apps.core",
    "apps.accounts",
    "apps.contacts",
    "apps.leads",
    "apps.sequences",
    "apps.messaging",
    "apps.api",
]

# Keep your list intact, only add postpress_ai unconditionally (anymail NOT used).  # CHANGED:
for _app in ["postpress_ai"]:  # CHANGED:
    if _app not in INSTALLED_APPS:
        INSTALLED_APPS += [_app]

# [PPA SAFETY] Drop optional monorepo apps if missing to avoid ModuleNotFoundError
try:
    from importlib import import_module
    _final_apps = []
    _missing_apps = []
    for _app in INSTALLED_APPS:
        try:
            import_module(_app)
            _final_apps.append(_app)
        except ModuleNotFoundError:
            # Treat monorepo-local apps as optional; skip if not importable on this deployment
            if _app.startswith("apps.") or _app in {
                "website_analyzer",
                "barista_assistant",
                "barista_assistant.menu",
                "barista_assistant.orders",
                "content_strategy_generator_agent",
                "humancapital",
                "personal_mentor",
                "promptopilot",
                "therapylib",
            }:
                _missing_apps.append(_app)
            else:
                raise
    if _missing_apps:
        print(f"[settings_pm] Optional apps not present; skipping: {_missing_apps}")
    INSTALLED_APPS = _final_apps
except Exception as _guard_exc:
    print(f"[settings_pm] App guard failed: {_guard_exc}")

# ========= Middleware =========
# Build middleware list and skip optional ones if their module can't import (Render-safe).  # CHANGED:
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

# Optional middleware entries (only include if importable).  # CHANGED:
_OPTIONAL_MW = [
    "website_analyzer.middleware.FrameAncestorMiddleware",
    "personal_mentor.middleware.MentorAccessMiddleware",
]
try:  # CHANGED:
    from importlib import import_module as _mw_import  # CHANGED:
    for _mw in _OPTIONAL_MW:  # CHANGED:
        _mod = _mw.rsplit(".", 1)[0]  # CHANGED:
        try:  # CHANGED:
            _mw_import(_mod)  # CHANGED:
            # Keep MentorAccessMiddleware after sessions/csrf (we append at end).  # CHANGED:
            MIDDLEWARE.append(_mw)  # CHANGED:
        except ModuleNotFoundError:  # CHANGED:
            print(f"[settings_pm] Optional middleware not present; skipping: {_mw}")  # CHANGED:
except Exception as _mw_exc:  # CHANGED:
    print(f"[settings_pm] Optional middleware guard failed: {_mw_exc}")  # CHANGED:

# ========= URL / Templates / WSGI =========
ROOT_URLCONF = "agentsuite.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "agentsuite.wsgi.application"

# ========= Database =========
# Render: DATABASE_URL is required for Postgres. Local/PA can still use SQLite fallback.  # CHANGED:
_env = environ.Env()  # CHANGED:
if os.getenv("DATABASE_URL"):  # CHANGED:
    DATABASES = {"default": _env.db("DATABASE_URL")}  # CHANGED:
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            "OPTIONS": {"timeout": 30},
        }
    }

# ========= Cache (shared across workers) =========
PPA_CACHE_DIR = os.getenv("PPA_CACHE_DIR", str(BASE_DIR / "ppa_cache"))  # CHANGED:

_can_write_cache_dir = False
try:
    os.makedirs(PPA_CACHE_DIR, exist_ok=True)
    _can_write_cache_dir = os.access(PPA_CACHE_DIR, os.W_OK)
except Exception as _cache_exc:
    print(f"[settings_pm] PPA cache dir create failed ({PPA_CACHE_DIR}): {_cache_exc}")
    _can_write_cache_dir = False

if _can_write_cache_dir:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
            "LOCATION": PPA_CACHE_DIR,
            "TIMEOUT": None,
            "OPTIONS": {
                "MAX_ENTRIES": 5000,
                "CULL_FREQUENCY": 3,
            },
        }
    }
    print(f"[settings_pm] CACHES=FileBasedCache ({PPA_CACHE_DIR})")
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ppa-fallback-locmem",
        }
    }
    print("[settings_pm] CACHES=LocMemCache fallback (PPA cache dir not writable)")

# ========= Password validation =========
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ========= I18N =========
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ========= Security headers =========
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# ========= Static / Media =========
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

def set_custom_headers(headers, path, url):
    if path.endswith(".css") or path.endswith(".js"):
        headers["Access-Control-Allow-Origin"] = "*"

WHITENOISE_ADD_HEADERS_FUNCTION = set_custom_headers

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ========= Defaults =========
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ========= PostPress AI shared config =========
PPA_WP_API_URL = os.getenv("PPA_WP_API_URL", "")
PPA_WP_USER = os.getenv("PPA_WP_USER", "")
PPA_WP_PASS = os.getenv("PPA_WP_PASS", "")

PPA_SHARED_KEY = os.getenv("PPA_SHARED_KEY", "")
PPA_ALLOWED_ORIGINS = _split_csv_env("PPA_ALLOWED_ORIGINS") or [  # CHANGED:
    "https://techwithwayne.com",
]

# ========= CORS / CSRF =========
CORS_ALLOWED_ORIGINS = [
    "https://showcase.techwithwayne.com",
    "https://apps.techwithwayne.com",
    "https://promptopilot.com",
    "https://tools.promptopilot.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://techwithwayne.com",
    "https://techwithwayne.com",
]
for _o in PPA_ALLOWED_ORIGINS:
    if _o and _o not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_o)

_CSRF_EXTRA = [
    "https://techwithwayne.pythonanywhere.com",
]
CSRF_TRUSTED_ORIGINS = list({*CORS_ALLOWED_ORIGINS, *_CSRF_EXTRA})

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = list({
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-ppa-key",
    "x-ppa-install",
    "x-ppa-version",
})

# ========= Session config =========
SESSION_COOKIE_AGE = 3600
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ========= Email =========
# If your email_config returns an anymail backend but anymail isn't installed, fall back safely.  # CHANGED:
try:
    from postpress_ai.email_config import get_email_settings
    _PPA_EMAIL_SETTINGS = get_email_settings()
    globals().update(_PPA_EMAIL_SETTINGS)

    # If settings point at anymail but package isn't present, don't crash later.  # CHANGED:
    _backend = str(globals().get("EMAIL_BACKEND", "")).strip()  # CHANGED:
    if _backend.startswith("anymail.") or ".anymail." in _backend:  # CHANGED:
        try:  # CHANGED:
            import anymail  # noqa: F401  # CHANGED:
        except ModuleNotFoundError:  # CHANGED:
            EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"  # CHANGED:
            print("[settings_pm] anymail not installed; EMAIL_BACKEND forced to console backend.")  # CHANGED:

    print(f"[settings_pm] EMAIL_BACKEND = {globals().get('EMAIL_BACKEND')}")
    print(f"[settings_pm] DEFAULT_FROM_EMAIL = {globals().get('DEFAULT_FROM_EMAIL')}")
except Exception as _ppa_email_exc:
    print(f"[settings_pm] PPA email config not applied: {_ppa_email_exc}")
    EMAIL_BACKEND = os.getenv("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
    DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "no-reply@localhost")

# ========= OpenAI =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# ========= Extra Security (prod) =========
SECURE_SSL_REDIRECT = not DEBUG

# ========= Logging =========
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOG_DIR / 'webdoctor.log',
            'maxBytes': 1024*1024*15,
            'backupCount': 10,
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'loggers': {
        'webdoctor': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': True,
        },
        'django': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': True,
        },
        'django.core.mail': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'postpress_ai.views': {
            'handlers': ['file', 'console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

try:
    if isinstance(LOGGING, dict):
        handlers = LOGGING.setdefault("handlers", {})
        for _name, _h in list(handlers.items()):
            cls = str(_h.get("class", "")).rsplit(".", 1)[-1]
            if cls == "RotatingFileHandler" and not _h.get("encoding"):
                _h["encoding"] = "utf-8"
except Exception:
    pass

# ========= Stripe =========
DEPLOY_BASE_URL = os.getenv("DEPLOY_BASE_URL", "https://apps.techwithwayne.com").rstrip("/")

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")

STRIPE_SUCCESS_URL = os.getenv(
    "STRIPE_SUCCESS_URL",
    f"{DEPLOY_BASE_URL}/success/?session_id={{CHECKOUT_SESSION_ID}}"
)
STRIPE_CANCEL_URL = os.getenv(
    "STRIPE_CANCEL_URL",
    f"{DEPLOY_BASE_URL}/barista-assistant/"
)
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")