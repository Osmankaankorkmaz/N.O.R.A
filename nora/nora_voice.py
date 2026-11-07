"""Speech output, one-shot Turkish STT and a resilient wake-word listener.

All microphone access is serialized.  The wake listener is a daemon thread and
pauses while Nora speaks or a manual listening request owns the microphone.
Audio is sent to Google Speech Recognition only when listening is enabled; Nora
does not save recordings to disk.  Qt signals marshal results to the UI thread.
"""

from __future__ import annotations

import logging
import queue
import re
import threading
import time
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

_WAKE_RE = re.compile(r"(?<!\w)nora(?!\w)", re.IGNORECASE)
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0000fe00-\U0000fe0f\U0000200d]+"
)
_GOOGLE_ENDPOINT = "https://www.google.com/speech-api/v2/recognize"


def speech_text(text: str) -> str:
    return re.sub(r"\s+", " ", _EMOJI_RE.sub("", text or "")).strip()[:1200]


class NoraVoice(QObject):
    speaking_started = pyqtSignal()
    speaking_finished = pyqtSignal()
    speech_error = pyqtSignal(str)
    voice_error = pyqtSignal(str)
    listening_finished = pyqtSignal(int, str, str)  # request id, transcript, error
    wake_word_detected = pyqtSignal(str)  # words after "Nora", possibly empty

    def __init__(
        self, *, tts_enabled: bool = True, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.tts_enabled = tts_enabled
        self._closed = False
        self._speech_queue: queue.Queue = queue.Queue()
        self._speech_lock = threading.RLock()
        self._speech_pending = 0
        self._speech_generation = 0
        self._tts_stop = threading.Event()
        self._tts_thread: threading.Thread | None = None
        self._engine: Any = None
        self._mic_lock = threading.Lock()
        self._listen_request_lock = threading.Lock()
        self._listening = False
        self._last_listen_error = ""
        self._wake_stop = threading.Event()
        self._wake_thread: threading.Thread | None = None
        self._wake_callback: Callable[[str], None] | None = None
        self._last_wake_error = ""
        self._last_wake_error_at = 0.0

    # --------------------------------------------------------------------- TTS
    @property
    def is_speaking(self) -> bool:
        with self._speech_lock:
            return self._speech_pending > 0

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def wake_word_active(self) -> bool:
        return bool(
            self._wake_thread
            and self._wake_thread.is_alive()
            and not self._wake_stop.is_set()
        )

    def _ensure_tts_thread(self) -> None:
        if self._tts_thread is None or not self._tts_thread.is_alive():
            self._tts_stop.clear()
            self._tts_thread = threading.Thread(
                target=self._tts_worker, name="nora-tts", daemon=True
            )
            self._tts_thread.start()

    def speak(
        self,
        text: str,
        on_start: Callable | None = None,
        on_end: Callable | None = None,
    ) -> bool:
        text = speech_text(text)
        if self._closed or not self.tts_enabled or not text:
            return False
        with self._speech_lock:
            self._speech_pending += 1
            generation = self._speech_generation
        try:
            self._ensure_tts_thread()
            self._speech_queue.put((generation, text, on_start, on_end))
        except Exception as exc:
            with self._speech_lock:
                self._speech_pending = max(0, self._speech_pending - 1)
            logger.warning("TTS thread başlatılamadı: %s", type(exc).__name__)
            self.speech_error.emit("Ses motorunu başlatamadım senpai. 🔊")
            return False
        return True

    def _make_engine(self) -> Any:
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 180)
        engine.setProperty("volume", 0.9)
        try:
            voices = engine.getProperty("voices") or []
            female_words = (
                "zira",
                "hazel",
                "female",
                "woman",
                "zeynep",
                "tuba",
                "seda",
                "sara",
                "elena",
                "samantha",
                "victoria",
                "fiona",
                "karen",
                "moira",
                "tessa",
            )

            def score(voice: Any) -> tuple[int, int, int]:
                identity = (
                    f"{getattr(voice, 'id', '')} {getattr(voice, 'name', '')}".lower()
                )
                languages = " ".join(
                    str(x).lower() for x in (getattr(voice, "languages", []) or [])
                )
                turkish = any(
                    token in identity + languages
                    for token in ("tr-tr", "turkish", "türkçe", "_tr")
                )
                female = (
                    any(word in identity for word in female_words)
                    or "female" in str(getattr(voice, "gender", "")).lower()
                )
                return (int(turkish and female), int(female), int(turkish))

            if voices:
                best = max(voices, key=score)
                if score(best)[1] or score(best)[2]:
                    engine.setProperty("voice", best.id)
        except Exception:
            logger.debug(
                "Ses listesi okunamadı; varsayılan ses kullanılacak.", exc_info=True
            )
        return engine

    def _tts_worker(self) -> None:
        while not self._tts_stop.is_set():
            item = self._speech_queue.get()
            if item is None:
                break
            generation, text, on_start, on_end = item
            try:
                with self._speech_lock:
                    current = generation == self._speech_generation and not self._closed
                if not current:
                    continue
                if self._engine is None:
                    self._engine = self._make_engine()
                self.speaking_started.emit()
                if on_start:
                    try:
                        on_start()
                    except Exception:
                        logger.exception("TTS başlangıç callback hatası")
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as exc:
                logger.warning("Ses motoru hatası: %s", type(exc).__name__)
                self.speech_error.emit(
                    "Ses motorunu açamadım senpai. Windows SAPI veya espeak-ng kurulumunu kontrol et. 🔊"
                )
                self._engine = None
            finally:
                if on_end:
                    try:
                        on_end()
                    except Exception:
                        logger.exception("TTS bitiş callback hatası")
                with self._speech_lock:
                    self._speech_pending = max(0, self._speech_pending - 1)
                self.speaking_finished.emit()
                self._speech_queue.task_done()

    def stop_speaking(self) -> None:
        with self._speech_lock:
            self._speech_generation += 1
            self._speech_pending = 0
        while True:
            try:
                self._speech_queue.get_nowait()
                self._speech_queue.task_done()
            except queue.Empty:
                break
        engine = self._engine
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                logger.debug("TTS durdurulamadı", exc_info=True)
        self.speaking_finished.emit()

    def set_tts_enabled(self, enabled: bool) -> None:
        self.tts_enabled = bool(enabled)
        if not enabled:
            self.stop_speaking()

    # --------------------------------------------------------------------- STT
    def _recognizer(self, energy: int = 250) -> Any:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = energy
        recognizer.dynamic_energy_threshold = True
        recognizer.pause_threshold = 0.7
        recognizer.operation_timeout = 8
        return recognizer

    def _capture(
        self,
        timeout: float,
        phrase_limit: float,
        ambient: float,
        energy: int = 250,
        *,
        wake: bool = False,
    ) -> tuple[str, str]:
        try:
            import speech_recognition as sr
        except ImportError:
            return (
                "",
                "Ses tanıma paketi kurulu değil senpai: SpeechRecognition ve PyAudio. 🎤",
            )
        try:
            recognizer = self._recognizer(energy)
            with sr.Microphone(sample_rate=16000) as source:
                recognizer.adjust_for_ambient_noise(source, duration=ambient)
                if (
                    self._closed
                    or self.is_speaking
                    or (wake and self._wake_stop.is_set())
                ):
                    return "", ""
                audio = recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            if self._closed:
                return "", ""
            text = recognizer.recognize_google(
                audio, language="tr-TR", endpoint=_GOOGLE_ENDPOINT
            )
            return str(text).strip(), ""
        except sr.WaitTimeoutError:
            return "", ""
        except sr.UnknownValueError:
            return "", "Seni duyamadım senpai. Biraz daha net konuşur musun? 🎤"
        except sr.RequestError:
            return (
                "",
                "Ses tanımaya ulaşamadım senpai. İnternet bağlantını kontrol et. 🎤",
            )
        except (ImportError, AttributeError, OSError):
            return (
                "",
                "Mikrofona erişemedim senpai. PyAudio, mikrofon izni ve cihazı kontrol et. 🎤",
            )
        except Exception as exc:
            logger.warning("Ses tanıma hatası: %s", type(exc).__name__)
            return (
                "",
                "Mikrofonla küçük bir sorun yaşadım senpai. Tekrar dener misin? 🎤",
            )

    def listen_once(self, timeout: float = 6, phrase_time_limit: float = 10) -> str:
        if (
            self._closed
            or self.is_speaking
            or not self._mic_lock.acquire(blocking=False)
        ):
            self._last_listen_error = "Şu an konuşuyorum veya mikrofon meşgul senpai."
            return ""
        self._listening = True
        try:
            text, error = self._capture(timeout, phrase_time_limit, ambient=0.5)
            self._last_listen_error = error
            if error:
                self.voice_error.emit(error)
            return text
        finally:
            self._listening = False
            self._mic_lock.release()

    def listen_async(
        self, request_id: int = 0, callback: Callable[[str], None] | None = None
    ) -> bool:
        with self._listen_request_lock:
            if self._closed or self._listening:
                return False
            # Reserve before starting the thread so the wake loop cannot open a
            # second microphone stream in the scheduling gap.
            self._listening = True

        def run() -> None:
            try:
                text = self.listen_once()
                error = self._last_listen_error
            except Exception as exc:
                logger.exception("Dinleme thread hatası: %s", type(exc).__name__)
                text, error = "", "Mikrofon dinlemesi tamamlanamadı senpai. 🎤"
            finally:
                self._listening = False
            if callback:
                try:
                    callback(text)
                except Exception:
                    logger.exception("Dinleme callback hatası")
            if not self._closed:
                self.listening_finished.emit(request_id, text, error)

        try:
            thread = threading.Thread(
                target=run, name=f"nora-listen-{request_id}", daemon=True
            )
            thread.start()
        except Exception:
            self._listening = False
            raise
        return True

    # ---------------------------------------------------------------- wake word
    def start_wake_word_listener(
        self, callback: Callable[[str], None] | None = None
    ) -> bool:
        if self._closed:
            return False
        if callback is not None:
            self._wake_callback = callback
        if self.wake_word_active:
            return True
        self._wake_stop.clear()
        self._wake_thread = threading.Thread(
            target=self._wake_loop, name="nora-wake-word", daemon=True
        )
        self._wake_thread.start()
        return True

    def _wake_loop(self) -> None:
        while not self._wake_stop.wait(0.05):
            if self._closed or self.is_speaking or self._listening:
                self._wake_stop.wait(0.2)
                continue
            if not self._mic_lock.acquire(timeout=0.2):
                continue
            try:
                if self._closed or self.is_speaking or self._listening:
                    continue
                text, error = self._capture(
                    timeout=3, phrase_limit=4, ambient=0.3, energy=250, wake=True
                )
                if error:
                    now = time.monotonic()
                    if (
                        error != self._last_wake_error
                        or now - self._last_wake_error_at > 60
                    ):
                        self._last_wake_error = error
                        self._last_wake_error_at = now
                        self.voice_error.emit(error)
                    self._wake_stop.wait(1)
                    continue
                if not text:
                    continue
                normalized = text.translate(str.maketrans("Iİ", "ıi")).lower()
                match = _WAKE_RE.search(normalized)
                if not match:
                    continue
                remainder = text[match.end() :].strip(" \t\r\n,.;:!?-")
                self.wake_word_detected.emit(remainder)
                if self._wake_callback:
                    try:
                        self._wake_callback(remainder)
                    except Exception:
                        logger.exception("Wake word callback hatası")
            except Exception as exc:
                logger.warning("Wake word döngüsü hatası: %s", type(exc).__name__)
                self._wake_stop.wait(1)
            finally:
                self._mic_lock.release()

    def stop_wake_word_listener(self) -> None:
        self._wake_stop.set()
        thread = self._wake_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def close(self) -> None:
        self._closed = True
        self.stop_wake_word_listener()
        self.stop_speaking()
        self._tts_stop.set()
        self._speech_queue.put(None)
        thread = self._tts_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
