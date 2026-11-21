"""Tests for 1.11.0: realistic avatar, glass panel, Groq key, installer."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QLineEdit

from nora.nora_avatar import (
    DEFAULT_HAIR,
    SUPPORTED_EYE_COLORS,
    RealisticCharacter,
)
from nora.nora_pet import NoraPet, _character_style, _tooltip_for
from nora.nora_ui import NoraApp, NoraOptions


# --------------------------------------------------------------------- avatar
def test_realistic_portrait_is_smooth_shaded_not_pixel_art(qapp):
    artist = RealisticCharacter()
    image = artist.portrait(state="idle", emotion="happy")
    assert image.width() == 260 and image.height() == 360
    # A 3× downscaled painterly render has far more distinct colours than the
    # 20-ish palette of the old chibi.
    colours = {
        image.pixelColor(x, y).rgba()
        for x in range(0, image.width(), 3)
        for y in range(0, image.height(), 3)
    }
    assert len(colours) > 300
    # Transparent corners: the pet window is not a rectangle.
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(0, 120).alpha() == 0
    # torso is opaque near the bottom centre but never reaches the corners
    assert image.pixelColor(130, 340).alpha() > 0
    assert image.pixelColor(4, 356).alpha() == 0


def test_avatar_eyes_are_green_and_hair_is_kumral(qapp):
    artist = RealisticCharacter()
    image = artist.portrait(
        appearance={"hair_color": DEFAULT_HAIR, "eye_color": "yesil"}
    )
    greens = browns = 0
    for x in range(0, image.width(), 2):
        for y in range(0, image.height(), 2):
            colour = image.pixelColor(x, y)
            if colour.alpha() < 200:
                continue
            hue = colour.hue()
            if 60 <= hue <= 130 and colour.green() > colour.red() + 8:
                greens += 1
            elif 15 <= hue <= 35 and colour.red() > colour.green() > colour.blue():
                browns += 1
    assert greens > 20
    assert browns > 400


@pytest.mark.parametrize("emotion", ["happy", "love", "angry", "sleepy", "thinking"])
def test_every_emotion_and_state_changes_the_avatar(qapp, emotion):
    artist = RealisticCharacter()
    base = artist.portrait(state="idle", emotion="happy")
    variant = artist.portrait(state="idle", emotion=emotion)
    assert not variant.isNull()
    if emotion != "happy":
        assert variant != base


def test_blink_frame_differs_and_caching_is_transparent(qapp):
    artist = RealisticCharacter()
    open_eyes = artist.portrait(state="idle", frame=10)
    closed_eyes = artist.portrait(state="idle", frame=10, blinking=True)
    assert open_eyes != closed_eyes
    # identical arguments must come back from the memo cache
    assert artist.portrait(state="idle", frame=10) is artist.portrait(
        state="idle", frame=10
    )


def test_tray_icon_uses_the_realistic_face(qapp):
    from PyQt5.QtGui import QPixmap

    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    RealisticCharacter().draw_icon(painter, 64, {"hair_color": DEFAULT_HAIR})
    painter.end()
    image = pixmap.toImage()
    opaque = sum(
        image.pixelColor(x, y).alpha() > 0
        for x in range(image.width())
        for y in range(image.height())
    )
    assert opaque > 1500


# ---------------------------------------------------------------- style switch
def test_full_body_is_default_and_other_styles_still_available(qapp):
    pet = NoraPet()
    pet._timer.stop()
    # default: the small full-body character (arms, legs, feet)
    assert pet.character_style == "body"
    assert (pet.width(), pet.height()) == (132, 312)
    assert not pet.grab().isNull()

    pet.set_appearance({"character_style": "pixel"})
    assert pet.character_style == "pixel"
    assert (pet.width(), pet.height()) == (120, 150)

    pet.set_appearance({"character_style": "realistic"})
    assert pet.character_style == "realistic"
    assert (pet.width(), pet.height()) == (260, 360)

    pet.set_appearance({"character_style": "body"})
    assert (pet.width(), pet.height()) == (132, 312)
    pet.shutdown()


def test_character_style_preference_and_env(monkeypatch):
    assert _character_style({"character_style": "pixel"}) == "pixel"
    assert _character_style({"character_style": "nonsense"}) == "body"
    monkeypatch.setenv("NORA_CHARACTER", "pixel")
    assert _character_style({}) == "pixel"
    monkeypatch.setenv("NORA_CHARACTER", "unknown")
    assert _character_style({}) == "body"
    assert "8-bit" in _tooltip_for("pixel")
    assert "8-bit" not in _tooltip_for("realistic")


def test_store_validates_and_migrates_appearance(qapp, tmp_path):
    from nora.nora_store import NoraStore

    store = NoraStore(tmp_path / "state.json")
    assert store.preference("character_style") == "body"
    assert store.preference("hair_color") == DEFAULT_HAIR
    assert store.preference("appearance_version") == 3
    with pytest.raises(ValueError):
        store.set_preference("character_style", "anime")
    with pytest.raises(ValueError):
        store.set_preference("eye_color", "turquoise")
    store.set_preference("eye_color", "hazel")
    assert NoraStore(tmp_path / "state.json").preference("eye_color") == "hazel"


def test_all_documented_eye_colours_render(qapp):
    artist = RealisticCharacter()
    images = set()
    for name in SUPPORTED_EYE_COLORS:
        image = artist.portrait(appearance={"eye_color": name})
        assert not image.isNull()
        images.add(image.pixelColor(104, 132).rgba())
    assert len(images) >= 4


# ------------------------------------------------------------------ glass chat
def test_chat_uses_glass_panel_and_bubbles(qapp, tmp_path):
    from nora.nora_glass import GlassBubble, FrostedPanel

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    assert isinstance(app.glass_panel, FrostedPanel)
    app.add_message("Merhaba", "bot")
    app.add_message("selam", "user")
    bubbles = app.chat_window.findChildren(GlassBubble)
    assert len(bubbles) == 2
    assert {b.sender for b in bubbles} == {"bot", "user"}
    # the panel must be translucent, not an opaque rectangle
    assert app.chat_window.testAttribute(Qt.WA_TranslucentBackground)
    app.shutdown()


def test_glass_panel_paints_a_translucent_card(qapp):
    from nora.nora_glass import FrostedPanel

    panel = FrostedPanel()
    panel.resize(240, 300)
    image = panel.grab().toImage()
    assert image.pixelColor(120, 150).alpha() in range(1, 256)
    assert image.pixelColor(0, 0).alpha() == 0  # rounded corner stays clear
    panel.set_backdrop_enabled(False)
    assert panel.backdrop_enabled() is False


def test_chat_typing_indicator_follows_busy_state(qapp, tmp_path):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.show_chat()
    app._set_busy(True, "düşünüyorum…")
    assert app.typing_indicator.isVisible()
    app._set_busy(False)
    assert app.typing_indicator.isHidden()
    app.shutdown()


# ------------------------------------------------------------------- Groq key
def test_groq_key_is_validated_and_never_written_to_json(monkeypatch, tmp_path):
    from nora import nora_secrets

    monkeypatch.setattr(nora_secrets, "_keyring", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    nora_secrets._session_key = ""

    assert "gsk_" in nora_secrets.save_groq_key("kisa")
    status = nora_secrets.save_groq_key("gsk_" + "a" * 40)
    assert "bellekte" in status  # no keyring → session only, said honestly
    assert nora_secrets.resolve_groq_key() == "gsk_" + "a" * 40
    assert nora_secrets.mask_groq_key().startswith("gsk_")
    assert nora_secrets.groq_key_present()
    nora_secrets.clear_groq_key()
    assert not nora_secrets.groq_key_present()

    from nora.nora_store import NoraStore

    store = NoraStore(tmp_path / "state.json")
    store.update_preferences({"chat_model": "openai/gpt-oss-120b"})
    raw = (tmp_path / "state.json").read_text(encoding="utf-8")
    assert "gsk_" not in raw
    assert json.loads(raw)["preferences"]["chat_model"] == "openai/gpt-oss-120b"


def test_env_key_wins_over_stored_key(monkeypatch):
    from nora import nora_secrets

    monkeypatch.setattr(nora_secrets, "_keyring", lambda: None)
    nora_secrets._session_key = "gsk_session"
    monkeypatch.setenv("GROQ_API_KEY", "gsk_env")
    assert nora_secrets.resolve_groq_key() == "gsk_env"
    assert nora_secrets.groq_key_source() == "ortam değişkeni"


def test_settings_dialog_masks_key_and_validates_chat_model(qapp, tmp_path):
    from nora.nora_settings_dialog import NoraSettingsDialog
    from nora.nora_store import NoraStore

    store = NoraStore(tmp_path / "state.json")
    dialog = NoraSettingsDialog(store, on_apply=lambda values: None)
    field = dialog.fields["groq_api_key"]
    assert isinstance(field, QLineEdit)
    assert field.echoMode() == QLineEdit.Password
    assert dialog.api_key() == ""
    assert "character_style" in dialog.fields
    assert "eye_color" in dialog.fields
    dialog.fields["character_style"].setCurrentIndex(
        dialog.fields["character_style"].findData("pixel")
    )
    values = dialog.values()
    assert values["character_style"] == "pixel"
    assert "groq_api_key" not in values


def test_brain_reloads_credentials_without_offline_fallback(monkeypatch):
    from nora.nora_brain import NoraBrain

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr("nora.nora_brain._stored_key", lambda: "")
    brain = NoraBrain(offline=False)
    assert not brain.available
    status = brain.reload_credentials("gsk_" + "b" * 40)
    # groq is installed in the test env, so the client must open
    assert brain.available or "paketi" in status
    brain.close()


def test_brain_probe_reports_offline_without_network():
    from nora.nora_brain import NoraBrain

    brain = NoraBrain(offline=True)
    ok, message = brain.probe()
    assert ok is False
    assert "Çevrimdışı" in message


# ----------------------------------------------------------------- Spotify app
@pytest.mark.parametrize(
    "text,expected",
    [
        ("spotify aç ve back in black çal", "back in black"),
        (
            "spotify aç ve back in black i çal bilgisayarımdaki uygulumasını aç",
            "back in black",
        ),
        ("back in black’ı spotify’da çal", "back in black"),
        ("spotify uygulamasını aç ve nothing else matters çal", "nothing else matters"),
    ],
)
def test_spotify_open_and_play_is_parsed(text, expected):
    from nora.nora_commands import parse_direct_command

    result = parse_direct_command(text)
    assert result is not None
    assert result.command["command"] == "media"
    assert result.command["query"] == expected
    assert result.command.get("open_app") is True


def test_spotify_plain_search_command_is_unchanged():
    from nora.nora_commands import parse_direct_command

    result = parse_direct_command("spotifyda lofi hip hop çal")
    assert result.command["query"] == "lofi hip hop"
    assert "open_app" not in result.command


def test_play_music_opens_app_then_reports_honestly(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    opened = []
    monkeypatch.setattr(
        app.tools,
        "open_app",
        lambda name: opened.append(name) or "spotify başlattım senpai~",
    )
    # Never touch the real spotify: URL handler (it exists on Windows/macOS CI).
    deep_links: list[str] = []
    monkeypatch.setattr(
        type(app),
        "_open_spotify_deep_link",
        lambda self, query: deep_links.append(query) or False,
    )
    searched = []
    monkeypatch.setattr(
        app.tools,
        "spotify_search",
        lambda query: (
            searched.append(query) or "Bağlantıyı tarayıcıda açtım senpai. 🔗"
        ),
    )
    message = app._play_music("back in black", open_app=True)
    assert opened == ["spotify"]
    assert searched == ["back in black"]
    assert deep_links == ["back in black"]
    assert "Spotify aramasını" in message
    assert "çalıyorum" not in message.split("Spotify aramasını")[0]
    app.shutdown()


def test_play_music_uses_api_when_connected(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    monkeypatch.setattr(type(app.spotify), "connected", lambda self: True)
    monkeypatch.setattr(
        app.spotify,
        "play_track",
        lambda query: f"Spotify'da çalıyorum: {query} 🎧",
    )
    message = app._play_music("back in black")
    assert "Spotify'da çalıyorum: back in black" in message
    app.shutdown()


# -------------------------------------------------------------------- installer
def test_installer_defaults_full_and_doctor_only(monkeypatch, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import install

    assert install.selected_features(install.parse_args([])) == ["piper"]
    assert set(install.selected_features(install.parse_args(["--full"]))) == set(
        install.FEATURES
    )
    assert install.selected_features(install.parse_args(["--base"])) == []
    assert install.selected_features(
        install.parse_args(["--features", "chat,piper"])
    ) == ["chat", "piper"]
    with pytest.raises(SystemExit):
        install.selected_features(install.parse_args(["--features", "nope"]))
    install.paint("x", install.GREEN)
    install.ok("tamam")
    assert "tamam" in capsys.readouterr().out


def test_installer_doctor_only_runs_headless_doctor(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import install

    calls = []
    monkeypatch.setattr(
        install,
        "run_doctor",
        lambda python, checks, quiet=False: calls.append(checks) or 1,
    )
    assert install.main(["--doctor-only", "--base"]) == 1
    assert calls == [[]]


def test_installer_rejects_old_python(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import install

    class FakeVersion(tuple):
        major, minor = 3, 8

        def __getitem__(self, item):
            return (3, 8)[item]

    monkeypatch.setattr(install.sys, "version_info", FakeVersion())
    assert install.check_python() is False


def test_installer_never_runs_sudo(monkeypatch, capsys):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import install

    commands = []
    monkeypatch.setattr(install.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        install.subprocess, "run", lambda *a, **k: commands.append(a) or None
    )
    install.linux_hint()
    assert "sudo apt-get install" in capsys.readouterr().out
    assert commands == []


def test_deep_link_success_is_reported_without_browser_fallback(
    qapp, tmp_path, monkeypatch
):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    monkeypatch.setattr(type(app.spotify), "connected", lambda self: False)
    monkeypatch.setattr(type(app), "_open_spotify_deep_link", lambda self, query: True)
    searched: list[str] = []
    monkeypatch.setattr(
        app.tools, "spotify_search", lambda query: searched.append(query) or "x"
    )
    message = app._play_music("back in black")
    assert "Spotify uygulamasında aramayı açtım" in message
    assert searched == []  # no browser tab when the app accepted the link
    assert "bağla" in message  # still honest that playback needs the API
    app.shutdown()


def test_deep_link_is_platform_guarded(qapp, tmp_path, monkeypatch):
    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    monkeypatch.setattr("nora.nora_ui.sys.platform", "linux")
    started: list[str] = []
    monkeypatch.setattr(
        "nora.nora_ui.os.startfile", lambda uri: started.append(uri), raising=False
    )
    # the autouse fixture stubs the public hook; exercise the real guarded code
    guarded = type(app)._real_open_spotify_deep_link
    assert guarded(app, "back in black") is False
    assert guarded(app, "") is False
    assert started == []
    app.shutdown()
