"""Known GNOME infrastructure is not a child-facing application."""

import pytest

from sanea.utils.applications import is_desktop_component


@pytest.mark.parametrize(("prc_name", "exe", "app_id", "expected"), [
    ("mutter-x11-fram", "/usr/libexec/mutter-x11-frames", None, True),
    ("other-name", "/usr/libexec/mutter-x11-frames", None, True),
    ("gnome-shell", "/usr/bin/gnome-shell", None, True),
    ("gjs", "/usr/bin/gjs", "gjs:/usr/share/gnome-shell/extensions/ding@rastersoft.com/ding.js", True),
    ("gjs", "/usr/bin/gjs", "gjs:/home/demo/.local/share/gnome-shell/extensions/ding@rastersoft.com/app/ding.js", True),
    ("gjs", "/usr/bin/gjs", "desktop:com.rastersoft.ding", True),
    ("gjs", "/usr/bin/gjs", "gjs:/apps/ding.js", False),
    ("gjs", "/usr/bin/gjs", "gjs:/apps/ding@rastersoft.com/editor.js", False),
    ("gjs", "/usr/bin/gjs", "desktop:org.gnome.Maps", False),
    ("gjs", "/usr/bin/gjs", None, False),
    (None, None, None, False),
])
def test_identifies_only_known_desktop_components(
    prc_name: str | None, exe: str | None, app_id: str | None, expected: bool,
) -> None:
    assert is_desktop_component(prc_name, exe, app_id) is expected
