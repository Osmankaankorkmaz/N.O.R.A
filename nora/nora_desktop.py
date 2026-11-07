"""Explicit, reversible window-position snapshots (primarily Windows/pygetwindow).

This never closes, opens, minimizes or maximizes applications. It only restores
positions/sizes of still-open windows with matching titles, after UI confirmation.
Unsupported platforms fail honestly instead of pretending to rearrange windows.
"""

from __future__ import annotations

import sys
from typing import Any


class DesktopLayouts:
    @staticmethod
    def _windows() -> list[Any]:
        if sys.platform != "win32":
            raise ValueError(
                "Pencere düzeni kaydetme/geri yükleme şu an Windows'ta destekleniyor senpai. Diğer platformlarda pencere yöneticisi izinleri farklı. 🖥️"
            )
        try:
            import pygetwindow as gw
        except ImportError as exc:
            raise ValueError(
                "Pencere düzeni için pygetwindow/pyautogui kurulumunu kontrol et senpai."
            ) from exc
        return list(gw.getAllWindows())

    def snapshot(self) -> list[dict[str, Any]]:
        entries = []
        for window in self._windows():
            try:
                title = str(window.title or "").strip()
                if (
                    not title
                    or title.startswith("Nora")
                    or not window.visible
                    or window.isMinimized
                    or window.isMaximized
                ):
                    continue
                if window.width < 120 or window.height < 120:
                    continue
                entries.append(
                    {
                        "title": title[:240],
                        "left": int(window.left),
                        "top": int(window.top),
                        "width": int(window.width),
                        "height": int(window.height),
                    }
                )
            except (AttributeError, TypeError, ValueError, OSError):
                continue
            if len(entries) >= 40:
                break
        if not entries:
            raise ValueError(
                "Kaydedilecek normal boyutlu pencere bulamadım; simge durumundaki pencereleri kaydetmiyorum."
            )
        return entries

    def preview(self, entries: list[dict[str, Any]]) -> str:
        return "\n".join(
            f"• {entry['title']} → ({entry['left']}, {entry['top']}) {entry['width']}×{entry['height']}"
            for entry in entries[:40]
        )

    def restore(self, entries: list[dict[str, Any]]) -> str:
        windows = self._windows()
        moved, skipped = 0, 0
        for entry in entries[:40]:
            matches = [
                window
                for window in windows
                if str(getattr(window, "title", "")) == entry.get("title")
            ]
            if len(matches) != 1:
                skipped += 1
                continue
            window = matches[0]
            try:
                if window.isMinimized:
                    window.restore()
                if window.isMaximized:
                    skipped += 1
                    continue
                window.moveTo(int(entry["left"]), int(entry["top"]))
                window.resizeTo(int(entry["width"]), int(entry["height"]))
                moved += 1
            except (AttributeError, TypeError, ValueError, KeyError, OSError):
                skipped += 1
        return f"{moved} pencereyi eski konumuna aldım senpai." + (
            f" {skipped} pencere kapanmış, başlığı değişmiş veya desteklenmiyor; onlara dokunmadım."
            if skipped
            else ""
        )
