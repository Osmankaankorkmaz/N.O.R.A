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

from PyQt5.QtCore import Qt, QTimer, QEventLoop
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


# ------------------------------------------------------- frameless white shell
def test_chat_window_has_no_system_title_bar(nora_app) -> None:
    """The OS chrome (icon, minimise, maximise, close) must not be there."""
    from PyQt5.QtCore import Qt

    flags = nora_app.chat_window.windowFlags()
    assert flags & Qt.FramelessWindowHint, "the window must be frameless"
    for chrome in (
        Qt.WindowTitleHint,
        Qt.WindowMinMaxButtonsHint,
        Qt.WindowCloseButtonHint,
        Qt.WindowSystemMenuHint,
    ):
        assert not flags & chrome, f"system chrome still present: {int(chrome)}"


def test_header_carries_only_the_window_controls(nora_app) -> None:
    """Top right: minimise, maximise, close — and nothing else.

    The cluttered toolbar (mic chips, settings, overflow, a second minimise and
    a hide "x") is gone; what remains are the three controls a frameless window
    actually needs.
    """
    from PyQt5.QtWidgets import QAbstractButton

    from nora.nora_glass import GradientWindowButton

    nora_app.show_chat()
    nora_app.chat_window.resize(900, 660)
    _pump(200)
    header = nora_app.chat_header
    buttons = [
        child
        for child in header.findChildren(QAbstractButton)
        if child is not nora_app.logo_button
    ]
    assert len(buttons) == 3, f"expected three window controls, got {buttons}"
    assert all(isinstance(b, GradientWindowButton) for b in buttons)
    assert [b.glyph for b in buttons] == ["minimize", "maximize", "close"]

    # they sit on the right: their left edge is past the header's midpoint
    half = header.width() / 2
    for button in buttons:
        assert button.mapTo(header, button.rect().center()).x() > half

    # the retired *toolbar* buttons are still retired from the header; the
    # rail owns the settings button now, so it is checked separately below
    for gone in ("mic_button", "more_button"):
        assert not hasattr(nora_app, gone), f"{gone} should be gone from the header"
    assert not header.isAncestorOf(nora_app.settings_button)
    assert nora_app.sidebar.isAncestorOf(nora_app.settings_button)


def test_window_controls_are_brand_gradient(app) -> None:
    """The controls are glyphs in the mor–pembe ink, not grey OS buttons.

    1.19.0 drew each control as a filled gradient disc; 1.22.0 emptied the disc
    and moved the gradient into the stroke, so the row stops competing with the
    page.  What must not regress: the ink is the brand family — violet at the
    minimise end, pink for close — and nothing is filled.
    """
    from nora.nora_glass import GradientWindowButton

    for glyph, danger in (("minimize", False), ("maximize", False), ("close", True)):
        button = GradientWindowButton(glyph, size=30, danger=danger)
        button.show()
        _pump(50)
        # grab(), not render(): render() lays an opaque background first.
        image = button.grab().toImage()

        inked = [
            image.pixelColor(x, y)
            for x in range(30)
            for y in range(30)
            if image.pixelColor(x, y).alpha() > 90
        ]
        assert inked, f"{glyph} drew nothing"

        # every stroke pixel is brand colour of the right temperature
        for colour in inked:
            assert colour.saturation() > 60, (
                f"{glyph} has a grey stroke: {colour.name()}"
            )
            hue = colour.hue()
            if danger:
                assert hue >= 300 or hue <= 20, (
                    f"close should stay in the pink end, got {colour.name()}"
                )
            else:
                assert 230 <= hue <= 330, (
                    f"{glyph} should stay violet→pink, got {colour.name()}"
                )

        # a glyph, not a disc: the corners and the middle are empty
        assert image.pixelColor(1, 1).alpha() < 40
        assert image.pixelColor(28, 28).alpha() < 40
        filled = sum(
            1
            for x in range(30)
            for y in range(30)
            if image.pixelColor(x, y).alpha() > 90
        )
        assert filled < 90, f"{glyph} still paints a filled shape ({filled} px)"


