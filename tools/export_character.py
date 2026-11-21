#!/usr/bin/env python3
"""Export Nora's QPainter characters as PNG poses, sheets and animated GIFs.

Three renderers are exported from the exact same code paths the app uses:

* ``body/``: the default full-body character (arms, legs, shoes) with one
  frame per AI-selectable gesture
* ``realistic/``: the semi-realistic VTuber portrait (kumral hair,
  green-leaning eyes, smooth shading)
* the top-level ``poses/`` … ``animations/`` folders: the legacy 8-bit chibi,
  kept so both styles stay documented and regression-tested

No external sprite is used by the application.

Usage:
    python tools/export_character.py --output docs/character
    python tools/export_character.py --style body          # only the full body
    python tools/export_character.py --style realistic     # only the portrait
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

# Allow running as a plain script from a fresh checkout.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from PyQt5.QtCore import Qt  # noqa: E402
from PyQt5.QtGui import QImage, QPainter  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

from nora.nora_avatar import AVATAR_HEIGHT, AVATAR_WIDTH, RealisticCharacter  # noqa: E402
from nora.nora_personality import EMOTIONS  # noqa: E402
from nora.nora_pixel_art import (  # noqa: E402
    DEFAULT_HAIR_COLOR,
    GRID_HEIGHT,
    GRID_WIDTH,
    PIXEL_SIZE,
    PixelCharacter,
)

DEFAULT_APPEARANCE = {
    "outfit": "classic",
    "hair_color": DEFAULT_HAIR_COLOR,
    "accessory": "none",
}
NATIVE_SIZE = (GRID_WIDTH * PIXEL_SIZE, GRID_HEIGHT * PIXEL_SIZE)


@dataclass(frozen=True)
class Frame:
    state: str = "idle"
    emotion: str = "happy"
    frame: int = 0
    talking: bool = False
    listening: bool = False
    blinking: bool = False
    affection: bool = False
    grounded: bool = True


def _cycles(state: str, frames: list[int], **kwargs) -> list[Frame]:
    return [Frame(state=state, frame=frame, **kwargs) for frame in frames]


POSE_FRAMES: dict[str, Frame] = {
    "idle": Frame("idle"),
    "walk_left": Frame("walk_left", frame=6),
    "walk_right": Frame("walk_right", frame=6),
    "sit": Frame("sit", emotion="smug"),
    "sleep": Frame("sleep", emotion="sleepy"),
    "jump": Frame("jump", grounded=False),
    "fall": Frame("fall", emotion="surprised", grounded=False),
    "wave": Frame("wave", frame=8),
    "talk": Frame("talk", talking=True),
    "listening": Frame("listening", listening=True, frame=8),
    "surprised": Frame("surprised", emotion="surprised"),
    "love": Frame("love", emotion="love"),
    "angry": Frame("angry", emotion="angry"),
    "drag": Frame("drag", emotion="surprised", grounded=False),
    "dance": Frame("dance", emotion="love", frame=6),
    "yawn": Frame("yawn", emotion="sleepy", frame=10),
    "watch": Frame("watch"),
    "land": Frame("land", frame=6),
}

ANIMATIONS: dict[str, list[Frame]] = {
    "idle": _cycles("idle", [0, 12, 24, 36, 48, 60, 72, 84]),
    "blink": [
        Frame("idle", frame=0),
        Frame("idle", frame=0, blinking=True),
        Frame("idle", frame=0, blinking=True),
        Frame("idle", frame=0),
    ],
    "walk-left": _cycles("walk_left", list(range(0, 48, 6))),
    "walk-right": _cycles("walk_right", list(range(0, 48, 6))),
    "sit": _cycles("sit", [0, 30, 60, 90], emotion="smug"),
    "sleep": _cycles("sleep", [0, 12, 24, 36, 48, 60], emotion="sleepy"),
    "jump": [
        Frame("jump", frame=0, grounded=False),
        Frame("jump", frame=8, grounded=False),
        Frame("fall", frame=16, emotion="surprised", grounded=False),
        Frame("fall", frame=24, emotion="surprised", grounded=False),
    ],
    "fall": _cycles("fall", [0, 8, 16, 24], emotion="surprised", grounded=False),
    "wave": _cycles("wave", list(range(0, 64, 8))),
    "talk": _cycles("talk", list(range(0, 36, 6)), talking=True),
    "listening": _cycles("listening", list(range(0, 48, 8)), listening=True),
    "surprised": _cycles("surprised", [0, 10, 20, 30], emotion="surprised"),
    "love": _cycles("love", [0, 12, 24, 36], emotion="love"),
    "angry": _cycles("angry", [0, 8, 16, 24], emotion="angry"),
    "sad": _cycles("idle", [0, 24, 48, 72], emotion="sad"),
    "smug": _cycles("idle", [0, 24, 48, 72], emotion="smug"),
    "thinking": _cycles("idle", [0, 24, 48, 72], emotion="thinking"),
    "sleepy": _cycles("idle", [0, 12, 24, 36], emotion="sleepy"),
    "dance": _cycles("dance", list(range(0, 48, 6)), emotion="love"),
    "yawn": _cycles("yawn", [0, 10, 20, 30], emotion="sleepy"),
    "drag": [
        Frame("drag", frame=0, emotion="surprised", grounded=False),
        Frame("drag", frame=8, emotion="surprised", grounded=False),
        Frame("drag", frame=16, emotion="angry", grounded=False),
        Frame("drag", frame=24, emotion="angry", grounded=False),
    ],
    "watch": _cycles("watch", [0, 12, 24, 36]),
    "land": _cycles("land", [0, 6, 12, 18]),
    "affection": _cycles(
        "love", [0, 10, 20, 30, 40, 50], emotion="love", affection=True
    ),
}


REALISTIC_APPEARANCE = {
    "outfit": "classic",
    "hair_color": "#7d5a44",
    "accessory": "none",
    "eye_color": "yesil",
}
REALISTIC_SIZE = (AVATAR_WIDTH, AVATAR_HEIGHT)


def render_realistic(spec: Frame, appearance: dict | None = None) -> QImage:
    """Render the semi-realistic portrait through the app's own renderer."""
    image = QImage(*REALISTIC_SIZE, QImage.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    RealisticCharacter().draw(
        painter,
        state=spec.state,
        emotion=spec.emotion,
        frame=spec.frame,
        appearance=appearance or REALISTIC_APPEARANCE,
        talking=spec.talking,
        listening=spec.listening,
        blinking=spec.blinking,
        affection=spec.affection,
        grounded=spec.grounded,
    )
    painter.end()
    return image


def save_realistic(
    spec: Frame, path: Path, *, appearance: dict | None = None, scale: int = 1
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = render_realistic(spec, appearance)
    result = _pil(image, 1)
    if scale != 1:
        result = result.resize(
            (result.width * scale, result.height * scale),
            Image.Resampling.LANCZOS,
        )
    result.save(path)


def save_realistic_gif(
    name: str,
    path: Path,
    *,
    duration: int = 120,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = [_pil(render_realistic(spec), 1) for spec in ANIMATIONS[name]]
    converted = []
    for frame in frames:
        palette = frame.convert("RGB").convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=255
        )
        mask = frame.getchannel("A").point(lambda alpha: 255 if alpha <= 128 else 0)
        palette.paste(255, mask)
        converted.append(palette)
    converted[0].save(
        path,
        save_all=True,
        append_images=converted[1:],
        duration=duration,
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )


def export_realistic(output: Path) -> dict[str, int]:
    """Write the semi-realistic avatar as poses, sheets and GIFs."""
    ensure_app()
    output = Path(output) / "realistic"
    for folder in (
        "poses",
        "emotions",
        "accessories",
        "outfits",
        "sheets",
        "animations",
    ):
        (output / folder).mkdir(parents=True, exist_ok=True)
    for name, spec in POSE_FRAMES.items():
        save_realistic(spec, output / "poses" / f"{name}.png")
    for emotion in EMOTIONS:
        save_realistic(
            Frame("idle", emotion=emotion),
            output / "emotions" / f"{emotion}.png",
        )
    for accessory in ("none", "headphones", "glasses", "ribbon"):
        save_realistic(
            Frame("idle"),
            output / "accessories" / f"{accessory}.png",
            appearance={**REALISTIC_APPEARANCE, "accessory": accessory},
        )
    for outfit in ("classic", "casual", "night"):
        save_realistic(
            Frame("idle"),
            output / "outfits" / f"{outfit}.png",
            appearance={**REALISTIC_APPEARANCE, "outfit": outfit},
        )
    for name in ANIMATIONS:
        save_realistic_gif(name, output / "animations" / f"{name}.gif")
    # one contact sheet of every pose at native resolution
    cell_w, cell_h = 270, 370
    columns = 6
    items = list(POSE_FRAMES.items())
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), "#201a2b")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, spec) in enumerate(items):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        sheet.alpha_composite(_pil(render_realistic(spec), 1), (x + 5, y + 4))
        draw.text((x + 14, y + cell_h - 18), label, fill="#f7ecff", font=font)
    sheet.save(output / "sheets" / "poses.png")
    save_realistic(Frame("idle"), output / "hero.png", scale=2)
    _realistic_index_html(output.parent if output.name == "realistic" else output)
    return {
        "poses": len(POSE_FRAMES),
        "emotions": len(EMOTIONS),
        "accessories": 4,
        "outfits": 3,
        "animations": len(ANIMATIONS),
    }


