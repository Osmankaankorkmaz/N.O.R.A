import pytest

pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter, QPixmap

from nora.nora_pet import NoraPet, PetState
from nora.nora_pixel_art import GRID_HEIGHT, GRID_WIDTH, PIXEL_SIZE, PixelCharacter


def _assert_crisp_grid(image: QImage, block: int) -> None:
    assert image.width() % block == 0 and image.height() % block == 0
    for y in range(0, image.height(), block):
        for x in range(0, image.width(), block):
            color = image.pixelColor(x, y)
            for dy in range(block):
                for dx in range(block):
                    assert image.pixelColor(x + dx, y + dy) == color


def _opaque_count(image: QImage) -> int:
    return sum(
        image.pixelColor(x, y).alpha() > 0
        for x in range(image.width())
        for y in range(image.height())
    )


@pytest.mark.parametrize("state", list(PetState))
def test_every_pet_pose_is_crisp_and_fits_the_transparent_canvas(qapp, state):
    pet = NoraPet()
    pet._timer.stop()
    pet._set_state(state, 100000)
    image = pet.grab().toImage()
    assert image.width() == GRID_WIDTH * PIXEL_SIZE == 120
    assert image.height() == GRID_HEIGHT * PIXEL_SIZE == 150
    assert _opaque_count(image) > 1500
    _assert_crisp_grid(image, PIXEL_SIZE)
    for x in range(image.width()):
        assert image.pixelColor(x, 0).alpha() == 0
        assert image.pixelColor(x, image.height() - 1).alpha() == 0
    for y in range(image.height()):
        assert image.pixelColor(0, y).alpha() == 0
        assert image.pixelColor(image.width() - 1, y).alpha() == 0
    pet.shutdown()


def test_hair_outfit_and_accessories_change_the_pixel_art(qapp):
    pet = NoraPet()
    pet._timer.stop()
    base = pet.grab().toImage()
    pet.set_appearance({"hair_color": "#202b52"})
    assert pet.grab().toImage() != base
    pet.set_appearance({"outfit": "casual"})
    casual = pet.grab().toImage()
    assert casual != base
    pet.set_appearance({"outfit": "night"})
    assert pet.grab().toImage() != casual
    for accessory in ("headphones", "glasses", "ribbon"):
        pet.set_appearance({"accessory": "none"})
        without = pet.grab().toImage()
        pet.set_appearance({"accessory": accessory})
        assert pet.grab().toImage() != without
    pet.shutdown()


def test_listening_hand_talking_mouth_and_decorative_toggle_are_visible(qapp):
    pet = NoraPet()
    pet._timer.stop()
    pet.set_listening(True)
    assert pet.state == PetState.LISTENING
    listening = pet.grab().toImage()
    assert listening.pixelColor(32 * PIXEL_SIZE, 19 * PIXEL_SIZE).alpha() > 0
    pet.set_listening(False)
    pet.set_speaking(True)
    pet._frame = 0
    open_mouth = pet.grab().toImage()
    pet._frame = 6
    assert pet.grab().toImage() != open_mouth
    pet.set_speaking(False)
    pet.set_appearance({"animations": False})
    pet._frame = 0
    still = pet.grab().toImage()
    pet._frame = 96
    assert pet.grab().toImage() == still
    pet.shutdown()


def test_sleep_walk_love_and_dance_have_distinct_pixel_frames(qapp):
    pet = NoraPet()
    pet._timer.stop()
    for state, next_frame in (
        (PetState.SLEEP, 12),
        (PetState.WALK_RIGHT, 6),
        (PetState.LOVE, 12),
        (PetState.DANCE, 6),
    ):
        pet._set_state(state, 100000)
        pet._frame = 0
        first = pet.grab().toImage()
        pet._frame = next_frame
        assert pet.grab().toImage() != first
    pet.shutdown()


def test_tray_icon_uses_the_same_integer_pixel_style(qapp):
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    PixelCharacter.draw_icon(
        painter, 64, {"hair_color": "#33204d", "outfit": "classic"}
    )
    painter.end()
    image = pixmap.toImage()
    assert _opaque_count(image) > 200
    _assert_crisp_grid(image, 4)
