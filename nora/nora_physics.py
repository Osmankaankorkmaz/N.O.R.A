"""Airborne physics for the pet window.

The user can grab Nora with the mouse and throw her; she dangles, falls,
bounces and gets back up on her own.  The state machine is deliberately small
and deterministic (no randomness), so it can be unit tested and so the sprite
renderer always knows which illustration to show.

States::

    GROUND  --grab-->  HELD  --release-->  FALLING  --touchdown-->  LANDING
       ^                                                              |
       +------------------------- RECOVERING <-----------------------+

``THROWN`` is entered when the release happens with enough speed: she keeps the
thrown velocity, arcs through the air and only then falls.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

#: Downward acceleration in px/s².  Chosen so a 300 px drop takes ~1 second.
GRAVITY = 1600.0
#: Vertical speed kept after bouncing off the floor.
BOUNCE = 0.34
#: Below this speed the bounce is not worth animating.
MIN_BOUNCE = 90.0
#: Release speed (px/s) above which she is "thrown" rather than dropped.
THROW_SPEED = 320.0
#: Wall bounce keeps this fraction of the horizontal speed.
WALL_BOUNCE = 0.55
#: Longest drop we integrate in one step, to stay stable at low frame rates.
MAX_STEP = 1.0 / 30.0


class AirState(str, Enum):
    GROUND = "ground"
    HELD = "held"
    FALLING = "falling"
    LANDING = "landing"
    RECOVERING = "recovering"


@dataclass
class Body:
    """A tiny 2-D body: position in screen pixels, velocity in px/s."""

    x: float
    y: float
    vx: float = 0.0
    vy: float = 0.0

    def step(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt


class AirPhysics:
    """Drives the pet's vertical position through grab/throw/fall/land."""

    def __init__(self, floor_y: float, *, width: float = 0.0) -> None:
        self.floor_y = float(floor_y)
        self.width = float(width)
        self.body = Body(0.0, floor_y)
        self.state = AirState.GROUND
        self._recover_left = 0.0
        self._land_left = 0.0
        self._bounces = 0
        self._held_long = False

    # ------------------------------------------------------------------ helpers
    @property
    def airborne(self) -> bool:
        """``True`` while the sprite set should replace the ground mood."""
        return self.state in {AirState.HELD, AirState.FALLING}

    @property
    def stage(self) -> str | None:
        """Name of the sprite stage for the current state (see nora_sprite)."""
        if self.state is AirState.HELD:
            return "held" if self._held_long else "picked_up"
        if self.state is AirState.FALLING:
            return "bracing" if self.body.vy > 620.0 else "falling"
        if self.state is AirState.LANDING:
            return "landing"
        if self.state is AirState.RECOVERING:
            return "recovering"
        return None

    # ------------------------------------------------------------------ actions
    def grab(self, x: float, y: float) -> None:
        """Start dragging with the pointer at ``(x, y)``."""
        self.state = AirState.HELD
        self.body.vx = self.body.vy = 0.0
        self.body.x = float(x)
        self.body.y = float(y)
        self._held_long = False

    def drag_to(self, x: float, y: float, dt: float) -> None:
        """Move the held body, tracking the pointer's velocity."""
        dt = max(dt, 1e-3)
        new_x, new_y = float(x), float(y)
        self.body.vx = (new_x - self.body.x) / dt
        self.body.vy = (new_y - self.body.y) / dt
        self.body.x, self.body.y = new_x, new_y
        # Dangling for a moment changes the sprite from "just picked up" to
        # "held", which is what makes the interaction feel animated.
        self._held_long = True

    def release(self) -> None:
        """Let go: drop, or arc away when the release was fast."""
        if self.state is not AirState.HELD:
            return
        speed = math.hypot(self.body.vx, self.body.vy)
        if speed > THROW_SPEED and self.body.vy < -60.0:
            # Thrown upward: keep the arc, gravity takes over.
            self.body.vx *= 0.55
            self.body.vy = min(self.body.vy, -THROW_SPEED)
        elif speed > THROW_SPEED:
            self.body.vx *= 0.7
            self.body.vy = min(self.body.vy, 60.0)
        else:
            self.body.vx = math.copysign(min(abs(self.body.vx), 120.0), self.body.vx)
        self.state = AirState.FALLING
        self._bounces = 0
        self._held_long = False

    # ------------------------------------------------------------------- update
    def tick(
        self, dt: float, *, min_x: float | None = None, max_x: float | None = None
    ) -> bool:
        """Advance physics. Returns ``True`` while something is happening."""
        dt = max(0.0, min(float(dt), MAX_STEP))
        if dt == 0.0:
            return self.state is not AirState.GROUND

        if self.state is AirState.HELD:
            return True

        if self.state is AirState.FALLING:
            self.body.vy += GRAVITY * dt
            self.body.step(dt)
            self._clamp_horizontal(min_x, max_x)
            if self.body.y >= self.floor_y:
                self.body.y = self.floor_y
                if self.body.vy > MIN_BOUNCE and self._bounces < 2:
                    self.body.vy = -self.body.vy * BOUNCE
                    self.body.vx *= 0.6
                    self._bounces += 1
                else:
                    self.body.vy = 0.0
                    self.body.vx = 0.0
                    self.state = AirState.LANDING
                    self._land_left = 0.26
            return True

        if self.state is AirState.LANDING:
            self._land_left -= dt
            if self._land_left <= 0.0:
                self.state = AirState.RECOVERING
                self._recover_left = 0.5
            return True

        if self.state is AirState.RECOVERING:
            self._recover_left -= dt
            if self._recover_left <= 0.0:
                self.state = AirState.GROUND
                self.body.y = self.floor_y
                return False
            return True

        return False

    def _clamp_horizontal(self, min_x: float | None, max_x: float | None) -> None:
        if max_x is None or min_x is None or max_x <= min_x:
            return
        if self.body.x < min_x:
            self.body.x = min_x
            self.body.vx = abs(self.body.vx) * WALL_BOUNCE
        elif self.body.x > max_x:
            self.body.x = max_x
            self.body.vx = -abs(self.body.vx) * WALL_BOUNCE

    # ------------------------------------------------------------------ queries
    def offset_y(self) -> float:
        """How far above the floor she currently floats (0 = standing)."""
        return max(0.0, self.floor_y - self.body.y)


