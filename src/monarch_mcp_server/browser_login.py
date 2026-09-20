"""Embedded-browser login for login_setup.py.

Opens a small native browser window (WebView2 on Windows, WebKit on macOS,
WebKitGTK on Linux, all via the ``pywebview`` package) pointed at Monarch's
login page, lets the user sign in normally -- including SSO and MFA, since
it is a real browser engine rendering Monarch's own page -- and extracts the
session cookies once they appear, with no DevTools/copy-paste required.

This is intentionally optional. ``pywebview`` is a fairly heavy, platform-
variable dependency (it needs a working GUI toolkit under it: WebView2 on
Windows, PyObjC+WebKit on macOS, GTK+WebKit2GTK on Linux), so nothing in the
rest of this package imports this module at load time. login_setup.py
imports it lazily and falls back to the existing manual-cookie/password/
token menu if the prerequisites are not met -- see check_prerequisites()
and the *_missing_gui_backend* codepath below for what "not met" covers on
each platform.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, List, Optional

# The two cookies monarchmoney.MonarchMoney.set_cookies() requires. Login is
# not considered complete until both are present, regardless of which URL
# the window has navigated to -- Monarch's login flow can involve SSO
# redirects through third-party domains, so waiting for a specific "logged
# in" URL pattern would be guessing at something that can change out from
# under us. Cookie presence is exactly the condition the downstream code
# itself checks, so it can't drift out of sync with it.
REQUIRED_COOKIE_NAMES = frozenset({"session_id", "csrftoken"})

MONARCH_LOGIN_URL = "https://app.monarch.com/login"

# How long to let the window sit open before giving up and treating it as a
# cancelled login. A human filling in SSO/MFA can reasonably take a few
# minutes; this is generous rather than tight.
DEFAULT_TIMEOUT_SECONDS = 600


@dataclass
class PrerequisiteCheck:
    """Result of checking whether the embedded-browser login can run here."""

    available: bool
    reason: Optional[str] = None
    # Text explaining how to fix it manually, shown when available is False
    # and the user either declines or auto-install doesn't apply/fails.
    install_instructions: Optional[str] = None
    # Whether attempt_auto_install() has anything worth trying for this
    # platform. False for e.g. "the WebView2 runtime itself is missing on
    # Windows" -- that is a signed installer from Microsoft, not something
    # this script should silently fetch and execute.
    can_auto_install: bool = False


def _pywebview_importable() -> bool:
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    return True


def _linux_gui_backend_available() -> bool:
    """Best-effort check for a GUI toolkit pywebview can actually use on Linux.

    pywebview itself is pure Python and imports fine even with no GUI
    toolkit underneath it; the failure only happens later, inside
    webview.start(), when it tries to pick a backend and finds none. This
    checks for the two toolkits pywebview supports (GTK+WebKit2GTK via
    PyGObject, or Qt+QtWebEngine) so that failure can be caught up front
    instead of surfacing as an unexplained crash mid-login.

    This is inherently best-effort: even a hit here doesn't guarantee
    webview.start() will succeed (a partial GTK install without the WebKit2
    typelib specifically is a real, common case), so login_with_embedded_
    browser() still wraps the actual attempt in its own try/except.
    """
    try:
        import gi  # noqa: F401

        gi.require_version("WebKit2", "4.1")
        from gi.repository import WebKit2  # noqa: F401

        return True
    except Exception:
        pass
    try:
        gi.require_version("WebKit2", "4.0")  # type: ignore[possibly-undefined]
        from gi.repository import WebKit2  # noqa: F401,F811

        return True
    except Exception:
        pass
    for qt_pkg in ("PyQt6", "PySide6", "PyQt5", "PySide2"):
        try:
            __import__(qt_pkg)
            __import__(f"{qt_pkg}.QtWebEngineWidgets")
            return True
        except Exception:
            continue
    return False


_LINUX_INSTALL_INSTRUCTIONS = """\
Linux needs a GTK+WebKit2GTK (or Qt+QtWebEngine) install for the embedded
browser window. The exact package names vary by distro:

  Debian / Ubuntu:
    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1

  Fedora:
    sudo dnf install python3-gobject gtk3 webkit2gtk4.1

  Arch:
    sudo pacman -S python-gobject gtk3 webkit2gtk-4.1

Then: pip install pywebview (or: uv sync --extra browser-login)
"""

_WINDOWS_INSTALL_INSTRUCTIONS = """\
Windows needs the Microsoft Edge WebView2 Runtime. It's preinstalled on most
Windows 10 (21H2+) and all Windows 11 systems; if it's missing, download the
Evergreen Bootstrapper from Microsoft directly and run it:

  https://developer.microsoft.com/microsoft-edge/webview2/

Then: pip install pywebview pythonnet (or: uv sync --extra browser-login)
"""

_MACOS_INSTALL_INSTRUCTIONS = """\
macOS uses the system WebKit framework, which is always present -- this
should normally work out of the box. If it still fails:

  pip install pywebview (or: uv sync --extra browser-login)
