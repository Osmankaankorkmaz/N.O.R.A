"""Optional Spotify Web API control using Authorization Code + PKCE.

No client secret is embedded or requested. OAuth uses a short-lived loopback
callback; tokens are kept in the OS credential store when available and never
written to Nora's JSON state. Without a connection the existing OS media-key
path remains available, but API failures are reported rather than hidden.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

logger = logging.getLogger(__name__)
AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_URL = "https://api.spotify.com/v1"
SCOPES = (
    "user-read-currently-playing user-read-playback-state user-modify-playback-state"
)
KEYRING_SERVICE = "Nora.Spotify"


class SpotifyError(RuntimeError):
    pass


def _challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )


class _CallbackServer(HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int) -> None:
        self.result: dict[str, str] | None = None
        super().__init__(("127.0.0.1", port), _CallbackHandler)
        self.timeout = 0.4


class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        parsed = urlsplit(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query, keep_blank_values=True)
        self.server.result = {
            key: values[0]
            for key, values in query.items()
            if key in {"code", "state", "error"}
        }
        body = (
            "<!doctype html><meta charset='utf-8'><title>Nora · Spotify</title>"
            "<body style='font-family:sans-serif;background:#24182f;color:#fff;padding:3rem'>"
            "<h2>Spotify yanıtı alındı 💜</h2><p>Bu sekmeyi kapatabilirsin. Nora sonucu doğrulayacak.</p></body>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


class SpotifyClient:
    def __init__(
        self,
        client_id: str = "",
        *,
        session: Any = None,
        keyring_module: Any = None,
        open_browser: Any = None,
        timeout: float = 120.0,
    ) -> None:
        self.client_id = str(client_id or "").strip()
        self._session = session or requests.Session()
        self._keyring = keyring_module
        self._open_browser = open_browser or webbrowser.open
        self.timeout = max(5.0, min(float(timeout), 300.0))
        self._tokens: dict[str, Any] | None = None
        self._revoked = False
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self.storage_notice = ""

    def configure(self, client_id: str) -> None:
        client_id = str(client_id or "").strip()
        if client_id and (not client_id.isalnum() or not 16 <= len(client_id) <= 80):
            raise ValueError("Spotify Client ID harf/rakam içermeli.")
        with self._lock:
            if client_id != self.client_id:
                self._tokens = None
            self.client_id = client_id

    @property
    def configured(self) -> bool:
        return bool(self.client_id)

    def _keyring_module(self) -> Any:
        if self._keyring is not None:
            return self._keyring
        try:
            import keyring

            self._keyring = keyring
            return keyring
        except ImportError:
            return None

    def _username(self) -> str:
        return hashlib.sha256(self.client_id.encode("utf-8")).hexdigest()[:24]

    def _load_tokens(self) -> dict[str, Any] | None:
        with self._lock:
            if self._revoked:
                return None
            if self._tokens is not None:
                return dict(self._tokens)
        keyring = self._keyring_module()
        if keyring is None:
            self.storage_notice = (
                "Sistem anahtar kasası yok; token yalnızca bu oturumda tutulur."
            )
            return None
        try:
            raw = keyring.get_password(KEYRING_SERVICE, self._username())
            data = json.loads(raw) if raw else None
            if (
                isinstance(data, dict)
                and data.get("access_token")
                and data.get("client_id") == self.client_id
            ):
                with self._lock:
                    self._tokens = data
                return dict(data)
        except Exception:
            self.storage_notice = (
                "Sistem anahtar kasası okunamadı; yeniden Spotify bağlantısı kur."
            )
        return None

    def _save_tokens(self, payload: dict[str, Any], *, refresh: bool = False) -> None:
        previous = self._load_tokens() or {} if refresh else {}
        data = {
            "client_id": self.client_id,
            "access_token": str(payload["access_token"]),
            "refresh_token": str(
                payload.get("refresh_token") or previous.get("refresh_token", "")
            ),
            "expires_at": time.time()
            + max(30, int(payload.get("expires_in", 3600)))
            - 30,
            "scope": str(payload.get("scope", SCOPES)),
        }
        with self._lock:
            self._tokens = data
            self._revoked = False
        keyring = self._keyring_module()
        if keyring is None:
            self.storage_notice = (
                "Sistem anahtar kasası yok; token yalnızca bu oturumda tutulur."
            )
            return
        try:
            keyring.set_password(KEYRING_SERVICE, self._username(), json.dumps(data))
            self.storage_notice = "Token sistem anahtar kasasında saklanıyor."
        except Exception:
            self.storage_notice = (
                "Token sistem kasasına yazılamadı; yalnızca bu oturumda tutuluyor."
            )

    def _clear_tokens(self) -> None:
        with self._lock:
            self._tokens = None
        keyring = self._keyring_module()
        if keyring is not None:
            try:
                keyring.delete_password(KEYRING_SERVICE, self._username())
            except Exception:
                pass

    def cancel(self) -> None:
        self._cancel.set()

    def connect(self, client_id: str | None = None, *, port: int = 8765) -> str:
        if client_id is not None:
            self.configure(client_id)
        if not self.configured:
            raise SpotifyError(
                "Önce Spotify Client ID gir senpai. Spotify Developer uygulamasında redirect URI olarak http://127.0.0.1:8765/callback ekle."
            )
        if (
            not isinstance(port, int)
            or isinstance(port, bool)
            or not 0 <= port <= 65535
        ):
            raise SpotifyError("OAuth portu geçersiz.")
        self._cancel.clear()
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        try:
            server = _CallbackServer(port)
        except OSError as exc:
            raise SpotifyError(
                "OAuth geri çağrı portu açılamadı. 8765 portunu kullanan başka bir uygulamayı kapat veya Spotify redirect ayarını kontrol et."
            ) from exc
        redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "scope": SCOPES,
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": _challenge(verifier),
        }
        try:
            if not self._open_browser(AUTH_URL + "?" + urlencode(params)):
                raise SpotifyError(
                    "Tarayıcı açılamadı; Spotify bağlantısı başlatılamadı."
                )
            deadline = time.monotonic() + self.timeout
            while (
                server.result is None
                and time.monotonic() < deadline
                and not self._cancel.is_set()
            ):
                server.handle_request()
            if self._cancel.is_set():
                raise SpotifyError("Spotify bağlantısı iptal edildi.")
            result = server.result
            if result is None:
                raise SpotifyError(
                    "Spotify bağlantısı zaman aşımına uğradı. Tarayıcıda izin verip tekrar dene."
                )
            if not hmac.compare_digest(str(result.get("state", "")), state):
                raise SpotifyError(
                    "Spotify OAuth state doğrulaması başarısız; yanıt reddedildi."
                )
            if result.get("error"):
                raise SpotifyError("Spotify izni verilmedi veya bağlantı reddedildi.")
            code = result.get("code", "")
            if not code:
                raise SpotifyError("Spotify yetkilendirme kodu alınamadı.")
            response = self._session.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier,
                },
                timeout=20,
            )
            if response.status_code >= 400:
                raise SpotifyError(
                    "Spotify token isteği reddedildi. Client ID ve redirect URI ayarını kontrol et."
                )
            payload = response.json()
            if not isinstance(payload, dict) or not payload.get("access_token"):
                raise SpotifyError("Spotify geçerli bir access token döndürmedi.")
            self._save_tokens(payload)
            return "Spotify bağlantısı kuruldu. Artık çalan parçayı okuyabilir ve oynatmayı kontrol edebilirim. 🎧"
        except requests.RequestException as exc:
            raise SpotifyError(
                "Spotify bağlantısına ulaşılamadı. İnterneti kontrol et."
            ) from exc
        finally:
            server.server_close()

    def disconnect(self) -> str:
        self.cancel()
        with self._lock:
            self._tokens = None
            self._revoked = True
        keyring = self._keyring_module()
        if keyring is None:
            return "Spotify oturum tokenını bellekten temizledim; sistem kasası kullanılmıyordu. 🎧"
        try:
            keyring.delete_password(KEYRING_SERVICE, self._username())
            if keyring.get_password(KEYRING_SERVICE, self._username()):
                raise RuntimeError("token remains")
        except Exception:
            self.storage_notice = (
                "Oturum kapandı ama sistem kasasındaki token silinemedi."
            )
            return (
                "Spotify oturumunu kapattım; sistem anahtar kasasındaki token silinemedi. "
                "Windows Kimlik Bilgileri Yöneticisi / sistem anahtarlığından Nora.Spotify kaydını elle kaldırabilirsin. 🎧"
            )
        self.storage_notice = "Yerel Spotify token kaydı silindi."
        return "Spotify bağlantısını ve yerel token kaydını temizledim. 🎧"

    def connected(self) -> bool:
        return bool(self.configured and self._load_tokens())

    def status(self) -> str:
        if not self.configured:
            return "Spotify API bağlı değil. Ayarlara Client ID girip 'spotify bağlan' de; medya tuşları yine çalışabilir. 🎧"
        state = "bağlı" if self._load_tokens() else "bağlantı bekliyor"
        return f"Spotify API: {state}. {self.storage_notice or 'Token için sistem anahtar kasası kullanılır.'}"

    def _refresh(self, tokens: dict[str, Any]) -> dict[str, Any]:
        refresh_token = tokens.get("refresh_token")
        if not refresh_token:
            self._clear_tokens()
            raise SpotifyError(
                "Spotify oturumu yenilenemedi; 'spotify bağlan' ile yeniden izin ver."
            )
        try:
            response = self._session.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                timeout=20,
            )
        except requests.RequestException as exc:
            raise SpotifyError("Spotify token yenileme isteği gönderilemedi.") from exc
        if response.status_code >= 400:
            self._clear_tokens()
            raise SpotifyError(
                "Spotify oturumu geçersiz; 'spotify bağlan' ile yeniden bağlan."
            )
        payload = response.json()
        if not isinstance(payload, dict) or not payload.get("access_token"):
            self._clear_tokens()
            raise SpotifyError("Spotify yenileme yanıtı geçersiz.")
        self._save_tokens(payload, refresh=True)
        return dict(self._tokens or {})

    def _access_token(self) -> str:
        tokens = self._load_tokens()
        if tokens is None:
            raise SpotifyError("Spotify API bağlı değil. 'spotify bağlan' de senpai.")
        if float(tokens.get("expires_at", 0)) <= time.time():
            tokens = self._refresh(tokens)
        return str(tokens["access_token"])

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        body: dict | None = None,
        retry: bool = True,
    ) -> Any:
        token = self._access_token()
        try:
            response = self._session.request(
                method,
                API_URL + path,
                headers={"Authorization": f"Bearer {token}"},
                params=params,
                json=body,
                timeout=15,
            )
        except requests.RequestException as exc:
            raise SpotifyError(
                "Spotify API isteği gönderilemedi. İnterneti kontrol et."
            ) from exc
        if response.status_code == 401 and retry:
            tokens = self._load_tokens() or {}
            self._refresh(tokens)
            return self._request(method, path, params=params, body=body, retry=False)
        if response.status_code == 204:
            return None
        if response.status_code == 403:
            raise SpotifyError(
                "Spotify bu işlemi reddetti. Premium/uygulama izni veya hesap kısıtı olabilir."
            )
        if response.status_code == 404:
            raise SpotifyError(
                "Aktif Spotify cihazı bulunamadı. Spotify'ı açıp bir cihazda oynatmayı başlat."
            )
        if response.status_code == 429:
            raise SpotifyError("Spotify hız sınırına takıldı; biraz sonra tekrar dene.")
        if response.status_code >= 400:
            raise SpotifyError(f"Spotify API hatası ({response.status_code}).")
        try:
            return response.json() if response.content else None
        except ValueError as exc:
            raise SpotifyError("Spotify API yanıtı okunamadı.") from exc

    def now_playing(self) -> str:
        data = self._request("GET", "/me/player/currently-playing")
        if not isinstance(data, dict) or not isinstance(data.get("item"), dict):
            return "Spotify'da şu an okunabilir bir parça yok veya aktif cihaz yok. 🎧"
        item = data["item"]
        artists = ", ".join(
            str(artist.get("name", ""))
            for artist in item.get("artists", [])
            if isinstance(artist, dict)
        )
        state = "çalıyor" if data.get("is_playing") else "duraklatılmış"
        return f"Şu an {state}: {item.get('name', 'Bilinmeyen parça')} — {artists or 'bilinmeyen sanatçı'} 🎧"

    def devices(self) -> str:
        data = self._request("GET", "/me/player/devices")
        devices = data.get("devices", []) if isinstance(data, dict) else []
        if not devices:
            return "Spotify cihazı görünmüyor. Masaüstü/web oynatıcısını aç senpai. 🎧"
        return "Spotify cihazları 🎧\n" + "\n".join(
            f"• {device.get('name', 'Cihaz')} · {'aktif' if device.get('is_active') else 'pasif'} · {device.get('type', '')}"
            for device in devices[:10]
        )

    def control(self, action: str) -> str:
        if action == "now_playing":
            return self.now_playing()
        if action == "play_pause":
            data = self._request("GET", "/me/player/currently-playing")
            playing = bool(isinstance(data, dict) and data.get("is_playing"))
            self._request("PUT", "/me/player/pause" if playing else "/me/player/play")
            return (
                "Spotify'ı duraklattım. ⏸️" if playing else "Spotify'ı devam ettirdim. ▶️"
            )
        if action in {"next", "previous"}:
            self._request("POST", f"/me/player/{action}")
            return (
                "Sonraki parçaya geçtim. ⏭️"
                if action == "next"
                else "Önceki parçaya döndüm. ⏮️"
            )
        if action == "stop":
            self._request("PUT", "/me/player/pause")
            return "Spotify oynatmasını duraklattım. ⏹️"
        raise SpotifyError("Bu Spotify kontrolünü bilmiyorum.")

    def close(self) -> None:
        self.cancel()
        try:
            self._session.close()
        except Exception:
            pass
