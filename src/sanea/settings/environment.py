"""Detected sanea environment and loaded .env files."""

from envbox import PRODUCTION, get_environment


ENVIRONMENT = get_environment(default=PRODUCTION)
