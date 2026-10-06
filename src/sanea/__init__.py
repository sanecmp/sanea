"""Parent application for sanex-managed computers."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("sanea")

except PackageNotFoundError:
    __version__ = "development"
