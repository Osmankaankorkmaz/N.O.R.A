"""Desktop tools with lazy optional imports and explicit safety boundaries.

Nothing here uses ``shell=True``.  Timers emit a Qt signal so a Python timer
thread never touches a widget.  Camera frames are released immediately after a
capture; screenshots and camera images are not written to disk by Nora.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlsplit

from PyQt5.QtCore import QObject, pyqtSignal

from .nora_personality import CommandError, normalize_command
from .nora_store import NoraStore

logger = logging.getLogger(__name__)


class NoraTools(QObject):
    timer_finished = pyqtSignal(str)

    APP_ALIASES = {
        "not defteri": "notepad",
        "notepad": "notepad",
        "chrome": "chrome",
        "google chrome": "chrome",
        "hesap makinesi": "calculator",
        "calculator": "calculator",
        "paint": "paint",
        "cmd": "cmd",
        "terminal": "cmd",
        "spotify": "spotify",
        "discord": "discord",
        "vscode": "vscode",
        "vs code": "vscode",
        "edge": "edge",
        "word": "word",
        "excel": "excel",
        "ayarlar": "settings",
        "settings": "settings",
        "görev yöneticisi": "task_manager",
        "task manager": "task_manager",
        "dosya yöneticisi": "file_manager",
        "file manager": "file_manager",
        "files": "file_manager",
    }

    def __init__(
        self,
        *,
        allow_code: bool | None = None,
        store: NoraStore | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.allow_code = (
            (os.getenv("NORA_ALLOW_CODE", "0") == "1")
            if allow_code is None
            else allow_code
        )
        self.store = store if store is not None else NoraStore()
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.RLock()
        self._camera_lock = threading.Lock()
        self._camera: Any = None
        self._closed = False
        self._shutdown_pending = False

    # ------------------------------------------------------------------ screen
    def screenshot(self) -> str | None:
        """Return a JPEG/base64 screenshot, at most 1024×576, or None."""
        try:
            import pyautogui
            from PIL import Image

            image = pyautogui.screenshot()
            image = image.convert("RGB")
            image.thumbnail((1024, 576), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=85, optimize=True)
            return base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception as exc:
            logger.warning("Ekran görüntüsü alınamadı: %s", type(exc).__name__)
            return None

    def type_text(self, text: str) -> str:
        if not isinstance(text, str) or not text or len(text) > 5000:
            return "Yazılacak metin 1-5000 karakter olmalı senpai."
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            if text.isascii():
                pyautogui.write(text, interval=0.012)
                return "Metni etkin pencereye yazdım senpai. ⌨️"
            import pyperclip

            pyperclip.copy(text)
            pyautogui.hotkey("command" if sys.platform == "darwin" else "ctrl", "v")
            return "Türkçe karakterleri panoya yapıştırarak yazdım; pano içeriği değişti senpai. ⌨️"
        except Exception as exc:
            logger.warning("Metin yazılamadı: %s", type(exc).__name__)
            return "Pff, metni yazamadım. Etkin pencereyi ve masaüstü erişimini kontrol et senpai."

    def clipboard_copy(self, text: str) -> str:
        try:
            import pyperclip

            pyperclip.copy(str(text))
            return "Panoya kopyaladım senpai. 📋"
        except Exception as exc:
            logger.warning("Panoya kopyalanamadı: %s", type(exc).__name__)
            return "Panoya erişemedim senpai. Bir pano aracı kurulu mu?"

    def clipboard_paste(self) -> str:
        try:
            import pyperclip

            return pyperclip.paste() or ""
        except Exception:
            return ""

    # ------------------------------------------------------------------ camera
    def capture_camera(self) -> str | None:
        """Capture one frame and release the camera in every exit path."""
        if self._closed:
            return None
        with self._camera_lock:
            camera = None
            try:
                import cv2

                backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
                camera = cv2.VideoCapture(0, backend)
                self._camera = camera
                if not camera.isOpened():
                    return None
                camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                frame = None
                for _ in range(8):  # let exposure/white balance settle
                    ok, candidate = camera.read()
                    if ok and candidate is not None:
                        frame = candidate
                if frame is None:
                    return None
                h, w = frame.shape[:2]
                scale = min(640 / w, 480 / h, 1.0)
                if scale < 1:
                    frame = cv2.resize(
                        frame,
                        (max(1, int(w * scale)), max(1, int(h * scale))),
                        interpolation=cv2.INTER_AREA,
                    )
                ok, encoded = cv2.imencode(
                    ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                )
                return (
                    base64.b64encode(encoded.tobytes()).decode("ascii") if ok else None
                )
            except Exception as exc:
                logger.warning("Kamera açılamadı: %s", type(exc).__name__)
                return None
            finally:
                if camera is not None:
                    try:
                        camera.release()
                    except Exception:
                        pass
                self._camera = None

    # --------------------------------------------------------------------- apps
    def _app_candidates(self, app: str) -> list[list[str]]:
        system = platform.system()
        if system == "Windows":
            pf = os.environ.get("ProgramFiles", r"C:\Program Files")
            pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
            local = os.environ.get("LOCALAPPDATA", "")
            return {
                "notepad": [["notepad.exe"]],
                "chrome": [
                    [str(Path(pf) / "Google/Chrome/Application/chrome.exe")],
                    [str(Path(pf86) / "Google/Chrome/Application/chrome.exe")],
                    [str(Path(local) / "Google/Chrome/Application/chrome.exe")],
                    ["chrome"],
                ],
                "calculator": [["calc.exe"]],
                "paint": [["mspaint.exe"], ["mspaint"]],
                "cmd": [["cmd.exe"]],
                "spotify": [[str(Path(local) / "Spotify/Spotify.exe")], ["spotify"]],
                "discord": [
                    [
                        str(Path(local) / "Discord/Update.exe"),
                        "--processStart",
                        "Discord.exe",
                    ]
                ],
                "vscode": [
                    ["code"],
                    [str(Path(local) / "Programs/Microsoft VS Code/Code.exe")],
                ],
                "edge": [
                    ["msedge"],
                    [str(Path(pf86) / "Microsoft/Edge/Application/msedge.exe")],
                ],
                "word": [["winword"]],
                "excel": [["excel"]],
                "settings": [["ms-settings:"]],
                "task_manager": [["taskmgr.exe"]],
                "file_manager": [["explorer.exe"]],
            }.get(app, [])
        if system == "Darwin":
            names = {
                "notepad": "TextEdit",
                "chrome": "Google Chrome",
                "calculator": "Calculator",
                "paint": "Preview",
                "cmd": "Terminal",
                "spotify": "Spotify",
                "discord": "Discord",
                "vscode": "Visual Studio Code",
                "edge": "Microsoft Edge",
                "word": "Microsoft Word",
                "excel": "Microsoft Excel",
                "settings": "System Settings",
                "task_manager": "Activity Monitor",
                "file_manager": "Finder",
            }
            return [["open", "-a", names[app]]] if app in names else []
        return {
            "notepad": [["gedit"], ["mousepad"], ["kate"]],
            "chrome": [["google-chrome"], ["chromium"], ["chromium-browser"]],
            "calculator": [["gnome-calculator"], ["galculator"], ["kcalc"]],
            "paint": [["pinta"], ["krita"], ["gimp"]],
            "cmd": [["gnome-terminal"], ["konsole"], ["xfce4-terminal"], ["xterm"]],
            "spotify": [["spotify"]],
            "discord": [["discord"]],
            "vscode": [["code"]],
            "edge": [["microsoft-edge"]],
            "word": [["libreoffice", "--writer"]],
            "excel": [["libreoffice", "--calc"]],
            "settings": [["gnome-control-center"]],
            "task_manager": [["gnome-system-monitor"], ["ksysguard"]],
            "file_manager": [["xdg-open", str(Path.home())]],
        }.get(app, [])

    def open_app(self, app: str) -> str:
        raw = str(app).strip()
        key = self.APP_ALIASES.get(raw.lower(), raw.lower())
        candidates = self._app_candidates(key)
        if not candidates:
            # Unknown names may only be a single executable on PATH, never a
            # shell snippet, path, option, or command with arguments.
            if not re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9_. -]{0,79}", raw
            ) or raw.startswith("-"):
                return "Bu uygulama adını güvenli biçimde çözemedim senpai. Bilinen bir ad söyle. 😾"
            resolved = shutil.which(raw)
            candidates = [[resolved]] if resolved else []
        for args in candidates:
            if args == ["ms-settings:"] and sys.platform == "win32":
                try:
                    os.startfile("ms-settings:")  # type: ignore[attr-defined]
                    return "Ayarları açtım senpai. ⚙️"
                except OSError:
                    continue
            executable = args[0]
            resolved = (
                executable
                if Path(executable).is_absolute() and Path(executable).exists()
                else shutil.which(executable)
            )
            if not resolved:
                continue
            try:
                kwargs: dict[str, Any] = {
                    "stdout": subprocess.DEVNULL,
                    "stderr": subprocess.DEVNULL,
                }
                if os.name == "posix":
                    kwargs["start_new_session"] = True
                subprocess.Popen([resolved, *args[1:]], shell=False, **kwargs)
                return f"{raw} başlattım senpai~ Heh, rica ederim. 🐾"
            except Exception as exc:
                logger.warning("Uygulama başlatılamadı %s: %s", raw, type(exc).__name__)
        return (
            f"{raw} bulunamadı veya başlatılamadı senpai. Kurulu olduğundan emin ol. 🐾"
        )

    @staticmethod
    def _safe_url(url: str) -> str:
        value = str(url).strip()
        if (
            not value
            or len(value) > 2048
            or any(c.isspace() or ord(c) < 32 for c in value)
        ):
            raise CommandError("Geçersiz URL.")
        scheme = re.match(r"^([A-Za-z][A-Za-z0-9+.-]*):", value)
        if scheme and scheme.group(1).lower() not in {"http", "https"}:
            raise CommandError("Yalnızca http/https adresleri açılabilir.")
        if "://" not in value:
            value = "https://" + value
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
        ):
            raise CommandError("Yalnızca http/https adresleri açılabilir.")
        return value

    def open_url(self, url: str) -> str:
        try:
            safe = self._safe_url(url)
            if not webbrowser.open(safe, new=2):
                return "Tarayıcı açılamadı senpai. Varsayılan tarayıcını kontrol et."
            return "Bağlantıyı tarayıcıda açtım senpai. 🔗"
        except (CommandError, ValueError):
            return "Bu adres güvenli görünmüyor senpai. http veya https ile bir link ver. 😾"
        except Exception as exc:
            logger.warning("URL açılamadı: %s", type(exc).__name__)
            return "Bağlantıyı açamadım senpai."

    def search(self, query: str) -> str:
        query = str(query).strip()[:300]
        if not query:
            return "Ne arayım senpai? Bir şey yaz. 🐾"
        return self.open_url("https://www.google.com/search?q=" + quote_plus(query))

    def play_music(self, query: str) -> str:
        query = str(query).strip()[:300]
        if not query:
            return "Ne dinlemek istersin senpai?"
        result = self.open_url(
            "https://www.youtube.com/results?search_query=" + quote_plus(query)
        )
        return result.replace("Bağlantıyı", "YouTube aramasını") + " 🎧"

    def spotify_search(self, query: str) -> str:
        query = str(query).strip()[:200] or "lofi hip hop"
        result = self.open_url("https://open.spotify.com/search/" + quote(query))
        return result.replace("Bağlantıyı", "Spotify aramasını") + " 🎧"

    def video_search(self, query: str) -> str:
        query = str(query).strip()[:200] or "sevimli kediler"
        result = self.open_url(
            "https://www.youtube.com/results?search_query=" + quote_plus(query)
        )
        return result.replace("Bağlantıyı", "YouTube video aramasını") + " 🍿"

    # ------------------------------------------------------------------- volume
    def set_volume(self, level: int | float) -> str:
        try:
            level = max(0, min(100, float(level)))
        except (TypeError, ValueError):
            return "Ses seviyesi 0-100 olmalı senpai."
        try:
            if sys.platform == "win32":
                self._windows_volume(level)
            elif sys.platform == "darwin":
                subprocess.run(
                    ["osascript", "-e", f"set volume output volume {round(level)}"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            else:
                if shutil.which("pactl"):
                    subprocess.run(
                        [
                            "pactl",
                            "set-sink-volume",
                            "@DEFAULT_SINK@",
                            f"{round(level)}%",
                        ],
                        check=True,
                        capture_output=True,
                        timeout=5,
                    )
                elif shutil.which("amixer"):
                    subprocess.run(
                        ["amixer", "-D", "pulse", "sset", "Master", f"{round(level)}%"],
                        check=True,
                        capture_output=True,
                        timeout=5,
                    )
                else:
                    return "Ses denetimi için PulseAudio/ALSA aracı bulunamadı senpai."
            return f"Sesi %{round(level)} yaptım senpai. 🔊"
        except Exception as exc:
            logger.warning("Ses ayarlanamadı: %s", type(exc).__name__)
            return "Sesi ayarlayamadım senpai. Ses sunucusunu kontrol et. 🐾"

    @staticmethod
    def _windows_volume(level: float) -> None:
        """Absolute master volume through Core Audio COM (no shell trickery)."""
        import ctypes

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_uint32),
                ("Data2", ctypes.c_uint16),
                ("Data3", ctypes.c_uint16),
                ("Data4", ctypes.c_ubyte * 8),
            ]

            def __init__(self, value: str):
                raw = uuid.UUID(value).bytes
                super().__init__(
                    int.from_bytes(raw[:4], "little"),
                    int.from_bytes(raw[4:6], "little"),
                    int.from_bytes(raw[6:8], "little"),
                    (ctypes.c_ubyte * 8)(*raw[8:16]),
                )

        def call(
            obj: Any,
            index: int,
            *args: Any,
            argtypes: tuple = (),
            restype: Any = ctypes.c_long,
        ) -> Any:
            table = ctypes.cast(
                obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
            ).contents
            prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
            return prototype(table[index])(obj, *args)

        ole32 = ctypes.windll.ole32  # type: ignore[attr-defined]
        hr = ole32.CoInitializeEx(None, 2)
        uninitialize = hr in (0, 1)
        enumerator = device = endpoint = ctypes.c_void_p()
        try:
            clsid = GUID("BCDE0395-E52F-467C-8E3D-C4579291692E")
            iid_enum = GUID("A95664D2-9614-4F35-A746-DE8DB63617A6")
            iid_volume = GUID("5CDF2C82-841E-4546-9722-0CF74078229A")
            result = ole32.CoCreateInstance(
                ctypes.byref(clsid),
                None,
                23,
                ctypes.byref(iid_enum),
                ctypes.byref(enumerator),
            )
            if result < 0:
                raise OSError(f"COM HRESULT {result:#x}")
            result = call(
                enumerator,
                4,
                0,
                1,
                ctypes.byref(device),
                argtypes=(ctypes.c_int, ctypes.c_int, ctypes.c_void_p),
            )
            if result < 0:
                raise OSError(f"COM HRESULT {result:#x}")
            result = call(
                device,
                3,
                ctypes.byref(iid_volume),
                23,
                None,
                ctypes.byref(endpoint),
                argtypes=(
                    ctypes.c_void_p,
                    ctypes.c_uint32,
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                ),
            )
            if result < 0:
                raise OSError(f"COM HRESULT {result:#x}")
            result = call(
                endpoint,
                8,
                ctypes.c_float(level / 100.0),
                None,
                argtypes=(ctypes.c_float, ctypes.c_void_p),
            )
            if result < 0:
                raise OSError(f"COM HRESULT {result:#x}")
        finally:
            for obj in (endpoint, device, enumerator):
                if obj:
                    call(obj, 2, restype=ctypes.c_ulong)
            if uninitialize:
                ole32.CoUninitialize()

    def set_brightness(self, level: int | float) -> str:
        try:
            level = max(0, min(100, int(float(level))))
            import screen_brightness_control as sbc

            sbc.set_brightness(level)
            return f"Parlaklığı %{level} yaptım senpai. ☀️"
        except ImportError:
            return "Parlaklık modülü kurulu değil senpai: screen-brightness-control. 🐾"
        except Exception as exc:
            logger.warning("Parlaklık ayarlanamadı: %s", type(exc).__name__)
            return "Bu ekranda parlaklığı ayarlayamadım senpai. Harici ekranlarda destek değişebilir."

    # ------------------------------------------------------------ system health
    def system_info(self) -> str:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=0.15)
            ram = psutil.virtual_memory()
            disk = psutil.disk_usage(str(Path.home().anchor or "/"))
            lines = [
                "Sistem durumun senpai~ 💻",
                f"🧠 CPU: %{cpu:.1f}",
                f"🧩 RAM: {ram.used / 2**30:.1f} / {ram.total / 2**30:.1f} GB (%{ram.percent:.1f})",
                f"💾 Disk: %{disk.percent:.1f}",
            ]
            battery = psutil.sensors_battery()
            if battery is not None:
                status = "şarjda" if battery.power_plugged else "pilde"
                lines.append(f"🔋 Batarya: %{battery.percent:.0f} ({status})")
            else:
                lines.append("🔋 Batarya: bulunamadı / masaüstü")
            lines.extend(
                [
                    f"🖥️ Sistem: {platform.system()} {platform.release()}",
                    f"📅 Tarih: {datetime.now():%d.%m.%Y %H:%M}",
                ]
            )
            return "\n".join(lines)
        except Exception as exc:
            logger.warning("Sistem bilgisi alınamadı: %s", type(exc).__name__)
            return (
                "Sistem bilgisini okuyamadım senpai. psutil kurulumunu kontrol et. 🐾"
            )

    def check_system_health(self) -> dict[str, Any] | None:
        try:
            import psutil

            cpu = psutil.cpu_percent(interval=None)
            if cpu > 90:
                return {
                    "kind": "cpu",
                    "value": cpu,
                    "message": f"Senpai, CPU %{cpu:.0f}! Biraz nefes aldıralım mı? 😾",
                }
            ram = psutil.virtual_memory().percent
            if ram > 90:
                return {
                    "kind": "ram",
                    "value": ram,
                    "message": f"RAM %{ram:.0f} dolu senpai. Pff, biraz yer açsak iyi olur. 🧩",
                }
            battery = psutil.sensors_battery()
            if (
                battery is not None
                and battery.percent < 15
                and not battery.power_plugged
            ):
                return {
                    "kind": "battery",
                    "value": battery.percent,
                    "message": f"Batarya %{battery.percent:.0f} senpai! Şarja tak, beni de merakta bırakma. 🔋",
                }
        except Exception:
            logger.debug("Sistem sağlık kontrolü yapılamadı", exc_info=True)
        return None

    def shutdown(self) -> str:
        """Schedule a cancellable shutdown 60 seconds from now (UI confirms)."""
        try:
            args = (
                ["shutdown", "/s", "/t", "60"]
                if sys.platform == "win32"
                else ["shutdown", "-h", "+1"]
            )
            subprocess.run(
                args, shell=False, check=True, capture_output=True, timeout=5
            )
            self._shutdown_pending = True
            return "Bilgisayar 60 saniye sonra kapanacak senpai. İptal etmek için 'kapatmayı iptal et' de. ⏰"
        except Exception as exc:
            logger.warning("Kapatma planlanamadı: %s", type(exc).__name__)
            return "Kapatma planlayamadım senpai. Yetki gerekebilir; komut çalıştırılmadı. 🐾"

    def cancel_shutdown(self) -> str:
        if not self._shutdown_pending:
            return "Bekleyen bir kapatma işi yok senpai. Rahat ol. 🐾"
        try:
            args = ["shutdown", "/a"] if sys.platform == "win32" else ["shutdown", "-c"]
            subprocess.run(args, check=True, capture_output=True, timeout=5)
            self._shutdown_pending = False
            return "Kapatmayı iptal ettim senpai. Yanında kalmaya devam. 💜"
        except Exception as exc:
            logger.warning("Kapatma iptal edilemedi: %s", type(exc).__name__)
            return "İptal edemedim senpai; sistem yetkisi gerekebilir. İşletim sisteminin kapatma komutunu kontrol et."

    def lock_screen(self) -> str:
        try:
            if sys.platform == "win32":
                import ctypes

                if not ctypes.windll.user32.LockWorkStation():  # type: ignore[attr-defined]
                    raise OSError("LockWorkStation başarısız")
            elif sys.platform == "darwin":
                subprocess.run(
                    ["pmset", "displaysleepnow"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            elif shutil.which("loginctl"):
                subprocess.run(
                    ["loginctl", "lock-session"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            elif shutil.which("xdg-screensaver"):
                subprocess.run(
                    ["xdg-screensaver", "lock"],
                    check=True,
                    capture_output=True,
                    timeout=5,
                )
            else:
                return "Bu masaüstünde kilit ekranı aracı bulamadım senpai."
            return "Ekranı kilitledim senpai. Dönüşünde buradayım. 🔒"
        except Exception as exc:
            logger.warning("Ekran kilitlenemedi: %s", type(exc).__name__)
            return "Ekranı kilitleyemedim senpai. Oturum kilidi desteğini kontrol et."

    # -------------------------------------------------------------------- notes
    def add_note(self, text: str) -> str:
        text = str(text).strip()
        if not text or len(text) > 2000:
            return "Not 1-2000 karakter olmalı senpai."
        try:
            note = self.store.add_note(text)
        except ValueError as exc:
            return f"Not kaydedilemedi senpai: {exc}"
        return f"Notunu kalıcı olarak aldım senpai: {text} [{note['id']}] 📝"

    def list_notes(self) -> str:
        notes = self.store.notes
        if not notes:
            return "Henüz notun yok senpai. 'Not al: ...' dersen yazarım. 📝"
        lines = ["Notların senpai~ 📝"]
        for index, note in enumerate(notes, 1):
            stamp = datetime.fromisoformat(note["created_at"]).strftime("%d.%m %H:%M")
            lines.append(f"{index}. [{stamp}] {note['text']} [{note.get('id', '')}]")
        return "\n".join(lines)

    @property
    def notes(self) -> list[dict[str, str]]:
        return self.store.notes

    def delete_note(self, identifier: str) -> str:
        try:
            return (
                "Notu sildim senpai."
                if self.store.delete_note(identifier)
                else "Bu notu bulamadım senpai."
            )
        except ValueError as exc:
            return str(exc)

    # ------------------------------------------------------------------ weather
    def weather(self, city: str) -> str:
        city = str(city).strip()[:80]
        if not city:
            return "Hangi şehir senpai? Bir şehir adı söyle. 🌤️"
        try:
            import requests

            response = requests.get(
                f"https://wttr.in/{quote(city, safe='')}",
                params={"format": "j1", "lang": "tr"},
                timeout=5,
                headers={"User-Agent": "Nora-desktop-assistant/1.0"},
            )
            response.raise_for_status()
            current = response.json()["current_condition"][0]
            descriptions = current.get("lang_tr") or current.get("weatherDesc") or []
            description = (
                descriptions[0].get("value", "bilinmiyor")
                if descriptions
                else "bilinmiyor"
            )
            return (
                f"🌤️ {city.title()} hava durumu\n"
                f"{description}, {current['temp_C']}°C (hissedilen {current['FeelsLikeC']}°C)\n"
                f"💧 Nem: %{current['humidity']}  💨 Rüzgâr: {current['windspeedKmph']} km/s\n"
                "Kaynak: wttr.in · Şemsiyeni unutma senpai. 🐾"
            )
        except Exception as exc:
            logger.warning("Hava durumu alınamadı: %s", type(exc).__name__)
            return f"{city.title()} için havaya ulaşamadım senpai. İnterneti veya şehir adını kontrol et. 🌤️"

    # ------------------------------------------------------------------- timers
    def set_timer(
        self, seconds: int | float, message: str = "Süre doldu senpai!"
    ) -> str:
        command = normalize_command(
            {"command": "set_timer", "seconds": seconds, "message": message}
        )
        seconds = command["seconds"]
        message = command["message"]
        timer_id = uuid.uuid4().hex[:8]

        def fire() -> None:
            with self._lock:
                self._timers.pop(timer_id, None)
                closed = self._closed
            if not closed:
                self.timer_finished.emit(message)

        timer = threading.Timer(float(seconds), fire)
        timer.daemon = True
        timer.name = f"nora-reminder-{timer_id}"
        with self._lock:
            if self._closed:
                return "Kapanıyorum senpai, yeni hatırlatıcı kuramam."
            if len(self._timers) >= 50:
                return (
                    "Çok fazla hatırlatıcı var senpai (50). Önce birazını iptal et. ⏰"
                )
            self._timers[timer_id] = timer
            timer.start()
        label = (
            f"{seconds:g} saniye"
            if seconds < 60
            else (
                f"{seconds / 60:g} dakika"
                if seconds < 3600
                else f"{seconds / 3600:g} saat"
            )
        )
        return f"⏰ {label} sonra: {message} [{timer_id}]"

    def cancel_timer(self, timer_id: str) -> str:
        with self._lock:
            timer = self._timers.pop(str(timer_id), None)
        if timer is None:
            return "Bu hatırlatıcıyı bulamadım senpai."
        timer.cancel()
        return "Hatırlatıcıyı iptal ettim senpai. ⏰"

    @property
    def active_timers(self) -> list[str]:
        with self._lock:
            return list(self._timers)

    # --------------------------------------------------------------------- code
    def run_code(self, code: str, language: str = "python") -> str:
        """Explicitly opt-in Python execution; NOT a security sandbox."""
        if not self.allow_code:
            return (
                "Kod çalıştırma kapalı senpai. Açmak için NORA_ALLOW_CODE=1 gerekir; "
                "sonra da her kod için onayını isterim. 😾"
            )
        command = normalize_command(
            {"command": "run_code", "code": code, "language": language}
        )
        env = {"PATH": os.defpath, "PYTHONIOENCODING": "utf-8"}
        if os.name == "nt":
            env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", r"C:\Windows")
        try:
            with tempfile.TemporaryDirectory(prefix="nora-code-") as directory:
                result = subprocess.run(
                    [sys.executable, "-I", "-c", command["code"]],
                    cwd=directory,
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                    shell=False,
                )
            output = (result.stdout or "") + (
                ("\n" + result.stderr) if result.stderr else ""
            )
            output = output.strip()[:4000] or "(çıktı yok)"
            return f"Kod bitti, çıkış kodu {result.returncode} senpai. 💻\n{output}"
        except subprocess.TimeoutExpired:
            return "Kod 10 saniyeyi aştı, durdurdum senpai. Sonsuz döngüye izin yok. 😾"
        except Exception as exc:
            logger.warning("Kod çalıştırılamadı: %s", type(exc).__name__)
            return "Kodu çalıştıramadım senpai. Python kurulumunu kontrol et."

    # ----------------------------------------------------------------- lifecycle
    def close(self) -> None:
        with self._lock:
            self._closed = True
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()
        with self._camera_lock:
            if self._camera is not None:
                try:
                    self._camera.release()
                except Exception:
                    pass
                self._camera = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