class AirStages:
    """Sequences the airborne sprites on top of the pet's own window physics.

    The pet already integrates gravity for its window position; this class adds
    the *acting*: which illustration to show and for how long.  Keeping it
    separate means the walking/jumping behaviour and its regression tests stay
    untouched while the sprite set gets the full pick-up → fall → land arc.
    """

    #: How long the "just picked up" sprite is held before switching to "held".
    PICKUP_TIME = 0.45
    #: How long the landing crouch and the dust-yourself-off sprites are shown.
    LAND_TIME = 0.30
    RECOVER_TIME = 0.55

    def __init__(self) -> None:
        self.state: AirState = AirState.GROUND
        self.elapsed = 0.0
        self.fall_speed = 0.0

    # ------------------------------------------------------------------ events
    def grab(self) -> None:
        self.state = AirState.HELD
        self.elapsed = 0.0
        self.fall_speed = 0.0

    def release(self, speed: float = 0.0) -> None:
        if self.state is not AirState.HELD:
            return
        self.state = AirState.FALLING
        self.elapsed = 0.0
        self.fall_speed = abs(float(speed))

    def landed(self, speed: float = 0.0) -> None:
        if self.state is not AirState.FALLING:
            return
        self.state = AirState.LANDING
        self.elapsed = 0.0
        self.fall_speed = abs(float(speed))

    def reset(self) -> None:
        self.state = AirState.GROUND
        self.elapsed = 0.0
        self.fall_speed = 0.0

    # ------------------------------------------------------------------ update
    def tick(self, dt: float) -> None:
        """Advance the stage machine, consuming the *whole* delta.

        A time budget is spent stage by stage, so a window that was hidden for
        several seconds lands, recovers and is standing again instead of being
        stuck halfway through one short phase.
        """
        budget = max(0.0, min(float(dt), 30.0))
        while budget > 0.0:
            if self.state not in (AirState.LANDING, AirState.RECOVERING):
                # HELD / FALLING are driven by the grab, release and landed
                # events (and by the pet's own gravity), not by a timer.
                self.elapsed += budget
                return
            finish = (
                self.LAND_TIME if self.state is AirState.LANDING else self.RECOVER_TIME
            )
            needed = max(0.0, finish - self.elapsed)
            if budget < needed:
                self.elapsed += budget
                return
            budget -= needed
            self.elapsed = 0.0
            if self.state is AirState.LANDING:
                self.state = AirState.RECOVERING
            else:
                self.state = AirState.GROUND

    # ----------------------------------------------------------------- queries
    @property
    def busy(self) -> bool:
        return self.state is not AirState.GROUND

    def stage(self) -> str | None:
        """Sprite stage name, or ``None`` when she is standing normally."""
        if self.state is AirState.HELD:
            return "picked_up" if self.elapsed < self.PICKUP_TIME else "held"
        if self.state is AirState.FALLING:
            return "bracing" if self.fall_speed > 620.0 else "falling"
        if self.state is AirState.LANDING:
            return "landing"
        if self.state is AirState.RECOVERING:
            return "recovering"
        return None


__all__ = [
    "BOUNCE",
    "GRAVITY",
    "MAX_STEP",
    "MIN_BOUNCE",
    "THROW_SPEED",
    "AirPhysics",
    "AirStages",
    "AirState",
    "Body",
]
