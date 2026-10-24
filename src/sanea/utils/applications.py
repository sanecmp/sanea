"""Distinguish desktop infrastructure from application usage."""

from pathlib import PurePosixPath


def is_desktop_component(prc_name: str | None, exe: str | None, app_id: str | None) -> bool:
    """Recognize GNOME's shell, X11 frames and DING, not arbitrary GJS scripts."""

    if prc_name in {"gnome-shell", "mutter-x11-fram", "mutter-x11-frames"}:
        return True

    if PurePosixPath(exe or "").name in {"gnome-shell", "mutter-x11-frames"}:
        return True

    if app_id in {"desktop:org.gnome.Shell", "desktop:com.rastersoft.ding"}:
        return True

    if app_id and app_id.startswith("gjs:"):
        script = PurePosixPath(app_id.removeprefix("gjs:"))
        return script.name == "ding.js" and "ding@rastersoft.com" in script.parts

    return False
