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
import threading
import time
from typing import Any, Callable

from PyQt5.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

WAKE_PHRASE = "hey nora"
_WAKE_RE = re.compile(r"(?<!\w)hey\s+nora(?!\w)", re.IGNORECASE)
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
                with self._speech_lock:
                    settings = dict(self._tts_settings)
                for key, value in (
                    ("rate", settings["rate"]),
                    ("volume", settings["volume"]),
                ):
                    self._engine.setProperty(key, value)
                if settings["voice_id"]:
                    self._engine.setProperty("voice", settings["voice_id"])
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
        recognizer.pause_threshold = 0.6
        recognizer.non_speaking_duration = 0.4
        recognizer.dynamic_energy_adjustment_damping = 0.15
        recognizer.dynamic_energy_ratio = 1.5
        recognizer.operation_timeout = 8
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
            self.last_capture_info["backend"] = self.stt_backend
            if self.stt_backend == "local":
                if self.local_speech is None:
                    return (
                        "",
                        "Yerel ses motoru yapılandırılmadı; sesini buluta göndermedim. 🎤",
                    )
                try:
                    text = self.local_speech.transcribe(
                        audio.get_raw_data(convert_rate=16000, convert_width=2), 16000
                    )
                    return (
                        text,
                        ""
                        if text
                        else "Ses geldi ama yerel model sözleri çıkaramadı senpai. 🎤",
                    )
                except Exception as exc:
                    from .nora_local_ai import LocalModelMissing

                    if isinstance(exc, (LocalModelMissing, ValueError)):
                        return "", str(exc)
                    logger.warning("Yerel STT hatası: %s", type(exc).__name__)
                    return (
                        "",
                        "Yerel ses modeli çalıştırılamadı. Ayarları kontrol et; sesini buluta göndermedim. 🎤",
                    )
            text = recognizer.recognize_google(
                audio, language="tr-TR", endpoint=_GOOGLE_ENDPOINT
            )
            return str(text).strip(), ""
        except sr.WaitTimeoutError:
            logger.debug("Mikrofon dinleme zaman aşımı (wake=%s)", wake)
            if wake:
                return "", ""
            return (
                "",
                "Mikrofon ses algılamadı senpai. Mikrofon seçimini/seviyesini kontrol et; sağ tık → Mikrofon Testi'ni dene. 🎤",
            )
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
        timeout: float = 6,
        phrase_time_limit: float = 10,
        request_id: int | None = None,
    ) -> str:
        if self._closed or self.is_speaking or not self._mic_lock.acquire(timeout=1.5):
            self._last_listen_error = "Şu an konuşuyorum veya mikrofon meşgul senpai."
            return ""
        self._listening = True
        try:
            text, error = self._capture(
                timeout, phrase_time_limit, ambient=0.5, request_id=request_id
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
        decoder.add_keyphrase("nora_wake", WAKE_PHRASE)
        decoder.activate_search("nora_wake")
        return decoder

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
                    if self._closed or self.is_speaking or self._listening:
                        return False
                    buf = stream.read(chunk, exception_on_overflow=False)
                    if not buf:
                        return False
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
            if self._closed or self.is_speaking or self._listening:
                self._wake_stop.wait(0.2)
                continue
            if not self._mic_lock.acquire(timeout=0.2):
                continue
            try:
                if self._closed or self.is_speaking or self._listening:
                    continue
                detected = self._local_wake_session()
                if detected and not self._closed:
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
            except Exception as exc:
                logger.warning("Yerel wake word döngüsü hatası: %s", type(exc).__name__)
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
        self.stop_wake_word_listener()
        self.stop_speaking()
        self._tts_stop.set()
        self._speech_queue.put(None)
        thread = self._tts_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)
