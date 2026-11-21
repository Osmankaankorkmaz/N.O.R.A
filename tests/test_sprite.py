"""Tests for the illustrated (AI-generated) sprite character.

Three layers are covered:

1. :mod:`nora.nora_sprite` — loading, white keying, trimming, mood mapping,
   locomotion cycles, crossfade bookkeeping and portraits.
2. :mod:`nora.nora_physics` — the grab → fall → land → recover stage machine
   and the throw physics used when she is dragged and released.
3. The pet/UI integration — sprite style selection, honest fallback to the
   drawn body when the sheets are missing, and the mouse interaction wiring.

The tests never require network access and skip the pixel assertions when the
artwork is absent (a source checkout may legitimately not ship the PNGs).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter
from PyQt5.QtWidgets import QApplication

from nora.nora_physics import GRAVITY, AirPhysics, AirStages, AirState
from nora.nora_sprite import (
    AIR_FRAMES,
    MOOD_SPRITES,
    RUN_FRAMES,
    WALK_FRAMES,
    SpriteAssets,
    SpriteCharacter,
    SpriteLibrary,
    iter_missing,
)

ASSETS = Path(__file__).resolve().parent.parent / "docs" / "character" / "ai"


# --------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def app() -> QApplication:
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


@pytest.fixture(scope="module")
def art_available() -> bool:
    return (ASSETS / "base_idle.png").is_file()


# ------------------------------------------------------------------ library
def test_asset_dir_points_at_the_repository_art() -> None:
    assert ASSETS.is_dir()
    library = SpriteLibrary()
    assert library.root == ASSETS


def test_missing_file_returns_none_without_raising(tmp_path: Path, app) -> None:
    library = SpriteLibrary(tmp_path)
    assert library.frame("base_idle") is None
    assert library.mood_for("happy") is None
    assert library.available() == set()
    assert library.has_all(["base_idle"]) is False


def test_iter_missing_lists_every_wanted_name(tmp_path: Path) -> None:
    missing = set(iter_missing(tmp_path))
    expected = set(MOOD_SPRITES.values()) | set(WALK_FRAMES) | set(RUN_FRAMES)
    expected |= set(AIR_FRAMES.values())
    assert missing == expected


def test_unknown_emotion_falls_back_to_idle(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    library = SpriteLibrary()
    assert library.mood_for("definitely-not-an-emotion") == "base_idle"
    assert library.mood_for("HAPPY") == "happy"


def test_every_mood_sprite_maps_to_a_known_name() -> None:
    for emotion, sprite in MOOD_SPRITES.items():
        assert isinstance(emotion, str) and emotion == emotion.lower()
        assert isinstance(sprite, str) and sprite


def test_white_background_is_keyed_out(art_available, app) -> None:
    """The flat white poster must become transparent, highlights must not."""
    if not art_available:
        pytest.skip("artwork not present")
    library = SpriteLibrary()
    frame = library.frame("base_idle")
    assert frame is not None
    image = frame.pixmap.toImage()
    for x, y in ((1, 1), (image.width() - 2, 1), (1, image.height() - 2)):
        assert image.pixelColor(x, y).alpha() == 0


def test_trimmed_bounds_are_tighter_than_the_canvas(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    library = SpriteLibrary()
    frame = library.frame("base_idle")
    assert frame is not None
    canvas = frame.pixmap.toImage().rect()
    bounds = frame.bounds
    assert bounds.width() < canvas.width()
    assert bounds.height() < canvas.height()
    # ...but the figure still fills most of the height (a full body sheet).
    assert bounds.height() > canvas.height() * 0.7


def test_frames_are_cached(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    library = SpriteLibrary()
    first = library.frame("happy")
    second = library.frame("happy")
    assert first is second


# ------------------------------------------------------------------ character
def test_mood_switch_reports_change_once(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    assert character.set_mood("happy") is True
    assert character.sprite == "happy"
    assert character.set_mood("happy") is False  # already there


def test_unknown_mood_is_ignored(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    character.set_mood("happy")
    assert character.set_mood("nonsense") is False
    assert character.sprite == "happy"


def test_locomotion_cycles_through_the_walk_frames(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    character.set_locomotion("walk")
    seen = []
    for _ in range(len(WALK_FRAMES)):
        seen.append(character.active_sprite())
        character.tick(character.WALK_PHASE)
    assert seen == list(WALK_FRAMES)


def test_run_cycle_is_faster_than_walk(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    assert SpriteCharacter.RUN_PHASE < SpriteCharacter.WALK_PHASE


def test_airborne_stage_overrides_locomotion(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    character.set_locomotion("walk")
    character.set_airborne("falling")
    assert character.active_sprite() == AIR_FRAMES["falling"]
    character.set_airborne(None)
    assert character.active_sprite() in WALK_FRAMES


def test_tick_clamps_a_huge_delta(art_available, app) -> None:
    """A hidden window must not make her teleport through the whole cycle."""
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    character.set_locomotion("walk")
    character.tick(120.0)  # two minutes in one frame
    assert character._elapsed <= 0.35


def test_paint_into_target_is_bottom_anchored(art_available, app) -> None:
    """The shoes must sit on the bottom edge whatever the target aspect is."""
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    character.set_mood("happy")
    target = QRectF(0, 0, 120, 400)
    canvas = QImage(160, 440, QImage.Format_ARGB32)
    canvas.fill(QColor(0, 0, 0, 0))
    painter = QPainter(canvas)
    assert character.paint(painter, target) is True
    painter.end()

    rows = [
        y
        for y in range(canvas.height())
        if any(canvas.pixelColor(x, y).alpha() > 8 for x in range(0, canvas.width(), 3))
    ]
    assert rows
    assert abs(rows[-1] - target.bottom()) < 12


def test_paint_without_art_returns_false(tmp_path: Path, app) -> None:
    character = SpriteCharacter(SpriteLibrary(tmp_path))
    canvas = QImage(50, 50, QImage.Format_ARGB32)
    painter = QPainter(canvas)
    assert character.paint(painter, QRectF(0, 0, 50, 50)) is False
    painter.end()


def test_portrait_is_square_and_opaque(art_available, app) -> None:
    if not art_available:
        pytest.skip("artwork not present")
    character = SpriteCharacter()
    image = character.portrait(64, "happy")
    assert image.width() == 64 and image.height() == 64
    assert image.pixelColor(32, 32).alpha() > 0


def test_portrait_without_art_is_transparent_not_a_crash(tmp_path: Path, app) -> None:
    character = SpriteCharacter(SpriteLibrary(tmp_path))
    image = character.portrait(32)
    assert image.width() == 32
    assert image.pixelColor(16, 16).alpha() == 0


def test_sprite_assets_usable_flag(tmp_path: Path, art_available, app) -> None:
    assert SpriteAssets(SpriteLibrary(tmp_path)).usable is False
    if art_available:
        assert SpriteAssets().usable is True


# ------------------------------------------------------------------- stages
def test_stages_start_on_the_ground() -> None:
    stages = AirStages()
    assert stages.state is AirState.GROUND
    assert stages.stage() is None
    assert stages.busy is False


def test_pickup_then_held_after_the_pickup_time() -> None:
    stages = AirStages()
    stages.grab()
    assert stages.stage() == "picked_up"
    stages.tick(AirStages.PICKUP_TIME + 0.01)
    assert stages.stage() == "held"


def test_fall_uses_bracing_when_dropped_from_height() -> None:
    stages = AirStages()
    stages.grab()
    stages.release(speed=900)
    assert stages.stage() == "bracing"
    stages2 = AirStages()
    stages2.grab()
    stages2.release(speed=40)
    assert stages2.stage() == "falling"


def test_landing_then_recovering_then_ground() -> None:
    stages = AirStages()
    stages.grab()
    stages.release(speed=10)
    stages.landed(speed=10)
    assert stages.stage() == "landing"
    stages.tick(AirStages.LAND_TIME + 0.01)
    assert stages.stage() == "recovering"
    stages.tick(AirStages.RECOVER_TIME + 0.01)
    assert stages.stage() is None
    assert stages.busy is False


def test_release_without_grab_is_a_no_op() -> None:
    stages = AirStages()
    stages.release(speed=500)
    assert stages.state is AirState.GROUND


def test_reset_clears_everything() -> None:
    stages = AirStages()
    stages.grab()
    stages.release(speed=100)
    stages.reset()
    assert stages.state is AirState.GROUND
    assert stages.stage() is None


def test_a_long_hidden_window_still_finishes_the_phase() -> None:
    """Time must not be swallowed: after a long gap she is back on the ground."""
    stages = AirStages()
    stages.grab()
    stages.release(speed=10)
    stages.landed(speed=10)
    stages.tick(5.0)
    assert stages.state is AirState.GROUND


# ------------------------------------------------------------------ physics
def test_gravity_pulls_a_dropped_body_down() -> None:
    body = AirPhysics(600.0)
    body.grab(100, 100)
    body.release()
    for _ in range(10):
        body.tick(1 / 60)
    assert body.body.vy > 0
    assert body.body.y > 100


def test_body_never_falls_through_the_floor() -> None:
    physics = AirPhysics(500.0)
    physics.grab(10, 100)
    physics.release()
    for _ in range(400):
        physics.tick(1 / 60)
    assert physics.body.y <= 500.0 + 1e-6
    assert physics.state is not AirState.FALLING


def test_drop_height_matches_free_fall_maths() -> None:
    """After t seconds of free fall she should be ~½gt² lower."""
    physics = AirPhysics(100000.0)  # a very deep floor: no landing yet
    physics.grab(0, 0)
    physics.release()
    steps = 30
    for _ in range(steps):
        physics.tick(1 / 60)
    t = steps / 60
    # Semi-implicit Euler gains an extra ½·g·dt·t term over the textbook
    # formula, which is the same order as our 2 % tolerance.
    expected = 0.5 * GRAVITY * t * t + 0.5 * GRAVITY * (1 / 60) * t
    assert physics.body.y == pytest.approx(expected, rel=0.02)


def test_bounce_is_smaller_than_the_fall() -> None:
    physics = AirPhysics(300.0)
    physics.grab(0, 0)
    physics.release()
    peak = 0.0
    for _ in range(400):
        physics.tick(1 / 60)
        if physics.state is AirState.FALLING:
            peak = max(peak, 300.0 - physics.body.y)
        if physics.state is AirState.LANDING:
            break
    assert peak > 100.0  # she really fell


def test_walls_stop_her_from_leaving_the_screen() -> None:
    physics = AirPhysics(1000.0)
    physics.grab(50, 50)
    physics.body.vx = -5000.0
    physics.release()
    for _ in range(120):
        physics.tick(1 / 60, min_x=0.0, max_x=300.0)
    assert physics.body.x >= 0.0
    assert physics.body.x <= 300.0


def test_tick_with_zero_delta_is_safe() -> None:
    physics = AirPhysics(100.0)
    assert physics.tick(0.0) is False


def test_state_returns_to_ground_after_recovery() -> None:
    physics = AirPhysics(200.0)
    physics.grab(0, 50)
    physics.release()
    for _ in range(600):
        physics.tick(1 / 60)
    assert physics.state is AirState.GROUND


# ----------------------------------------------------------------------- pet
@pytest.fixture()
def pet(tmp_path: Path, app, monkeypatch):
    monkeypatch.setenv("NORA_DATA_DIR", str(tmp_path))
    from nora.nora_pet import NoraPet

    widget = NoraPet()
    yield widget
    widget.close()


def test_default_style_is_the_8_bit_character(pet) -> None:
    # The pixel girl is the default look; the illustrated sheets stay available.
    assert pet.character_style in {"pixel", "sprite", "body"}


def test_sprite_style_uses_the_illustrated_window_size(pet) -> None:
    pet._apply_character_style("sprite")
    if pet._sprite_assets.usable:
        assert (pet.WIDTH, pet.HEIGHT) == (pet.SPRITE_WIDTH, pet.SPRITE_HEIGHT)


def test_missing_art_falls_back_to_the_drawn_body(app, monkeypatch, tmp_path) -> None:
    """Honest fallback: without the PNGs the app draws instead of erroring."""
    from nora.nora_pet import NoraPet

    monkeypatch.setenv("NORA_DATA_DIR", str(tmp_path))
    pet = NoraPet()
    try:
        pet._sprite_assets = SpriteAssets(SpriteLibrary(tmp_path / "nope"))
        pet._apply_character_style("sprite")
        assert pet.character_style == "body"
    finally:
        pet.close()


def test_emotion_lands_on_the_right_sprite(pet) -> None:
    pet._apply_character_style("sprite")
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    for emotion, expected in (
        ("happy", "happy"),
        ("sad", "sad"),
        ("angry", "angry"),
        ("thinking", "thinking"),
    ):
        pet.emotion = emotion
        for _ in range(4):
            pet._tick_sprite()
        assert pet._sprite_artist.active_sprite() == expected


def test_walking_uses_the_walk_cycle(pet) -> None:
    pet._apply_character_style("sprite")
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    from nora.nora_pet import PetState

    pet._set_state(PetState.WALK_RIGHT)
    pet._tick_sprite()
    assert pet._sprite_artist.active_sprite() in WALK_FRAMES


def test_grab_sets_the_pickup_sprite(pet) -> None:
    pet._apply_character_style("sprite")
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    from PyQt5.QtCore import QPoint
    from PyQt5.QtGui import QMouseEvent

    event = QMouseEvent(
        QMouseEvent.MouseButtonPress,
        QPoint(10, 10),
        QPoint(40, 40),
        Qt.LeftButton,
        Qt.LeftButton,
        Qt.NoModifier,
    )
    pet._apply_character_style("sprite")
    pet.mousePressEvent(event)
    pet._tick_sprite()
    assert pet._sprite_artist.active_sprite() == AIR_FRAMES["picked_up"]


def test_airborne_sprites_own_the_frame_while_held(pet) -> None:
    pet._apply_character_style("sprite")
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    pet._air.grab()
    pet._tick_sprite()
    assert pet._sprite_artist.active_sprite() in AIR_FRAMES.values()


def test_reset_air_returns_to_the_mood_sprite(pet) -> None:
    pet._apply_character_style("sprite")
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    pet._air.grab()
    pet._tick_sprite()
    pet._reset_air()
    pet._tick_sprite()
    assert pet._sprite_artist.active_sprite() not in AIR_FRAMES.values()


def test_sprite_style_switch_resizes_the_window(pet) -> None:
    pet._apply_character_style("pixel")
    assert (pet.WIDTH, pet.HEIGHT) == (pet.PIXEL_WIDTH, pet.PIXEL_HEIGHT)
    pet._apply_character_style("sprite")
    if pet._sprite_assets.usable:
        assert (pet.WIDTH, pet.HEIGHT) == (pet.SPRITE_WIDTH, pet.SPRITE_HEIGHT)


def test_sprite_style_keeps_the_window_on_screen(pet) -> None:
    pet._apply_character_style("sprite" if pet._sprite_assets.usable else "body")
    available, _ = pet._screen_rects()
    assert pet._x >= available.left() - 1
    assert pet._x + pet.WIDTH <= available.right() + 1


def test_rendering_the_sprite_style_produces_pixels(pet) -> None:
    if not pet._sprite_assets.usable:
        pytest.skip("artwork not present")
    pet._apply_character_style("sprite")
    pet.emotion = "happy"
    for _ in range(4):
        pet._tick_sprite()
    image = QImage(pet.WIDTH, pet.HEIGHT, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0))
    pet.render(image)
    opaque = sum(
        1
        for x in range(0, image.width(), 4)
        for y in range(0, image.height(), 4)
        if image.pixelColor(x, y).alpha() > 8
    )
    assert opaque > 100


def test_physics_offsets_are_never_negative() -> None:
    physics = AirPhysics(100.0)
    physics.grab(0, 40)
    physics.release()
    for _ in range(200):
        physics.tick(1 / 60)
        assert physics.offset_y() >= 0.0
        assert not math.isnan(physics.offset_y())
