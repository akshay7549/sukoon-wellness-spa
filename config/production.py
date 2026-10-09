from .settings import *
DEBUG = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS","3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# Enable only behind a proxy that strips incoming X-Forwarded-Proto headers.
if os.environ.get("TRUST_PROXY_HTTPS","False").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if not DATABASES["default"]["USER"] or not DATABASES["default"]["PASSWORD"]:
    raise ImproperlyConfigured("Configure production DB_USER and DB_PASSWORD.")
if DATABASES["default"]["USER"] == "root":
    raise ImproperlyConfigured("Use a dedicated database user in production, not root.")
CONN_MAX_AGE = 60
DATABASES["default"]["CONN_MAX_AGE"] = 60
