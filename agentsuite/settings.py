# /home/techwithwayne/agentsuite/agentsuite/settings.py
"""
Agentsuite Django settings

CHANGE LOG
----------
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
import logging   # CHANGED: for PDF engine validation logging
from dotenv import load_dotenv

# ========= Base / Env =========
# Robust .env loader that works on PythonAnywhere and local machines
BASE_DIR = Path(__file__).resolve().parent.parent

# ## PPA: load .env (minimal)
# Populate os.environ from BASE_DIR/.env if present, without extra deps.
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
            # do NOT override variables already set in the environment
            if _k and _k not in _PPAOS.environ:
                _PPAOS.environ[_k] = _v
except Exception:
    pass
# ## /PPA


ENV_CANDIDATES = [
    Path(os.path.expanduser('~/agentsuite/.env')),  # PythonAnywhere: ~/agentsuite/.env
    BASE_DIR / '.env',                               # Local: project root
    BASE_DIR.parent / '.env',                        # Local: repo root (if settings/ nested)
]
for _env in ENV_CANDIDATES:
    if _env.exists():
        load_dotenv(_env)
        print(f"[settings_pm] Loaded env from: {_env}")
        break
else:
    load_dotenv()  # fallback (no-op if missing)
    print("[settings_pm] No .env found in common locations; relying on os.environ.")

# ========= PDF Engine (TherapyLib) =========
# CHANGED: Load PDF engine from env, validate, and fallback safely
ALLOWED_PDF_ENGINES = {"weasyprint", "xhtml2pdf", "pdfkit"}  # CHANGED

_pdf_engine = os.getenv("THERAPYLIB_PDF_ENGINE", "xhtml2pdf").lower()  # CHANGED
if _pdf_engine not in ALLOWED_PDF_ENGINES:  # CHANGED
    # logger = logging.getLogger(__name__)  # CHANGED
    print("[WARNING]"
        f"Invalid THERAPYLIB_PDF_ENGINE '{_pdf_engine}' detected. "
        "Falling back to 'xhtml2pdf'. Allowed values: weasyprint, xhtml2pdf, pdfkit."
    )
    _pdf_engine = "xhtml2pdf"  # CHANGED

THERAPYLIB_PDF_ENGINE = _pdf_engine  # CHANGED: available across project

# ========= Secret Key =========
DJANGO_SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
if not DJANGO_SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY must be set in .env file")
SECRET_KEY = DJANGO_SECRET_KEY

DEBUG = os.getenv("DEBUG", "False") == "True"

# ========= Hosts / CSRF / Security (PA-ready) =========
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "apps.techwithwayne.com",
    "techwithwayne.pythonanywhere.com",
    "testserver",
    "ppa-api.techwithwayne.com",
] + (os.getenv("ADDITIONAL_HOSTS", "").split(",") if os.getenv("ADDITIONAL_HOSTS") else [])

# If behind HTTPS (recommended on PA)
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

# Keep your list intact, only add anymail (Mailgun API) and postpress_ai unconditionally
# [PPA FIX] ensure both apps exist independently of each other
for _app in ["anymail", "postpress_ai"]:
    if _app not in INSTALLED_APPS:
        INSTALLED_APPS += [_app]

# [PPA SAFETY] Drop optional monorepo apps if missing to avoid ModuleNotFoundError on PA  # CHANGED:
try:  # CHANGED:
    from importlib import import_module  # CHANGED:
    _final_apps = []  # CHANGED:
    _missing_apps = []  # CHANGED:
    for _app in INSTALLED_APPS:  # CHANGED:
        try:  # CHANGED:
            import_module(_app)  # CHANGED:
            _final_apps.append(_app)  # CHANGED:
        except ModuleNotFoundError as _e:  # CHANGED:
            # Treat monorepo-local apps as optional; skip if not importable on this deployment  # CHANGED:
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
            }:  # CHANGED:
                _missing_apps.append(_app)  # CHANGED:
            else:  # CHANGED:
                raise  # non-optional (e.g., django.*, rest_framework)                     # CHANGED:
    if _missing_apps:  # CHANGED:
        print(f"[settings_pm] Optional apps not present; skipping: {_missing_apps}")  # CHANGED:
    INSTALLED_APPS = _final_apps  # CHANGED:
except Exception as _guard_exc:  # CHANGED:
    print(f"[settings_pm] App guard failed: {_guard_exc}")  # CHANGED:

# ========= Middleware =========
# [PPA FIX] Move CORS middleware to the very top (django-cors-headers best practice)
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",

    "website_analyzer.middleware.FrameAncestorMiddleware",  # must import successfully
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    # Mentor access gate must run after sessions & CSRF:
    "personal_mentor.middleware.MentorAccessMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    # "django.middleware.clickjacking.XFrameOptionsMiddleware",  # keep disabled
]

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
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 30},
    }
}

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

# Use WhiteNoise for static file serving in production
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
# [PPA FIX] Centralize shared key and allowed origins used by views
PPA_SHARED_KEY = os.getenv("PPA_SHARED_KEY", "")
PPA_ALLOWED_ORIGINS = os.getenv(
    "PPA_ALLOWED_ORIGINS",
    "https://techwithwayne.com,https://techwithwayne.com"
).split(",")

# ========= CORS / CSRF (single source of truth) =========
CORS_ALLOWED_ORIGINS = [
    "https://showcase.techwithwayne.com",
    "https://apps.techwithwayne.com",
    "https://promptopilot.com",
    "https://tools.promptopilot.com",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://techwithwayne.com",
    "https://techwithwayne.com",
]  # keep existing entries
# [PPA FIX] Ensure PPA_ALLOWED_ORIGINS are included (de-duped)
for _o in PPA_ALLOWED_ORIGINS:
    if _o and _o not in CORS_ALLOWED_ORIGINS:
        CORS_ALLOWED_ORIGINS.append(_o)

# Include PythonAnywhere/app domains for CSRF
_CSRF_EXTRA = [
    "https://techwithwayne.pythonanywhere.com",
]
CSRF_TRUSTED_ORIGINS = list({*CORS_ALLOWED_ORIGINS, *_CSRF_EXTRA})

CORS_ALLOW_CREDENTIALS = True  # allow cookies/auth across domains

# [PPA FIX] Explicitly allow our custom auth header for preflight success
CORS_ALLOW_HEADERS = list({
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-ppa-key",  # critical for Django + Cloudflare preflight
    "x-ppa-install",
    "x-ppa-version",
})

# ========= Session config =========
SESSION_COOKIE_AGE = 3600  # 1 hour
SESSION_SAVE_EVERY_REQUEST = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# ========= Email (Mailgun via Anymail preferred) =========
# Default to Mailgun API backend via Anymail (works on PythonAnywhere Free)
EMAIL_BACKEND = os.getenv(
    "DJANGO_EMAIL_BACKEND",
    "anymail.backends.mailgun.EmailBackend"
)

# Anymail / Mailgun API configuration
ANYMAIL = {
    "MAILGUN_API_KEY": os.getenv("MAILGUN_API_KEY", ""),
    "MAILGUN_SENDER_DOMAIN": os.getenv("MAILGUN_DOMAIN", ""),  # e.g. mg.yourdomain.com
    # If using EU region, set ANYMAIL_MAILGUN_API_URL=https://api.eu.mailgun.net/v3
    "MAILGUN_API_URL": os.getenv("ANYMAIL_MAILGUN_API_URL", "https://api.mailgun.net/v3"),
}

# SMTP variables — ONLY used if you explicitly set EMAIL_BACKEND to SMTP
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.mailgun.org")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "false").strip().lower() == "true"  # CHANGED: strict true only
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")       # e.g. postmaster@mg.yourdomain.com
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")  # your Mailgun SMTP password

# From address (use your Mailgun domain for best deliverability)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Personal Mentor <no-reply@mg.yourdomain.com>")

# Helpful visibility on startup
print(f"[settings_pm] EMAIL_BACKEND = {EMAIL_BACKEND}")
print(f"[settings_pm] DEFAULT_FROM_EMAIL = {DEFAULT_FROM_EMAIL}")

if EMAIL_BACKEND.endswith("smtp.EmailBackend") and not all([EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD]):
    print("⚠️  EMAIL configuration incomplete - set EMAIL_HOST / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD")

# ========= OpenAI =========
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_ASSISTANT_ID = os.getenv("OPENAI_ASSISTANT_ID")

# ========= Extra Security (prod) =========
SECURE_SSL_REDIRECT = not DEBUG  # redirect only if in prod (re-affirm)

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

        # ============================================================
        # 2025-11-13 • Add PostPress AI view logger → INFO to webdoctor.log  # CHANGED:
        # ============================================================
        'postpress_ai.views': {                                                 # CHANGED:
            'handlers': ['file', 'console'],                                    # CHANGED:
            'level': 'INFO',                                                    # CHANGED:
            'propagate': False,                                                 # CHANGED:
        },                                                                       # CHANGED:
    },
}

# Defensive: ensure ANY RotatingFileHandler gets UTF-8 if not set explicitly
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
# (full file content pasted above)
