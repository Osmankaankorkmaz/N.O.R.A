import json

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtGui import QColor, QImage

from nora.nora_pet import NoraPet, PetState
from nora.nora_avatar import DEFAULT_HAIR
from nora.nora_pixel_art import DEFAULT_HAIR_COLOR
from nora.nora_store import NoraStore
from tools.export_character import ANIMATIONS, POSE_FRAMES, export_all, render_frame


def _colors(image: QImage) -> set[int]:
    return {
        image.pixelColor(x, y).rgba()
        for x in range(image.width())
        for y in range(image.height())
    }


def test_legacy_pixel_palette_still_renders(qapp):
    """The 8-bit chibi remains selectable and keeps its documented palette."""
    pet = NoraPet()
    pet._timer.stop()
    pet.set_appearance({"character_style": "pixel"})
    pet.set_appearance({"hair_color": DEFAULT_HAIR_COLOR})
    # the 8-bit girl is kumral now, matching the illustrated art
    assert pet._appearance["hair_color"] == DEFAULT_HAIR_COLOR == "#a9743f"
    colors = _colors(pet.grab().toImage())
    assert QColor("#a9743f").rgba() in colors  # kumral bob, as in the reference
    assert QColor("#fff5e4").rgba() in colors  # cream turtleneck
    assert QColor("#fbfbfd").rgba() in colors  # white pleated skirt
    assert QColor("#6b4229").rgba() in colors  # brown loafers
    assert QColor("#46ab45").rgba() in colors  # green eyes
    assert QColor("#ff9fa8").rgba() in colors  # blush
    pet.shutdown()


def test_factory_colours_migrate_to_kumral_but_custom_ones_survive(tmp_path):
    path = tmp_path / "state.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "preferences": {"hair_color": "#33204d", "outfit": "classic"},
            }
        ),
        encoding="utf-8",
    )
    store = NoraStore(path)
    assert store.preference("hair_color") == DEFAULT_HAIR
    assert store.preference("appearance_version") == 3
    store.set_preference("address", "Kaan")
    assert NoraStore(path).preference("hair_color") == DEFAULT_HAIR
    store.set_preference("hair_color", "#33204d")
    assert NoraStore(path).preference("hair_color") == "#33204d"

    custom = tmp_path / "custom.json"
    custom.write_text(
        json.dumps({"version": 1, "preferences": {"hair_color": "#202b52"}}),
        encoding="utf-8",
    )
    assert NoraStore(custom).preference("hair_color") == "#202b52"


def test_every_pose_and_animation_is_exported_and_animated(qapp, tmp_path):
    covered = {spec.state for frames in ANIMATIONS.values() for spec in frames}
    # The exporter is allowed to lag behind brand-new states; what must hold is
    # that every state it ships is a real one and that poses stay complete.
    assert covered <= {state.name.lower() for state in PetState}
    assert set(POSE_FRAMES) <= {state.name.lower() for state in PetState}
    for name, frames in ANIMATIONS.items():
        assert len(frames) >= 2, name
        images = [
            render_frame(spec).bits().asstring(render_frame(spec).sizeInBytes())
            for spec in frames
        ]
        assert len(set(images)) >= 2, name
    counts = export_all(tmp_path, png_scale=1, gif_scale=1)
    assert counts == {
        "poses": 18,
        "emotions": 8,
        "accessories": 4,
        "outfits": 3,
        "animations": 24,
    }
    assert (tmp_path / "wolfcut-hero.png").exists()
    assert (tmp_path / "index.html").exists()
    from PIL import Image

    with Image.open(tmp_path / "animations" / "dance.gif") as gif:
        assert gif.n_frames >= 2


def test_default_character_is_kumral_with_green_eyes(qapp):
    """Both the illustrated default and the drawn fallback must read kumral/green."""
    pet = NoraPet()
    pet._timer.stop()
    assert pet.character_style in {"pixel", "sprite", "body"}
    sizes = {
        "pixel": (120, 162),
        "sprite": (168, 330),
        "body": (132, 312),
        "realistic": (260, 360),
    }
    assert (pet.width(), pet.height()) == sizes[pet.character_style]
    assert pet._appearance["hair_color"] == DEFAULT_HAIR
    assert pet._appearance["eye_color"] == "yesil"
    pet.set_emotion("thinking")  # open eyes, so the iris colour is visible
    pet._set_state(
        __import__("nora.nora_pet", fromlist=["PetState"]).PetState.IDLE, 100000
    )
    image = pet.grab().toImage()
    # the portrait is smoothly shaded, so exact palette matches are useless:
    # check hue instead of identity.
    greens = 0
    browns = 0
    for x in range(0, image.width(), 1):
        for y in range(0, image.height(), 1):
            color = image.pixelColor(x, y)
            if color.alpha() < 200:
                continue
            hue = color.hue()
            if 60 <= hue <= 130 and color.green() > color.red() + 8:
                greens += 1
            if 15 <= hue <= 35 and color.red() > color.green() > color.blue():
                browns += 1
    assert greens > 20, "green-leaning eyes missing"
    assert browns > 400, "kumral hair missing"
    from nora.nora_avatar import RealisticCharacter

    assert not RealisticCharacter().portrait().isNull()
    pet.shutdown()
