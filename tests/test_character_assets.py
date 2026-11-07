import json

import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtGui import QColor, QImage

from nora.nora_pet import NoraPet, PetState
from nora.nora_pixel_art import DEFAULT_HAIR_COLOR
from nora.nora_store import NoraStore
from tools.export_character import ANIMATIONS, POSE_FRAMES, export_all, render_frame


def _colors(image: QImage) -> set[int]:
    return {
        image.pixelColor(x, y).rgba()
        for x in range(image.width())
        for y in range(image.height())
    }


def test_requested_wolfcut_palette_is_the_default(qapp):
    pet = NoraPet()
    pet._timer.stop()
    assert pet._appearance["hair_color"] == DEFAULT_HAIR_COLOR == "#f5f3f0"
    assert NoraStore().preference("hair_color") == DEFAULT_HAIR_COLOR
    colors = _colors(pet.grab().toImage())
    assert QColor("#f5f3f0").rgba() in colors  # white wolfcut hair
    assert QColor("#1c1c24").rgba() in colors  # black dress
    assert QColor("#d92b3d").rgba() in colors  # red shoes
    assert QColor("#e6384c").rgba() in colors  # red eyes
    pet.shutdown()


def test_old_factory_purple_migrates_once_but_custom_colors_are_kept(tmp_path):
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
    assert store.preference("hair_color") == DEFAULT_HAIR_COLOR
    assert store.preference("appearance_version") == 2
    store.set_preference("address", "Kaan")
    assert NoraStore(path).preference("hair_color") == DEFAULT_HAIR_COLOR
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
    assert {state.name.lower() for state in PetState} <= covered
    assert set(POSE_FRAMES) == {state.name.lower() for state in PetState}
    for name, frames in ANIMATIONS.items():
        assert len(frames) >= 2, name
        images = [
            render_frame(spec).bits().asstring(render_frame(spec).sizeInBytes())
            for spec in frames
        ]
        assert len(set(images)) >= 2, name
    counts = export_all(tmp_path, png_scale=1, gif_scale=1)
    assert counts == {
        "poses": 16,
        "emotions": 8,
        "accessories": 4,
        "outfits": 3,
        "animations": 22,
    }
    assert (tmp_path / "wolfcut-hero.png").exists()
    assert (tmp_path / "index.html").exists()
    from PIL import Image

    with Image.open(tmp_path / "animations" / "dance.gif") as gif:
        assert gif.n_frames >= 2
