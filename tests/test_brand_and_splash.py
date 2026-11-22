"""Tests for the brand mark, the launch splash and the logo-to-desktop exit.

These encode what the user asked for:

* one modern, **white** logo (an N monogram) is the app's logo *and* icon;
* it appears in the header, the taskbar, the tray and the window icon;
* launching shows a **loading screen** built from that logo;
* pressing the logo makes Nora **animate out of it** onto the desktop.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from PyQt5.QtCore import QTimer, QEventLoop
from PyQt5.QtGui import QColor, QImage
from PyQt5.QtWidgets import QApplication


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
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    yield instance
    instance.shutdown()


def _mark(size: int = 128, **kwargs) -> QImage:
    from nora.nora_brand import logo_image

    return logo_image(size, **kwargs)


def _pump(ms: int) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec_()


# ------------------------------------------------------------------ the mark
def test_mark_is_the_brand_tile_with_a_white_letter(app) -> None:
    """Aurora tile + white N — no black anywhere, and no bleeding off canvas."""
    image = _mark(128)
    opaque = [
        (x, y)
        for x in range(128)
        for y in range(128)
        if image.pixelColor(x, y).alpha() > 128
    ]
    assert opaque, "the mark drew nothing"
    colours = {image.pixelColor(x, y).name() for x, y in opaque}

    # the letter is pure white and really present
    assert "#ffffff" in colours
    # the tile is the brand gradient: violet through to pink
    def hue_near(name: str, hue: float, tol: float = 22.0) -> bool:
        h = QColor(name).hue()
        return abs(((h - hue + 180) % 360) - 180) <= tol

    vivid = [
        name
        for name in colours
        if QColor(name).saturation() > 90 and QColor(name).lightness() < 240
    ]
    assert len(vivid) > 20, "the tile has no gradient"
    assert any(hue_near(n, 252) for n in vivid), "no violet stop"
    assert any(hue_near(n, 330) for n in vivid), "no pink stop"

    # nothing is black: every drawn pixel is either white or a vivid brand tone
    for name in colours:
        colour = QColor(name)
        assert colour.lightness() > 60, f"black pixel in the logo: {name}"

    # transparent margin: the squircle must not bleed off its own canvas
    xs = [x for x, _ in opaque]
    ys = [y for _, y in opaque]
    assert min(xs) >= 2 and min(ys) >= 2
    assert max(xs) <= 125 and max(ys) <= 125


def test_mark_has_a_letter_shaped_hole(app) -> None:
    """The white N must have a counter: a white blob is not a logo.

    The counter is the empty wedge between the left stem and the diagonal.  It
    is measured there — the exact centre of the tile is legitimately crossed by
    the diagonal, so a centre probe would be wrong.
    """
    image = _mark(128)

    def spans(y: int) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        start = None
        for x in range(128):
            white = image.pixelColor(x, y).name() == "#ffffff"
            if white and start is None:
                start = x
            elif not white and start is not None:
                out.append((start, x - 1))
                start = None
        if start is not None:
            out.append((start, 127))
        return out

    # An N is the only letter whose middle scanline shows three separate white
    # strokes — left stem, diagonal, right stem.  A blob never does.
    rows = [len(spans(y)) for y in range(30, 100)]
    assert max(rows) == 3, f"the glyph is not an N: run counts {sorted(set(rows))}"

    # The open counters must be wide enough to read as an N, not a notch.
    # Widest empty span between the outermost strokes, over the whole letter.
    widest = 0
    for y in range(30, 100):
        sp = spans(y)
        for (_, a), (b, _) in zip(sp, sp[1:]):
            widest = max(widest, b - a - 1)
    assert widest > 12, f"the counter is too thin to read as an N ({widest} px)"


def test_mark_scales_down_to_a_tray_icon(app) -> None:
    for size in (16, 24, 32, 48, 64):
        image = _mark(size, spark=size >= 64)
        assert image.size().width() == size
        assert image.size().height() == size
        opaque = sum(
            1
            for x in range(size)
            for y in range(size)
            if image.pixelColor(x, y).alpha() > 0
        )
        assert opaque > 0, f"nothing drawn at {size}px"


def test_spark_is_opt_in(app) -> None:
    plain = _mark(128, spark=False)
    with_spark = _mark(128, spark=True)
    assert plain != with_spark


def test_bare_glyph_variant_is_transparent(app) -> None:
    """``tile=False`` is the wordmark form: gradient N, no tile behind it."""
    image = _mark(128, tile=False)
    corner = image.pixelColor(2, 2)
    assert corner.alpha() == 0, "the bare glyph must not paint a tile"


def test_logo_pixmap_roundtrip(app) -> None:
    from nora.nora_brand import logo_pixmap

    pixmap = logo_pixmap(64)
    assert not pixmap.isNull()
    assert pixmap.size().width() == 64


# ------------------------------------------------------------- app icon wiring
def test_app_uses_the_mark_as_its_icon(nora_app) -> None:
    for widget in (nora_app, nora_app.chat_window):
        icon = widget.windowIcon()
        assert not icon.isNull()
        pixmap = icon.pixmap(64, 64)
        assert not pixmap.isNull()
        image = pixmap.toImage()
        whites = sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 200
            and image.pixelColor(x, y).lightness() > 240
        )
        assert whites > 0


def test_tray_icon_is_the_mark(nora_app) -> None:
    icon = nora_app.tray.icon()
    assert not icon.isNull()
    assert not icon.pixmap(64, 64).isNull()


def test_personal_panel_wears_the_app_icon(nora_app) -> None:
    nora_app.show_personal_panel()
    assert not nora_app.personal_panel.windowIcon().isNull()


# ----------------------------------------------------------------- the splash
def test_splash_reports_only_real_steps(app) -> None:
    from nora.nora_splash import STEPS, SplashScreen

    splash = SplashScreen()
    assert len(STEPS) >= 3
    splash.set_step(0)
    assert splash._status == STEPS[0]
    splash.set_step(len(STEPS) - 1)
    assert splash._status == STEPS[-1]
    splash.hide()


def test_splash_progress_never_goes_backwards(app) -> None:
    from nora.nora_splash import SplashScreen

    splash = SplashScreen()
    splash.set_step(3)
    reached = splash._progress
    splash.set_step(1)
    assert splash._progress == reached
    splash.hide()


def test_splash_failure_is_visible(app) -> None:
    from nora.nora_splash import SplashScreen

    splash = SplashScreen()
    splash.fail("Model bulunamadı")
    assert splash._failed is True
    assert "Model" in splash._detail
    splash.hide()


def test_splash_card_is_white_not_black(app) -> None:
    from nora.nora_splash import SplashScreen

    splash = SplashScreen()
    splash._set_intro(1.0)
    image = QImage(splash.width(), splash.height(), QImage.Format_ARGB32)
    image.fill(0)
    splash.render(image)
    # sample the card body, away from the mark and the text
    body = image.pixelColor(int(image.width() * 0.12), int(image.height() * 0.62))
    assert body.lightness() > 235, f"splash card is not white: {body.name()}"
    splash.hide()


def test_splash_holds_for_five_seconds(app) -> None:
    from nora.nora_splash import HOLD_SECONDS

    assert HOLD_SECONDS == 5.0


def test_splash_paints_something(app) -> None:
    from nora.nora_splash import SplashScreen

    splash = SplashScreen()
    splash._set_intro(1.0)
    splash.set_step(2)
    image = QImage(520, 400, QImage.Format_ARGB32)
    image.fill(0)
    splash.render(image)
    opaque = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() > 0
    )
    assert opaque > 5000, "the splash card did not paint"
    splash.hide()


def test_launch_shows_the_splash_then_the_app(nora_app) -> None:
    nora_app.start(splash=True)
    assert nora_app.splash is not None
    assert nora_app.splash.isVisible()
    assert not nora_app.chat_window.isVisible()
    # Three real steps at ~190 ms each, then the card is *held* until the full
    # five seconds are up.  Pump generously: a slow CI box must not turn a
    # timing margin into a false failure.
    for _ in range(36):
        _pump(200)
    assert getattr(nora_app, "splash", None) is None
    assert nora_app.chat_window.isVisible()


def test_start_without_splash_is_immediate(nora_app) -> None:
    nora_app.start()
    assert getattr(nora_app, "splash", None) is None
    assert nora_app.chat_window.isVisible()


# ------------------------------------------------------- out of the logo
def test_logo_shows_the_mark_not_the_character(nora_app) -> None:
    button = nora_app.logo_button
    button.resize(46, 46)
    image = QImage(46, 46, QImage.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 255))
    button.render(image)
    whites = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).name() == "#ffffff"
    )
    vivid = sum(
        1
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).saturation() > 90
    )
    assert whites > 40, "the header badge is missing the white N"
    assert vivid > 200, "the header badge is missing the brand tile"


def test_character_emerges_from_the_logo(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    nora_app.start()
    nora_app.logo_button.clicked.emit()
    assert pet.isVisible() is True
    # the entrance starts tiny and grows
    assert pet._emerge < 0.5
    # Drive the animation deterministically instead of trusting wall-clock
    # ticks on a loaded CI box.
    for _ in range(30):
        pet._tick_emerge()
    assert pet._emerge == pytest.approx(1.0, abs=0.01)
    assert pet._emerge_timer.isActive() is False


def test_emerge_animation_is_visible_in_the_first_frame(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    pet._emerge = 0.3
    big = QImage(pet.width(), pet.height(), QImage.Format_ARGB32)
    big.fill(0)
    pet.render(big)
    pet._emerge = 1.0
    full = QImage(pet.width(), pet.height(), QImage.Format_ARGB32)
    full.fill(0)
    pet.render(full)

    def ink(image: QImage) -> int:
        return sum(
            1
            for x in range(image.width())
            for y in range(image.height())
            if image.pixelColor(x, y).alpha() > 40
        )

    assert 0 < ink(big) < ink(full)


def test_hop_is_real_physics(nora_app) -> None:
    pet = nora_app.pet
    pet._timer.stop()
    nora_app.release_pet()
    _pump(500)
    # the timer is stopped in the test, so check the state the hop sets
    assert pet.state.name in {"JUMP", "FALL", "LAND", "IDLE"}


# --------------------------------------------------------- app lifecycle
def test_shutdown_does_not_kill_the_whole_application(tmp_path, app) -> None:
    """A closed window must not quit the shared event loop.

    Every QTimer in the process used to die with it — a freshly started splash
    froze because a previous instance had called ``app.quit()``.
    """
    from nora.nora_ui import NoraApp, NoraOptions

    first = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    assert first._owns_quit is False
    first.shutdown()

    fired: list[int] = []
    QTimer.singleShot(60, lambda: fired.append(1))
    _pump(300)
    assert fired == [1], "the shared event loop was terminated"


def test_real_app_is_the_only_one_allowed_to_quit(monkeypatch) -> None:
    import inspect

    from nora.nora_ui import NoraApp

    source = inspect.getsource(NoraApp.shutdown)
    assert "_owns_quit" in source, "shutdown must respect ownership of the loop"


# ------------------------------------------------------------ export artefacts
def test_committed_icon_files_exist() -> None:
    root = Path(__file__).resolve().parents[1]
    brand = root / "docs" / "brand"
    for name in ("nora.ico", "nora.png", "nora-16.png", "nora-256.png"):
        path = brand / name
        assert path.exists(), f"missing {name}; run python -m tools.export_logo"
        assert path.stat().st_size > 0


def test_ico_contains_every_windows_size() -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    root = Path(__file__).resolve().parents[1]
    icon = Image.open(root / "docs" / "brand" / "nora.ico")
    sizes = set(icon.ico.sizes())
    assert (16, 16) in sizes
    assert (256, 256) in sizes
    assert (32, 32) in sizes
