"""Tests for the embedded-browser login prerequisite checks and orchestration.

The actual GUI window (webview.start()) needs a real display and a real
WebView2/WebKit/WebKitGTK backend, so it isn't exercised end to end here.
What is tested: the availability checks, the auto-install confirmation
gating, the cookie-formatting helpers, and login_with_embedded_browser()'s
orchestration logic against a fully faked `webview` module.
"""

import sys
import types
from http.cookies import SimpleCookie
from unittest.mock import MagicMock

import pytest

from monarch_mcp_server import browser_login as bl


class TestCheckPrerequisitesPywebviewMissing:
    def test_reports_unavailable_when_pywebview_not_importable(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        result = bl.check_prerequisites()
        assert result.available is False
        assert "not installed" in result.reason
        assert result.can_auto_install is True
        assert result.install_instructions is not None

    def test_macos_instructions_mention_webkit(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "darwin")
        result = bl.check_prerequisites()
        assert "WebKit" in result.install_instructions

    def test_windows_instructions_mention_webview2(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "win32")
        result = bl.check_prerequisites()
        assert "WebView2" in result.install_instructions

    def test_linux_instructions_mention_apt(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "linux")
        result = bl.check_prerequisites()
        assert "apt install" in result.install_instructions


class TestCheckPrerequisitesPywebviewInstalled:
    def test_macos_available_without_linux_backend_check(self, monkeypatch):
        """macOS/Windows never need the Linux GUI-toolkit probe."""
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: True)
        monkeypatch.setattr(bl.sys, "platform", "darwin")
        monkeypatch.setattr(
            bl,
            "_linux_gui_backend_available",
            lambda: (_ for _ in ()).throw(AssertionError("should not be called")),
        )
        result = bl.check_prerequisites()
        assert result.available is True

    def test_linux_unavailable_without_gui_toolkit(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: True)
        monkeypatch.setattr(bl.sys, "platform", "linux")
        monkeypatch.setattr(bl, "_linux_gui_backend_available", lambda: False)
        result = bl.check_prerequisites()
        assert result.available is False
        assert "GUI toolkit" in result.reason
        assert result.can_auto_install is True

    def test_linux_available_with_gui_toolkit(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: True)
        monkeypatch.setattr(bl.sys, "platform", "linux")
        monkeypatch.setattr(bl, "_linux_gui_backend_available", lambda: True)
        result = bl.check_prerequisites()
        assert result.available is True


class TestAttemptAutoInstall:
    def test_declining_pip_install_skips_the_command(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "darwin")
        check = bl.check_prerequisites()

        run_command = MagicMock(return_value=0)
        bl.attempt_auto_install(check, confirm=lambda _q: False, run_command=run_command)

        run_command.assert_not_called()

    def test_confirming_pip_install_runs_it(self, monkeypatch):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "darwin")
        check = bl.check_prerequisites()

        run_command = MagicMock(return_value=0)
        bl.attempt_auto_install(check, confirm=lambda _q: True, run_command=run_command)

        run_command.assert_called_once()
        cmd = run_command.call_args.args[0]
        assert cmd[:3] == [sys.executable, "-m", "pip"]
        assert "pywebview" in cmd

    def test_linux_system_package_prompt_is_separate_from_pip_prompt(self, monkeypatch):
        """Declining the pip prompt must not skip the system-package prompt,
        and vice versa -- they are different trust levels (user-scoped vs sudo)."""
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: False)
        monkeypatch.setattr(bl, "_linux_gui_backend_available", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "linux")
        monkeypatch.setattr(bl.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None)
        check = bl.check_prerequisites()

        prompts_seen = []

        def confirm(question):
            prompts_seen.append(question)
            return "sudo" not in question  # accept pip, decline the sudo one

        run_command = MagicMock(return_value=0)
        bl.attempt_auto_install(check, confirm=confirm, run_command=run_command)

        assert len(prompts_seen) == 2
        run_command.assert_called_once()  # only the pip install ran
        assert run_command.call_args.args[0][:3] == [sys.executable, "-m", "pip"]

    def test_linux_no_known_package_manager_prints_manual_note(self, monkeypatch, capsys):
        monkeypatch.setattr(bl, "_pywebview_importable", lambda: True)
        monkeypatch.setattr(bl, "_linux_gui_backend_available", lambda: False)
        monkeypatch.setattr(bl.sys, "platform", "linux")
        monkeypatch.setattr(bl.shutil, "which", lambda _name: None)
        check = bl.check_prerequisites()

        run_command = MagicMock(return_value=0)
        bl.attempt_auto_install(check, confirm=lambda _q: True, run_command=run_command)

        run_command.assert_not_called()
        assert "manually" in capsys.readouterr().out

    def test_returns_final_importability(self, monkeypatch):
        monkeypatch.setattr(bl.sys, "platform", "darwin")
        calls = {"n": 0}

        def fake_importable():
            calls["n"] += 1
            return calls["n"] > 1  # not importable on the check, importable after "install"

        monkeypatch.setattr(bl, "_pywebview_importable", fake_importable)
        check = bl.check_prerequisites()
        assert check.available is False

        result = bl.attempt_auto_install(
            check, confirm=lambda _q: True, run_command=MagicMock(return_value=0)
        )
        assert result is True


