"""Speech output, local "Hey Nora" spotting, and explicit command listening.

The background wake watcher uses PocketSphinx locally: it does not transcribe
conversation and does not send audio to Google.  Cloud STT starts only after the
exact wake phrase is spotted or the user presses the microphone button.  All
microphone access is serialized, and Qt signals marshal results to the UI thread.
"""

from __future__ import annotations

import logging
import os
import queue
import re
import sys
import threading
import time
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtSignal

from .nora_commands import parse_direct_command
from .nora_speech import choose_transcript, google_candidates, repair_transcript

logger = logging.getLogger(__name__)

WAKE_PHRASE = "hey nora"
_WAKE_RE = re.compile(r"(?<!\w)hey\s+nora(?!\w)", re.IGNORECASE)
_EMOJI_RE = re.compile(
    "[\U0001f000-\U0001faff\U00002600-\U000027bf\U0000fe00-\U0000fe0f\U0000200d]+"
)
_GOOGLE_ENDPOINT = "https://www.google.com/speech-api/v2/recognize"


def speech_text(text: str) -> str:
    """Clean assistant text for TTS without silently dropping long replies."""
    value = str(text or "")
    value = re.sub(
        r"```.*?```", " Kod bloğunu sohbete yazdım. ", value, flags=re.DOTALL
    )
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"https?://\S+", " bağlantı ", value)
    value = re.sub(r"[*_#>|]+", " ", value)
    value = _EMOJI_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:12000]


def split_speech(text: str, limit: int = 900) -> list[str]:
    """Sentence-aware chunks so long answers are fully spoken, not truncated."""
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?…])\s+", text):
        if not sentence:
            continue
        if len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            while len(sentence) > limit:
                cut = sentence.rfind(" ", 0, limit)
                if cut < limit // 2:
                    cut = limit
                chunks.append(sentence[:cut].strip())
                sentence = sentence[cut:].strip()
            if sentence:
                current = sentence
        elif current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


