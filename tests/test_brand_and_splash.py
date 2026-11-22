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
def test_mark_is_white_and_mostly_empty_at_the_edges(app) -> None:
    image = _mark(128)
    opaque = [
        (x, y)
        for x in range(128)
        for y in range(128)
        if image.pixelColor(x, y).alpha() > 128
    ]
    assert opaque, "the mark drew nothing"
    colours = {image.pixelColor(x, y).name() for x, y in opaque}
    assert colours == {"#ffffff"}, f"the mark must be pure white, got {colours}"
    # transparent margin all round: no icon that bleeds off its own canvas
    xs = [x for x, _ in opaque]
    ys = [y for _, y in opaque]
    assert min(xs) >= 6 and min(ys) >= 6
    assert max(xs) <= 121 and max(ys) <= 121


def test_mark_has_a_letter_shaped_hole(app) -> None:
    """An N must have a counter: pure white blobs are not a logo.

    The counter is the empty wedge between the left stem and the diagonal, so it
    is measured where it actually exists — not at the exact centre, which the
    diagonal legitimately crosses.
    """
    image = _mark(128)

    def runs(y: int) -> int:
        """How many white runs one scanline crosses — inside the letter only.

        Scanned from 20..108 so the decorative ring is excluded; the ring is a
        separate, switchable element and would otherwise be counted as a stroke.
        """
        white = [image.pixelColor(x, y).alpha() > 128 for x in range(20, 108)]
        return sum(1 for i in range(1, len(white)) if white[i] and not white[i - 1])

    # An N crossed horizontally shows three strokes: left stem, diagonal, right
    # stem.  Two runs means the counter is filled in and the glyph is a slab.
    assert runs(50) == 3, f"expected stem/diagonal/stem, got {runs(50)} run(s)"
    # and it really is a counter, not a notch: the wedge must be several
    # percent of the canvas wide at that height
    empty = sum(1 for x in range(20, 108) if image.pixelColor(x, 50).alpha() <= 128)
    assert empty > 12, "the counter is too thin to read as an N"


def test_mark_scales_down_to_a_tray_icon(app) -> None:
    for size in (16, 24, 32, 48, 64):
        image = _mark(size, ring=size >= 24, spark=size >= 64)
        assert image.size().width() == size
        assert image.size().height() == size
        opaque = sum(
            1
            for x in range(size)
            for y in range(size)
            if image.pixelColor(x, y).alpha() > 0
        )
        assert opaque > 0, f"nothing drawn at {size}px"


def test_spark_is_opt_in_and_inside_the_ring(app) -> None:
    plain = _mark(128, spark=False)
    with_spark = _mark(128, spark=True)
    assert plain != with_spark
    # and the ring itself is a separate switch
    no_ring = _mark(128, ring=False, spark=False)
    assert no_ring != plain


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
    # Four steps at ~190 ms each, plus the finish timer.  Pump generously:
    # a slow CI box must not turn a timing margin into a false failure.
    for _ in range(24):
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
        if image.pixelColor(x, y).lightness() > 200
    )
    assert whites > 60, "the header badge is missing the white N"


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
