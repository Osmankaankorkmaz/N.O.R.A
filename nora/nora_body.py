"""Nora's full-body character, drawn procedurally with QPainter.

The character has a complete body — head, neck, torso, two arms with elbows
and hands, a skirt, two legs with knees, and shoes on the feet.  Nothing is a
pre-rendered sprite: :meth:`FullBodyCharacter.render` takes a
:class:`nora.nora_motion.Pose` and paints every joint from it, so any pose the
motion engine can describe is a pose the character can strike.

Design
------
* **Design space** is 220×520 px; painting happens at 3× and is scaled down
  with smooth sampling, which is what gives the soft, non-pixel look.
* **Palette** follows the reference art: caramel/light-brown bob hair, large
  green eyes, cream turtleneck, white pleated skirt, brown loafers.
* **Shading** is layered gradients (skin, knit, hair strands, iris) plus a
  rim light — no outlines-only "clip art" look.

Poses come in as angles; :func:`skeleton` converts them to joint coordinates,
and :meth:`FullBodyCharacter.render` draws the skeleton.  Keeping those two
steps separate is what lets the AI drive the body without touching geometry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

from PyQt5.QtCore import QPointF, QRectF, QSizeF, Qt
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

from .nora_motion import Pose

DESIGN_WIDTH = 220
DESIGN_HEIGHT = 520
SUPERSAMPLE = 3

DEFAULT_SKIN = "#f3d3bd"
DEFAULT_HAIR = "#8a5f3f"
DEFAULT_EYE = "#69934f"
DEFAULT_OUTFIT = "cream"

#: Joint anchors in design space (feet on the floor at y≈506).
GROUND = 506.0
HIP_Y = 300.0
SHOULDER_Y = 162.0
NECK_Y = 142.0
HEAD_CY = 100.0
SHOULDER_X = 40.0
HIP_X = 22.0
THIGH = 76.0
SHIN = 78.0
UPPER_ARM = 52.0
FOREARM = 48.0
HEAD_R = 50.0

OUTFITS: dict[str, dict[str, str]] = {
    "cream": {"main": "#f6efe2", "shade": "#ddd0bd", "trim": "#fffaf1"},
    "classic": {"main": "#3c3648", "shade": "#282432", "trim": "#4b4459"},
    "casual": {"main": "#e8a4b4", "shade": "#c98294", "trim": "#f5c2ce"},
    "night": {"main": "#46527a", "shade": "#333c5c", "trim": "#55628c"},
}
SUPPORTED_EYE_COLORS: dict[str, str] = {
    "yesil": "#69934f",
    "hazel": "#8a7a3f",
    "ela": "#7d8a52",
    "kahve": "#7a5232",
    "mavi": "#4f7fa8",
    "gri": "#7b8794",
}


# --------------------------------------------------------------------------
# small colour helpers
# --------------------------------------------------------------------------
def _color(value: Any, fallback: QColor) -> QColor:
    if isinstance(value, QColor) and value.isValid():
        return QColor(value)
    if isinstance(value, str) and value.strip():
        candidate = QColor(value.strip())
        if candidate.isValid():
            return candidate
    return QColor(fallback)


def _alpha(color: QColor, alpha: int) -> QColor:
    out = QColor(color)
    out.setAlpha(max(0, min(255, int(alpha))))
    return out


def _mix(first: QColor, second: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(
        round(first.red() + (second.red() - first.red()) * t),
        round(first.green() + (second.green() - first.green()) * t),
        round(first.blue() + (second.blue() - first.blue()) * t),
        round(first.alpha() + (second.alpha() - first.alpha()) * t),
    )


def _pt(x: float, y: float) -> QPointF:
    return QPointF(float(x), float(y))


def _rot(origin: QPointF, length: float, degrees: float) -> QPointF:
    """Point ``length`` away from ``origin`` at ``degrees`` (0 = straight down)."""
    radians = math.radians(degrees)
    return _pt(
        origin.x() + math.sin(radians) * length,
        origin.y() + math.cos(radians) * length,
    )


# --------------------------------------------------------------------------
# skeleton
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Skeleton:
    """Joint positions in design space, derived from a :class:`Pose`."""

    head: QPointF
    neck: QPointF
    shoulder_l: QPointF
    shoulder_r: QPointF
    elbow_l: QPointF
    elbow_r: QPointF
    wrist_l: QPointF
    wrist_r: QPointF
    hip_l: QPointF
    hip_r: QPointF
    knee_l: QPointF
    knee_r: QPointF
    ankle_l: QPointF
    ankle_r: QPointF
    toe_l: QPointF
    toe_r: QPointF
    pelvis: QPointF
    chest: QPointF


def skeleton(pose: Pose) -> Skeleton:
    """Turn joint angles into coordinates.

    The torso is a single rigid segment that leans about the hips; the head
    hangs off the top of it.  Arm and leg angles are absolute (0 = hanging
    straight down) which keeps the lookup table in the renderer trivial.
    """
    pelvis = _pt(DESIGN_WIDTH / 2 + pose.hip_shift, HIP_Y + pose.crouch + pose.bounce)
    lean = pose.lean
    chest = _rot(pelvis, SHOULDER_Y - HIP_Y - pose.crouch * 0.35, lean + 180.0)
    # ``_rot`` grows downwards, so the chest is mirrored back up the spine.
    chest = _pt(
        pelvis.x() + math.sin(math.radians(lean)) * (HIP_Y - SHOULDER_Y),
        pelvis.y() - (HIP_Y - SHOULDER_Y) * math.cos(math.radians(lean)),
    )
    neck = _pt(
        chest.x() + math.sin(math.radians(lean)) * (SHOULDER_Y - NECK_Y),
        chest.y() - (SHOULDER_Y - NECK_Y) * math.cos(math.radians(lean)),
    )
    head_tilt = pose.head_tilt + lean * 0.35
    head = _pt(
        neck.x() + math.sin(math.radians(head_tilt)) * (NECK_Y - HEAD_CY),
        neck.y() - (NECK_Y - HEAD_CY) * math.cos(math.radians(head_tilt)),
    )

    def shoulder(sign: float) -> QPointF:
        return _pt(
            chest.x() + sign * SHOULDER_X * math.cos(math.radians(lean)),
            chest.y() + sign * SHOULDER_X * math.sin(math.radians(lean)) * 0.35,
        )

    shoulder_l = shoulder(-1.0)
    shoulder_r = shoulder(1.0)

    # a small outward rest angle keeps the arms clear of the torso without
    # needing bigger shoulders; the pose angles add on top of it
    elbow_l = _rot(
        shoulder_l, UPPER_ARM, pose.arm_l - 6.0 + pose.elbow_l * 0.45 - lean * 0.3
    )
    elbow_r = _rot(
        shoulder_r, UPPER_ARM, pose.arm_r + 6.0 + pose.elbow_r * 0.45 - lean * 0.3
    )
    wrist_l = _rot(elbow_l, FOREARM, pose.arm_l - 3.0 + pose.elbow_l - lean * 0.3)
    wrist_r = _rot(elbow_r, FOREARM, pose.arm_r + 3.0 + pose.elbow_r - lean * 0.3)

    hip_l = _pt(pelvis.x() - HIP_X * math.cos(math.radians(lean)), pelvis.y())
    hip_r = _pt(pelvis.x() + HIP_X * math.cos(math.radians(lean)), pelvis.y())
    knee_l = _rot(hip_l, THIGH, pose.leg_l + pose.knee_l * 0.5)
    knee_r = _rot(hip_r, THIGH, pose.leg_r + pose.knee_r * 0.5)
    ankle_l = _rot(knee_l, SHIN, pose.leg_l + pose.knee_l)
    ankle_r = _rot(knee_r, SHIN, pose.leg_r + pose.knee_r)
    toe_l = _pt(ankle_l.x() + pose.foot_l * 0.6 + 3.0, ankle_l.y() + 15.0)
    toe_r = _pt(ankle_r.x() + pose.foot_r * 0.6 + 3.0, ankle_r.y() + 15.0)

    return Skeleton(
        head=head,
        neck=neck,
        shoulder_l=shoulder_l,
        shoulder_r=shoulder_r,
        elbow_l=elbow_l,
        elbow_r=elbow_r,
        wrist_l=wrist_l,
        wrist_r=wrist_r,
        hip_l=hip_l,
        hip_r=hip_r,
        knee_l=knee_l,
        knee_r=knee_r,
        ankle_l=ankle_l,
        ankle_r=ankle_r,
        toe_l=toe_l,
        toe_r=toe_r,
        pelvis=pelvis,
        chest=chest,
    )


def _ground_feet(pose: Pose, joints: Skeleton) -> Skeleton:
    """Slide the whole body down so the lowest foot touches the floor."""
    lowest = max(
        joints.toe_l.y(), joints.toe_r.y(), joints.ankle_l.y(), joints.ankle_r.y()
    )
    offset = GROUND - lowest
    if abs(offset) < 0.5:
        return joints
    shifted = {
        name: _pt(getattr(joints, name).x(), getattr(joints, name).y() + offset)
        for name in (
            "head",
            "neck",
            "shoulder_l",
            "shoulder_r",
            "elbow_l",
            "elbow_r",
            "wrist_l",
            "wrist_r",
            "hip_l",
            "hip_r",
            "knee_l",
            "knee_r",
            "ankle_l",
            "ankle_r",
            "toe_l",
            "toe_r",
            "pelvis",
            "chest",
        )
    }
    return Skeleton(**shifted)


# --------------------------------------------------------------------------
# drawing primitives
# --------------------------------------------------------------------------
def _limb(
    painter: QPainter,
    start: QPointF,
    end: QPointF,
    w0: float,
    w1: float,
    base: QColor,
    *,
    light: float = 0.30,
) -> None:
    """A shaded limb drawn as layered round strokes (no self-intersections).

    Tapered capsules built from arcs are easy to get wrong and produce dark
    wedges where the path winds back on itself.  Three strokes — a shadow
    core, the base tone and a rim light — read as a soft cylinder and are
    impossible to break, whatever the joint angles are.
    """
    stroke = QPen(base, (w0 + w1) / 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(stroke)
    painter.setBrush(Qt.NoBrush)
    painter.drawLine(start, end)

    # inner shading along the lower-right side of the limb
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length = math.hypot(dx, dy) or 1e-6
    nx, ny = -dy / length, dx / length
    off = (w0 + w1) * 0.16
    painter.setPen(
        QPen(
            _alpha(_mix(base, QColor("#3a2218"), 0.34), 150),
            (w0 + w1) * 0.34,
            Qt.SolidLine,
            Qt.RoundCap,
        )
    )
    painter.drawLine(
        _pt(start.x() + nx * off, start.y() + ny * off + 1.5),
        _pt(end.x() + nx * off, end.y() + ny * off + 1.5),
    )
    # rim light on the opposite side
    painter.setPen(
        QPen(
            _alpha(_mix(base, QColor("#ffffff"), 0.55 + light * 0.2), 120),
            (w0 + w1) * 0.24,
            Qt.SolidLine,
            Qt.RoundCap,
        )
    )
    painter.drawLine(
        _pt(start.x() - nx * off * 0.9, start.y() - ny * off),
        _pt(end.x() - nx * off * 0.9, end.y() - ny * off),
    )


def _soft_shadow(
    painter: QPainter, centre: QPointF, rx: float, ry: float, alpha: int
) -> None:
    grad = QRadialGradient(centre, max(rx, ry))
    grad.setColorAt(0.0, QColor(20, 14, 26, alpha))
    grad.setColorAt(0.62, QColor(20, 14, 26, int(alpha * 0.45)))
    grad.setColorAt(1.0, QColor(20, 14, 26, 0))
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(grad))
    painter.drawEllipse(QRectF(centre.x() - rx, centre.y() - ry, rx * 2, ry * 2))


# --------------------------------------------------------------------------
# character
# --------------------------------------------------------------------------
class FullBodyCharacter:
    """Renders the complete character for a given :class:`Pose`."""

    def __init__(
        self,
        width: int = DESIGN_WIDTH,
        height: int = DESIGN_HEIGHT,
        *,
        supersample: int = SUPERSAMPLE,
    ) -> None:
        self.width = width
        self.height = height
        self.supersample = max(1, int(supersample))
        self._cache: dict[tuple, QImage] = {}

    # -- public ---------------------------------------------------------
    def frame(
        self,
        pose: Pose,
        *,
        appearance: Mapping[str, Any] | None = None,
        size: tuple[int, int] | None = None,
        talking: bool = False,
    ) -> QImage:
        """Return a rendered frame; identical inputs come from a memo cache."""
        appearance = appearance or {}
        key = (
            tuple(round(getattr(pose, name), 3) for name in pose.__dataclass_fields__),
            self._appearance_key(appearance),
            size,
            bool(talking),
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        image = self._render(pose, appearance=appearance, talking=talking)
        if size and (image.width(), image.height()) != size:
            image = image.scaled(
                size[0],
                size[1],
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )
        if len(self._cache) > 220:
            self._cache.clear()
        self._cache[key] = image
        return image

    # -- portraits for small avatars (tray, header, icon) -----------------
    def portrait(
        self,
        size: int = 64,
        *,
        appearance: Mapping[str, Any] | None = None,
        pose: Pose | None = None,
        crop: str = "face",
    ) -> QImage:
        """Square crop of the character for tiny avatars and the tray icon.

        ``crop="face"`` frames the head; ``crop="full"`` keeps the whole body.
        """
        from .nora_motion import Pose as _Pose

        pose = pose or _Pose(smile=0.8, eye_open=1.0)
        full = self.frame(pose, appearance=appearance or {})
        if crop == "full":
            # keep the body's aspect ratio and pad into a transparent square
            scaled = full.scaled(
                size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            canvas = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            painter.drawImage(
                (size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled
            )
            painter.end()
            return canvas
        joints = skeleton(pose)
        centre = joints.head
        radius = HEAD_R * 1.30
        size_px = int(round(radius * 2))
        x0 = int(max(0, min(full.width() - size_px, centre.x() - radius)))
        y0 = int(max(0, min(full.height() - size_px, centre.y() - radius * 0.92)))
        cropped = full.copy(x0, y0, size_px, size_px)
        return cropped.scaled(size, size, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)

    def draw(
        self,
        painter: QPainter,
        pose: Pose,
        *,
        appearance: Mapping[str, Any] | None = None,
        target: QRectF | None = None,
        talking: bool = False,
    ) -> None:
        if target is None:
            target = QRectF(0, 0, self.width, self.height)
        image = self.frame(
            pose,
            appearance=appearance,
            size=(max(1, int(target.width())), max(1, int(target.height()))),
            talking=talking,
        )
        painter.drawImage(target, image)

    @staticmethod
    def _appearance_key(appearance: Mapping[str, Any]) -> tuple:
        return tuple(
            sorted(
                (str(key), str(value))
                for key, value in appearance.items()
                if key
                in {"hair_color", "skin_tone", "eye_color", "outfit", "accessory"}
            )
        )

    # -- rendering ------------------------------------------------------
    def _render(
        self,
        pose: Pose,
        *,
        appearance: Mapping[str, Any],
        talking: bool,
    ) -> QImage:
        scale = self.supersample
        canvas = QImage(
            self.width * scale,
            self.height * scale,
            QImage.Format_ARGB32_Premultiplied,
        )
        canvas.fill(Qt.transparent)
        painter = QPainter(canvas)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.scale(scale, scale)
        try:
            self._paint(painter, pose, appearance, talking)
        finally:
            painter.end()
        return canvas.scaled(
            self.width,
            self.height,
            Qt.IgnoreAspectRatio,
            Qt.SmoothTransformation,
        )

    def _paint(
        self,
        painter: QPainter,
        pose: Pose,
        appearance: Mapping[str, Any],
        talking: bool,
    ) -> None:
        skin = _color(appearance.get("skin_tone"), QColor(DEFAULT_SKIN))
        hair = _color(appearance.get("hair_color"), QColor(DEFAULT_HAIR))
        eye_value = str(appearance.get("eye_color", "yesil")).strip().lower()
        eye = QColor(SUPPORTED_EYE_COLORS.get(eye_value, eye_value))
        if not eye.isValid():
            eye = QColor(DEFAULT_EYE)
        outfit_name = str(appearance.get("outfit", DEFAULT_OUTFIT)).strip().lower()
        outfit = OUTFITS.get(outfit_name) or OUTFITS[DEFAULT_OUTFIT]

        joints = _ground_feet(pose, skeleton(pose))

        # 1. contact shadow keeps her glued to the floor
        _soft_shadow(painter, _pt(DESIGN_WIDTH / 2, GROUND + 6), 54, 12, 92)

        # 2. hair mass behind everything
        self._hair_back(painter, joints, hair, pose)

        # 3. legs and shoes (behind the skirt hem)
        self._legs(painter, joints, skin, outfit, pose)

        # 4. neck first, so the collar and torso cover its base
        self._neck_skin(painter, joints, skin)

        # 5. skirt + torso
        self._skirt(painter, joints, outfit, pose)
        self._torso(painter, joints, outfit, pose)

        # 6. arms behind, torso already covers the shoulder joint
        self._arms(painter, joints, skin, outfit, pose)

        # 7. torso again over the shoulder joints (single clean silhouette)
        self._shoulders(painter, joints, outfit)

        # 8. turtleneck collar on top
        self._collar(painter, joints, outfit)

        # 6. head, face, front hair
        self._head(painter, joints, skin, hair, eye, pose, talking)
        self._hair_front(painter, joints, hair, pose)
        self._accessory(painter, joints, appearance)
        self._mood(painter, joints, pose)

    # ---- legs ---------------------------------------------------------
    def _legs(
        self,
        painter: QPainter,
        joints: Skeleton,
        skin: QColor,
        outfit: Mapping[str, str],
        pose: Pose,
    ) -> None:
        """Legs as thick tapered curves, knees shaded, loafers on the feet."""
        for hip, knee, ankle, toe in (
            (joints.hip_l, joints.knee_l, joints.ankle_l, joints.toe_l),
            (joints.hip_r, joints.knee_r, joints.ankle_r, joints.toe_r),
        ):
            thigh = QPainterPath(_pt(hip.x(), hip.y() - 6))
            thigh.cubicTo(
                _pt(hip.x() - 15, hip.y() + 26),
                _pt(knee.x() - 11.5, knee.y() - 18),
                _pt(knee.x() - 9.5, knee.y()),
            )
            thigh.lineTo(_pt(knee.x() + 9.5, knee.y()))
            thigh.cubicTo(
                _pt(knee.x() + 11.5, knee.y() - 18),
                _pt(hip.x() + 15, hip.y() + 26),
                _pt(hip.x(), hip.y() - 6),
            )
            thigh.closeSubpath()
            grad = QLinearGradient(
                _pt(hip.x() - 14, hip.y()), _pt(hip.x() + 14, knee.y())
            )
            grad.setColorAt(0.0, _mix(skin, QColor("#ffffff"), 0.30))
            grad.setColorAt(0.45, skin)
            grad.setColorAt(1.0, _mix(skin, QColor("#b9785c"), 0.38))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(thigh)

            # calf: narrower, with a soft bulge high up
            calf = QPainterPath(_pt(knee.x() - 9.5, knee.y()))
            calf.cubicTo(
                _pt(knee.x() - 11, knee.y() + 20),
                _pt(ankle.x() - 6, ankle.y() - 26),
                _pt(ankle.x() - 6, ankle.y() + 4),
            )
            calf.lineTo(_pt(ankle.x() + 6, ankle.y() + 4))
            calf.cubicTo(
                _pt(ankle.x() + 6, ankle.y() - 26),
                _pt(knee.x() + 12.5, knee.y() + 20),
                _pt(knee.x() + 9.5, knee.y()),
            )
            calf.closeSubpath()
            grad = QLinearGradient(
                _pt(knee.x() - 10, knee.y()), _pt(knee.x() + 10, ankle.y())
            )
            grad.setColorAt(0.0, _mix(skin, QColor("#ffffff"), 0.22))
            grad.setColorAt(0.5, skin)
            grad.setColorAt(1.0, _mix(skin, QColor("#b9785c"), 0.34))
            painter.setBrush(QBrush(grad))
            painter.drawPath(calf)

            # knee cap highlight
            painter.setBrush(QBrush(_alpha(_mix(skin, QColor("#ffffff"), 0.55), 90)))
            painter.drawEllipse(QRectF(knee.x() - 7, knee.y() - 5, 14, 11))

            # loafer
            shoe = QPainterPath(_pt(ankle.x() - 9, ankle.y() + 12))
            shoe.cubicTo(
                _pt(ankle.x() - 10, ankle.y() + 2),
                _pt(ankle.x() + 2, ankle.y() - 1),
                _pt(toe.x() + 3, toe.y() - 1),
            )
            shoe.cubicTo(
                _pt(toe.x() + 10, toe.y() + 1),
                _pt(toe.x() + 7, toe.y() + 7),
                _pt(ankle.x() - 2, toe.y() + 6),
            )
            shoe.closeSubpath()
            brown = QColor("#8a5c3a")
            sg = QLinearGradient(
                _pt(ankle.x() - 10, ankle.y()), _pt(ankle.x() + 12, toe.y() + 6)
            )
            sg.setColorAt(0.0, _mix(brown, QColor("#ffffff"), 0.28))
            sg.setColorAt(0.5, brown)
            sg.setColorAt(1.0, brown.darker(155))
            painter.setBrush(QBrush(sg))
            painter.drawPath(shoe)
            # sole
            painter.setPen(QPen(QColor("#efe6da"), 2.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                _pt(ankle.x() - 7, ankle.y() + 13.0), _pt(toe.x() + 5, toe.y() + 6.5)
            )
            painter.setPen(Qt.NoPen)

    # ---- skirt --------------------------------------------------------
    def _skirt(
        self,
        painter: QPainter,
        joints: Skeleton,
        outfit: Mapping[str, str],
        pose: Pose,
    ) -> None:
        pelvis = joints.pelvis
        sway = pose.skirt_sway
        top_y = pelvis.y() - 18.0
        hem_y = pelvis.y() + 44.0
        half_top = 24.0
        half_hem = 44.0

        path = QPainterPath(_pt(pelvis.x() - half_top, top_y))
        path.cubicTo(
            _pt(pelvis.x() - half_top - 10 + sway * 0.6, top_y + 30),
            _pt(pelvis.x() - half_hem - 6 + sway, hem_y - 16),
            _pt(pelvis.x() - half_hem + sway * 1.6, hem_y),
        )
        steps = 8
        for index in range(steps):
            x0 = pelvis.x() - half_hem + sway * 1.6 + (2 * half_hem / steps) * index
            x1 = x0 + (2 * half_hem / steps)
            path.quadTo(_pt((x0 + x1) / 2, hem_y + 7.0), _pt(x1, hem_y))
        path.cubicTo(
            _pt(pelvis.x() + half_hem + 6 + sway, hem_y - 16),
            _pt(pelvis.x() + half_top + 10 + sway * 0.6, top_y + 30),
            _pt(pelvis.x() + half_top, top_y),
        )
        path.closeSubpath()

        base = _color(outfit["trim"], QColor("#fdf8ef"))
        grad = QLinearGradient(_pt(pelvis.x(), top_y), _pt(pelvis.x(), hem_y + 8))
        grad.setColorAt(0.0, _mix(base, QColor("#dfe6f0"), 0.35))
        grad.setColorAt(0.5, base)
        grad.setColorAt(1.0, _mix(base, QColor("#8e97ab"), 0.42))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        # pleat folds: alternating light/shadow wedges
        painter.save()
        painter.setClipPath(path)
        for index in range(steps):
            fraction = index / steps
            x_top = pelvis.x() - half_top + 2 * half_top * fraction
            x_hem = pelvis.x() - half_hem + sway * 1.6 + 2 * half_hem * fraction
            wedge = QPainterPath(_pt(x_top, top_y + 4))
            wedge.lineTo(_pt(x_hem + 3, hem_y + 2))
            wedge.lineTo(_pt(x_hem + 9, hem_y + 2))
            wedge.closeSubpath()
            shade = 46 if index % 2 == 0 else 22
            painter.setBrush(QBrush(_alpha(QColor("#7d8aa2"), shade)))
            painter.drawPath(wedge)
        painter.restore()

        painter.setPen(QPen(_alpha(QColor("#ffffff"), 120), 1.6))
        for index in range(1, steps):
            fraction = index / steps
            x_hem = pelvis.x() - half_hem + sway * 1.6 + 2 * half_hem * fraction
            painter.drawLine(_pt(x_hem, hem_y + 1), _pt(x_hem, hem_y - 4))
        painter.setPen(Qt.NoPen)

        # waistband
        painter.setBrush(QBrush(_mix(base, QColor("#b8c0d0"), 0.45)))
        painter.drawRoundedRect(
            QRectF(pelvis.x() - half_top - 1, top_y - 6, half_top * 2 + 2, 10), 5, 5
        )

    # ---- torso --------------------------------------------------------
    def _torso(
        self,
        painter: QPainter,
        joints: Skeleton,
        outfit: Mapping[str, str],
        pose: Pose,
    ) -> None:
        """Cream turtleneck: soft trapezoid from shoulders to waist."""
        chest = joints.chest
        pelvis = joints.pelvis
        main = _color(outfit["main"], QColor("#f6efe2"))
        shade = _color(outfit["shade"], QColor("#ddd0bd"))
        lean = pose.lean

        sx = 34.0
        waist = 24.0
        waist_y = pelvis.y() - 28.0
        half_shoulder = sx
        angle = math.radians(lean)

        def offset(dx: float, dy: float) -> QPointF:
            return _pt(
                chest.x() + dx * math.cos(angle) - dy * math.sin(angle),
                chest.y() + dx * math.sin(angle) + dy * math.cos(angle),
            )

        height = waist_y - chest.y()
        path = QPainterPath(offset(-half_shoulder + 8, -8))
        # rounded shoulder cap
        path.cubicTo(
            offset(-half_shoulder - 4, -6),
            offset(-half_shoulder - 4, 10),
            offset(-half_shoulder + 2, 20),
        )
        # waist: curve in, then flare slightly at the hip
        path.cubicTo(
            offset(-waist - 2, height * 0.55),
            offset(-waist - 1, height * 0.85),
            offset(-waist + 1, height),
        )
        path.lineTo(offset(waist - 1, height))
        path.cubicTo(
            offset(waist + 1, height * 0.85),
            offset(waist + 2, height * 0.55),
            offset(half_shoulder - 2, 20),
        )
        path.cubicTo(
            offset(half_shoulder + 4, 10),
            offset(half_shoulder + 4, -6),
            offset(half_shoulder - 8, -8),
        )
        # shoulder line: a soft, sloping shoulder that swallows the joint
        path.cubicTo(offset(30, -9), offset(12, -17), offset(0, -17))
        path.cubicTo(offset(-12, -17), offset(-30, -9), offset(-half_shoulder, -2))
        path.closeSubpath()

        grad = QLinearGradient(offset(-30, 0), offset(30, waist_y - chest.y()))
        grad.setColorAt(0.0, _mix(main, QColor("#ffffff"), 0.34))
        grad.setColorAt(0.45, main)
        grad.setColorAt(1.0, shade)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        painter.save()
        painter.setClipPath(path)
        # knit ribbing
        painter.setPen(QPen(_alpha(shade, 55), 1.0))
        for index in range(-6, 7):
            x = index * 5.5
            painter.drawLine(offset(x, -14), offset(x * 0.82, waist_y - chest.y()))
        # soft shadow under the bust and along both sides
        for sign in (-1, 1):
            shadow = QLinearGradient(offset(sign * 26, 20), offset(sign * 6, 34))
            shadow.setColorAt(0.0, _alpha(shade, 130))
            shadow.setColorAt(1.0, _alpha(shade, 0))
            painter.setBrush(QBrush(shadow))
            painter.drawRect(
                QRectF(
                    offset(min(sign * 26, sign * 4), 18),
                    QSizeF(28, 40),
                )
            )
        painter.restore()

        # waist band
        painter.setBrush(QBrush(_mix(main, shade, 0.55)))
        painter.drawRoundedRect(QRectF(pelvis.x() - 25, waist_y - 3, 50, 11), 5, 5)

    def _neck_skin(
        self,
        painter: QPainter,
        joints: Skeleton,
        skin: QColor,
    ) -> None:
        top = joints.neck
        chest = joints.chest
        neck = QPainterPath(_pt(top.x() - 9, top.y() - 6))
        neck.lineTo(_pt(top.x() + 9, top.y() - 6))
        neck.cubicTo(
            _pt(top.x() + 8, chest.y() - 2),
            _pt(chest.x() + 12, chest.y()),
            _pt(chest.x() + 12, chest.y() + 6),
        )
        neck.lineTo(_pt(chest.x() - 12, chest.y() + 6))
        neck.cubicTo(
            _pt(chest.x() - 12, chest.y()),
            _pt(top.x() - 8, chest.y() - 2),
            _pt(top.x() - 9, top.y() - 6),
        )
        neck.closeSubpath()
        grad = QLinearGradient(_pt(top.x() - 10, top.y()), _pt(top.x() + 10, chest.y()))
        grad.setColorAt(0.0, _mix(skin, QColor("#bf8568"), 0.34))
        grad.setColorAt(0.55, _mix(skin, QColor("#cf9678"), 0.24))
        grad.setColorAt(1.0, _mix(skin, QColor("#bf8568"), 0.40))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(neck)

    def _shoulders(
        self,
        painter: QPainter,
        joints: Skeleton,
        outfit: Mapping[str, str],
    ) -> None:
        """Re-paint the two shoulder "sleeve heads" as part of the knit top.

        Drawn after the arms so the deltoid of the sweater flows into the
        sleeve with no socket, seam or pad: exactly one silhouette.
        """
        main = _color(outfit["main"], QColor("#f6efe2"))
        shade = _color(outfit["shade"], QColor("#ddd0bd"))
        chest = joints.chest
        for shoulder in (joints.shoulder_l, joints.shoulder_r):
            centre = _pt(
                chest.x() + (shoulder.x() - chest.x()) * 0.62,
                chest.y() + (shoulder.y() - chest.y()) * 0.62 + 5.0,
            )
            grad = QLinearGradient(
                _pt(centre.x() - 12, centre.y() - 10),
                _pt(centre.x() + 12, centre.y() + 12),
            )
            grad.setColorAt(0.0, _mix(main, QColor("#ffffff"), 0.34))
            grad.setColorAt(0.55, main)
            grad.setColorAt(1.0, _mix(main, shade, 0.55))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(
                QRectF(centre.x() - 13.0, centre.y() - 12.0, 26.0, 24.0)
            )
        painter.setPen(Qt.NoPen)

    def _collar(
        self,
        painter: QPainter,
        joints: Skeleton,
        outfit: Mapping[str, str],
    ) -> None:
        """Turtleneck roll that blends into the shoulders instead of a box."""
        top = joints.neck
        chest = joints.chest
        main = _color(outfit["main"], QColor("#f6efe2"))
        shade = _color(outfit["shade"], QColor("#ddd0bd"))

        roll = QPainterPath()
        roll.moveTo(top.x() - 10.5, top.y() - 6)
        roll.cubicTo(
            _pt(top.x() - 14, top.y() + 4),
            _pt(top.x() - 13, chest.y() - 6),
            _pt(top.x() - 6, chest.y() - 1),
        )
        roll.cubicTo(
            _pt(top.x() - 2, chest.y() + 3),
            _pt(top.x() + 2, chest.y() + 3),
            _pt(top.x() + 6, chest.y() - 1),
        )
        roll.cubicTo(
            _pt(top.x() + 13, chest.y() - 6),
            _pt(top.x() + 14, top.y() + 4),
            _pt(top.x() + 10.5, top.y() - 6),
        )
        roll.closeSubpath()

        grad = QLinearGradient(
            _pt(top.x() - 12, top.y() - 6), _pt(top.x() + 12, chest.y())
        )
        grad.setColorAt(0.0, _mix(main, QColor("#ffffff"), 0.40))
        grad.setColorAt(0.55, main)
        grad.setColorAt(1.0, shade)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(roll)

        # rib arcs + top rim highlight
        painter.setPen(QPen(_alpha(shade, 140), 1.1))
        for offset in (-6.0, 0.0, 6.0):
            painter.drawArc(
                QRectF(top.x() + offset - 5, top.y() - 3, 10, 15), 95 * 16, 170 * 16
            )
        painter.setPen(
            QPen(_alpha(QColor("#ffffff"), 170), 1.6, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawArc(QRectF(top.x() - 10, top.y() - 7, 20, 12), 20 * 16, 140 * 16)
        painter.setPen(Qt.NoPen)

    # ---- arms ---------------------------------------------------------
    def _arms(
        self,
        painter: QPainter,
        joints: Skeleton,
        skin: QColor,
        outfit: Mapping[str, str],
        pose: Pose,
    ) -> None:
        main = _color(outfit["main"], QColor("#f6efe2"))
        sleeve = _mix(main, QColor("#ffffff"), 0.10)
        for shoulder, elbow, wrist in (
            (joints.shoulder_l, joints.elbow_l, joints.wrist_l),
            (joints.shoulder_r, joints.elbow_r, joints.wrist_r),
        ):
            mid = _pt(
                shoulder.x() * 0.62 + elbow.x() * 0.38,
                shoulder.y() * 0.62 + elbow.y() * 0.38,
            )
            # 3/4 sleeve: a soft taper, no shoulder pad poking out
            inner = _pt(
                shoulder.x() * 0.94 + elbow.x() * 0.06,
                shoulder.y() * 0.94 + elbow.y() * 0.06 + 2.0,
            )
            _limb(painter, inner, mid, 20.0, 17.0, sleeve, light=0.26)
            _limb(painter, mid, elbow, 17.0, 13.5, sleeve, light=0.20)
            _limb(painter, elbow, wrist, 14.5, 10.5, skin, light=0.18)
            # cuff ring
            painter.setPen(
                QPen(
                    _mix(main, QColor("#ffffff"), 0.42), 3.0, Qt.SolidLine, Qt.RoundCap
                )
            )
            painter.drawLine(
                _pt(elbow.x() - 7.5, elbow.y() + 1.5),
                _pt(elbow.x() + 7.5, elbow.y() - 1.5),
            )
            # hand
            dx = wrist.x() - elbow.x()
            dy = wrist.y() - elbow.y()
            length = math.hypot(dx, dy) or 1e-6
            palm = _pt(wrist.x() + dx / length * 4.5, wrist.y() + dy / length * 4.5)
            hand = QPainterPath()
            hand.addEllipse(QRectF(palm.x() - 6.5, palm.y() - 6.5, 13.0, 17.0))
            hg = QLinearGradient(
                _pt(palm.x() - 6, palm.y()), _pt(palm.x() + 6, palm.y() + 13)
            )
            hg.setColorAt(0.0, _mix(skin, QColor("#ffffff"), 0.28))
            hg.setColorAt(1.0, _mix(skin, QColor("#b9785c"), 0.42))
            painter.setBrush(QBrush(hg))
            painter.drawPath(hand)
            painter.setPen(QPen(_alpha(_mix(skin, QColor("#9c6a52"), 0.6), 90), 1.0))
            for index in range(3):
                offset = -3.0 + index * 3.0
                painter.drawLine(
                    _pt(palm.x() + offset, palm.y() + 6.0),
                    _pt(palm.x() + offset, palm.y() + 12.0),
                )
            painter.setPen(Qt.NoPen)

    # ---- head ---------------------------------------------------------
    def _head(
        self,
        painter: QPainter,
        joints: Skeleton,
        skin: QColor,
        hair: QColor,
        eye: QColor,
        pose: Pose,
        talking: bool,
    ) -> None:
        centre = joints.head
        tilt = pose.head_tilt * 0.9 + pose.lean * 0.3
        painter.save()
        painter.translate(centre)
        painter.rotate(tilt)
        painter.translate(-centre)

        face = self._face_path(centre, pose)
        grad = QRadialGradient(_pt(centre.x() - 12, centre.y() - 14), HEAD_R * 2.1)
        grad.setColorAt(0.0, _mix(skin, QColor("#ffffff"), 0.42))
        grad.setColorAt(0.55, skin)
        grad.setColorAt(1.0, _mix(skin, QColor("#c98f74"), 0.32))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(face)

        # ears
        for sign in (-1, 1):
            ear = QRectF(centre.x() + sign * (HEAD_R - 6) - 5, centre.y() + 2, 10, 16)
            painter.setBrush(QBrush(_mix(skin, QColor("#c98f74"), 0.16)))
            painter.drawEllipse(ear)

        # neck shadow under the jaw
        jaw = QPainterPath(_pt(centre.x() - 20, centre.y() + HEAD_R - 10))
        jaw.quadTo(
            _pt(centre.x(), centre.y() + HEAD_R + 4),
            _pt(centre.x() + 20, centre.y() + HEAD_R - 10),
        )
        painter.setPen(
            QPen(_alpha(QColor("#000000"), 26), 5.0, Qt.SolidLine, Qt.RoundCap)
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(jaw)

        self._eyes(painter, centre, eye, pose, skin)
        self._brows(painter, centre, hair, pose)
        self._nose(painter, centre, skin)
        self._mouth(painter, centre, skin, pose, talking)
        self._blush(painter, centre, pose)
        painter.restore()
        del joints

    def _face_path(self, centre: QPointF, pose: Pose) -> QPainterPath:
        """Soft heart-shaped face with a pointed chin."""
        top = centre.y() - HEAD_R
        jaw_y = centre.y() + HEAD_R * 0.42
        chin_y = centre.y() + HEAD_R * 1.06
        path = QPainterPath(_pt(centre.x(), top))
        path.cubicTo(
            _pt(centre.x() + HEAD_R * 1.02, top + 6),
            _pt(centre.x() + HEAD_R * 0.99, jaw_y),
            _pt(centre.x() + HEAD_R * 0.62, jaw_y + 16),
        )
        path.cubicTo(
            _pt(centre.x() + HEAD_R * 0.34, chin_y - 2),
            _pt(centre.x() + 6, chin_y),
            _pt(centre.x(), chin_y),
        )
        path.cubicTo(
            _pt(centre.x() - 6, chin_y),
            _pt(centre.x() - HEAD_R * 0.34, chin_y - 2),
            _pt(centre.x() - HEAD_R * 0.62, jaw_y + 16),
        )
        path.cubicTo(
            _pt(centre.x() - HEAD_R * 0.99, jaw_y),
            _pt(centre.x() - HEAD_R * 1.02, top + 6),
            _pt(centre.x(), top),
        )
        path.closeSubpath()
        del pose
        return path

    def _eyes(
        self,
        painter: QPainter,
        centre: QPointF,
        eye: QColor,
        pose: Pose,
        skin: QColor | None = None,
    ) -> None:
        open_ratio = max(0.0, min(1.2, pose.eye_open))
        eye_y = centre.y() + 9.0
        spread = HEAD_R * 0.35
        width = HEAD_R * 0.60
        height = (HEAD_R * 0.36) * open_ratio
        for sign in (-1, 1):
            cx = centre.x() + sign * spread
            sx = cx - width / 2
            if height < 1.2:
                # closed lid: a small skin-coloured mound with a lash line
                painter.setPen(Qt.NoPen)
                lid = _mix(skin or QColor(DEFAULT_SKIN), QColor("#ffffff"), 0.18)
                painter.setBrush(QBrush(lid))
                painter.drawRoundedRect(QRectF(sx, eye_y - 3.0, width, 7.0), 3.0, 3.0)
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor("#40261c"), 2.4, Qt.SolidLine, Qt.RoundCap))
                painter.drawArc(
                    QRectF(sx + 1, eye_y - 5.0, width - 2, 9.0), 200 * 16, 140 * 16
                )
                continue
            # sclera
            sclera = QPainterPath()
            sclera.addEllipse(QRectF(sx, eye_y - height / 2, width, height))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#fffaf7")))
            painter.drawPath(sclera)

            # iris
            iris_r = min(width * 0.36, height * 0.92)
            pupil_x = cx + pose.look_x * 4.0
            pupil_y = eye_y + pose.look_y * 3.0
            iris = QRadialGradient(_pt(pupil_x, pupil_y), iris_r * 1.5)
            iris.setColorAt(0.0, _mix(eye, QColor("#ffffff"), 0.45))
            iris.setColorAt(0.42, eye)
            iris.setColorAt(0.85, _mix(eye, QColor("#12100e"), 0.55))
            iris.setColorAt(1.0, _mix(eye, QColor("#12100e"), 0.78))
            painter.setBrush(QBrush(iris))
            painter.drawEllipse(
                QRectF(pupil_x - iris_r, pupil_y - iris_r, iris_r * 2, iris_r * 2)
            )

            # pupil + catchlights
            painter.setBrush(QBrush(QColor("#161310")))
            pupil_r = iris_r * 0.42
            painter.drawEllipse(
                QRectF(pupil_x - pupil_r, pupil_y - pupil_r, pupil_r * 2, pupil_r * 2)
            )
            painter.setBrush(QBrush(_alpha(QColor("#ffffff"), 235)))
            painter.drawEllipse(
                QRectF(
                    pupil_x - iris_r * 0.62,
                    pupil_y - iris_r * 0.78,
                    iris_r * 0.62,
                    iris_r * 0.58,
                )
            )
            painter.setBrush(QBrush(_alpha(QColor("#ffffff"), 150)))
            painter.drawEllipse(
                QRectF(
                    pupil_x + iris_r * 0.18,
                    pupil_y + iris_r * 0.22,
                    iris_r * 0.34,
                    iris_r * 0.30,
                )
            )

            # clip everything to the eye shape, then add lids/lashes
            painter.save()
            clip = QPainterPath()
            clip.addEllipse(QRectF(sx, eye_y - height / 2, width, height))
            painter.setClipPath(clip)
            painter.setPen(QPen(_alpha(QColor("#3a2419"), 150), 3.0))
            painter.setBrush(Qt.NoBrush)
            painter.drawLine(
                _pt(sx, eye_y - height / 2 - 1),
                _pt(sx + width, eye_y - height / 2 - 1),
            )
            if pose.squint > 0.01:
                painter.setBrush(
                    QBrush(_alpha(QColor("#f3d3bd"), int(200 * pose.squint)))
                )
                painter.setPen(Qt.NoPen)
                painter.drawRect(
                    QRectF(sx, eye_y - height / 2, width, height * 0.45 * pose.squint)
                )
            painter.restore()

            # upper lash line, thicker at the outer corner
            lash = QPainterPath(_pt(sx - 1.5, eye_y - height / 2 + 1.5))
            lash.quadTo(
                _pt(sx + width / 2, eye_y - height / 2 - 4.5),
                _pt(sx + width + 1.0, eye_y - height / 2 + 2.5),
            )
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#2a1a13"), 2.9, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(lash)
            # outer corner flick
            painter.setPen(QPen(QColor("#2a1a13"), 2.2, Qt.SolidLine, Qt.RoundCap))
            painter.drawLine(
                _pt(sx + width + 0.5, eye_y - height / 2 + 2.5),
                _pt(sx + width + 4.5, eye_y - height / 2 - 1.0),
            )
            # lower lash
            painter.setPen(
                QPen(_alpha(QColor("#5b3a2a"), 150), 1.3, Qt.SolidLine, Qt.RoundCap)
            )
            painter.drawArc(
                QRectF(sx + 2, eye_y - height / 2 + 1, width - 4, height - 2),
                200 * 16,
                120 * 16,
            )
            # eyelid crease
            painter.setPen(
                QPen(_alpha(QColor("#b98267"), 120), 1.6, Qt.SolidLine, Qt.RoundCap)
            )
            painter.drawArc(
                QRectF(sx + 1, eye_y - height / 2 - 7, width - 2, height * 0.8),
                20 * 16,
                140 * 16,
            )

    def _brows(
        self, painter: QPainter, centre: QPointF, hair: QColor, pose: Pose
    ) -> None:
        """Short arched brows sitting above the eyes, tapering outward."""
        base = _mix(hair, QColor("#4a2b1c"), 0.5)
        lift = pose.brow * 2.6
        pinch = pose.brow_in * 3.0
        for sign in (-1, 1):
            inner = _pt(
                centre.x() + sign * 9.0,
                base_y_inner := (centre.y() - 9.0) + pinch,
            )
            peak = _pt(centre.x() + sign * 18.0, centre.y() - 15.0 - lift)
            outer = _pt(centre.x() + sign * 27.0, centre.y() - 10.0 - lift * 0.4)
            path = QPainterPath(inner)
            path.quadTo(peak, outer)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(_alpha(base, 200), 2.1, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(path)
            del base_y_inner

    def _nose(self, painter: QPainter, centre: QPointF, skin: QColor) -> None:
        painter.setPen(
            QPen(
                _alpha(_mix(skin, QColor("#b0745a"), 0.55), 130),
                1.6,
                Qt.SolidLine,
                Qt.RoundCap,
            )
        )
        path = QPainterPath(_pt(centre.x() + 1.0, centre.y() + 22.0))
        path.quadTo(
            _pt(centre.x() + 3.4, centre.y() + 27.0),
            _pt(centre.x() - 0.6, centre.y() + 27.6),
        )
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _mouth(
        self,
        painter: QPainter,
        centre: QPointF,
        skin: QColor,
        pose: Pose,
        talking: bool,
    ) -> None:
        mouth_y = centre.y() + 36.0
        openness = max(
            0.0, min(1.0, pose.mouth if not talking else max(pose.mouth, 0.45))
        )
        warm = _mix(QColor("#b3555c"), skin, 0.25)
        if openness > 0.06:
            shape = QPainterPath(_pt(centre.x() - 8.0, mouth_y))
            shape.quadTo(
                _pt(centre.x(), mouth_y - 1.4 + openness * 2.0),
                _pt(centre.x() + 8.0, mouth_y),
            )
            shape.quadTo(
                _pt(centre.x(), mouth_y + 4.0 + openness * 11.0),
                _pt(centre.x() - 8.0, mouth_y),
            )
            shape.closeSubpath()
            grad = QLinearGradient(
                _pt(centre.x(), mouth_y), _pt(centre.x(), mouth_y + 12)
            )
            grad.setColorAt(0.0, _mix(warm, QColor("#6d2a35"), 0.45))
            grad.setColorAt(1.0, _mix(warm, QColor("#e2858f"), 0.35))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPath(shape)
            if openness > 0.4:
                painter.setBrush(QBrush(_alpha(QColor("#f0a3ac"), 200)))
                painter.drawEllipse(
                    QRectF(centre.x() - 4.0, mouth_y + 4.0, 8.0, 2.6 + openness * 3.0)
                )
            return
        smile = pose.smile
        lift = smile * 3.4
        width = 7.2 + max(0.0, smile) * 2.2
        curve = QPainterPath(_pt(centre.x() - width, mouth_y - lift * 0.4))
        curve.quadTo(
            _pt(centre.x(), mouth_y + (1.6 if smile >= 0 else -1.6) + lift * 0.35),
            _pt(centre.x() + width, mouth_y - lift * 0.4),
        )
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(_mix(warm, QColor("#7d3a44"), 0.35), 2.5, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawPath(curve)
        # upper lip highlight
        painter.setPen(
            QPen(_alpha(QColor("#ffffff"), 60), 1.2, Qt.SolidLine, Qt.RoundCap)
        )
        painter.drawArc(
            QRectF(centre.x() - width, mouth_y - 1.0, width * 2, 6.0), 20 * 16, 140 * 16
        )

    def _blush(self, painter: QPainter, centre: QPointF, pose: Pose) -> None:
        strength = max(0.0, min(1.0, pose.blush))
        if strength < 0.02:
            return
        for sign in (-1, 1):
            cx = centre.x() + sign * 27.0
            cy = centre.y() + 24.0
            grad = QRadialGradient(_pt(cx, cy), 15.0)
            grad.setColorAt(0.0, _alpha(QColor("#ff8296"), int(140 * strength)))
            grad.setColorAt(1.0, _alpha(QColor("#ff8296"), 0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(QRectF(cx - 15, cy - 10, 30, 20))
            painter.setPen(
                QPen(
                    _alpha(QColor("#ff6f88"), int(120 * strength)),
                    1.3,
                    Qt.SolidLine,
                    Qt.RoundCap,
                )
            )
            for offset in (-4.0, 0.0, 4.0):
                painter.drawLine(
                    _pt(cx + offset, cy - 3.0), _pt(cx + offset - 1.5, cy + 4.0)
                )

    # ---- hair ---------------------------------------------------------
    def _hair_back(
        self,
        painter: QPainter,
        joints: Skeleton,
        hair: QColor,
        pose: Pose,
    ) -> None:
        """Bob silhouette: a rounded cap that widens to the jaw and curls in."""
        centre = joints.head
        sway = pose.hair_sway * 0.8
        dark = hair.darker(155)
        top = centre.y() - HEAD_R - 10
        chin = centre.y() + HEAD_R * 0.72
        half = HEAD_R + 5

        path = QPainterPath(_pt(centre.x(), top))
        # right side of the cap, down to the jaw
        path.cubicTo(
            _pt(centre.x() + half * 1.05, top + 4),
            _pt(centre.x() + half * 1.10, centre.y() + 30),
            _pt(centre.x() + half * 0.94 + sway, chin),
        )
        # inward curl at the tip
        path.cubicTo(
            _pt(centre.x() + half * 0.84 + sway, chin + 14),
            _pt(centre.x() + half * 0.46 + sway, chin + 10),
            _pt(centre.x() + half * 0.40, chin - 6),
        )
        # close across the neck to the left tip
        path.lineTo(_pt(centre.x() - half * 0.40, chin - 6))
        path.cubicTo(
            _pt(centre.x() - half * 0.46 + sway, chin + 10),
            _pt(centre.x() - half * 0.84 + sway, chin + 14),
            _pt(centre.x() - half * 0.94 + sway, chin),
        )
        path.cubicTo(
            _pt(centre.x() - half * 1.10, centre.y() + 30),
            _pt(centre.x() - half * 1.05, top + 4),
            _pt(centre.x(), top),
        )
        path.closeSubpath()

        grad = QLinearGradient(
            _pt(centre.x() - half, top), _pt(centre.x() + half * 0.6, chin + 12)
        )
        grad.setColorAt(0.0, _mix(hair, QColor("#ffffff"), 0.14))
        grad.setColorAt(0.42, hair)
        grad.setColorAt(1.0, dark)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(path)

        # soft inner shading where the hair meets the neck
        painter.setBrush(QBrush(_alpha(_mix(hair, QColor("#1b120d"), 0.55), 90)))
        painter.drawEllipse(QRectF(centre.x() - 22, centre.y() + HEAD_R * 0.30, 44, 26))

    def _hair_front(
        self,
        painter: QPainter,
        joints: Skeleton,
        hair: QColor,
        pose: Pose,
    ) -> None:
        """Side-swept fringe plus face-framing locks that hug the cheeks."""
        centre = joints.head
        sway = pose.hair_sway * 0.7
        light = _mix(hair, QColor("#ffffff"), 0.26)
        dark = hair.darker(150)
        top = centre.y() - HEAD_R - 8
        half = HEAD_R + 4

        # crown cap: follows the skull, ends just above the eyebrows
        cap = QPainterPath(_pt(centre.x(), top))
        cap.cubicTo(
            _pt(centre.x() + half * 0.72, top + 2),
            _pt(centre.x() + half * 0.99, centre.y() - HEAD_R * 0.45),
            _pt(centre.x() + half * 0.92, centre.y() - HEAD_R * 0.02),
        )
        # side-swept fringe: drops on the right, sweeps up on the left
        cap.cubicTo(
            _pt(centre.x() + half * 0.72, centre.y() - 6),
            _pt(centre.x() + 16, centre.y() - 34),
            _pt(centre.x() - 2, centre.y() - 37),
        )
        cap.cubicTo(
            _pt(centre.x() - 24, centre.y() - 38),
            _pt(centre.x() - half * 0.78, centre.y() - 33),
            _pt(centre.x() - half * 0.92, centre.y() - HEAD_R * 0.02),
        )
        cap.cubicTo(
            _pt(centre.x() - half * 0.99, centre.y() - HEAD_R * 0.45),
            _pt(centre.x() - half * 0.72, top + 2),
            _pt(centre.x(), top),
        )
        cap.closeSubpath()
        grad = QLinearGradient(
            _pt(centre.x() - half * 0.6, top),
            _pt(centre.x() + half * 0.6, centre.y() - 8),
        )
        grad.setColorAt(0.0, light)
        grad.setColorAt(0.45, hair)
        grad.setColorAt(1.0, _mix(hair, dark, 0.45))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPath(cap)

        # face-framing locks: smooth, tapering to the jaw, no points
        for sign in (-1, 1):
            lock = QPainterPath(
                _pt(centre.x() + sign * half * 0.86, centre.y() - HEAD_R * 0.32)
            )
            lock.cubicTo(
                _pt(centre.x() + sign * (half + 5), centre.y() + 4),
                _pt(centre.x() + sign * (half + 3) + sway, centre.y() + 30),
                _pt(centre.x() + sign * (half - 9) + sway, centre.y() + HEAD_R * 0.62),
            )
            lock.cubicTo(
                _pt(centre.x() + sign * (half - 16) + sway, centre.y() + 18),
                _pt(centre.x() + sign * (half - 20), centre.y() - 4),
                _pt(centre.x() + sign * (half - 26), centre.y() - 26),
            )
            lock.closeSubpath()
            lg = QLinearGradient(
                _pt(centre.x() + sign * half, centre.y() - HEAD_R * 0.3),
                _pt(centre.x() + sign * half, centre.y() + HEAD_R * 0.6),
            )
            lg.setColorAt(0.0, _mix(hair, QColor("#ffffff"), 0.18))
            lg.setColorAt(0.5, hair)
            lg.setColorAt(1.0, _mix(hair, dark, 0.35))
            painter.setBrush(QBrush(lg))
            painter.drawPath(lock)

        # soft strand highlights, kept inside the hair silhouette
        painter.setBrush(Qt.NoBrush)
        painter.setPen(
            QPen(_alpha(QColor("#fff4e6"), 90), 3.0, Qt.SolidLine, Qt.RoundCap)
        )
        sheen = QPainterPath(_pt(centre.x() - 20, centre.y() - HEAD_R + 6))
        sheen.quadTo(
            _pt(centre.x() + 2, centre.y() - HEAD_R - 3),
            _pt(centre.x() + 26, centre.y() - HEAD_R + 8),
        )
        painter.drawPath(sheen)

        painter.setPen(QPen(_alpha(dark, 70), 1.1, Qt.SolidLine, Qt.RoundCap))
        for sign in (-1, 1):
            strand = QPainterPath(_pt(centre.x() + sign * 12, centre.y() - HEAD_R + 2))
            strand.quadTo(
                _pt(centre.x() + sign * 30, centre.y() - HEAD_R + 20),
                _pt(centre.x() + sign * 33, centre.y() + HEAD_R * 0.42),
            )
            painter.drawPath(strand)
        painter.setPen(Qt.NoPen)

    def _accessory(
        self,
        painter: QPainter,
        joints: Skeleton,
        appearance: Mapping[str, Any],
    ) -> None:
        accessory = str(appearance.get("accessory", "none")).strip().lower()
        centre = joints.head
        if accessory in {"none", ""}:
            return
        if accessory == "ribbon":
            base = QColor("#e8608c")
            for sign in (-1, 1):
                bow = QPainterPath()
                bow.moveTo(_pt(centre.x() + 22, centre.y() - HEAD_R + 6))
                bow.quadTo(
                    _pt(centre.x() + 22 + sign * 16, centre.y() - HEAD_R - 6),
                    _pt(centre.x() + 22 + sign * 20, centre.y() - HEAD_R + 12),
                )
                bow.quadTo(
                    _pt(centre.x() + 22 + sign * 8, centre.y() - HEAD_R + 10),
                    _pt(centre.x() + 22, centre.y() - HEAD_R + 6),
                )
                grad = QLinearGradient(
                    _pt(centre.x() + 22, centre.y() - HEAD_R - 4),
                    _pt(centre.x() + 22, centre.y() - HEAD_R + 14),
                )
                grad.setColorAt(0.0, _mix(base, QColor("#ffffff"), 0.30))
                grad.setColorAt(1.0, base.darker(130))
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(grad))
                painter.drawPath(bow)
        elif accessory == "glasses":
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(_alpha(QColor("#3a3a44"), 200), 1.8))
            for sign in (-1, 1):
                painter.drawRoundedRect(
                    QRectF(centre.x() + sign * 17 - 15, centre.y() - 6, 30, 24), 7, 7
                )
            painter.drawLine(
                _pt(centre.x() - 3, centre.y() + 4), _pt(centre.x() + 3, centre.y() + 4)
            )
        elif accessory == "headphones":
            band = QPainterPath(_pt(centre.x() - HEAD_R - 2, centre.y() - 4))
            band.cubicTo(
                _pt(centre.x() - HEAD_R, centre.y() - HEAD_R - 22),
                _pt(centre.x() + HEAD_R, centre.y() - HEAD_R - 22),
                _pt(centre.x() + HEAD_R + 2, centre.y() - 4),
            )
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor("#3f4353"), 5.0, Qt.SolidLine, Qt.RoundCap))
            painter.drawPath(band)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(QColor("#4d5266")))
            for sign in (-1, 1):
                painter.drawRoundedRect(
                    QRectF(
                        centre.x() + sign * (HEAD_R + 2) - 7, centre.y() + 2, 14, 22
                    ),
                    6,
                    6,
                )

    def _mood(self, painter: QPainter, joints: Skeleton, pose: Pose) -> None:
        """Tiny flourishes that sell the emotion (sweat drop, sparkles)."""
        centre = joints.head
        if pose.brow_in > 0.7 and pose.smile < -0.2:
            # anger mark
            x = centre.x() + HEAD_R - 4
            y = centre.y() - HEAD_R + 6
            painter.setPen(QPen(QColor("#e0525f"), 2.0, Qt.SolidLine, Qt.RoundCap))
            for index in range(3):
                painter.drawLine(_pt(x + index * 5, y), _pt(x + index * 5 + 3, y - 7))
        if pose.squint > 0.6 and pose.mouth > 0.5:
            # little sparkles for joy
            for sign, offset in ((-1, 12.0), (1, 16.0)):
                x = centre.x() + sign * (HEAD_R + offset)
                y = centre.y() - HEAD_R + 8
                painter.setPen(
                    QPen(_alpha(QColor("#ffd76e"), 220), 2.0, Qt.SolidLine, Qt.RoundCap)
                )
                painter.drawLine(_pt(x - 4, y), _pt(x + 4, y))
                painter.drawLine(_pt(x, y - 4), _pt(x, y + 4))
