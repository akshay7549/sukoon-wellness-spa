from pathlib import Path
import os
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if len(SECRET_KEY) < 50 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured("Set a unique DJANGO_SECRET_KEY of at least 50 characters in .env.")
ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost,sukoonwellnessandspa.in,www.sukoonwellnessandspa.in").split(",") if h.strip()]
PUBLIC_SITE_URL = os.environ.get("PUBLIC_SITE_URL", "https://sukoonwellnessandspa.in").rstrip("/")
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.sitemaps", "spa"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware", "spa.rate_limits.SubmissionRateLimitMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates", "DIRS":[BASE_DIR / "templates"], "APP_DIRS":True, "OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages","spa.context_processors.site_context"]}}]
WSGI_APPLICATION = "config.wsgi.application"
DATABASES = {"default":{"ENGINE":"django.db.backends.mysql", "NAME":os.environ.get("DB_NAME","sukoon_spa"), "USER":os.environ.get("DB_USER",""), "PASSWORD":os.environ.get("DB_PASSWORD",""), "HOST":os.environ.get("DB_HOST","127.0.0.1"), "PORT":os.environ.get("DB_PORT","3307"), "CONN_MAX_AGE":60 if not DEBUG else 0, "OPTIONS":{"charset":"utf8mb4","init_command":"SET sql_mode='STRICT_TRANS_TABLES'"}}}
AUTH_PASSWORD_VALIDATORS = [{"NAME":f"django.contrib.auth.password_validation.{name}"} for name in ["UserAttributeSimilarityValidator","MinimumLengthValidator","CommonPasswordValidator","NumericPasswordValidator"]]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "my_bookings"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_TRUSTED_ORIGINS = ["https://sukoonwellnessandspa.in","https://www.sukoonwellnessandspa.in"]
SECURE_SSL_REDIRECT = not DEBUG
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = False
X_FRAME_OPTIONS = "DENY"
PASSWORD_RESET_TIMEOUT = 3600
CUSTOMER_CHANGE_CUTOFF_HOURS = 2
EMAIL_ENABLED = os.environ.get("EMAIL_ENABLED","False").lower() == "true"
BUSINESS_EMAIL = os.environ.get("BUSINESS_EMAIL","")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", BUSINESS_EMAIL or "noreply@sukoonwellnessandspa.in")
MAILERS = {"default":{"BACKEND":"django.core.mail.backends.dummy.EmailBackend"}}
if EMAIL_ENABLED:
    if not os.environ.get("SMTP_HOST") or not BUSINESS_EMAIL:
        raise ImproperlyConfigured("EMAIL_ENABLED requires SMTP_HOST and BUSINESS_EMAIL.")
    MAILERS = {"default":{"BACKEND":"django.core.mail.backends.smtp.EmailBackend","OPTIONS":{"host":os.environ["SMTP_HOST"],"port":int(os.environ.get("SMTP_PORT","587")),"username":os.environ.get("SMTP_USER",""),"password":os.environ.get("SMTP_PASSWORD",""),"use_tls":os.environ.get("SMTP_USE_TLS","True").lower()=="true","use_ssl":os.environ.get("SMTP_USE_SSL","False").lower()=="true","timeout":15}}}
WHATSAPP_ENABLED = os.environ.get("WHATSAPP_ENABLED","False").lower() == "true"
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL","")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN","")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID","")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.environ.get("WHATSAPP_BUSINESS_ACCOUNT_ID","")
WHATSAPP_TEMPLATE_NAME = os.environ.get("WHATSAPP_TEMPLATE_NAME","")
WHATSAPP_TEMPLATE_LANGUAGE = os.environ.get("WHATSAPP_TEMPLATE_LANGUAGE","en")
DATA_DIR = BASE_DIR / "data"
(DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
LOGGING = {"version":1,"disable_existing_loggers":False,"handlers":{"console":{"class":"logging.StreamHandler"},"file":{"class":"logging.handlers.RotatingFileHandler","filename":str(DATA_DIR/"logs"/"application.log"),"maxBytes":5*1024*1024,"backupCount":3,"encoding":"utf-8"}},"loggers":{"spa":{"handlers":["console","file"],"level":"WARNING","propagate":False},"django.request":{"handlers":["console","file"],"level":"ERROR","propagate":False}}}
from django.contrib.messages import constants as message_constants
MESSAGE_TAGS = {message_constants.DEBUG:"debug",message_constants.INFO:"info",message_constants.SUCCESS:"success",message_constants.WARNING:"warning",message_constants.ERROR:"error"}