def test_window_controls_do_what_they_say(nora_app) -> None:
    nora_app.show_chat()
    _pump(150)

    # maximise speaks the truth about what it does next
    assert not nora_app.chat_window.isMaximized()
    assert nora_app.maximize_button.glyph == "maximize"
    nora_app.maximize_button.click()
    _pump(150)
    assert nora_app.chat_window.isMaximized()
    assert nora_app.maximize_button.glyph == "restore"
    nora_app.maximize_button.click()
    _pump(150)
    assert not nora_app.chat_window.isMaximized()
    assert nora_app.maximize_button.glyph == "maximize"

    # close hides, it does not quit: Nora keeps living in the tray
    nora_app.close_button.click()
    _pump(150)
    assert not nora_app.chat_window.isVisible()
    assert not nora_app._closing


def test_white_page_paints_the_splash_colour(nora_app) -> None:
    """The page behind the glass is the splash backdrop, not a grey rectangle."""
    nora_app.show_chat()
    nora_app.chat_window.resize(240, 200)
    _pump(200)
    page = nora_app.white_page
    page.resize(240, 200)
    image = QImage(page.size(), QImage.Format_ARGB32)
    image.fill(0)
    page.render(image)

    # The page is rounded, so the outermost corners are cut away by design.
    # Everything inside the arc is white — this is a light page, not a dark one.
    from nora.nora_brand import CARD_RADIUS

    inset = int(CARD_RADIUS * 0.8)
    for point in (
        (inset, inset),
        (page.width() - inset - 1, inset),
        (inset, page.height() - inset - 1),
        (page.width() - inset - 1, page.height() - inset - 1),
        (page.width() // 2, page.height() // 2),
    ):
        colour = image.pixelColor(*point)
        assert colour.lightness() > 235, (
            f"page is not white at {point}: {colour.name()}"
        )
    # and the very corner really is transparent: the page is shaped, not square
    assert image.pixelColor(0, 0).alpha() == 0

    # The brand bloom is present: the violet corner is measurably cooler than
    # a flat white fill would be, and bluer than green.
    bloom = image.pixelColor(70, 40)
    assert bloom.blue() > bloom.green(), "the violet bloom is missing"
    assert bloom.name() != "#ffffff", "the page is flat white, not the splash gradient"


def test_frameless_window_keeps_drag_resize_and_escape(nora_app) -> None:
    """A window without a title bar still has to be movable, resizable, closable."""
    nora_app.show_chat()
    _pump(120)
    grip = nora_app.resize_grip
    assert grip.isVisible()
    # it follows the frame
    nora_app.chat_window.resize(920, 700)
    _pump(60)
    assert grip.x() == 920 - grip.SIZE
    assert grip.y() == 700 - grip.SIZE
    from PyQt5.QtCore import Qt as _Qt

    assert nora_app.chat_header.cursor().shape() == _Qt.OpenHandCursor

    from PyQt5.QtCore import QEvent, Qt
    from PyQt5.QtGui import QKeyEvent

    nora_app.chat_window.show()
    event = QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier)
    nora_app.eventFilter(nora_app.chat_window, event)
    assert not nora_app.chat_window.isVisible()


def test_splash_handover_is_a_fade_on_the_same_spot(nora_app) -> None:
    """The card dissolves over the window that opened underneath it."""
    nora_app.start(splash=True)
    splash = nora_app.splash
    assert splash is not None
    _pump(200)
    # the card is up and the window is not, exactly as before
    assert not nora_app.chat_window.isVisible()
    for _ in range(34):
        _pump(200)
    # the chat window is up and the card faded away on the same spot
    assert nora_app.chat_window.isVisible()
    assert getattr(nora_app, "splash", None) is None
    # the card is off screen and scheduled for deletion: it never lingers
    import sip

    assert sip.isdeleted(splash) or splash.isHidden()


# --------------------------------------------------- one corner language
def test_card_radius_is_shared_by_splash_and_window() -> None:
    """The launch card and the app must not disagree about corner softness."""
    from nora.nora_brand import CARD_RADIUS
    from nora.nora_glass import FrostedPanel
    from nora.nora_splash import SplashScreen

    assert CARD_RADIUS >= 24, "a 30 px radius is the product's corner language"
    assert FrostedPanel().radius == CARD_RADIUS

    splash = SplashScreen()
    try:
        # the splash really paints that radius: no pixel outside the arc
        assert splash.width() > 2 * CARD_RADIUS
    finally:
        splash.hide()
        splash.deleteLater()