def ensure_app() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def render_frame(spec: Frame, appearance: dict | None = None) -> QImage:
    image = QImage(*NATIVE_SIZE, QImage.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    PixelCharacter().draw(
        painter,
        state=spec.state,
        emotion=spec.emotion,
        frame=spec.frame,
        appearance=appearance or DEFAULT_APPEARANCE,
        talking=spec.talking,
        listening=spec.listening,
        blinking=spec.blinking,
        affection=spec.affection,
        grounded=spec.grounded,
    )
    painter.end()
    return image


def _pil(image: QImage, scale: int = 1) -> Image.Image:
    image = image.convertToFormat(QImage.Format_RGBA8888)
    width, height = image.width(), image.height()
    data = image.bits().asstring(image.sizeInBytes())
    result = Image.frombytes("RGBA", (width, height), data)
    if scale != 1:
        result = result.resize(
            (width * scale, height * scale), Image.Resampling.NEAREST
        )
    return result


def save_png(
    spec: Frame, path: Path, *, appearance: dict | None = None, scale: int = 3
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _pil(render_frame(spec, appearance), scale).save(path)


def save_gif(
    name: str,
    path: Path,
    *,
    appearance: dict | None = None,
    scale: int = 2,
    duration: int = 140,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = [_pil(render_frame(spec, appearance), scale) for spec in ANIMATIONS[name]]
    converted = []
    for frame in frames:
        palette = frame.convert("RGB").convert(
            "P", palette=Image.Palette.ADAPTIVE, colors=255
        )
        mask = frame.getchannel("A").point(lambda alpha: 255 if alpha <= 128 else 0)
        palette.paste(255, mask)
        converted.append(palette)
    converted[0].save(
        path,
        save_all=True,
        append_images=converted[1:],
        duration=duration,
        loop=0,
        transparency=255,
        disposal=2,
        optimize=False,
    )


def _sheet(items: list[tuple[str, Frame]], path: Path, columns: int = 4) -> None:
    cell_w, cell_h = 160, 190
    rows = (len(items) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * cell_w, rows * cell_h), "#201a2b")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()
    for index, (label, spec) in enumerate(items):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        character = _pil(render_frame(spec), 1)
        sheet.alpha_composite(character, (x + (cell_w - NATIVE_SIZE[0]) // 2, y + 8))
        draw.text((x + 12, y + 166), label, fill="#f7ecff", font=font)
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)


def _index_html(output: Path) -> None:
    poses = "".join(
        f'<figure><img src="poses/{name}.png" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in POSE_FRAMES
    )
    emotions = "".join(
        f'<figure><img src="emotions/{name}.png" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in EMOTIONS
    )
    animations = "".join(
        f'<figure><img src="animations/{name}.gif" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in ANIMATIONS
    )
    html = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Nora 8-bit karakter galerisi</title>
<style>
body{{background:#17131f;color:#f7ecff;font-family:system-ui,sans-serif;margin:24px}}
h1,h2{{color:#ff8fb3}}section{{display:flex;flex-wrap:wrap;gap:16px}}
figure{{margin:0;background:#241b31;border:1px solid #4a315c;border-radius:12px;padding:12px;text-align:center}}
img{{image-rendering:pixelated;width:180px;height:225px;object-fit:contain}}
figcaption{{margin-top:8px;font-size:13px;color:#d7a8cc}}
</style></head><body>
<h1>Nora · daha tatlı chibi · siyah elbise, kırmızı ayakkabı, kırmızı göz, beyaz wolfcut</h1>
<p>Bu görseller uygulamanın kendi QPainter çiziminden üretildi; çalışma zamanında harici sprite kullanılmaz. Büyük parıltılı kırmızı gözler, pembe yanaklar, kalp toka ve etek danteli aynı 8-bit ızgarada çizilir.</p>
<h2>Pozlar</h2><section>{poses}</section>
<h2>Duygular</h2><section>{emotions}</section>
<h2>Animasyonlar</h2><section>{animations}</section>
</body></html>"""
    (output / "index.html").write_text(html, encoding="utf-8")


def _realistic_index_html(output: Path) -> None:
    realistic = output / "realistic"
    poses = "".join(
        f'<figure><img src="poses/{name}.png" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in POSE_FRAMES
    )
    emotions = "".join(
        f'<figure><img src="emotions/{name}.png" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in EMOTIONS
    )
    animations = "".join(
        f'<figure><img src="animations/{name}.gif" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in ANIMATIONS
    )
    html = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Nora gerçekçi VTuber avatar galerisi</title>
<style>
body{{background:#141119;color:#f4ecf7;font-family:system-ui,sans-serif;margin:24px}}
h1,h2{{color:#f2a7d0;font-weight:600}}section{{display:flex;flex-wrap:wrap;gap:16px}}
figure{{margin:0;background:linear-gradient(160deg,#2b2237,#1d1826);border:1px solid rgba(255,255,255,.10);
border-radius:16px;padding:10px;text-align:center;box-shadow:0 10px 26px rgba(0,0,0,.35)}}
img{{width:200px;height:277px;object-fit:contain}}
figcaption{{margin-top:8px;font-size:12px;color:#c4b2cf;letter-spacing:.3px}}
p{{max-width:70ch;color:#c4b2cf;line-height:1.6}}
</style></head><body>
<h1>Nora · gerçekçi VTuber avatarı</h1>
<p>Kumral saç, yeşilimsi ela gözler, yumuşak gölgeli cilt. Bu görseller uygulamanın
kendi QPainter çiziminden, 3× süper örnekleme ile üretildi; çalışma zamanında
harici sprite veya model dosyası kullanılmaz. <a href="../index.html">8-bit chibi galerisi →</a></p>
<h2>Pozlar</h2><section>{poses}</section>
<h2>Duygular</h2><section>{emotions}</section>
<h2>Animasyonlar</h2><section>{animations}</section>
</body></html>"""
    (realistic / "index.html").write_text(html, encoding="utf-8")


def export_all(
    output: Path, *, png_scale: int = 3, gif_scale: int = 2
) -> dict[str, int]:
    ensure_app()
    output = Path(output)
    for folder in (
        "poses",
        "emotions",
        "accessories",
        "outfits",
        "animations",
        "sheets",
    ):
        (output / folder).mkdir(parents=True, exist_ok=True)
    for name, spec in POSE_FRAMES.items():
        save_png(spec, output / "poses" / f"{name}.png", scale=png_scale)
    for emotion in EMOTIONS:
        save_png(
            Frame("idle", emotion=emotion),
            output / "emotions" / f"{emotion}.png",
            scale=png_scale,
        )
    for accessory in ("none", "headphones", "glasses", "ribbon"):
        save_png(
            Frame("idle"),
            output / "accessories" / f"{accessory}.png",
            appearance={**DEFAULT_APPEARANCE, "accessory": accessory},
            scale=png_scale,
        )
    for outfit in ("classic", "casual", "night"):
        save_png(
            Frame("idle"),
            output / "outfits" / f"{outfit}.png",
            appearance={**DEFAULT_APPEARANCE, "outfit": outfit},
            scale=png_scale,
        )
    for name in ANIMATIONS:
        save_gif(name, output / "animations" / f"{name}.gif", scale=gif_scale)
    _sheet(list(POSE_FRAMES.items()), output / "sheets" / "poses.png")
    _sheet(
        [(name, Frame("idle", emotion=name)) for name in EMOTIONS],
        output / "sheets" / "emotions.png",
    )
    save_png(Frame("idle"), output / "wolfcut-hero.png", scale=4)
    _index_html(output)
    return {
        "poses": len(POSE_FRAMES),
        "emotions": len(EMOTIONS),
        "accessories": 4,
        "outfits": 3,
        "animations": len(ANIMATIONS),
    }


def export_full_body(output: Path) -> dict[str, int]:
    """Render the full-body character: pose sheet + one frame per AI gesture."""
    from nora.nora_body import FullBodyCharacter
    from nora.nora_motion import GESTURES, MotionController

    import random

    ensure_app()
    target = output / "body"
    (target / "poses").mkdir(parents=True, exist_ok=True)
    (target / "moves").mkdir(parents=True, exist_ok=True)
    artist = FullBodyCharacter()
    counts = {"poses": 0, "moves": 0}

    # A) neutral poses across the emotions the model can emit
    for emotion in (
        "happy",
        "love",
        "thinking",
        "surprised",
        "angry",
        "sad",
        "sleepy",
        "smug",
    ):
        pose = MotionController(random.Random(0)).tick(0.0)
        pose = replace(pose, smile=_EMOTION_SMILE[emotion])
        artist.frame(pose).scaled(
            330, 780, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ).save(str(target / "poses" / f"{emotion}.png"))
        counts["poses"] += 1

    # B) every AI-selectable gesture at its most expressive frame
    for name in GESTURES:
        controller = MotionController(random.Random(7))
        controller.play_name(name)
        best = None
        best_score = -1.0
        for _ in range(70):
            pose = controller.tick(1 / 30)
            score = (
                abs(pose.arm_l)
                + abs(pose.arm_r)
                + abs(pose.bounce)
                + abs(pose.hip_shift)
                + abs(pose.head_tilt)
                + abs(pose.crouch)
            )
            if score > best_score:
                best_score, best = score, pose
        artist.frame(best).scaled(
            330, 780, Qt.KeepAspectRatio, Qt.SmoothTransformation
        ).save(str(target / "moves" / f"{name}.png"))
        counts["moves"] += 1

    # C) hero shot + preview sheet
    artist.frame(MotionController(random.Random(3)).tick(0.0)).save(
        str(target / "hero.png")
    )
    _body_index_html(target)
    return counts


_EMOTION_SMILE = {
    "happy": 0.85,
    "love": 0.95,
    "thinking": 0.2,
    "surprised": 0.1,
    "angry": -0.5,
    "sad": -0.65,
    "sleepy": 0.3,
    "smug": 0.7,
}


def _body_index_html(target: Path) -> None:
    moves = sorted(path.stem for path in (target / "moves").glob("*.png"))
    cards = "".join(
        f'<figure><img src="moves/{name}.png" alt="{name}"><figcaption>{name}</figcaption></figure>'
        for name in moves
    )
    html = f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>Nora tam vücut karakter</title>
<style>
body{{background:#191622;color:#f2ecf7;font-family:system-ui,sans-serif;margin:24px}}
h1{{color:#f2a7d0;font-weight:600}}section{{display:flex;flex-wrap:wrap;gap:14px}}
figure{{margin:0;background:linear-gradient(160deg,#2b2438,#1d1826);border:1px solid rgba(255,255,255,.09);
border-radius:14px;padding:8px;text-align:center}}
img{{width:200px;height:auto}}
figcaption{{margin-top:6px;font-size:12px;color:#c4b2cf}}
p{{max-width:74ch;color:#c4b2cf;line-height:1.6}}
</style></head><body>
<h1>Nora · tam vücut karakter</h1>
<p>Kollar, eller, bacaklar ve ayakkabılar dahil; her jest hareket motoru tarafından
o anda üretilir. Bu görseller yapay zekânın seçebileceği {len(moves)} hareketin en
belirgin karesidir. Uygulamada hareketler 30 fps akıcılığında ara karelerle oynar.</p>
<section>{cards}</section>
</body></html>"""
    (target / "index.html").write_text(html, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nora PNG/GIF dışa aktarımı")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "character")
    parser.add_argument("--png-scale", type=int, default=3)
    parser.add_argument("--gif-scale", type=int, default=2)
    parser.add_argument(
        "--style",
        choices=("all", "body", "realistic", "pixel"),
        default="all",
        help="Hangi karakter stili dışa aktarılsın (varsayılan: hepsi).",
    )
    args = parser.parse_args(argv)
    app = ensure_app()  # keep the QApplication alive while painting
    if args.style in {"all", "body"}:
        counts = export_full_body(args.output)
        print(f"Nora tam vücut görselleri: {args.output / 'body'}")
        for key, value in counts.items():
            print(f"  {key}: {value}")
    if args.style in {"all", "realistic"}:
        counts = export_realistic(args.output)
        print(f"Nora gerçekçi avatar görselleri: {args.output / 'realistic'}")
        for key, value in counts.items():
            print(f"  {key}: {value}")
    if args.style in {"all", "pixel"}:
        counts = export_all(
            args.output, png_scale=args.png_scale, gif_scale=args.gif_scale
        )
        print(f"Nora 8-bit görselleri: {args.output}")
        for key, value in counts.items():
            print(f"  {key}: {value}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
