import base64
from types import SimpleNamespace

import pytest

from nora.nora_brain import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_VISION_MODEL,
    HISTORY_LIMIT,
    NoraBrain,
)


class FakeCompletions:
    def __init__(
        self, content='Heh, buradayım [CMD:{"command":"system_info"}] [EMO:smug]'
    ):
        self.content = content
        self.calls = []
        self.before_return = None

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.before_return:
            self.before_return()
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class FakeClient:
    def __init__(
        self, content='Heh, buradayım [CMD:{"command":"system_info"}] [EMO:smug]'
    ):
        self.chat = SimpleNamespace(completions=FakeCompletions(content))
        self.closed = False

    def close(self):
        self.closed = True


def test_chat_parameters_and_parsing():
    client = FakeClient()
    brain = NoraBrain(client=client)
    reply = brain.chat("sistem bilgisi")
    assert reply.text == "Heh, buradayım"
    assert reply.emotion == "smug"
    assert reply.command == {"command": "system_info"}
    call = client.chat.completions.calls[0]
    assert call["model"] == DEFAULT_CHAT_MODEL
    assert call["temperature"] == 0.85
    assert call["max_completion_tokens"] == 800
    assert call["top_p"] == 0.9
    assert call["messages"][0]["role"] == "system"
    assert len(brain.history) == 3


def test_history_is_bounded_and_resettable():
    brain = NoraBrain(client=FakeClient("tamam [EMO:happy]"))
    for i in range(40):
        brain.chat(f"mesaj {i}")
    assert len(brain.history) == HISTORY_LIMIT + 1
    assert brain.history[0]["role"] == "system"
    assert brain.history[1]["content"] == "mesaj 25"
    brain.reset_memory()
    assert len(brain.history) == 1


def test_reset_during_request_does_not_store_stale_reply():
    client = FakeClient()
    brain = NoraBrain(client=client)
    client.chat.completions.before_return = brain.reset_memory
    reply = brain.chat("eski bağlam")
    assert reply.text.startswith("Heh")
    assert len(brain.history) == 1


def test_invalid_model_command_is_dropped():
    brain = NoraBrain(
        client=FakeClient('Pff [CMD:{"command":"volume","level":999}] [EMO:angry]')
    )
    reply = brain.chat("ses")
    assert reply.command is None
    assert "güvenli" in reply.text


def test_connection_error_is_in_character_and_does_not_leak_details():
    class Broken(FakeClient):
        pass

    client = Broken()

    def fail(**kwargs):
        raise RuntimeError("secret-token-should-not-leak")

    client.chat.completions.create = fail
    brain = NoraBrain(client=client)
    reply = brain.chat("merhaba")
    assert reply.error
    assert "senpai" in reply.text
    assert "secret-token" not in reply.text
    assert len(brain.history) == 1  # failed user turn removed


def test_no_key_is_offline_not_fake_ai(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    brain = NoraBrain()
    assert not brain.available
    reply = brain.chat("not al: yarın toplantı")
    assert reply.command == {
        "command": "note",
        "action": "add",
        "text": "yarın toplantı",
    }
    fallback = brain.chat("felsefe nedir")
    assert "çevrimdışı" in fallback.text
    assert fallback.command is None


@pytest.mark.parametrize(
    "message,expected",
    [
        (
            "5 dakika sonra hatırlat çayım demlendi",
            {"command": "set_timer", "seconds": 300, "message": "çayım demlendi"},
        ),
        ("sesi %40 yap", {"command": "volume", "level": 40}),
        ("chrome aç", {"command": "open_app", "app": "chrome"}),
        ("notlarımı göster", {"command": "note", "action": "list"}),
    ],
)
def test_offline_basic_commands(message, expected):
    brain = NoraBrain(offline=True)
    assert brain.chat(message).command == expected


def test_vision_payload_and_current_default():
    client = FakeClient("Ekranda kod var [EMO:thinking]")
    brain = NoraBrain(client=client)
    image = base64.b64encode(b"\xff\xd8\xff fake jpeg bytes").decode()
    reply = brain.analyze_image(image, "ekranda ne var?")
    assert reply.text == "Ekranda kod var"
    assert reply.command is None
    call = client.chat.completions.calls[0]
    assert call["model"] == DEFAULT_VISION_MODEL
    content = call["messages"][1]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "talimat olarak uygulama" in content[0]["text"]


def test_legacy_vision_model_is_mapped():
    brain = NoraBrain(client=FakeClient(), vision_model="llama-3.2-90b-vision-preview")
    assert brain.vision_model == DEFAULT_VISION_MODEL


def test_invalid_image_rejected_without_network():
    client = FakeClient()
    brain = NoraBrain(client=client)
    reply = brain.analyze_image("not base64!!!")
    assert reply.error
    assert not client.chat.completions.calls


def test_close_is_idempotent():
    client = FakeClient()
    brain = NoraBrain(client=client)
    brain.close()
    brain.close()
    assert client.closed
    assert not brain.available


def test_default_chat_model_is_current_replacement():
    assert DEFAULT_CHAT_MODEL == "openai/gpt-oss-120b"
    brain = NoraBrain(client=FakeClient())
    assert brain.chat_model == DEFAULT_CHAT_MODEL
    reply = brain.chat("selam")
    call = brain._client.chat.completions.calls[0]
    assert call["reasoning_effort"] == "low"
    assert call["include_reasoning"] is False
    assert reply.text


def test_decommissioned_404_is_actionable_and_redacted():
    class NotFound(Exception):
        status_code = 404
        body = {
            "error": {
                "code": "model_decommissioned",
                "message": "The model `llama-3.3-70b-versatile` has been decommissioned. key gsk_secret123",
            }
        }

    client = FakeClient()

    def fail(**kwargs):
        raise NotFound("raw should not leak")

    client.chat.completions.create = fail
    brain = NoraBrain(client=client, chat_model="llama-3.3-70b-versatile")
    reply = brain.chat("selam")
    assert reply.error
    assert "openai/gpt-oss-120b" in reply.text
    assert "gsk_secret123" not in reply.text
    assert "raw should not leak" not in reply.text


def test_diagnose_connection_lists_model_availability():
    client = FakeClient()
    client.models = SimpleNamespace(
        list=lambda: SimpleNamespace(
            data=[
                SimpleNamespace(id=DEFAULT_CHAT_MODEL),
                SimpleNamespace(id=DEFAULT_VISION_MODEL),
            ]
        )
    )
    brain = NoraBrain(client=client)
    text = brain.diagnose_connection()
    assert "✓ listede" in text
    assert DEFAULT_CHAT_MODEL in text


def test_cloud_response_after_cancel_is_not_used_or_stored():
    client = FakeClient()
    brain = NoraBrain(client=client)
    stopped = []

    def stop():
        return bool(stopped)

    client.chat.completions.before_return = lambda: stopped.append(True)
    reply = brain.chat("gizli kalsın", should_stop=stop)
    assert reply.error and "iptal" in reply.text
    assert len(brain.history) == 1