class NoraVoice(QObject):
    speaking_started = pyqtSignal()
    speaking_finished = pyqtSignal()
    speech_error = pyqtSignal(str)
    voice_error = pyqtSignal(str)
    listening_started = pyqtSignal(int)  # >0 manual request, 0 background wake capture
    listening_stopped = pyqtSignal(int)
    listening_finished = pyqtSignal(int, str, str)  # request id, transcript, error
    wake_word_detected = pyqtSignal(str)  # words after "Nora", possibly empty

    def __init__(
        self,
        *,
        tts_enabled: bool = True,
        stt_backend: str = "google",
        local_speech: Any = None,
        local_tts: Any = None,
        tts_backend: str = "system",
        barge_in: bool = False,
        speech_rate: int = 180,
        speech_volume: float = 0.9,
        voice_id: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.tts_enabled = tts_enabled
        self.stt_backend = (
            stt_backend if stt_backend in {"google", "local"} else "google"
        )
        self.local_speech = local_speech
        self.local_tts = local_tts
        self.tts_backend = (
            tts_backend if tts_backend in {"system", "piper"} else "system"
        )
        self.barge_in_enabled = bool(barge_in)
        self._tts_settings = {
            "rate": int(speech_rate),
            "volume": float(speech_volume),
            "voice_id": str(voice_id),
        }
        self._closed = False
        self._speech_queue: queue.Queue = queue.Queue()
        self._speech_lock = threading.RLock()
        self._speech_pending = 0
        self._speech_generation = 0
        self._active_speech: int | None = None
        # is_speaking becomes false on cancellation, but microphone capture must
        # wait until the backend has actually returned from runAndWait/write.
        self._playback_idle = threading.Event()
        self._playback_idle.set()
        self._tts_stop = threading.Event()
        self._tts_thread: threading.Thread | None = None
        self._engine: Any = None
        self.last_speech_error = ""
        self._mic_lock = threading.Lock()
        self._listen_request_lock = threading.Lock()
        self._listening = False
        self._last_listen_error = ""
        self._wake_stop = threading.Event()
        self._wake_thread: threading.Thread | None = None
        self._wake_callback: Callable[[str], None] | None = None
        self._last_wake_error = ""
        self._last_wake_error_at = 0.0
        self.microphone_index: int | None = None
        raw_index = os.getenv("NORA_MICROPHONE_INDEX", "").strip()
        if raw_index:
            try:
                self.microphone_index = int(raw_index)
            except ValueError:
                logger.warning(
                    "NORA_MICROPHONE_INDEX sayı olmalı; varsayılan mikrofon kullanılacak."
                )
        self.last_capture_info: dict[str, Any] = {}
        self.last_transcript = None
        self._ptt_stop_event: threading.Event | None = None
        self._ptt_thread: threading.Thread | None = None
        self._ptt_request = 0
        try:
            self.wake_threshold = float(os.getenv("NORA_WAKE_THRESHOLD", "1e-20"))
        except ValueError:
            self.wake_threshold = 1e-20

    # --------------------------------------------------------------------- TTS
    @property
    def is_speaking(self) -> bool:
        with self._speech_lock:
            return self._speech_pending > 0

    @property
    def playback_active(self) -> bool:
        return not self._playback_idle.is_set()

    def wait_for_playback_stop(self, timeout: float = 2.0) -> bool:
        """Wait outside UI locks; never open a microphone over dying audio."""
        return self._playback_idle.wait(max(0.0, min(float(timeout), 5.0)))

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
        cleaned = speech_text(text)
        if self._closed or not self.tts_enabled or not cleaned:
            return False
        chunks = split_speech(cleaned)
        if not chunks:
            return False
        with self._speech_lock:
            self._speech_pending += 1
            generation = self._speech_generation
        try:
            self._ensure_tts_thread()
            self._speech_queue.put((generation, chunks, on_start, on_end))
        except Exception as exc:
            with self._speech_lock:
                self._speech_pending = max(0, self._speech_pending - 1)
            self.last_speech_error = f"TTS kuyruğu başlatılamadı: {type(exc).__name__}"
            logger.warning("TTS thread başlatılamadı: %s", type(exc).__name__)
            self.speech_error.emit("Ses motorunu başlatamadım senpai. 🔊")
            return False
        return True

    @staticmethod
    def _com_initialize() -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            result = ctypes.windll.ole32.CoInitializeEx(None, 2)
            return result in (0, 1)
        except Exception:
            logger.debug("COM başlatılamadı", exc_info=True)
            return False

    @staticmethod
    def _com_uninitialize(initialized: bool) -> None:
        if not initialized or sys.platform != "win32":
            return
        try:
            import ctypes

            ctypes.windll.ole32.CoUninitialize()
        except Exception:
            logger.debug("COM kapatılamadı", exc_info=True)

    def set_tts_backend(self, backend: str) -> None:
        if backend not in {"system", "piper"}:
            raise ValueError("Konuşma motoru system/piper olmalı.")
        if backend != self.tts_backend:
            self.stop_speaking()
        self.tts_backend = backend

    def configure_barge_in(self, enabled: bool) -> None:
        self.barge_in_enabled = bool(enabled)

    def diagnose_speech(self) -> str:
        with self._speech_lock:
            settings = dict(self._tts_settings)
            pending = self._speech_pending
        state = "açık" if self.tts_enabled else "kapalı"
        if settings["volume"] <= 0:
            state += " ama ses düzeyi 0"
        return (
            f"Sesli yanıt {state} · motor {self.tts_backend} · hız {settings['rate']} · düzey {settings['volume']:.2f} · "
            f"kuyruk {pending} · motor {'hazır' if self._engine is not None else 'henüz başlatılmadı'}. "
            + (
                f"Son hata: {self.last_speech_error}"
                if self.last_speech_error
                else "Ses motoru hatası görünmüyor."
            )
        )

    def _make_engine(self) -> Any:
        import pyttsx3

        engine = pyttsx3.init()
        with self._speech_lock:
            settings = dict(self._tts_settings)
        engine.setProperty("rate", settings["rate"])
        engine.setProperty("volume", settings["volume"])
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

            if settings["voice_id"] and any(
                getattr(voice, "id", "") == settings["voice_id"] for voice in voices
            ):
                engine.setProperty("voice", settings["voice_id"])
            elif voices:
                best = max(voices, key=score)
                if score(best)[1] or score(best)[2]:
                    engine.setProperty("voice", best.id)
        except Exception:
            logger.debug(
                "Ses listesi okunamadı; varsayılan ses kullanılacak.", exc_info=True
            )
        return engine

    def _apply_engine_settings(self, engine: Any, settings: dict[str, Any]) -> None:
        engine.setProperty("rate", settings["rate"])
        engine.setProperty("volume", settings["volume"])
        voice_id = settings.get("voice_id", "")
        if not voice_id:
            return
        try:
            voices = engine.getProperty("voices") or []
            if any(getattr(voice, "id", "") == voice_id for voice in voices):
                engine.setProperty("voice", voice_id)
            else:
                self.last_speech_error = (
                    "Seçili ses bulunamadı; varsayılan ses kullanıldı."
                )
                self.speech_error.emit(
                    "Seçili konuşma sesi bulunamadı senpai; varsayılan sesle deniyorum. 🔊"
                )
        except Exception:
            logger.debug("Ses seçimi uygulanamadı", exc_info=True)

    def _speak_chunks(self, generation: int, chunks: list[str]) -> None:
        if self.tts_backend == "piper":
            self._speak_piper(generation, chunks)
            return
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                if self._engine is None:
                    self._engine = self._make_engine()
                with self._speech_lock:
                    settings = dict(self._tts_settings)
                self._apply_engine_settings(self._engine, settings)
                for chunk in chunks:
                    with self._speech_lock:
                        if (
                            self._closed
                            or not self.tts_enabled
                            or generation != self._speech_generation
                        ):
                            return
                    self._engine.say(chunk)
                    self._engine.runAndWait()
                    if generation != self._speech_generation or not self.tts_enabled:
                        return
                self.last_speech_error = ""
                return
            except Exception as exc:
                if generation != self._speech_generation or not self.tts_enabled:
                    return
                last_error = exc
                logger.warning(
                    "Ses motoru hatası (deneme %s): %s", attempt + 1, type(exc).__name__
                )
                engine, self._engine = self._engine, None
                if engine is not None:
                    try:
                        engine.stop()
                    except Exception:
                        logger.debug("Bozuk ses motoru durdurulamadı", exc_info=True)
        self.last_speech_error = (
            f"Ses motoru yanıt vermedi: {type(last_error).__name__}"
        )
        self.speech_error.emit(
            "Ses motorunu açamadım senpai. Windows SAPI/espeak-ng kurulumunu ve ses çıkışını kontrol et. 🔊"
        )

    def _speak_piper(self, generation: int, chunks: list[str]) -> None:
        if self.local_tts is None:
            self.last_speech_error = "Piper yapılandırılmadı."
            self.speech_error.emit(
                "Piper seçili ama yerel ses motoru yok senpai. Menüden Piper modeli içe aktar. Sistem sesine gizlice geçmedim. 🔊"
            )
            return
        with self._speech_lock:
            settings = dict(self._tts_settings)
        try:
            for chunk in chunks:
                with self._speech_lock:
                    if self._closed or generation != self._speech_generation:
                        return
                completed = self.local_tts.speak(
                    chunk,
                    volume=settings["volume"],
                    rate=settings["rate"],
                    should_stop=lambda: (
                        self._closed or generation != self._speech_generation
                    ),
                )
                if not completed:
                    return
            self.last_speech_error = ""
        except Exception as exc:
            if generation != self._speech_generation or not self.tts_enabled:
                return
            self.last_speech_error = f"Piper hatası: {type(exc).__name__}"
            logger.warning("Piper hatası: %s", type(exc).__name__, exc_info=True)
            detail = (
                str(exc)
                if isinstance(exc, ValueError)
                else "Piper ses motoru çalıştırılamadı."
            )
            self.speech_error.emit(detail + " Sistem sesine gizlice geçmedim. 🔊")

    def _tts_worker(self) -> None:
        com_initialized = self._com_initialize()
        try:
            while not self._tts_stop.is_set():
                item = self._speech_queue.get()
                if item is None:
                    break
                generation, chunks, on_start, on_end = item
                try:
                    with self._speech_lock:
                        current = (
                            generation == self._speech_generation
                            and not self._closed
                            and self.tts_enabled
                        )
                        if not current:
                            continue
                        self._active_speech = generation
                        self._playback_idle.clear()
                    self.speaking_started.emit()
                    if on_start:
                        try:
                            on_start()
                        except Exception:
                            logger.exception("TTS başlangıç callback hatası")
                    self._speak_chunks(generation, chunks)
                except Exception as exc:
                    self.last_speech_error = f"TTS worker hatası: {type(exc).__name__}"
                    logger.warning("TTS worker hatası: %s", type(exc).__name__)
                    self.speech_error.emit("Sesli yanıtta sorun yaşadım senpai. 🔊")
                finally:
                    if on_end:
                        try:
                            on_end()
                        except Exception:
                            logger.exception("TTS bitiş callback hatası")
                    with self._speech_lock:
                        # Cancellation owns the pending counter. A late worker
                        # must not decrement a NEW reply's count when it returns.
                        current = generation == self._speech_generation
                        if self._active_speech == generation:
                            self._active_speech = None
                            self._playback_idle.set()
                        if current:
                            self._speech_pending = max(0, self._speech_pending - 1)
                    if current:
                        self.speaking_finished.emit()
                    self._speech_queue.task_done()
        finally:
            self._com_uninitialize(com_initialized)

    def stop_speaking(self) -> None:
        with self._speech_lock:
            self._speech_generation += 1
            self._speech_pending = 0
            # Keep _active_speech until its worker acknowledges the stop.
        while True:
            try:
                item = self._speech_queue.get_nowait()
                self._speech_queue.task_done()
                if callable(item[3]):
                    try:
                        item[3]()
                    except Exception:
                        logger.exception("İptal edilen TTS bitiş işlevi hatası")
            except queue.Empty:
                break
        if self.local_tts is not None:
            try:
                self.local_tts.stop()
            except Exception:
                logger.debug("Piper durdurulamadı", exc_info=True)
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

    def configure_speech(self, rate: int, volume: float, voice_id: str = "") -> None:
        if (
            isinstance(rate, bool)
            or not isinstance(rate, (int, float))
            or not 100 <= rate <= 260
        ):
            raise ValueError("Ses hızı 100-260 olmalı.")
        if (
            isinstance(volume, bool)
            or not isinstance(volume, (int, float))
            or not 0 <= volume <= 1
        ):
            raise ValueError("Ses düzeyi 0-1 olmalı.")
        with self._speech_lock:
            self._tts_settings = {
                "rate": int(rate),
                "volume": float(volume),
                "voice_id": str(voice_id)[:240],
            }

    @staticmethod
    def list_output_voices() -> list[dict[str, str]]:
        """Enumerate system voices in a worker, never on the GUI thread."""
        initialized = NoraVoice._com_initialize()
        try:
            import pyttsx3

            engine = pyttsx3.init()
            try:
                return [
                    {"id": str(voice.id), "name": str(getattr(voice, "name", voice.id))}
                    for voice in engine.getProperty("voices") or []
                ]
            finally:
                engine.stop()
        except Exception as exc:
            logger.warning("Ses listesi alınamadı: %s", type(exc).__name__)
            return []
        finally:
            NoraVoice._com_uninitialize(initialized)

    # --------------------------------------------------------------------- STT
    def set_stt_backend(self, backend: str) -> None:
        if backend not in {"google", "local"}:
            raise ValueError("Ses motoru local/google olmalı.")
        self.stt_backend = backend

    def _recognizer(self, energy: int = 250) -> Any:
        import speech_recognition as sr

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = energy
        recognizer.dynamic_energy_threshold = True
        # Turkish commands often contain a short breath between the name and
        # the action. Do not cut the phrase at the first 0.6 s pause.
        recognizer.pause_threshold = 0.85
        recognizer.non_speaking_duration = 0.55
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.operation_timeout = 12
        return recognizer

    def set_microphone_index(self, index: int | None) -> None:
        self.microphone_index = index

    @staticmethod
    def list_microphones() -> list[str]:
        try:
            import speech_recognition as sr

            return list(sr.Microphone.list_microphone_names())
        except Exception as exc:
            logger.warning("Mikrofon listesi alınamadı: %s", type(exc).__name__)
            return []

    def _transcribe_audio(
        self, audio: Any, recognizer: Any, request_id: int | None = None
    ) -> str:
        """Shared STT path for silence-ended capture and push-to-talk release."""
        import speech_recognition as sr

        self.last_capture_info["backend"] = self.stt_backend
        if self.stt_backend == "local":
            if self.local_speech is None:
                raise ValueError(
                    "Yerel ses motoru yapılandırılmadı; sesini buluta göndermedim. 🎤"
                )
            try:
                text = self.local_speech.transcribe(
                    audio.get_raw_data(convert_rate=16000, convert_width=2), 16000
                )
            except Exception as exc:
                from .nora_local_ai import LocalModelMissing

                if isinstance(exc, (LocalModelMissing, ValueError)):
                    raise ValueError(str(exc)) from exc
                logger.warning("Yerel STT hatası: %s", type(exc).__name__)
                raise ValueError(
                    "Yerel ses modeli çalıştırılamadı. Ayarları kontrol et; sesini buluta göndermedim. 🎤"
                ) from exc
            if not text:
                raise ValueError(
                    "Ses geldi ama yerel model sözleri çıkaramadı senpai. 🎤"
                )
            self.last_transcript = repair_transcript(
                text, command_parser=parse_direct_command, request_id=request_id
            )
            self.last_capture_info["address_corrected"] = (
                self.last_transcript.address_corrected
            )
            return self.last_transcript.text
        raw = recognizer.recognize_google(
            audio, language="tr-TR", endpoint=_GOOGLE_ENDPOINT, show_all=True
        )
        candidates = google_candidates(raw)
        if not candidates:
            raise sr.UnknownValueError()
        self.last_transcript = choose_transcript(
            candidates, command_parser=parse_direct_command, request_id=request_id
        )
        self.last_capture_info.update(
            {
                "alternatives": len(candidates),
                "selected_alternative": self.last_transcript.selected_alternative,
                "confidence": self.last_transcript.confidence,
                "address_corrected": self.last_transcript.address_corrected,
            }
        )
        return self.last_transcript.text

    def _capture(
        self,
        timeout: float,
        phrase_limit: float,
        ambient: float,
        energy: int = 250,
        *,
        wake: bool = False,
        request_id: int | None = None,
    ) -> tuple[str, str]:
        self.last_transcript = None
        try:
            import speech_recognition as sr
        except ImportError:
            return (
                "",
                "Ses tanıma paketi kurulu değil senpai: SpeechRecognition ve PyAudio. 🎤",
            )
        try:
            recognizer = self._recognizer(energy)
            with sr.Microphone(
                sample_rate=16000, device_index=self.microphone_index
            ) as source:
                recognizer.adjust_for_ambient_noise(source, duration=ambient)
                if (
                    self._closed
                    or self.is_speaking
                    or (wake and self._wake_stop.is_set())
                ):
                    return "", ""
                if request_id is not None:
                    self.listening_started.emit(request_id)
                audio = recognizer.listen(
                    source, timeout=timeout, phrase_time_limit=phrase_limit
                )
            if self._closed:
                return "", ""
            self.last_capture_info = {
                "device_index": self.microphone_index,
                "sample_rate": getattr(audio, "sample_rate", None),
                "bytes": len(getattr(audio, "frame_data", b"") or b""),
                "energy_threshold": recognizer.energy_threshold,
            }
            return self._transcribe_audio(audio, recognizer, request_id), ""
        except sr.WaitTimeoutError:
            logger.debug("Mikrofon dinleme zaman aşımı (wake=%s)", wake)
            if wake:
                return "", ""
            return (
                "",
                "Mikrofon ses algılamadı senpai. Mikrofon seçimini/seviyesini kontrol et; sağ tık → Mikrofon Testi'ni dene. 🎤",
            )
        except ValueError as exc:
            return "", str(exc)
        except sr.UnknownValueError:
            return (
                "",
                "Ses geldi ama anlayamadım senpai. Biraz daha net konuşur musun? 🎤",
            )
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
        finally:
            if request_id is not None:
                self.listening_stopped.emit(request_id)

    def test_microphone(self, timeout: float = 3) -> str:
        """Local-only microphone level test; does not upload audio."""
        if self._closed or self.is_speaking or not self._mic_lock.acquire(timeout=1.5):
            return "Mikrofon şu an meşgul senpai. Konuşmamı/dinlememi bekle, sonra tekrar dene. 🎤"
        try:
            import speech_recognition as sr

            recognizer = self._recognizer()
            with sr.Microphone(
                sample_rate=16000, device_index=self.microphone_index
            ) as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                try:
                    audio = recognizer.listen(
                        source, timeout=timeout, phrase_time_limit=timeout
                    )
                except sr.WaitTimeoutError:
                    return (
                        f"Mikrofon açıldı ama {timeout:g} saniyede ses algılanmadı senpai. "
                        f"Cihaz: {self.microphone_index if self.microphone_index is not None else 'varsayılan'}. "
                        "Windows Ses ayarlarından giriş cihazını/seviyesini kontrol et veya Mikrofon Seç'i dene. 🎤"
                    )
            raw = audio.frame_data or b""
            peak = rms = 0
            if raw:
                import array

                samples = array.array("h")
                samples.frombytes(raw[: len(raw) // 2 * 2])
                if samples:
                    peak = max(abs(x) for x in samples)
                    rms = int((sum(x * x for x in samples) / len(samples)) ** 0.5)
            heard = peak > max(300, recognizer.energy_threshold * 0.5)
            self.last_capture_info = {
                "device_index": self.microphone_index,
                "peak": peak,
                "rms": rms,
                "energy_threshold": recognizer.energy_threshold,
                "heard": heard,
            }
            return (
                f"Mikrofon testi: cihaz {self.microphone_index if self.microphone_index is not None else 'varsayılan'}, "
                f"peak={peak}, rms={rms}, eşik≈{recognizer.energy_threshold:.0f}. "
                + (
                    "Sesini algıladım senpai~ 🎤"
                    if heard
                    else "Ses çok zayıf; giriş seviyesini/cihazı kontrol et. 🎤"
                )
            )
        except Exception as exc:
            logger.warning("Mikrofon testi hatası: %s", type(exc).__name__)
            return "Mikrofon test edilemedi senpai. PyAudio, mikrofon izni ve cihazı kontrol et. 🎤"
        finally:
            self._mic_lock.release()

    def listen_once(
        self,
        timeout: float = 8,
        phrase_time_limit: float = 15,
        request_id: int | None = None,
    ) -> str:
        if self._closed or self.is_speaking or not self._mic_lock.acquire(timeout=1.5):
            self._last_listen_error = "Şu an konuşuyorum veya mikrofon meşgul senpai."
            return ""
        self._listening = True
        try:
            text, error = self._capture(
                timeout, phrase_time_limit, ambient=0.7, request_id=request_id
            )
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
                text = self.listen_once(request_id=request_id)
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

    # ------------------------------------------------------------ push-to-talk
    def start_push_to_talk(self, request_id: int = 0) -> bool:
        """Record while the user holds a key; release stops and transcribes."""
        with self._listen_request_lock:
            if self._closed or self._listening or self.is_speaking:
                return False
            self._listening = True
            self._ptt_request = request_id
            self._ptt_stop_event = threading.Event()
        stop_event = self._ptt_stop_event

        def run() -> None:
            text, error = "", ""
            try:
                text, error = self._push_to_talk_capture(request_id, stop_event)
            except Exception as exc:
                logger.exception("Bas-konuş hatası: %s", type(exc).__name__)
                error = "Bas-konuş dinlemesi tamamlanamadı senpai. 🎤"
            finally:
                with self._listen_request_lock:
                    self._listening = False
                    self._ptt_stop_event = None
                    self._ptt_thread = None
                    self._ptt_request = 0
            if not self._closed:
                self.listening_finished.emit(request_id, text, error)

        try:
            self._ptt_thread = threading.Thread(
                target=run, name=f"nora-ptt-{request_id}", daemon=True
            )
            self._ptt_thread.start()
            return True
        except Exception:
            with self._listen_request_lock:
                self._listening = False
                self._ptt_stop_event = None
                self._ptt_thread = None
            raise

    def stop_push_to_talk(self) -> None:
        event = self._ptt_stop_event
        if event is not None:
            event.set()

    @property
    def push_to_talk_active(self) -> bool:
        return bool(self._ptt_thread and self._ptt_thread.is_alive())

    def _push_to_talk_capture(
        self, request_id: int, stop_event: threading.Event
    ) -> tuple[str, str]:
        try:
            import speech_recognition as sr
        except ImportError:
            return "", "Bas-konuş için SpeechRecognition ve PyAudio gerekli senpai. 🎤"
        if not self._mic_lock.acquire(timeout=1.5):
            return "", "Mikrofon meşgul senpai. Biraz sonra tekrar dene. 🎤"
        frames = bytearray()
        started = time.monotonic()
        stopped_emitted = False
        try:
            self.last_transcript = None
            recognizer = self._recognizer()
            with sr.Microphone(
                sample_rate=16000, device_index=self.microphone_index
            ) as source:
                stream = source.stream
                chunk = getattr(source, "CHUNK", 1024)
                if request_id:
                    self.listening_started.emit(request_id)
                while not stop_event.is_set() and not self._closed:
                    if time.monotonic() - started > 30:
                        break
                    raw = self._read_mic_chunk(stream, chunk)
                    if raw:
                        frames.extend(bytes(raw))
            if self._closed:
                return "", ""
            duration = time.monotonic() - started
            if request_id:
                self.listening_stopped.emit(request_id)
                stopped_emitted = True
            if duration < 0.25 or not frames:
                return (
                    "",
                    "Tuşa çok kısa bastın senpai. Basılı tutup konuş, bırakınca cevaplayayım. 🎤",
                )
            audio = sr.AudioData(bytes(frames), 16000, 2)
            self.last_capture_info = {
                "device_index": self.microphone_index,
                "sample_rate": 16000,
                "bytes": len(frames),
                "duration": round(duration, 2),
                "mode": "push_to_talk",
                "energy_threshold": recognizer.energy_threshold,
            }
            return self._transcribe_audio(audio, recognizer, request_id), ""
        except sr.WaitTimeoutError:
            return "", "Bas-konuş sırasında ses algılamadım senpai. 🎤"
        except sr.UnknownValueError:
            return (
                "",
                "Ses geldi ama anlayamadım senpai. Biraz daha net konuşur musun? 🎤",
            )
        except sr.RequestError:
            return (
                "",
                "Ses tanımaya ulaşamadım senpai. İnternet bağlantını kontrol et. 🎤",
            )
        except ValueError as exc:
            return "", str(exc)
        except (ImportError, AttributeError, OSError):
            return (
                "",
                "Mikrofona erişemedim senpai. PyAudio, mikrofon izni ve cihazı kontrol et. 🎤",
            )
        except Exception as exc:
            logger.warning("Bas-konuş ses tanıma hatası: %s", type(exc).__name__)
            return (
                "",
                "Bas-konuşta küçük bir sorun yaşadım senpai. Tekrar dener misin? 🎤",
            )
        finally:
            if request_id and not stopped_emitted:
                self.listening_stopped.emit(request_id)
            self._mic_lock.release()

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

    @staticmethod
    def _is_wake_hypothesis(text: str) -> bool:
        normalized = (text or "").translate(str.maketrans("Iİ", "ıi")).lower()
        return bool(_WAKE_RE.search(normalized))

    def _make_wake_decoder(self) -> Any:
        from pocketsphinx import Config, Decoder, set_loglevel

        set_loglevel("ERROR")
        config = Config()
        config.set_int("-samprate", 16000)
        config.set_float("-kws_threshold", self.wake_threshold)
        decoder = Decoder(config)
        if not decoder.lookup_word("nora"):
            decoder.add_word("nora", "N AO R AH", True)
        # Turkish speakers may round/unround the vowels differently. These are
        # still only pronunciations of "nora"; the spotted text gate remains the
        # exact phrase "hey nora" and never accepts "nova" or "no ra".
        for alternate, phones in (("nora(2)", "N OW R AH"), ("nora(3)", "N AO R AA")):
            if not decoder.lookup_word(alternate):
                decoder.add_word(alternate, phones, True)
        decoder.add_keyphrase("nora_wake", WAKE_PHRASE)
        decoder.activate_search("nora_wake")
        return decoder

    @staticmethod
    def _read_mic_chunk(stream: Any, chunk: int) -> Any:
        """Compatible with SpeechRecognition MicrophoneStream.read(size) and PyAudio.read."""
        try:
            return stream.read(chunk, exception_on_overflow=False)
        except TypeError as exc:
            # SpeechRecognition's wrapper already passes exception_on_overflow
            # to PyAudio internally and only accepts the positional size arg.
            if "exception_on_overflow" not in str(exc):
                raise
            return stream.read(chunk)

    def _wake_hyp_detected(self, decoder: Any) -> bool:
        hyp = decoder.hyp()
        return bool(hyp and self._is_wake_hypothesis(getattr(hyp, "hypstr", "")))

    def _local_wake_session(self) -> bool:
        """Block until the exact local keyphrase is heard; never call cloud STT."""
        import speech_recognition as sr

        decoder = self._make_wake_decoder()
        with sr.Microphone(
            sample_rate=16000, device_index=self.microphone_index
        ) as source:
            stream = source.stream
            chunk = getattr(source, "CHUNK", 1024)
            decoder.start_utt()
            silent_chunks = 0
            try:
                while not self._wake_stop.is_set():
                    if (
                        self._closed
                        or (self.is_speaking and not self.barge_in_enabled)
                        or self._listening
                    ):
                        return False
                    raw = self._read_mic_chunk(stream, chunk)
                    if not raw:
                        return False
                    # Some PortAudio/PyAudio builds return bytearray/memoryview.
                    # PocketSphinx's Cython binding requires plain bytes.
                    buf = bytes(raw)
                    decoder.process_raw(buf, False, False)
                    if self._wake_hyp_detected(decoder):
                        return True
                    if decoder.get_in_speech():
                        silent_chunks = 0
                    else:
                        silent_chunks += 1
                        if silent_chunks >= 15:
                            decoder.end_utt()
                            if self._wake_hyp_detected(decoder):
                                return True
                            decoder.start_utt()
                            silent_chunks = 0
                return False
            finally:
                try:
                    decoder.end_utt()
                except Exception:
                    pass

    def _wake_loop(self) -> None:
        while not self._wake_stop.wait(0.05):
            if (
                self._closed
                or (self.is_speaking and not self.barge_in_enabled)
                or self._listening
            ):
                self._wake_stop.wait(0.2)
                continue
            if not self._mic_lock.acquire(timeout=0.2):
                continue
            try:
                if (
                    self._closed
                    or (self.is_speaking and not self.barge_in_enabled)
                    or self._listening
                ):
                    continue
                detected = self._local_wake_session()
                if detected and not self._closed:
                    if self.is_speaking and self.barge_in_enabled:
                        self.stop_speaking()
                    # Local spotting only activates the assistant; the command
                    # itself is captured afterwards by explicit cloud STT.
                    self.wake_word_detected.emit("")
                    if self._wake_callback:
                        try:
                            self._wake_callback("")
                        except Exception:
                            logger.exception("Wake word callback hatası")
                    self._wake_stop.wait(0.5)
            except ImportError:
                self.voice_error.emit(
                    "Yerel 'Hey Nora' için pocketsphinx kurulu değil senpai. requirements.txt'yi kur veya 🎤 düğmesini kullan. 🎙️"
                )
                return
            except OSError:
                self._wake_error_rate_limited(
                    "Yerel 'Hey Nora' mikrofonu açamadı senpai. Mikrofon izni/cihazını kontrol et. 🎙️"
                )
                self._wake_stop.wait(1)
            except TypeError as exc:
                logger.warning(
                    "Yerel wake word veri biçimi hatası: %s", exc, exc_info=True
                )
                self._wake_error_rate_limited(
                    "Yerel 'Hey Nora' ses verisi biçimiyle sorun yaşadım; mikrofon/PyAudio sürümünü kontrol et. 🎤 düğmesi hâlâ çalışır. 🎙️"
                )
                self._wake_stop.wait(2)
            except Exception as exc:
                logger.warning(
                    "Yerel wake word döngüsü hatası: %s",
                    type(exc).__name__,
                    exc_info=True,
                )
                self._wake_error_rate_limited(
                    "Yerel 'Hey Nora' bekçisiyle sorun yaşadım senpai. 🎤 düğmesi hâlâ çalışır. 🎙️"
                )
                self._wake_stop.wait(1)
            finally:
                self._mic_lock.release()

    def _wake_error_rate_limited(self, message: str) -> None:
        now = time.monotonic()
        if message != self._last_wake_error or now - self._last_wake_error_at > 60:
            self._last_wake_error = message
            self._last_wake_error_at = now
            self.voice_error.emit(message)

    def stop_wake_word_listener(self) -> None:
        self._wake_stop.set()
        thread = self._wake_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def close(self) -> None:
        self._closed = True
        self.stop_push_to_talk()
        self.stop_wake_word_listener()
        self.stop_speaking()
        self._tts_stop.set()
        self._speech_queue.put(None)
        thread = self._tts_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