"""


def check_prerequisites() -> PrerequisiteCheck:
    """Check whether the embedded-browser login can run on this machine."""
    if not _pywebview_importable():
        if sys.platform == "darwin":
            instructions = _MACOS_INSTALL_INSTRUCTIONS
        elif sys.platform == "win32":
            instructions = _WINDOWS_INSTALL_INSTRUCTIONS
        else:
            instructions = _LINUX_INSTALL_INSTRUCTIONS
        return PrerequisiteCheck(
            available=False,
            reason="the 'pywebview' package is not installed",
            install_instructions=instructions,
            can_auto_install=True,
        )

    if sys.platform not in ("darwin", "win32") and not _linux_gui_backend_available():
        return PrerequisiteCheck(
            available=False,
            reason=(
                "pywebview is installed, but no usable GUI toolkit "
                "(GTK+WebKit2GTK or Qt+QtWebEngine) was found"
            ),
            install_instructions=_LINUX_INSTALL_INSTRUCTIONS,
            # pip alone can't fix this -- the missing piece is a system
            # package, not a Python one -- but attempt_auto_install() can
            # still offer to run the distro package manager command.
            can_auto_install=True,
        )

    return PrerequisiteCheck(available=True)


def _linux_package_manager_command() -> Optional[List[str]]:
    """Return the install command for whichever package manager is present.

    Checked in an arbitrary but fixed order; a machine with more than one
    installed (unusual) gets whichever is checked first.
    """
    candidates = {
        "apt-get": [
            "sudo",
            "apt-get",
            "install",
            "-y",
            "python3-gi",
            "python3-gi-cairo",
            "gir1.2-gtk-3.0",
            "gir1.2-webkit2-4.1",
        ],
        "dnf": [
            "sudo",
            "dnf",
            "install",
            "-y",
            "python3-gobject",
            "gtk3",
            "webkit2gtk4.1",
        ],
        "pacman": [
            "sudo",
            "pacman",
            "-S",
            "--noconfirm",
            "python-gobject",
            "gtk3",
            "webkit2gtk-4.1",
        ],
    }
    for binary, command in candidates.items():
        if shutil.which(binary):
            return command
    return None


def attempt_auto_install(
    check: PrerequisiteCheck,
    *,
    confirm: Callable[[str], bool],
    run_command: Callable[[List[str]], int] = lambda cmd: subprocess.run(cmd).returncode,
) -> bool:
    """Try to install what check_prerequisites() found missing.

    Every command runs only after the caller-supplied confirm() returns
    True for it -- this never installs anything the user hasn't explicitly
    approved, and a Linux system-package install is a *separate* prompt from
    the pip install, since one is a safe, user-scoped operation and the
    other runs a privileged command via sudo. run_command is a seam for
    tests; the real caller lets it inherit the terminal so sudo can prompt
    for a password normally.

    Returns True if pywebview now imports successfully (not a guarantee the
    Linux GUI backend is fully usable -- check_prerequisites() should be
    re-run to confirm that).
    """
    if not _pywebview_importable():
        pip_cmd = [sys.executable, "-m", "pip", "install", "pywebview"]
        if confirm(f"Run `{' '.join(pip_cmd)}` now?"):
            run_command(pip_cmd)

    if sys.platform not in ("darwin", "win32") and not _linux_gui_backend_available():
        system_cmd = _linux_package_manager_command()
        if system_cmd is None:
            print(
                "Could not detect apt-get, dnf, or pacman on this system; "
                "install the GTK+WebKit2GTK packages for your distro manually."
            )
        elif confirm(f"Run `{' '.join(system_cmd)}` now? (will prompt for sudo password)"):
            run_command(system_cmd)

    return _pywebview_importable()


def _cookie_string_from_pywebview_cookies(cookies) -> str:
    """Flatten pywebview's get_cookies() result into a Cookie-header string.

    Each item is an http.cookies.SimpleCookie holding exactly one morsel
    (that's how every pywebview GUI backend builds them -- see e.g.
    webview/platforms/cocoa.py's get_cookies -- one SimpleCookie per
    browser cookie, not one SimpleCookie for the whole jar). Iterating a
    SimpleCookie yields its morsel names.
    """
    parts = []
    for simple_cookie in cookies:
        for name in simple_cookie:
            parts.append(f"{name}={simple_cookie[name].value}")
    return "; ".join(parts)


def _cookie_names(cookies) -> set:
    names = set()
    for simple_cookie in cookies:
        names.update(simple_cookie.keys())
    return names


def login_with_embedded_browser(
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> Optional[str]:
    """Open the login window and return a Cookie-header string once signed in.

    Returns None if the user closes the window before REQUIRED_COOKIE_NAMES
    all appear (cancelled, or something about the flow this didn't
    anticipate), or if pywebview raises for any reason (missing backend at
    start() time despite check_prerequisites() passing, e.g.).

    Must be called before any asyncio event loop is running: pywebview owns
    the calling thread's event loop on macOS and Windows, so this is a
    plain blocking function, not a coroutine. login_setup.py calls it before
    entering its async flow.
    """
    import webview

    captured: dict = {"cookie_string": None}

    def on_loaded() -> None:
        window = webview.windows[0]
        try:
            cookies = window.get_cookies()
        except Exception:
            return
        if REQUIRED_COOKIE_NAMES <= _cookie_names(cookies):
            captured["cookie_string"] = _cookie_string_from_pywebview_cookies(cookies)
            window.destroy()

    window = webview.create_window(
        "Sign in to Monarch Money",
        MONARCH_LOGIN_URL,
        width=440,
        height=720,
    )
    window.events.loaded += on_loaded

    try:
        webview.start(private_mode=True)
    except Exception as e:
        print(f"❌ Embedded browser window failed to start: {e}")
        return None

    return captured["cookie_string"]
