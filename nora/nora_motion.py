"""Procedural full-body motion engine for Nora's character.

The character is not a set of pre-rendered frames.  Every frame is computed
from a :class:`Pose` (a small bundle of joint angles and facial parameters),
and poses are produced by *clips* — short functions of time.  That means the
AI can decide **what** Nora does at the moment she answers, and the engine
still draws completely smooth, never-seen-before in-between frames.

Two ideas make the motion feel alive instead of canned:

``MotionController``
    Keeps an idle layer (breathing, weight shift, blink, hair sway) that never
    stops, and cross-fades gesture overlays on top of it.  Nothing ever snaps:
    a new gesture fades in over ~120 ms from the pose that is on screen.

``normalize_move``
    The only entry point for model-supplied motion.  It accepts a tiny,
    whitelisted JSON object, clamps every number and rejects everything else,
    so a hallucinating model can never drive the renderer into an unknown
    state — it can only pick a gesture and say how strongly she means it.

The module is dependency-free (no Qt) so it can be unit-tested headless.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, fields, replace
from typing import Any, Callable, Iterable, Mapping

# --------------------------------------------------------------------------
# Pose
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Pose:
    """One complete snapshot of the body.

    All angles are degrees, all offsets are pixels in the 220×520 design
    space.  Positive ``lean`` tips the torso to the right (viewer's right),
    positive ``head_tilt`` drops the head to the right, positive arm/leg
    angles swing the limb away from the body midline.
    """

    # body
    breath: float = 0.0
    bounce: float = 0.0
    lean: float = 0.0
    hip_shift: float = 0.0
    crouch: float = 0.0
    # head
    head_tilt: float = 0.0
    head_nod: float = 0.0
    head_turn: float = 0.0
    # arms (left = viewer's left)
    arm_l: float = 0.0
    arm_r: float = 0.0
    elbow_l: float = 0.0
    elbow_r: float = 0.0
    hand_l: float = 0.0
    hand_r: float = 0.0
    # legs
    leg_l: float = 0.0
    leg_r: float = 0.0
    knee_l: float = 0.0
    knee_r: float = 0.0
    foot_l: float = 0.0
    foot_r: float = 0.0
    # face
    eye_open: float = 1.0
    look_x: float = 0.0
    look_y: float = 0.0
    mouth: float = 0.0
    smile: float = 0.55
    brow: float = 0.0
    brow_in: float = 0.0
    blush: float = 0.0
    squint: float = 0.0
    # secondary motion
    hair_sway: float = 0.0
    skirt_sway: float = 0.0


_POSE_FIELDS = tuple(f.name for f in fields(Pose))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def blend(first: Pose, second: Pose, weight: float) -> Pose:
    """Linear blend; ``weight=0`` returns ``first`` untouched."""
    if weight <= 0.0:
        return first
    if weight >= 1.0:
        return second
    values = {
        name: lerp(getattr(first, name), getattr(second, name), weight)
        for name in _POSE_FIELDS
    }
    return Pose(**values)


def add(first: Pose, second: Pose, weight: float = 1.0) -> Pose:
    """Add ``second`` on top of ``first`` (used for gesture overlays)."""
    values = {
        name: getattr(first, name) + getattr(second, name) * weight
        for name in _POSE_FIELDS
    }
    return Pose(**values)


def clamp_pose(pose: Pose) -> Pose:
    """Keep facial parameters in their legal ranges after blending."""
    return replace(
        pose,
        eye_open=max(0.0, min(1.4, pose.eye_open)),
        smile=max(-1.0, min(1.0, pose.smile)),
        brow=max(-1.0, min(1.0, pose.brow)),
        brow_in=max(0.0, min(1.0, pose.brow_in)),
        blush=max(0.0, min(1.0, pose.blush)),
        squint=max(0.0, min(1.0, pose.squint)),
        mouth=max(0.0, min(1.0, pose.mouth)),
    )


def _ease_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3.0 - 2.0 * t)


def _pulse(t: float) -> float:
    """0 → 1 → 0 envelope over the clip duration."""
    t = max(0.0, min(1.0, t))
    return math.sin(math.pi * t)


def _wave(t: float, cycles: float = 1.0, phase: float = 0.0) -> float:
    return math.sin(2.0 * math.pi * (cycles * t + phase))


def _settle(t: float, attack: float = 0.18) -> float:
    """Fast attack, slow spring-like release: reads as a real body movement."""
    t = max(0.0, min(1.0, t))
    if t < attack:
        return _ease_out(t / attack)
    return 1.0 - _ease_in_out((t - attack) / max(1e-6, 1.0 - attack))


# --------------------------------------------------------------------------
# Clips
# --------------------------------------------------------------------------

Clip = Callable[[float, float, random.Random], Pose]


def _clip_idle(t: float, amp: float, rng: random.Random) -> Pose:
    breath = _wave(t, 0.55) * amp
    return Pose(
        breath=breath,
        bounce=breath * 0.8,
        lean=_wave(t, 0.27) * 0.9 * amp,
        hip_shift=_wave(t, 0.23, 0.2) * 1.4 * amp,
        head_tilt=_wave(t, 0.21, 0.35) * 1.1 * amp,
        head_nod=_wave(t, 0.42) * 0.7 * amp,
        hair_sway=_wave(t, 0.24, 0.1) * 1.6 * amp,
        skirt_sway=_wave(t, 0.24, 0.1) * 1.2 * amp,
        arm_l=_wave(t, 0.27, 0.05) * 1.3 * amp,
        arm_r=_wave(t, 0.27, 0.05) * 1.3 * amp,
        elbow_l=(2.0 + _wave(t, 0.23) * 1.5) * amp,
        elbow_r=(2.0 + _wave(t, 0.23, 0.5) * 1.5) * amp,
        smile=0.5,
    )


def _clip_breathe_in(t: float, amp: float, rng: random.Random) -> Pose:
    """A deliberate deep breath — chest up, shoulders lifted, eyes closed."""
    p = _pulse(t)
    return Pose(
        breath=p * 2.6 * amp,
        bounce=p * 1.6 * amp,
        eye_open=1.0 - 0.75 * p,
        smile=0.62,
        head_nod=-1.4 * p,
        arm_l=-1.2 * p,
        arm_r=1.2 * p,
    )


def _clip_wave(t: float, amp: float, rng: random.Random) -> Pose:
    """Raise the right arm and wave the hand.  Non-looping and lively."""
    raise_t = _settle(t, attack=0.22)
    wave = _wave(t, 2.4) * _ease_out(min(1.0, t * 3.0)) * _pulse(t) ** 0.4
    return Pose(
        arm_r=-118.0 * raise_t * amp,
        elbow_r=(24.0 + 16.0 * wave) * raise_t * amp,
        hand_r=wave * 20.0 * amp,
        arm_l=4.0 * raise_t,
        lean=-3.2 * raise_t * amp,
        head_tilt=-3.0 * raise_t * amp,
        hair_sway=-2.4 * raise_t * amp,
        smile=0.85,
        eye_open=0.92 + 0.08 * (1.0 - raise_t),
        blush=0.18,
        brow=0.25,
    )


def _clip_jump(t: float, amp: float, rng: random.Random) -> Pose:
    """Anticipation crouch, airborne tuck, landing squash."""
    if t < 0.18:
        p = _ease_out(t / 0.18)
        return Pose(
            crouch=9.0 * p * amp,
            bounce=6.0 * p * amp,
            knee_l=16.0 * p * amp,
            knee_r=16.0 * p * amp,
            arm_l=-12.0 * p,
            arm_r=12.0 * p,
            smile=0.4,
        )
    if t < 0.30:
        p = _ease_out((t - 0.18) / 0.12)
        return Pose(
            bounce=-(34.0 * p) * amp,
            crouch=-4.0 * p,
            knee_l=-14.0 * p,
            knee_r=-14.0 * p,
            arm_l=-70.0 * p,
            arm_r=70.0 * p,
            head_nod=-3.0 * p,
            mouth=0.45 * p,
            eye_open=1.0 + 0.25 * p,
            hair_sway=-4.0 * p,
        )
    if t < 0.62:
        p = _ease_out((t - 0.30) / 0.32)
        return Pose(
            bounce=-34.0 * amp + 68.0 * amp * p,
            arm_l=-62.0 + 22.0 * p,
            arm_r=62.0 - 22.0 * p,
            knee_l=-10.0 + 6.0 * p,
            knee_r=-10.0 + 6.0 * p,
            hair_sway=5.0 * p * amp,
            mouth=0.3,
        )
    p = _ease_out((t - 0.62) / 0.38)
    squash = math.exp(-6.0 * p) * math.cos(p * 9.0)
    return Pose(
        crouch=7.0 * squash * amp,
        bounce=-3.0 * squash * amp,
        knee_l=12.0 * squash * amp,
        knee_r=12.0 * squash * amp,
        arm_l=-6.0 * squash,
        arm_r=6.0 * squash,
        head_nod=2.0 * squash,
        smile=0.7,
        hair_sway=-3.0 * squash,
    )


def _clip_dance(t: float, amp: float, rng: random.Random) -> Pose:
    """Continuous groove: hips, shoulders and head on different beats."""
    a = 2.0 * math.pi * t
    return Pose(
        hip_shift=math.sin(a * 2.0) * 6.0 * amp,
        lean=math.sin(a * 2.0 + 1.2) * 5.0 * amp,
        bounce=(math.sin(a * 4.0) * 3.0 - 1.0) * amp,
        head_tilt=math.sin(a * 2.0 + 0.5) * 5.0 * amp,
        head_nod=math.sin(a * 4.0 + 1.0) * 2.4 * amp,
        arm_l=-52.0 + math.sin(a * 2.0) * 26.0 * amp,
        arm_r=52.0 + math.sin(a * 2.0 + math.pi) * 26.0 * amp,
        elbow_l=58.0 + math.sin(a * 4.0) * 18.0,
        elbow_r=58.0 + math.sin(a * 4.0 + math.pi) * 18.0,
        hand_l=math.sin(a * 4.0) * 14.0,
        hand_r=math.sin(a * 4.0 + math.pi) * 14.0,
        knee_l=max(0.0, math.sin(a * 4.0)) * 9.0 * amp,
        knee_r=max(0.0, -math.sin(a * 4.0)) * 9.0 * amp,
        leg_l=math.sin(a * 2.0) * 4.0 * amp,
        leg_r=-math.sin(a * 2.0) * 4.0 * amp,
        skirt_sway=math.sin(a * 2.0 + 0.6) * 5.0 * amp,
        hair_sway=math.sin(a * 2.0 - 0.4) * 4.0 * amp,
        smile=0.95,
        blush=0.3,
        eye_open=0.86,
        mouth=0.12 + 0.12 * max(0.0, math.sin(a * 4.0)),
    )


def _clip_talk(t: float, amp: float, rng: random.Random) -> Pose:
    """Tiny emphatic gestures while speaking — never a static talking head."""
    return Pose(
        mouth=0.35 + 0.4 * abs(_wave(t, 3.2)),
        head_nod=_wave(t, 1.1) * 1.6 * amp,
        head_tilt=_wave(t, 0.7, 0.3) * 1.8 * amp,
        arm_l=6.0 + _wave(t, 0.8) * 5.0 * amp,
        arm_r=6.0 + _wave(t, 0.8, 0.5) * 5.0 * amp,
        elbow_l=16.0 + _wave(t, 1.2) * 6.0,
        elbow_r=16.0 + _wave(t, 1.2, 0.5) * 6.0,
        hand_l=_wave(t, 1.6) * 10.0 * amp,
        hand_r=_wave(t, 1.6, 0.4) * 10.0 * amp,
        smile=0.6,
    )


def _clip_listen(t: float, amp: float, rng: random.Random) -> Pose:
    p = _ease_out(t * 2.0) if t < 0.5 else 1.0
    return Pose(
        head_tilt=6.0 * p * amp,
        lean=2.0 * p,
        eye_open=1.1,
        brow=0.35 * p,
        smile=0.42,
        arm_l=-6.0 * p,
        arm_r=6.0 * p,
        elbow_l=22.0 * p,
        elbow_r=22.0 * p,
        head_turn=1.2 * p,
    )


def _clip_think(t: float, amp: float, rng: random.Random) -> Pose:
    p = _ease_out(min(1.0, t * 2.2))
    return Pose(
        head_tilt=-5.0 * p,
        brow_in=0.7 * p,
        brow=-0.15 * p,
        squint=0.35 * p,
        look_y=-0.55 * p,
        look_x=0.25 * p,
        smile=0.2,
        arm_r=-46.0 * p * amp,
        elbow_r=118.0 * p * amp,
        hand_r=-24.0 * p,
        arm_l=6.0 * p,
        elbow_l=26.0 * p,
        lean=1.6 * p,
    )


def _clip_laugh(t: float, amp: float, rng: random.Random) -> Pose:
    p = _pulse(t)
    shake = math.sin(t * 34.0) * p
    return Pose(
        head_nod=-4.0 * p,
        head_tilt=3.0 * p,
        bounce=2.5 * shake,
        lean=2.0 * p,
        mouth=0.85 * p,
        smile=1.0,
        squint=0.8 * p,
        eye_open=1.0 - 0.4 * p,
        blush=0.35 * p,
        arm_l=-14.0 * p,
        arm_r=14.0 * p,
        elbow_l=40.0 * p,
        elbow_r=40.0 * p,
        hair_sway=shake * 2.0,
    )


def _clip_surprised(t: float, amp: float, rng: random.Random) -> Pose:
    p = _settle(t, attack=0.10)
    jitter = math.sin(t * 26.0) * 0.6 * p
    return Pose(
        bounce=-4.0 * p * amp,
        eye_open=1.0 + 0.35 * p,
        brow=0.9 * p,
        mouth=0.62 * p,
        smile=0.1,
        arm_l=-26.0 * p * amp,
        arm_r=26.0 * p * amp,
        elbow_l=54.0 * p,
        elbow_r=54.0 * p,
        hand_l=12.0 * p,
        hand_r=12.0 * p,
        head_nod=-2.0 * p,
        lean=jitter,
        hair_sway=-3.0 * p,
    )


def _clip_shy(t: float, amp: float, rng: random.Random) -> Pose:
    p = _ease_out(min(1.0, t * 2.4))
    return Pose(
        head_tilt=7.0 * p * amp,
        head_nod=3.5 * p,
        look_x=-0.5 * p,
        look_y=0.45 * p,
        blush=0.85 * p,
        smile=0.55,
        brow=0.2 * p,
        arm_l=10.0 * p,
        arm_r=-10.0 * p,
        elbow_l=28.0 * p,
        elbow_r=28.0 * p,
        lean=-2.0 * p,
        hair_sway=-2.0 * p,
    )


def _clip_angry(t: float, amp: float, rng: random.Random) -> Pose:
    p = _settle(t, attack=0.14)
    shake = math.sin(t * 22.0) * p
    return Pose(
        brow_in=1.0 * p,
        brow=-0.75 * p,
        squint=0.55 * p,
        smile=-0.5 * p,
        mouth=0.2 * p,
        arm_l=-18.0 * p,
        arm_r=18.0 * p,
        elbow_l=62.0 * p,
        elbow_r=62.0 * p,
        lean=1.2 * shake,
        bounce=0.6 * shake,
        hair_sway=shake * 1.6,
        head_nod=1.4 * p,
    )


def _clip_sad(t: float, amp: float, rng: random.Random) -> Pose:
    p = _ease_out(min(1.0, t * 2.0))
    return Pose(
        head_nod=4.5 * p,
        head_tilt=-3.0 * p,
        brow_in=0.8 * p,
        brow=-0.3 * p,
        smile=-0.65 * p,
        eye_open=0.72 * p + 0.28,
        look_y=0.55 * p,
        arm_l=3.0 * p,
        arm_r=-3.0 * p,
        elbow_l=10.0 * p,
        elbow_r=10.0 * p,
        lean=-1.4 * p,
        hair_sway=1.6 * p,
    )


def _clip_sleep(t: float, amp: float, rng: random.Random) -> Pose:
    breath = _wave(t, 0.28)
    return Pose(
        head_tilt=11.0 * amp,
        head_nod=5.0 * amp,
        eye_open=0.0,
        smile=0.32,
        breath=breath * 2.0 * amp,
        bounce=breath * 1.4 * amp,
        lean=2.0 * amp,
        arm_l=2.0,
        arm_r=-2.0,
        elbow_l=4.0,
        elbow_r=4.0,
        hair_sway=breath * 0.8,
    )


def _clip_sit(t: float, amp: float, rng: random.Random) -> Pose:
    return Pose(
        crouch=52.0 * amp,
        knee_l=86.0 * amp,
        knee_r=86.0 * amp,
        leg_l=-14.0 * amp,
        leg_r=-14.0 * amp,
        lean=1.0,
        smile=0.6,
        arm_l=6.0,
        arm_r=-6.0,
        elbow_l=20.0,
        elbow_r=20.0,
    )


def _clip_walk(direction: float) -> Clip:
    def clip(t: float, amp: float, rng: random.Random) -> Pose:
        a = 2.0 * math.pi * t * 2.0
        swing = math.sin(a) * 14.0 * amp
        return Pose(
            leg_l=swing,
            leg_r=-swing,
            knee_l=max(0.0, math.sin(a + 0.6)) * 20.0 * amp,
            knee_r=max(0.0, -math.sin(a + 0.6)) * 20.0 * amp,
            arm_l=-swing * 0.8,
            arm_r=swing * 0.8,
            bounce=abs(math.sin(a)) * -2.2 * amp,
            lean=2.0 * direction * amp,
            hip_shift=math.sin(a) * 2.2 * amp,
            skirt_sway=math.sin(a) * 3.0 * amp,
            hair_sway=math.sin(a + 0.4) * 2.6 * amp,
            smile=0.62,
        )

    return clip


def _clip_shrug(t: float, amp: float, rng: random.Random) -> Pose:
    p = _pulse(t)
    return Pose(
        arm_l=-30.0 * p * amp,
        arm_r=30.0 * p * amp,
        elbow_l=74.0 * p,
        elbow_r=74.0 * p,
        hand_l=-18.0 * p,
        hand_r=18.0 * p,
        brow=0.55 * p,
        smile=0.35,
        head_tilt=2.5 * p,
    )


def _clip_stretch(t: float, amp: float, rng: random.Random) -> Pose:
    p = _pulse(t)
    return Pose(
        arm_l=-152.0 * p * amp,
        arm_r=152.0 * p * amp,
        elbow_l=10.0 * p,
        elbow_r=10.0 * p,
        head_nod=-6.0 * p,
        breath=3.0 * p,
        bounce=-5.0 * p * amp,
        eye_open=1.0 - 0.55 * p,
        mouth=0.35 * p,
        smile=0.5,
        lean=-1.5 * p,
    )


def _clip_nod(t: float, amp: float, rng: random.Random) -> Pose:
    return Pose(
        head_nod=5.0 * _wave(t, 1.6) * amp,
        smile=0.6,
        brow=0.1,
        eye_open=0.9,
    )


def _clip_shake(t: float, amp: float, rng: random.Random) -> Pose:
    return Pose(
        head_turn=_wave(t, 2.2) * 1.2 * amp,
        head_tilt=_wave(t, 2.2) * 1.6 * amp,
        smile=-0.1,
        brow_in=0.25,
        arm_l=-6.0 * abs(_wave(t, 2.2)) * amp,
        arm_r=6.0 * abs(_wave(t, 2.2)) * amp,
    )


def _clip_cheer(t: float, amp: float, rng: random.Random) -> Pose:
    p = _settle(t, attack=0.16)
    hop = abs(math.sin(t * math.pi * 2.2)) * p
    return Pose(
        arm_l=-140.0 * p * amp,
        arm_r=140.0 * p * amp,
        elbow_l=28.0 * p,
        elbow_r=28.0 * p,
        bounce=-12.0 * hop * amp,
        eye_open=0.85,
        mouth=0.5 * hop,
        smile=1.0,
        blush=0.45,
        head_nod=-3.0 * hop,
        hair_sway=-4.0 * hop,
        knee_l=max(0.0, -math.cos(t * math.pi * 2.2)) * 10.0 * p,
        knee_r=max(0.0, -math.cos(t * math.pi * 2.2)) * 10.0 * p,
    )


def _clip_point(t: float, amp: float, rng: random.Random) -> Pose:
    p = _settle(t, attack=0.20)
    return Pose(
        arm_r=-74.0 * p * amp,
        elbow_r=8.0 * p,
        hand_r=-8.0 * p,
        arm_l=6.0 * p,
        lean=2.4 * p,
        head_turn=1.0 * p,
        brow=0.4 * p,
        smile=0.6,
        mouth=0.18 * p,
    )


def _clip_clap(t: float, amp: float, rng: random.Random) -> Pose:
    beat = abs(_wave(t, 4.0))
    return Pose(
        arm_l=-56.0 * amp,
        arm_r=56.0 * amp,
        elbow_l=96.0 - 26.0 * (1.0 - beat),
        elbow_r=96.0 - 26.0 * (1.0 - beat),
        hand_l=18.0 * beat,
        hand_r=-18.0 * beat,
        smile=0.9,
        bounce=beat * -1.6,
        head_nod=beat * -1.4,
        blush=0.2,
    )


def _clip_bow(t: float, amp: float, rng: random.Random) -> Pose:
    p = _pulse(t)
    return Pose(
        lean=26.0 * p * amp,
        head_nod=10.0 * p,
        arm_l=-8.0 * p,
        arm_r=8.0 * p,
        elbow_l=14.0 * p,
        elbow_r=14.0 * p,
        eye_open=1.0 - 0.5 * p,
        smile=0.5,
        skirt_sway=-2.0 * p,
        hair_sway=-6.0 * p,
    )


def _clip_tilt_head(t: float, amp: float, rng: random.Random) -> Pose:
    p = _settle(t, attack=0.25)
    return Pose(
        head_tilt=-9.0 * p * amp,
        head_nod=1.5 * p,
        brow=0.45 * p,
        smile=0.6,
        eye_open=1.05,
        hair_sway=-2.0 * p,
        lean=-1.2 * p,
    )


# Registry: name → (clip, default duration seconds, loops, base amplitude)
GESTURES: dict[str, tuple[Clip, float, bool, float]] = {
    "idle": (_clip_idle, 6.0, True, 1.0),
    "breathe": (_clip_breathe_in, 3.4, False, 1.0),
    "wave": (_clip_wave, 2.2, False, 1.0),
    "jump": (_clip_jump, 1.5, False, 1.0),
    "dance": (_clip_dance, 4.0, True, 1.0),
    "talk": (_clip_talk, 2.5, True, 1.0),
    "listen": (_clip_listen, 3.0, True, 1.0),
    "think": (_clip_think, 4.0, True, 1.0),
    "laugh": (_clip_laugh, 1.6, False, 1.0),
    "surprised": (_clip_surprised, 1.5, False, 1.0),
    "shy": (_clip_shy, 3.0, False, 1.0),
    "angry": (_clip_angry, 2.0, False, 1.0),
    "sad": (_clip_sad, 3.0, False, 1.0),
    "sleep": (_clip_sleep, 5.0, True, 1.0),
    "sit": (_clip_sit, 5.0, True, 1.0),
    "walk_left": (_clip_walk(-1.0), 3.0, True, 1.0),
    "walk_right": (_clip_walk(1.0), 3.0, True, 1.0),
    "shrug": (_clip_shrug, 1.8, False, 1.0),
    "stretch": (_clip_stretch, 3.0, False, 1.0),
    "nod": (_clip_nod, 1.2, False, 1.0),
    "shake_head": (_clip_shake, 1.4, False, 1.0),
    "cheer": (_clip_cheer, 2.0, False, 1.0),
    "point": (_clip_point, 2.4, False, 1.0),
    "clap": (_clip_clap, 2.0, False, 1.0),
    "bow": (_clip_bow, 2.2, False, 1.0),
    "tilt_head": (_clip_tilt_head, 3.0, False, 1.0),
    # Alias with a calmer, smiling hold: the model can ask for "just smile".
    "smile_only": (_clip_idle, 6.0, True, 0.7),
}

#: Gestures the model is allowed to choose, in the order they appear in the
#: system prompt.  Kept small and expressive on purpose.
AI_GESTURES = (
    "wave",
    "nod",
    "shake_head",
    "tilt_head",
    "laugh",
    "smile_only",
    "idle",
    "surprised",
    "shy",
    "think",
    "shrug",
    "cheer",
    "clap",
    "point",
    "dance",
    "jump",
    "stretch",
    "bow",
    "listen",
    "talk",
    "sleep",
    "sit",
    "angry",
    "sad",
    "breathe",
)

#: Emotion → the gesture that reads best with it, used only when the model
#: omitted a move tag or when Nora runs offline (she still would not stand
#: perfectly still: the body language matches the feeling).
_EMOTION_FALLBACK: dict[str, tuple[str, ...]] = {
    "happy": ("wave", "nod", "tilt_head", "clap", "talk"),
    "love": ("shy", "nod", "tilt_head", "cheer"),
    "thinking": ("think", "tilt_head", "nod"),
    "surprised": ("surprised", "jump", "stretch"),
    "angry": ("angry", "shake_head", "shrug"),
    "sad": ("sad", "sit", "sleep"),
    "sleepy": ("sleep", "breathe", "sit"),
    "smug": ("tilt_head", "shrug", "nod"),
}

MAX_MOVE_STEPS = 3
DEFAULT_INTENSITY = 0.85
MAX_INTENSITY = 1.35
MIN_INTENSITY = 0.35
MIN_DURATION = 0.6
MAX_DURATION = 6.0


class MoveError(ValueError):
    """A model-supplied move was not safe or not well-formed."""


def _bounded(value: Any, low: float, high: float, default: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = float(value)
    if not math.isfinite(value):
        return default
    return max(low, min(high, value))


def _optional_number(item: Mapping[str, Any], key: str) -> float | None:
    """``None`` when absent; ``False`` when present but not a number."""
    if key not in item:
        return None
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MoveError(f"'{key}' sayı olmalı.")
    if not math.isfinite(float(value)):
        raise MoveError(f"'{key}' sınırlı bir sayı olmalı.")
    return float(value)


def normalize_move(raw: Any) -> dict[str, Any] | None:
    """Validate a model-supplied ``[MOVE:{...}]`` payload.

    Accepts either a single gesture object or ``{"steps": [...]}`` with a few
    chained gestures.  Unknown gesture names are rejected (never silently
    mapped) so the prompt's vocabulary stays the single source of truth.
    """
    if not isinstance(raw, Mapping):
        return None
    steps: list[dict[str, Any]] = []
    raw_steps: Iterable[Any]
    if "steps" in raw:
        candidate = raw.get("steps")
        if not isinstance(candidate, (list, tuple)) or not candidate:
            return None
        if len(candidate) > MAX_MOVE_STEPS:
            # silently dropping steps would make the tag dishonest
            return None
        raw_steps = list(candidate)
    else:
        raw_steps = [raw]

    for item in raw_steps:
        if not isinstance(item, Mapping):
            return None
        name = str(item.get("gesture") or item.get("name") or "").strip().lower()
        if name not in GESTURES:
            return None
        _clip, default_duration, _loops, _amp = GESTURES[name]
        try:
            raw_intensity = _optional_number(item, "intensity")
            raw_duration = _optional_number(item, "duration")
        except MoveError:
            return None
        intensity = (
            DEFAULT_INTENSITY
            if raw_intensity is None
            else max(MIN_INTENSITY, min(MAX_INTENSITY, raw_intensity))
        )
        duration = (
            default_duration
            if raw_duration is None
            else max(MIN_DURATION, min(MAX_DURATION, raw_duration))
        )
        steps.append(
            {
                "gesture": name,
                "intensity": round(intensity, 3),
                "duration": round(duration, 3),
            }
        )
    if not steps:
        return None
    return {"steps": steps}


def fallback_move(emotion: str, rng: random.Random | None = None) -> dict[str, Any]:
    """Body language for an emotion when no move tag arrived.

    Deliberately randomised: the same answer should not always produce the
    same gesture, otherwise the character looks pre-programmed.
    """
    chooser = rng or random
    options = _EMOTION_FALLBACK.get(emotion, _EMOTION_FALLBACK["happy"])
    name = chooser.choice(options)
    _clip, duration, _loops, _amp = GESTURES[name]
    return {"steps": [{"gesture": name, "intensity": 0.75, "duration": duration}]}


#: Gestures that should hold while the state lasts, not play once.
SUSTAINED = {
    "idle",
    "smile_only",
    "breathe",
    "dance",
    "talk",
    "listen",
    "think",
    "sleep",
    "sit",
    "walk_left",
    "walk_right",
}


@dataclass
class _Layer:
    gesture: str
    intensity: float
    duration: float
    loops: bool
    elapsed: float = 0.0
    weight: float = 0.0
    fading_out: bool = False


class MotionController:
    """Blends an always-on idle layer with gesture overlays.

    Everything is time based (`tick(seconds)`), so the caller's frame rate
    cannot change the speed of the animation — a 15 fps pet and a 60 fps chat
    avatar show the same movement.
    """

    FADE_IN = 0.14
    FADE_OUT = 0.26

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()
        self._time = 0.0
        self._layers: list[_Layer] = []
        self._sustained: _Layer | None = None
        self._last = Pose()
        self._blink_timer = 2.4
        self._blink_left = 0.0

    # -- public ----------------------------------------------------------
    def tick(self, dt: float) -> Pose:
        dt = max(0.0, min(0.25, float(dt)))
        self._time += dt
        target = self._base_pose()

        for layer in list(self._layers):
            layer.elapsed += dt
            if not layer.fading_out and layer.elapsed >= layer.duration:
                layer.fading_out = True
            if layer.fading_out:
                layer.weight = max(0.0, layer.weight - dt / self.FADE_OUT)
                if layer.weight <= 0.0:
                    self._layers.remove(layer)
                    continue
            else:
                layer.weight = min(1.0, layer.weight + dt / self.FADE_IN)
            target = add(target, self._evaluate(layer), layer.weight)

        if self._sustained is not None:
            layer = self._sustained
            # BUG FIX: sustained layers (walk/dance/talk/...) must advance their
            # own clock, otherwise they sit frozen on frame 0 forever.
            layer.elapsed += dt
            layer.weight = min(1.0, layer.weight + dt / self.FADE_IN)
            target = add(target, self._evaluate(layer), layer.weight)

        target = self._with_blink(target, dt)
        target = clamp_pose(target)
        self._last = target
        return target

    def play(
        self, move: Mapping[str, Any] | None, *, replace_sustained: bool = True
    ) -> bool:
        """Queue the steps of a validated move. Returns False when empty."""
        if not move:
            return False
        steps = list(move.get("steps") or [])[:MAX_MOVE_STEPS]
        if not steps:
            return False
        first = steps[0]
        name = first["gesture"]
        if name in SUSTAINED:
            if replace_sustained:
                self._sustained = None
            self._sustained = _Layer(
                gesture=name,
                intensity=float(first["intensity"]),
                duration=float(first["duration"]),
                loops=True,
                weight=0.0,
            )
            steps = steps[1:]
        for step in steps:
            name = step["gesture"]
            _clip, _duration, loops, _amp = GESTURES[name]
            layer = _Layer(
                gesture=name,
                intensity=float(step["intensity"]),
                duration=float(step["duration"]),
                loops=loops,
            )
            if name in SUSTAINED:
                self._sustained = layer
            else:
                self._layers.append(layer)
        return True

    def play_name(self, name: str, *, intensity: float = DEFAULT_INTENSITY) -> bool:
        return self.play(
            normalize_move({"gesture": name, "intensity": intensity}),
        )

    def stop_sustained(self) -> None:
        self._sustained = None

    def clear(self) -> None:
        self._layers.clear()
        self._sustained = None

    @property
    def sustained(self) -> str | None:
        return self._sustained.gesture if self._sustained else None

    @property
    def busy(self) -> bool:
        return bool(self._layers)

    # -- internals -------------------------------------------------------
    def _evaluate(self, layer: _Layer) -> Pose:
        clip, _duration, _loops, _base_amp = GESTURES[layer.gesture]
        t = layer.elapsed / max(1e-6, layer.duration)
        if clip_loops(layer.gesture) and layer.gesture != "idle":
            t = t % 1.0
        else:
            t = min(1.0, t)
        return clip(t, layer.intensity, self.rng)

    def _base_pose(self) -> Pose:
        """Idle breathing + slow weight shifts, always present."""
        t = self._time
        breath = math.sin(t * 1.75)
        sway = math.sin(t * 0.55)
        return Pose(
            breath=breath * 0.55,
            bounce=breath * 0.5,
            lean=sway * 0.7,
            hip_shift=math.sin(t * 0.47 + 0.6) * 1.1,
            head_tilt=math.sin(t * 0.41 + 0.2) * 0.9,
            head_nod=math.sin(t * 0.83) * 0.55,
            hair_sway=math.sin(t * 0.5 + 0.9) * 1.2,
            skirt_sway=math.sin(t * 0.5 + 0.9) * 0.9,
            arm_l=math.sin(t * 0.5 + 0.1) * 1.0,
            arm_r=math.sin(t * 0.5 + 0.1) * 1.0,
            elbow_l=3.0 + math.sin(t * 0.44) * 1.2,
            elbow_r=3.0 + math.sin(t * 0.44 + 0.4) * 1.2,
            smile=0.5,
        )

    BLINK_DURATION = 0.13

    def _with_blink(self, pose: Pose, dt: float) -> Pose:
        """Close and open the eyes over ~130 ms, every few seconds."""
        if self._blink_left > 0.0:
            self._blink_left = max(0.0, self._blink_left - dt)
            progress = 1.0 - (self._blink_left / self.BLINK_DURATION)
            # 0 → 1 → 0 triangle: 0 open, 1 shut
            closure = 1.0 - abs(2.0 * progress - 1.0)
            eyes = pose.eye_open * (1.0 - 0.95 * max(0.0, min(1.0, closure)))
            return replace(pose, eye_open=max(0.0, eyes))
        self._blink_timer -= dt
        if self._blink_timer <= 0.0:
            self._blink_left = self.BLINK_DURATION
            base = self.rng.uniform(2.2, 5.4)
            self._blink_timer = base if self.rng.random() > 0.12 else base * 0.45
        return pose


def clip_loops(name: str) -> bool:
    entry = GESTURES.get(name)
    return bool(entry[2]) if entry else False
