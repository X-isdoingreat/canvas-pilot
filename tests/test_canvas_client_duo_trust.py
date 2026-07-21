# SPDX-License-Identifier: AGPL-3.0-or-later
"""Offline tests for Duo trusted-device prompt handling."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _load_canvas_client(monkeypatch):
    monkeypatch.setenv("CANVAS_AUTH", "token")
    monkeypatch.setenv("CANVAS_TOKEN", "test-token")
    monkeypatch.setenv("CANVAS_BASE", "https://canvas.example.edu/api/v1")
    sys.modules.pop("src.canvas_client", None)
    return importlib.import_module("src.canvas_client")


class _FakeElement:
    def __init__(self, visible: bool = True) -> None:
        self.visible = visible
        self.clicked_timeout = None

    def is_visible(self) -> bool:
        return self.visible

    def click(self, timeout=None) -> None:
        self.clicked_timeout = timeout


class _FakeLocator:
    def __init__(self, element: _FakeElement | None) -> None:
        self._element = element

    def count(self) -> int:
        return 1 if self._element is not None else 0

    @property
    def first(self):
        return self._element


class _FakeFrame:
    def __init__(self, selector: str, element: _FakeElement | None) -> None:
        self._selector = selector
        self._element = element

    def locator(self, selector: str) -> _FakeLocator:
        if selector == self._selector:
            return _FakeLocator(self._element)
        return _FakeLocator(None)


class _FakePage:
    def __init__(self, frames) -> None:
        self.frames = frames


def test_clicks_visible_duo_trusted_device_prompt(monkeypatch):
    cv = _load_canvas_client(monkeypatch)
    element = _FakeElement(visible=True)
    selector = cv._DUO_TRUST_DEVICE_SELECTORS[0]
    page = _FakePage([_FakeFrame(selector, element)])

    assert cv._try_click_duo_trust_device(page) is True
    assert element.clicked_timeout == 1000


def test_ignores_hidden_duo_trusted_device_prompt(monkeypatch):
    cv = _load_canvas_client(monkeypatch)
    element = _FakeElement(visible=False)
    selector = cv._DUO_TRUST_DEVICE_SELECTORS[0]
    page = _FakePage([_FakeFrame(selector, element)])

    assert cv._try_click_duo_trust_device(page) is False
    assert element.clicked_timeout is None


def test_duo_trusted_device_wait_is_one_minute(monkeypatch):
    cv = _load_canvas_client(monkeypatch)

    assert cv.DUO_TRUST_DEVICE_WAIT_SEC == 60


def test_returns_false_when_duo_trusted_device_prompt_absent(monkeypatch):
    cv = _load_canvas_client(monkeypatch)
    page = _FakePage([_FakeFrame("button:has-text(\"Other\")", None)])

    assert cv._try_click_duo_trust_device(page) is False
