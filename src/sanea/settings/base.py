"""Settings shared by all sanea environments."""

from pathlib import Path

from sanelib.protocol import MAX_EVENT_PACKET_SIZE

from ..exceptions import ConfigurationError
from .environment import ENVIRONMENT


_state_dir_default = "/opt/sanea/state"
_secret_key_default = None
_allowed_hosts_default = ["localhost", "127.0.0.1", "[::1]"]

if ENVIRONMENT.is_development:
    _state_dir_default = ".state"
    _secret_key_default = "development-only-secret-key"
    _allowed_hosts_default = ["localhost", "127.0.0.1", "0.0.0.0", "[::1]"]

elif ENVIRONMENT.is_testing:
    _state_dir_default = "/tmp/sanea-tests"
    _secret_key_default = "test-only-secret-key"
    _allowed_hosts_default = ["localhost", "127.0.0.1", "testserver"]

STATE_DIR = Path(f"{ENVIRONMENT.get("SANEA_STATE_DIR", _state_dir_default)}")
_database_path_default = ":memory:" if ENVIRONMENT.is_testing else STATE_DIR / "sanea.sqlite3"
DATABASE_PATH = Path(
    f"{ENVIRONMENT.get("SANEA_DATABASE_PATH", _database_path_default)}"
)
PKI_DIR = Path(f"{ENVIRONMENT.get("SANEA_PKI_DIR", STATE_DIR / "pki")}")
SERVER_HOST = f"{ENVIRONMENT.get("SANEA_SERVER_HOST", "0.0.0.0")}"
HTTP_PORT = ENVIRONMENT.get_casted("SANEA_HTTP_PORT", 8000)
HTTPS_PORT = ENVIRONMENT.get_casted("SANEA_HTTPS_PORT", 8443)
DISCOVERY_PORT = ENVIRONMENT.get_casted("SANEA_DISCOVERY_PORT", 62_117)

if not SERVER_HOST:
    raise ConfigurationError("SANEA_SERVER_HOST must not be empty")

for _port_name, _port in (
    ("SANEA_HTTP_PORT", HTTP_PORT),
    ("SANEA_HTTPS_PORT", HTTPS_PORT),
    ("SANEA_DISCOVERY_PORT", DISCOVERY_PORT),
):

    if isinstance(_port, bool) or not isinstance(_port, int) or not 0 < _port < 65536:
        raise ConfigurationError(f"{_port_name} must be an integer from 1 to 65535")

if HTTP_PORT == HTTPS_PORT:
    raise ConfigurationError("SANEA_HTTP_PORT and SANEA_HTTPS_PORT must differ")

SECRET_KEY = ENVIRONMENT.get("SANEA_SECRET_KEY", _secret_key_default)

if not SECRET_KEY:
    raise ConfigurationError("SANEA_SECRET_KEY is required")

ALLOWED_HOSTS = ENVIRONMENT.get_casted(
    "SANEA_ALLOWED_HOSTS",
    _allowed_hosts_default,
)

if not isinstance(ALLOWED_HOSTS, (list, tuple)) or not ALLOWED_HOSTS:
    raise ConfigurationError("SANEA_ALLOWED_HOSTS must be a non-empty list")

ALLOWED_HOSTS = list(ALLOWED_HOSTS)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "etc",
    "sanea.core",
    "siteajax",
    "siteforms",
    "sitegate",
    "sitetree",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "siteajax.middleware.ajax_handler",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "sanea.urls"
WSGI_APPLICATION = "sanea.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "sanea.core.context_processors.application",
            ],
        },
    },
]

DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_EVENT_PACKET_SIZE

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATABASE_PATH,
        "OPTIONS": {
            "timeout": 10,
            "transaction_mode": "IMMEDIATE",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("ru", "Russian"),
]
LOCALE_PATHS = [Path(__file__).resolve().parent.parent / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = STATE_DIR / "static"
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"
AUTH_USER_MODEL = "core.User"
LOGIN_URL = "core:sign_in"
SITEGATE_SIGNUP_ENABLED = False

SITETREE_DYNAMIC_ONLY = True