class TestLinuxPackageManagerCommand:
    def test_prefers_apt_get_when_present(self, monkeypatch):
        monkeypatch.setattr(
            bl.shutil, "which", lambda name: "/usr/bin/apt-get" if name == "apt-get" else None
        )
        cmd = bl._linux_package_manager_command()
        assert cmd[:2] == ["sudo", "apt-get"]

    def test_falls_back_to_dnf(self, monkeypatch):
        monkeypatch.setattr(
            bl.shutil, "which", lambda name: "/usr/bin/dnf" if name == "dnf" else None
        )
        cmd = bl._linux_package_manager_command()
        assert cmd[:2] == ["sudo", "dnf"]

    def test_falls_back_to_pacman(self, monkeypatch):
        monkeypatch.setattr(
            bl.shutil, "which", lambda name: "/usr/bin/pacman" if name == "pacman" else None
        )
        cmd = bl._linux_package_manager_command()
        assert cmd[:2] == ["sudo", "pacman"]

    def test_none_found_returns_none(self, monkeypatch):
        monkeypatch.setattr(bl.shutil, "which", lambda _name: None)
        assert bl._linux_package_manager_command() is None


class TestCookieFormatting:
    def _cookie(self, name, value):
        c = SimpleCookie()
        c[name] = value
        return c

    def test_flattens_to_semicolon_separated_cookie_header(self):
        cookies = [self._cookie("session_id", "abc123"), self._cookie("csrftoken", "xyz789")]
        result = bl._cookie_string_from_pywebview_cookies(cookies)
        assert result == "session_id=abc123; csrftoken=xyz789"

    def test_extracts_all_cookie_names(self):
        cookies = [self._cookie("session_id", "a"), self._cookie("cf_clearance", "b")]
        assert bl._cookie_names(cookies) == {"session_id", "cf_clearance"}

    def test_empty_list_round_trips_cleanly(self):
        assert bl._cookie_string_from_pywebview_cookies([]) == ""
        assert bl._cookie_names([]) == set()


class _FakeEvent:
    """Minimal stand-in for webview's Event: supports += and fires it."""

    def __init__(self):
        self._callbacks = []

    def __iadd__(self, callback):
        self._callbacks.append(callback)
        return self

    def fire(self):
        for cb in self._callbacks:
            cb()


class _FakeWindow:
    def __init__(self, cookies_sequence):
        self.events = types.SimpleNamespace(loaded=_FakeEvent())
        self._cookies_sequence = list(cookies_sequence)
        self.destroyed = False

    def get_cookies(self):
        if self._cookies_sequence:
            return self._cookies_sequence.pop(0)
        return []

    def destroy(self):
        self.destroyed = True


@pytest.fixture
def fake_webview_module(monkeypatch):
    """Install a fake `webview` module and return (module, window_factory).

    login_with_embedded_browser() does `import webview` lazily inside the
    function body, so installing the fake into sys.modules before calling
    it is enough -- same technique test_secure_session.py uses for `keyring`.
    """

    def make(cookies_sequence):
        module = types.ModuleType("webview")
        window = _FakeWindow(cookies_sequence)
        module.windows = [window]
        module.create_window = MagicMock(return_value=window)

        def start(*, private_mode=False):
            # The real webview.start() blocks pumping GUI events until the
            # window is destroyed; the fake instead just fires "loaded"
            # once, synchronously, which is enough to exercise the
            # callback's cookie-check-and-destroy logic.
            window.events.loaded.fire()

        module.start = start
        monkeypatch.setitem(sys.modules, "webview", module)
        return module, window

    return make


class TestLoginWithEmbeddedBrowser:
    def test_returns_cookie_string_once_required_cookies_present(self, fake_webview_module):
        session = SimpleCookie()
        session["session_id"] = "sess-abc"
        csrf = SimpleCookie()
        csrf["csrftoken"] = "csrf-xyz"
        module, window = fake_webview_module([[session, csrf]])

        result = bl.login_with_embedded_browser()

        assert result == "session_id=sess-abc; csrftoken=csrf-xyz"
        assert window.destroyed is True
        module.create_window.assert_called_once()
        _args, kwargs = module.create_window.call_args
        assert module.create_window.call_args.args[1] == bl.MONARCH_LOGIN_URL

    def test_does_not_destroy_window_when_cookies_incomplete(self, fake_webview_module):
        """Only session_id present (no csrftoken yet) -- must keep waiting,
        not treat a partial cookie set as login completion."""
        session_only = SimpleCookie()
        session_only["session_id"] = "sess-abc"
        module, window = fake_webview_module([[session_only]])

        result = bl.login_with_embedded_browser()

        assert result is None
        assert window.destroyed is False

    def test_webview_start_exception_returns_none(self, monkeypatch):
        module = types.ModuleType("webview")
        window = _FakeWindow([])
        module.windows = [window]
        module.create_window = MagicMock(return_value=window)

        def start(*, private_mode=False):
            raise RuntimeError("no GUI backend available")

        module.start = start
        monkeypatch.setitem(sys.modules, "webview", module)

        assert bl.login_with_embedded_browser() is None
