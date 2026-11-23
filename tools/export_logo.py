"""Export the Nora brand mark as every icon file an OS may want.

Run once, commit the results::

    python -m tools.export_logo

Writes to ``docs/brand/``:

* ``nora.png``            1024 px transparent master
* ``nora-<size>.png``     the exact sizes Windows/macOS pick from
* ``nora.ico``            multi-resolution Windows icon (16 → 256)
* ``nora-<size>.white.png``  the mark on an opaque white tile (installer art)

The mark is drawn by :mod:`nora.nora_brand`, so re-running this after a design
change regenerates every file with no manual painting.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nora.nora_brand import draw_mark  # noqa: E402

OUT = ROOT / "docs" / "brand"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
PNG_SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)


def _render(size: int, *, background: QColor | None = None) -> QImage:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(background if background is not None else Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    draw_mark(painter, size, spark=size >= 64)
    painter.end()
    return image


def _qimage_to_pil(image: QImage):
    """QImage -> PIL, via raw RGBA.  Keeps the alpha exactly as drawn."""
    from PIL import Image

    image = image.convertToFormat(QImage.Format_RGBA8888)
    width, height = image.width(), image.height()
    buffer = image.constBits().asstring(image.sizeInBytes())
    return Image.frombuffer("RGBA", (width, height), buffer, "raw", "RGBA", 0, 1)


def main(argv: list[str] | None = None) -> int:
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance() or QApplication(argv or [])
    OUT.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for size in PNG_SIZES:
        path = OUT / f"nora-{size}.png"
        _render(size).save(str(path), "PNG")
        written.append(path)

    master = OUT / "nora.png"
    _render(1024).save(str(master), "PNG")
    written.append(master)

    # Windows .ico: PIL writes the sizes we give it, so the 16 px entry is the
    # real 16 px drawing (not a shrunk 256).
    if importlib.util.find_spec("PIL") is not None:
        frames = [
            _qimage_to_pil(_render(size, background=QColor(0, 0, 0, 0))).copy()
            for size in ICO_SIZES
        ]
        ico = OUT / "nora.ico"
        frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in ICO_SIZES])
        written.append(ico)
    else:
        print("Pillow yok: nora.ico üretilmedi (PNG'ler hazır).")

    # Installer / marketing tile: white mark on the brand's dark violet.
    tile = QImage(1024, 1024, QImage.Format_ARGB32)
    tile.fill(QColor("#221a33"))
    painter = QPainter(tile)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.translate(112, 112)
    draw_mark(painter, 800, spark=True)
    painter.end()
    tile_path = OUT / "nora-tile.png"
    tile.save(str(tile_path), "PNG")
    written.append(tile_path)

    for path in written:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bayt")
    print(f"\n{len(written)} dosya yazıldı -> {OUT.relative_to(ROOT)}")
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
