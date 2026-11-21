import json
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import urlopen

import pytest

from nora.nora_spotify import SpotifyClient, SpotifyError, _challenge


class FakeKeyring:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[(service, username)] = value

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


class Response:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload
        self.content = b"{}" if payload is not None else b""

    def json(self):
        return self._payload


class Session:
    def __init__(self):
        self.posts = []
        self.requests = []
        self.responses = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return Response(
            payload={
                "access_token": "access-1",
                "refresh_token": "refresh-1",
                "expires_in": 3600,
            }
        )

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.responses.pop(0) if self.responses else Response(204)

    def close(self):
        pass


def test_spotify_pkce_callback_state_and_keyring_storage():
    session, keyring = Session(), FakeKeyring()
    opened = []

    def browser(url):
        opened.append(url)
        query = parse_qs(urlsplit(url).query)
        redirect = query["redirect_uri"][0]
        state = query["state"][0]
        assert query["code_challenge_method"] == ["S256"]
        threading.Thread(
            target=lambda: urlopen(
                redirect + "?" + urlencode({"code": "code-1", "state": state})
            ).read(),
            daemon=True,
        ).start()
        return True

    client = SpotifyClient(
        "a" * 32, session=session, keyring_module=keyring, open_browser=browser
    )
    assert "kuruldu" in client.connect(port=0)
    data = session.posts[0][1]["data"]
    assert data["code_verifier"]
    auth_query = parse_qs(urlsplit(opened[0]).query)
    assert auth_query["code_challenge"] == [_challenge(data["code_verifier"])]
    assert keyring.values
    stored = json.loads(next(iter(keyring.values.values())))
    assert stored["access_token"] == "access-1"
    assert "access-1" not in json.dumps(stored.get("scope", ""))
    client.disconnect()
    assert not keyring.values
    client.close()


def test_spotify_rejects_wrong_state_and_never_posts_token():
    session = Session()

    def browser(url):
        query = parse_qs(urlsplit(url).query)
        redirect = query["redirect_uri"][0]
        threading.Thread(
            target=lambda: urlopen(
                redirect + "?" + urlencode({"code": "evil", "state": "wrong"})
            ).read(),
            daemon=True,
        ).start()
        return True

    client = SpotifyClient(
        "a" * 32, session=session, keyring_module=FakeKeyring(), open_browser=browser
    )
    with pytest.raises(SpotifyError, match="state"):
        client.connect(port=0)
    assert session.posts == []
    client.close()


def test_spotify_cancel_and_refresh_do_not_use_cloud_fallback():
    session, keyring = Session(), FakeKeyring()

    def cancel_browser(url):
        client.cancel()
        return True

    client = SpotifyClient(
        "a" * 32, session=session, keyring_module=keyring, open_browser=cancel_browser
    )
    with pytest.raises(SpotifyError, match="iptal"):
        client.connect(port=0)
    keyring.set_password(
        "Nora.Spotify",
        client._username(),
        json.dumps(
            {
                "client_id": "a" * 32,
                "access_token": "old",
                "refresh_token": "refresh-1",
                "expires_at": time.time() - 10,
            }
        ),
    )
    session.responses = [
        Response(
            payload={
                "item": {"name": "Şarkı", "artists": [{"name": "Sanatçı"}]},
                "is_playing": True,
            }
        )
    ]
    assert "Şarkı" in client.now_playing()
    assert session.posts[0][1]["data"]["grant_type"] == "refresh_token"
    assert session.requests[0][2]["headers"]["Authorization"] == "Bearer access-1"
    client.close()


def test_spotify_control_and_errors_are_explicit():
    session = Session()
    client = SpotifyClient("a" * 32, session=session, keyring_module=FakeKeyring())
    with pytest.raises(SpotifyError, match="bağlı değil"):
        client.control("next")
    client._tokens = {
        "client_id": "a" * 32,
        "access_token": "token",
        "expires_at": time.time() + 3600,
    }
    session.responses = [Response(payload={"is_playing": True}), Response(204)]
    assert "duraklattım" in client.control("play_pause")
    assert session.requests[-1][1].endswith("/me/player/pause")
    session.responses = [Response(403)]
    with pytest.raises(SpotifyError, match="reddetti"):
        client.control("next")
    client.close()


def test_disconnect_reports_keyring_delete_failure_honestly():
    class BrokenKeyring(FakeKeyring):
        def delete_password(self, service, username):
            raise RuntimeError("locked")

    keyring = BrokenKeyring()
    client = SpotifyClient("a" * 32, session=Session(), keyring_module=keyring)
    client._tokens = {"access_token": "secret", "client_id": client.client_id}
    message = client.disconnect()
    assert "silinemedi" in message
    assert not client.connected()
    assert client._tokens is None
    client._save_tokens({"access_token": "new-after-explicit-reconnect"})
    assert client.connected()
    client.close()
