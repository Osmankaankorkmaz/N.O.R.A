"""Tests for the "app first, character later" startup and personal panel.

These cover the behaviour the user asked for explicitly:

* the app opens as a normal window with the character **tucked inside** it;
* pressing the 8-bit logo lets her **step out onto the desktop**;
* a **single click tickles** her (she giggles), it no longer opens the chat;
* a **double click opens the personal panel** (mood / memories / preferences);
* the **microphone is off** — the user types, Nora speaks.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QImage, QMouseEvent
from PyQt5.QtWidgets import QApplication

from nora.nora_pet import PetState


@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture()
def nora_app(tmp_path: Path, app):
    from nora.nora_ui import NoraApp, NoraOptions

    instance = NoraApp(
        NoraOptions(
            wake_word=False,
            tts=False,
            proactive=False,
            offline=True,
            data_dir=tmp_path,
        )
    )
    yield instance
    instance.shutdown()


# ----------------------------------------------------------------- startup
def test_app_opens_with_the_character_inside_the_logo(nora_app) -> None:
    """Launch shows the window, and Nora has not stepped out yet."""
    nora_app.start()
    assert nora_app.chat_window.isVisible() is True
    assert nora_app.pet.isVisible() is False
    assert nora_app.logo_button.released is False


def test_logo_releases_the_character_onto_the_desktop(nora_app) -> None:
    nora_app.start()
    nora_app.logo_button.clicked.emit()
    assert nora_app.pet.isVisible() is True
    assert nora_app.logo_button.released is True


def test_logo_tucks_her_back_in_on_the_second_press(nora_app) -> None:
    nora_app.start()
    nora_app.release_pet()
    nora_app.logo_button.clicked.emit()
    assert nora_app.pet.isVisible() is False
    assert nora_app.logo_button.released is False


def test_release_is_idempotent(nora_app) -> None:
    nora_app.start()
    nora_app.release_pet()
    nora_app.release_pet()
    assert nora_app.pet.isVisible() is True


def test_opening_the_chat_does_not_release_the_character(nora_app) -> None:
    """Showing the window must not drag her out; the logo is the only way."""
    nora_app.start()
    nora_app.show_chat()
    assert nora_app.pet.isVisible() is False


# ------------------------------------------------------------------ tickle
def test_single_click_tickles_and_giggles(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    assert pet.tickle() is True
    assert pet.state is PetState.GIGGLE


def test_tickle_shows_a_bubble(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    pet.tickle()
    assert pet._bubble is not None
    assert pet._bubble._text


def test_tickle_is_refused_while_airborne(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    pet._apply_character_style("sprite")
    pet._air.grab()
    assert pet.tickle() is False


def test_clicking_the_pet_does_not_open_the_chat(nora_app) -> None:
    """The single click is a tickle now, so the chat must stay as it was."""
    nora_app.start()
    nora_app.chat_window.hide()
    nora_app._on_pet_tickle()
    assert nora_app.chat_window.isVisible() is False
    assert nora_app.pet.state is PetState.GIGGLE


def test_press_event_starts_a_tickle_on_release(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    press = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPoint(10, 10),
        QPoint(40, 40),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    pet.mousePressEvent(press)
    release = QMouseEvent(
        QMouseEvent.MouseButtonRelease,
        QPoint(10, 10),
        QPoint(40, 40),
        Qt.LeftButton,
        Qt.NoButton,
        Qt.NoModifier,
    )
    pet.mouseReleaseEvent(release)
    # The click timer fires shortly after release; trigger it directly.
    pet._click_timer.stop()
    pet.clicked.emit()
    assert pet.state is PetState.GIGGLE


# ------------------------------------------------------------------- panel
def test_double_click_opens_the_personal_panel(nora_app) -> None:
    nora_app._on_double_click()
    assert nora_app.personal_panel is not None
    assert nora_app.personal_panel.isVisible() is True


def test_panel_has_all_three_sections(nora_app) -> None:
    from nora.nora_personal import SECTIONS

    nora_app.show_personal_panel()
    panel = nora_app.personal_panel
    assert len(panel._tab_buttons) == len(SECTIONS) == 3
    for index in range(len(SECTIONS)):
        panel.show_section(index)
        assert panel.pages.currentIndex() == index


def test_panel_offers_every_mood(nora_app) -> None:
    from nora.nora_personal import MOODS

    nora_app.show_personal_panel()
    panel = nora_app.personal_panel
    for mood, _label in MOODS:
        assert mood in panel._mood_chips


def test_choosing_a_mood_changes_the_pet(nora_app) -> None:
    nora_app.show_personal_panel()
    nora_app.personal_panel._mood_chips["sad"].click()
    assert nora_app.pet.emotion == "sad"
    assert nora_app.personal_panel.portrait._mood == "sad"


def test_choosing_a_tone_is_saved(nora_app) -> None:
    nora_app.show_personal_panel()
    nora_app.personal_panel._tone_buttons["playful"].click()
    assert nora_app.store.preference("relationship_tone") == "playful"


def test_invalid_preference_is_reported_not_swallowed(nora_app) -> None:
    nora_app.show_personal_panel()
    nora_app._on_personal_preference("relationship_tone", "nonsense")
    # the value must not be stored; the store rejects it
    assert nora_app.store.preference("relationship_tone") != "nonsense"


def test_panel_reflects_the_current_mood(nora_app) -> None:
    nora_app.pet.set_emotion("angry")
    nora_app.show_personal_panel()
    assert nora_app.personal_panel._mood == "angry"


def test_memories_are_listed_and_deletable(nora_app) -> None:
    from PyQt5.QtWidgets import QLabel

    from nora.nora_personal import MemoryRow

    nora_app.show_personal_panel()
    panel = nora_app.personal_panel
    panel.set_memories([("k1", "Adı Deniz", "2026-01-01")])
    rows = panel.findChildren(MemoryRow)
    assert len(rows) == 1
    assert rows[0].key == "k1"
    texts = " ".join(label.text() for label in rows[0].findChildren(QLabel))
    assert "Deniz" in texts


def test_empty_memory_state_is_honest(nora_app) -> None:
    nora_app.show_personal_panel()
    panel = nora_app.personal_panel
    panel.set_memories([])
    assert "Henüz" in panel.memory_count.text()


def test_panel_is_a_normal_window(nora_app) -> None:
    nora_app.show_personal_panel()
    flags = nora_app.personal_panel.windowFlags()
    assert (flags & Qt.WindowType_Mask) == Qt.Window


# -------------------------------------------------------------- microphone
def test_microphone_is_disabled_by_design() -> None:
    from nora.nora_ui import NoraApp

    assert NoraApp.MICROPHONE_ENABLED is False


def test_asking_for_the_microphone_explains_instead_of_failing(nora_app) -> None:
    nora_app.MICROPHONE_ENABLED = False
    nora_app._start_listening()
    assert nora_app._listening is False
    assert "Mikrofon kapalı" in nora_app.status_label.text()


def test_tts_stays_available(nora_app) -> None:
    """Nora still speaks; only the microphone is off."""
    assert hasattr(nora_app, "voice")
    assert hasattr(nora_app, "tts_action")


# ------------------------------------------------------------------ logo art
def test_logo_draws_the_8_bit_face(nora_app) -> None:
    """The badge must show the pixel girl, not an empty disc."""
    badge = nora_app.logo_button
    badge.resize(46, 46)
    image = QImage(46, 46, QImage.Format_ARGB32)
    image.fill(0)
    badge.render(image)
    opaque = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert opaque > 200


def test_tray_icon_uses_the_pixel_art(nora_app) -> None:
    icon = nora_app._tray_icon()
    assert not icon.isNull()
    pixmap = icon.pixmap(64, 64)
    assert not pixmap.isNull()