def test_window_corners_are_actually_transparent(nora_app) -> None:
    """The whole window is shaped, not just the card drawn inside it.

    Painting a rounded panel is not enough: a translucent top-level window has
    its background composited behind every child, so square corners survive as
    a pale ghost.  The window itself carries a rounded mask.
    """
    from PyQt5.QtCore import QPoint
    from PyQt5.QtGui import QRegion

    from nora.nora_brand import CARD_RADIUS

    nora_app.show_chat()
    nora_app.chat_window.resize(420, 320)
    _pump(250)
    window = nora_app.chat_window
    mask = window.mask()
    assert not mask.isEmpty(), "the window has no rounded mask"

    # outside the arc: not part of the surface at all
    for point in ((0, 0), (2, 2), (window.width() - 1, 0), (0, window.height() - 1)):
        assert not mask.contains(QPoint(*point)), f"corner is not rounded: {point}"
    # inside: part of the surface
    assert mask.contains(QPoint(window.width() // 2, window.height() // 2))
    assert mask.contains(QPoint(window.width() // 2, 2))
    assert mask.contains(QPoint(1, window.height() // 2))
    # the corner is an arc, not a chamfer
    assert mask.contains(QPoint(int(CARD_RADIUS * 0.75), int(CARD_RADIUS * 0.75)))

    # and rendering really leaves the corner empty
    image = QImage(window.size(), QImage.Format_ARGB32)
    image.fill(0)
    window.render(image)
    assert image.pixelColor(0, 0).alpha() == 0
    assert image.pixelColor(window.width() // 2, window.height() // 2).alpha() >= 250
    # the mask and the painted card agree about the radius
    assert isinstance(mask, QRegion)


def test_window_silhouette_matches_the_launch_card(nora_app) -> None:
    """Sample both silhouettes and require the same corner profile."""
    from nora.nora_brand import CARD_RADIUS
    from nora.nora_splash import SplashScreen

    splash = SplashScreen()
    splash._set_intro(1.0)
    splash_image = QImage(splash.size(), QImage.Format_ARGB32)
    splash_image.fill(0)
    splash.render(splash_image)

    nora_app.show_chat()
    nora_app.chat_window.resize(400, 400)
    _pump(200)
    window = nora_app.chat_window
    window_image = QImage(window.size(), QImage.Format_ARGB32)
    window_image.fill(0)
    window.render(window_image)

    def first_solid(image: QImage, row: int) -> int:
        for x in range(0, min(image.width(), int(CARD_RADIUS) + 2)):
            if image.pixelColor(x, row).alpha() > 128:
                return x
        return -1

    # walk down the left edge from the very top: the inset must shrink the same
    # way on both, so their profiles agree within a pixel or two
    for row in (1, 2, 4, 8, 12, 16, 24):
        a = first_solid(splash_image, row)
        b = first_solid(window_image, row)
        assert a >= 0 and b >= 0, f"nothing solid at row {row}"
        assert abs(a - b) <= 3, f"corner profile differs at row {row}: {a} vs {b}"
    splash.hide()
    splash.deleteLater()


# ------------------------------------------------------------ 1.20.0 redesign
def test_hero_shows_on_an_empty_chat_and_leaves_on_the_first_message(nora_app) -> None:
    """A blank page is not a welcome: the empty state is a real screen."""
    nora_app.show_chat()
    nora_app.chat_window.resize(900, 660)
    _pump(200)
    assert nora_app.hero.isVisible()
    assert not nora_app.scroll.isVisible(), "the empty list must not eat the hero"

    # the hero must actually get enough room for its own content
    assert nora_app.hero.height() >= nora_app.hero.layout().minimumSize().height()

    nora_app.add_message("Merhaba", "user")
    _pump(120)
    assert not nora_app.hero.isVisible()
    assert nora_app.scroll.isVisible()

    nora_app._clear_messages()
    _pump(120)
    assert nora_app.hero.isVisible(), "clearing the history brings the welcome back"


def test_hero_mark_is_not_clipped(nora_app) -> None:
    """The mark is fixed-size: a shrunken label cropped the tile's lower half."""
    from PyQt5.QtWidgets import QLabel

    nora_app.show_chat()
    nora_app.chat_window.resize(900, 660)
    _pump(200)
    marks = [
        label
        for label in nora_app.hero.findChildren(QLabel)
        if label.pixmap() is not None and not label.pixmap().isNull()
    ]
    assert len(marks) == 1
    mark = marks[0]
    assert mark.size() == mark.pixmap().size(), "the mark label must match its pixmap"
    # and the title really sits below it, not on top of it
    title = nora_app.hero.findChild(QLabel, "heroTitle")
    assert title is not None
    assert title.y() >= mark.y() + mark.height()


def test_composer_is_one_card_with_the_shortcuts_inside(nora_app) -> None:
    nora_app.show_chat()
    _pump(150)
    composer = nora_app.composer
    assert composer.objectName() == "composerCard"
    # the field, the send button and every shortcut live inside the card
    assert composer.isAncestorOf(nora_app.input)
    assert composer.isAncestorOf(nora_app.send_button)
    for chip in nora_app.quick_buttons:
        assert composer.isAncestorOf(chip)
        assert chip.objectName() == "chip"


def test_sender_labels_are_human(nora_app) -> None:
    nora_app.show_chat()
    _pump(120)
    nora_app.add_message("selam", "user")
    nora_app.add_message("merhaba", "bot")
    _pump(120)
    from nora.nora_ui import ChatBubble

    bubbles = [row.findChild(ChatBubble) for row in nora_app._message_rows]
    assert [b.sender_name for b in bubbles] == ["Sen", "Nora"]
    assert bubbles[0].label.text() == "selam"
    assert bubbles[1].label.text() == "merhaba"


def test_css_helper_keeps_alpha() -> None:
    """``QColor.name()`` drops alpha — that turned hairlines into near-black."""
    from nora.nora_glass import css

    whisper = QColor(24, 18, 40, 34)
    assert css(whisper).startswith("rgba(24,18,40,")
    assert css(whisper).endswith("0.133)")
    solid = QColor("#ffffff")
    assert css(solid) == "#ffffff"


def test_translucent_hairlines_are_not_black() -> None:
    """A 1 px border at 8 % alpha must stay a whisper, not a black frame."""
    from nora.nora_glass import STYLE, css

    assert "#181428;" not in STYLE.replace(" ", "")
    for line in STYLE.splitlines():
        if "border: 1px solid" in line:
            value = line.split("solid", 1)[1].strip().rstrip(";")
            assert value.startswith("rgba(") or value.startswith("#"), line
            if value.startswith("rgba("):
                raw = value.rsplit(",", 1)[1].rstrip(")")
                alpha = float(raw)
                # Qt accepts both 0-255 and 0.0-1.0 here; normalise.
                if alpha > 1.0:
                    alpha /= 255.0
                assert alpha < 0.5, (
                    f"a hairline with alpha {alpha} is too strong: {line}"
                )
    assert css(QColor(24, 18, 40, 20)).endswith("0.078)")


# ------------------------------------------------------------- 1.21.0 rail
def test_sidebar_holds_identity_navigation_and_settings(nora_app) -> None:
    """The rail is where the identity lives now: mark first, then destinations."""
    from nora.nora_glass import NavButton

    nora_app.show_chat()
    nora_app.chat_window.resize(980, 700)
    _pump(200)
    rail = nora_app.sidebar
    assert rail.isVisible()
    # A *labelled* rail now: wide enough to name each destination, still a
    # column rather than a second page.
    assert 180 <= rail.width() <= 240, "a labelled rail, not a panel"

    # the mark is in the rail, at the top, and bigger than a header badge
    assert rail.isAncestorOf(nora_app.logo_button)
    assert nora_app.logo_button.width() >= 40
    assert (
        nora_app.logo_button.mapTo(rail, nora_app.logo_button.rect().topLeft()).y() < 40
    )

    # four destinations plus settings, all NavButtons
    assert set(nora_app.nav_buttons) == {"chat", "notes", "tools", "profile"}
    for button in nora_app.nav_buttons.values():
        assert isinstance(button, NavButton)
        assert rail.isAncestorOf(button)
        # every destination is *named*, not just an icon
        assert button.with_label
    assert isinstance(nora_app.settings_button, NavButton)
    assert rail.isAncestorOf(nora_app.settings_button)

    # settings sits at the bottom of the rail, not next to the destinations
    bottom = nora_app.settings_button.mapTo(
        rail, nora_app.settings_button.rect().topLeft()
    ).y()
    chat_y = (
        nora_app.nav_buttons["chat"]
        .mapTo(rail, nora_app.nav_buttons["chat"].rect().topLeft())
        .y()
    )
    assert bottom > chat_y + 200


def test_exactly_one_nav_destination_is_active(nora_app) -> None:
    nora_app.show_chat()
    _pump(150)
    active = [key for key, button in nora_app.nav_buttons.items() if button.isActive()]
    assert active == ["chat"]

    nora_app._set_active_nav("profile")
    active = [key for key, button in nora_app.nav_buttons.items() if button.isActive()]
    assert active == ["profile"]


def test_nav_glyph_ink_is_the_brand_gradient_with_no_panel(app) -> None:
    """The rail carries the brand in the *ink*, not in a filled button.

    Filled gradient pills turned the rail into five buttons shouting at the
    page, so the design moved the brand into the glyph: no background, active
    icon in the aurora gradient, idle icon in ink.
    """
    from nora.nora_glass import NavButton

    active = NavButton("chat", size=42)
    active.setActive(True)
    active.show()
    _pump(60)
    image = active.grab().toImage()

    # Something vivid is drawn (the gradient stroke) ...
    vivid = [
        image.pixelColor(x, y)
        for x in range(42)
        for y in range(42)
        if image.pixelColor(x, y).saturation() > 90
        and image.pixelColor(x, y).value() > 90
    ]
    assert len(vivid) > 25, "the active glyph lost its brand colour"

    # ... but it is *strokes*, not a filled disc.  A filled 42 px pill would
    # cover ~1000 px; a glyph is a couple of hundred at most.
    inked = sum(
        1 for x in range(42) for y in range(42) if image.pixelColor(x, y).alpha() > 60
    )
    assert inked < 260, f"the destination still paints a filled panel ({inked} px)"

    # The edges stay clear: no background, hence no black box on Windows either.
    for x, y in ((0, 0), (41, 0), (0, 41), (41, 41)):
        assert image.pixelColor(x, y).alpha() < 40

    # Idle is almost invisible next to active: ink, not colour.
    idle = NavButton("chat", size=42)
    idle.show()
    _pump(60)
    idle_image = idle.grab().toImage()
    idle_vivid = sum(
        1
        for x in range(42)
        for y in range(42)
        if idle_image.pixelColor(x, y).saturation() > 90
        and idle_image.pixelColor(x, y).alpha() > 60
    )
    assert idle_vivid < 10, "an idle destination must not wear the brand gradient"


def test_self_painting_widgets_request_a_translucent_buffer(app) -> None:
    """No widget may paint an opaque buffer on a translucent parent.

    Without WA_TranslucentBackground the buffer Qt hands to paintEvent has no
    alpha channel, and every pixel the glyph does not cover comes out **black**.
    That is exactly what the rail and the window controls looked like on
    Windows, so this is asserted for every hand-painted control.
    """
    from nora.nora_glass import GradientWindowButton, NavButton

    painted = [NavButton(glyph) for glyph in NavButton.GLYPHS]
    painted += [GradientWindowButton(glyph) for glyph in GradientWindowButton.GLYPHS]
    for widget in painted:
        assert widget.testAttribute(Qt.WA_TranslucentBackground), (
            f"{type(widget).__name__}({getattr(widget, 'glyph', '')}) would paint "
            "an opaque black buffer"
        )
        assert not widget.autoFillBackground()


def test_window_controls_are_gradient_glyphs_without_a_panel(app) -> None:
    """Window controls are icons in the brand ink, not filled circles."""
    from nora.nora_glass import GradientWindowButton

    button = GradientWindowButton("minimize", size=30)
    button.show()
    _pump(50)
    image = button.grab().toImage()

    vivid = [
        image.pixelColor(x, y)
        for x in range(30)
        for y in range(30)
        if image.pixelColor(x, y).alpha() > 90
        and image.pixelColor(x, y).saturation() > 70
    ]
    assert vivid, "the window control lost its brand ink"
    # a glyph, not a filled disc
    inked = sum(
        1 for x in range(30) for y in range(30) if image.pixelColor(x, y).alpha() > 90
    )
    assert inked < 90, f"the control still paints a filled circle ({inked} px)"
    # and the glyph is not pure white-on-gradient as it used to be
    white = sum(
        1
        for x in range(30)
        for y in range(30)
        if image.pixelColor(x, y).name() == "#ffffff"
        and image.pixelColor(x, y).alpha() > 200
    )
    assert white == 0, "a white glyph only made sense on top of a gradient disc"


def test_destinations_are_named_rows_not_bare_icons(nora_app) -> None:
    """A sidebar that names its destinations, the way a desktop app does.

    The previous design put five bare glyphs in a bordered pill.  Naming each
    row costs 100 px of width and removes the need to learn icons, which is
    what real app rails do.
    """
    nora_app.show_chat()
    _pump(150)
    rail = nora_app.sidebar
    for key, button in nora_app.nav_buttons.items():
        assert button.with_label, f"{key} lost its caption"
        assert button.LABELS[key]
        # a row, wider than tall
        assert button.width() > button.height(), f"{key} is not a row"
        assert rail.isAncestorOf(button)
        # the row uses the rail's width rather than hugging its glyph
        assert button.width() > rail.width() * 0.7

    # the section caption and the wordmark give the rail a hierarchy
    captions = [
        child.text()
        for child in rail.findChildren(type(nora_app.chat_title))
        if child.objectName() == "railCaption"
    ]
    assert captions, "the rail has no section caption"
    assert any(
        "Nora" == child.text() for child in rail.findChildren(type(nora_app.chat_title))
    ), "the rail lost its wordmark"

    # settings is separated: a divider sits between it and the destinations
    dividers = [
        child
        for child in rail.findChildren(type(nora_app.chat_header).__mro__[1])
        if child.objectName() == "railDivider"
    ]
    assert dividers, "settings is not visually separated from the destinations"


def test_header_title_follows_the_active_destination(nora_app) -> None:
    """One source of truth: the rail decides, the header echoes."""
    nora_app.show_chat()
    _pump(150)
    assert nora_app.chat_title.text() == nora_app.NAV_PAGES["chat"][0]
    assert nora_app.chat_subtitle.text() == nora_app.NAV_PAGES["chat"][1]

    nora_app._set_active_nav("notes")
    assert nora_app.chat_title.text() == "Notlar"
    assert nora_app.chat_subtitle.text() == nora_app.NAV_PAGES["notes"][1]

    nora_app._set_active_nav("chat")
    assert nora_app.chat_title.text() == "Sohbet"


def test_tools_menu_does_not_leave_the_rail_lit(nora_app) -> None:
    """Tools is a popup, not a page: closing it restores the real page."""
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    nora_app.show_chat()
    _pump(150)
    nora_app._set_active_nav("chat")

    def close_menus() -> None:
        for widget in QApplication.topLevelWidgets():
            if widget.inherits("QMenu"):
                widget.close()

    QTimer.singleShot(80, close_menus)
    nora_app._open_tools()
    _pump(200)
    assert nora_app._active_nav == "chat"
    assert nora_app.chat_title.text() == "Sohbet"


def test_hero_greets_and_offers_explained_suggestions(nora_app) -> None:
    """Open greeting + a grid of cards that say *what will happen*.

    The empty state used to be one bordered card with three bare pills.  It is
    now an open greeting (calmer on the white page) with suggestion cards that
    carry a glyph, a name and a one-line promise, so the greeting teaches the
    product instead of only welcoming.
    """
    from nora.nora_glass import SuggestionCard

    nora_app.show_chat()
    _pump(200)
    assert nora_app.hero.isVisible()
    assert len(nora_app.hero_chips) >= 4, "the greeting offers too few ways in"

    for card in nora_app.hero_chips:
        assert isinstance(card, SuggestionCard)
        assert card.title and card.blurb, "a suggestion without a promise"
        assert card.glyph in SuggestionCard.GLYPHS
        # cards are clickable rows, not pills
        assert card.height() >= 80

    # the greeting still names her and carries the mark
    titles = [
        label
        for label in nora_app.hero.findChildren(type(nora_app.chat_title))
        if label.objectName() == "heroTitle"
    ]
    assert len(titles) == 1
    assert titles[0].text().startswith("Merhaba")

    # The greeting column is centred on the page: equal margins either side.
    # Measure the hero's direct child that *contains* the title, rather than
    # walking up from the label — the search order of findChildren is not the
    # parent chain.
    holders = [
        child
        for child in nora_app.hero.findChildren(type(nora_app.hero))
        if child.parentWidget() is nora_app.hero and child.isAncestorOf(titles[0])
    ]
    assert len(holders) == 1, "the greeting is not a single centred column"
    column = holders[0]
    left = column.x()
    right = nora_app.hero.width() - left - column.width()
    assert abs(left - right) <= 3, f"the greeting is off-centre ({left} vs {right})"
