"""Tests for 1.12.0: full-body character, procedural motion, wide chat app."""

from __future__ import annotations

import math
import random
from pathlib import Path

import pytest

pytest.importorskip("PyQt5.QtWidgets")

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage, QPainter

from nora.nora_body import (
    DESIGN_HEIGHT,
    DESIGN_WIDTH,
    FullBodyCharacter,
    GROUND,
    skeleton,
)
from nora.nora_motion import (
    AI_GESTURES,
    GESTURES,
    MAX_MOVE_STEPS,
    MotionController,
    Pose,
    fallback_move,
    normalize_move,
)

# ----------------------------------------------------------------- motion core


def test_every_documented_gesture_exists_and_produces_a_pose():
    assert len(AI_GESTURES) >= 20
    for name in AI_GESTURES:
        assert name in GESTURES, f"{name} is offered to the model but missing"
        controller = MotionController(random.Random(7))
        controller.play_name(name)
        pose = controller.tick(0.2)
        assert isinstance(pose, Pose)


def test_motion_is_time_based_not_frame_based():
    slow = MotionController(random.Random(1))
    fast = MotionController(random.Random(1))
    slow.play_name("wave", intensity=1.0)
    fast.play_name("wave", intensity=1.0)
    # identical simulated time, different frame budgets
    for _ in range(60):
        slow.tick(1 / 60)
    for _ in range(15):
        fast.tick(4 / 60)
    assert slow.tick(0.0).arm_r == pytest.approx(fast.tick(0.0).arm_r, abs=0.5)


def test_idle_never_freezes_and_keeps_breathing():
    controller = MotionController(random.Random(3))
    poses = [controller.tick(1 / 30) for _ in range(180)]
    breaths = {round(pose.breath, 2) for pose in poses}
    assert len(breaths) > 20  # she breathes continuously
    # face/joints stay in sane ranges
    for pose in poses:
        assert -3.0 <= pose.lean <= 3.0
        assert 0.0 <= pose.eye_open <= 1.4


def test_blink_happens_on_its_own():
    controller = MotionController(random.Random(5))
    closed = False
    for _ in range(600):  # ~20 seconds at 30 fps
        pose = controller.tick(1 / 30)
        if pose.eye_open < 0.2:
            closed = True
            break
    assert closed, "the character never blinked in 20 seconds"


@pytest.mark.parametrize("gesture", ["wave", "jump", "laugh", "dance", "shrug"])
def test_gestures_change_the_body_and_return_to_idle(gesture):
    controller = MotionController(random.Random(11))
    controller.play_name(gesture, intensity=1.0)
    peak = 0.0
    for _ in range(240):
        pose = controller.tick(1 / 30)
        peak = max(peak, abs(pose.arm_l) + abs(pose.arm_r) + abs(pose.bounce))
    assert peak > 3.0, f"{gesture} did not move the body"
    assert not controller.busy, "the gesture never ended"


def test_cross_fade_is_smooth_never_a_jump():
    controller = MotionController(random.Random(13))
    previous = controller.tick(1 / 30)
    controller.play_name("wave")
    biggest = 0.0
    for _ in range(120):
        pose = controller.tick(1 / 30)
        biggest = max(biggest, abs(pose.arm_r - previous.arm_r))
        previous = pose
    # 0.14 s fade-in: per frame at 30 fps the arm cannot teleport
    assert biggest < 25.0


# --------------------------------------------------------------- model payload


@pytest.mark.parametrize(
    "payload",
    [
        {"gesture": "wave"},
        {"gesture": "WAVE", "intensity": 1.1, "duration": 2.0},
        {"steps": [{"gesture": "shrug"}, {"gesture": "nod", "duration": 0.8}]},
        {"gesture": "smile_only"},
    ],
)
def test_normalize_move_accepts_documented_payloads(payload):
    normalized = normalize_move(payload)
    assert normalized is not None
    assert 1 <= len(normalized["steps"]) <= MAX_MOVE_STEPS
    for step in normalized["steps"]:
        assert step["gesture"] in GESTURES
        assert 0.35 <= step["intensity"] <= 1.35
        assert 0.6 <= step["duration"] <= 6.0


@pytest.mark.parametrize(
    "payload",
    [
        None,
        "wave",
        {},
        {"gesture": "drop_table"},
        {"gesture": "wave", "steps": "nope"},
        {"steps": []},
        {"steps": [{"gesture": "wave"}] * (MAX_MOVE_STEPS + 5)},
        {"gesture": "wave", "intensity": "yüksek"},
    ],
)
def test_normalize_move_rejects_unsafe_payloads(payload):
    assert normalize_move(payload) is None


def test_intensity_and_duration_are_clamped_not_trusted():
    normalized = normalize_move({"gesture": "dance", "intensity": 99, "duration": 999})
    step = normalized["steps"][0]
    assert step["intensity"] == pytest.approx(1.35)
    assert step["duration"] == pytest.approx(6.0)
    normalized = normalize_move({"gesture": "dance", "intensity": -5})
    assert normalized["steps"][0]["intensity"] == pytest.approx(0.35)


def test_fallback_move_is_randomised_per_emotion():
    rng = random.Random(21)
    picks = {fallback_move("happy", rng)["steps"][0]["gesture"] for _ in range(40)}
    assert len(picks) > 1, "the fallback always plays the same gesture"
    assert normalize_move(fallback_move("thinking")) is not None


def test_ai_gesture_actually_moves_the_arm():
    controller = MotionController(random.Random(17))
    controller.play({"steps": [{"gesture": "wave", "intensity": 1.0, "duration": 2.0}]})
    lowest = min(controller.tick(1 / 30).arm_r for _ in range(40))
    assert lowest < -40.0  # the right arm really lifts


# ------------------------------------------------------------------ body render


def test_full_body_canvas_has_legs_arms_and_feet():
    artist = FullBodyCharacter()
    image = artist.frame(Pose())
    assert (image.width(), image.height()) == (DESIGN_WIDTH, DESIGN_HEIGHT)
    assert image.pixelColor(0, 0).alpha() == 0  # transparent corners
    # feet near the floor line are painted (shoes)
    shoe_rows = [
        y
        for y in range(int(GROUND) - 14, min(DESIGN_HEIGHT, int(GROUND) + 12))
        if any(image.pixelColor(x, y).alpha() > 40 for x in range(70, 150))
    ]
    assert shoe_rows, "no shoes painted at the floor line"

    # Both arms are painted: at least two separate opaque runs on a row that
    # crosses the elbows (left arm, torso, right arm).
    def runs(y: int) -> int:
        count = 0
        previous = False
        for x in range(DESIGN_WIDTH):
            opaque = image.pixelColor(x, y).alpha() > 40
            if opaque and not previous:
                count += 1
            previous = opaque
        return count

    # sample below the sleeves, where both bare forearms are separate from
    # the torso (the sleeves themselves intentionally merge into the shoulder)
    assert runs(int(skeleton(Pose()).wrist_l.y()) - 18) >= 3, (
        "arms are missing from the render"
    )


def test_skeleton_keeps_feet_on_the_ground_for_every_pose():
    artist = FullBodyCharacter()
    for pose in (
        Pose(),
        Pose(leg_l=20, leg_r=-20, knee_l=30),
        Pose(crouch=40, knee_l=80, knee_r=80),
        Pose(bounce=-20),
    ):
        joints = skeleton(pose)
        del joints  # skeleton() itself is pose space; the renderer grounds it
        image = artist.frame(pose)
        bottom = max(
            y
            for y in range(DESIGN_HEIGHT)
            if any(
                image.pixelColor(x, y).alpha() > 30 for x in range(0, DESIGN_WIDTH, 3)
            )
        )
        assert abs(bottom - GROUND) <= 26


def test_walking_alternates_the_legs():
    controller = MotionController(random.Random(23))
    controller.play_name("walk_right")
    angles = []
    for _ in range(90):
        pose = controller.tick(1 / 30)
        angles.append(pose.leg_l - pose.leg_r)
    assert max(angles) > 8.0
    assert min(angles) < -8.0


def test_face_follows_emotion_parameters():
    artist = FullBodyCharacter()
    neutral = artist.frame(Pose(smile=0.0, mouth=0.0, eye_open=1.0))
    laughing = artist.frame(Pose(smile=1.0, mouth=0.9, squint=0.7, blush=0.8))
    sleepy = artist.frame(Pose(eye_open=0.0))
    assert neutral != laughing
    assert neutral != sleepy

    # Closed eyes leave no green iris behind: count strongly green pixels in
    # the eye band (the iris is the only strongly green thing on the face).
    def iris_pixels(image):
        count = 0
        for x in range(40, 180):
            for y in range(120, 160):
                colour = image.pixelColor(x, y)
                if (
                    colour.alpha() > 150
                    and colour.green() > colour.red() + 10
                    and colour.green() > colour.blue() + 10
                ):
                    count += 1
        return count

    assert iris_pixels(neutral) > 80
    assert iris_pixels(sleepy) == 0


def test_portrait_crop_returns_a_square_face_image():
    artist = FullBodyCharacter()
    face = artist.portrait(96)
    assert (face.width(), face.height()) == (96, 96)
    painted = sum(
        face.pixelColor(x, y).alpha() > 40
        for x in range(0, 96, 2)
        for y in range(0, 96, 2)
    )
    assert painted > 700  # the head fills most of the crop
    assert face.pixelColor(48, 52).alpha() > 0  # nose/face centre is painted
    full = artist.portrait(96, crop="full")
    assert (full.width(), full.height()) == (96, 96)


def test_render_is_cached_and_matches_between_calls():
    artist = FullBodyCharacter()
    pose = Pose(smile=0.5)
    first = artist.frame(pose)
    second = artist.frame(pose)
    assert first is second  # memo cache
    other = artist.frame(Pose(smile=0.6))
    assert other is not first


def test_draw_fills_the_requested_rect():
    artist = FullBodyCharacter()
    canvas = QImage(140, 340, QImage.Format_ARGB32_Premultiplied)
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    from PyQt5.QtCore import QRectF

    artist.draw(painter, Pose(), target=QRectF(canvas.rect()))
    painter.end()
    opaque = sum(
        canvas.pixelColor(x, y).alpha() > 20
        for x in range(0, canvas.width(), 2)
        for y in range(0, canvas.height(), 2)
    )
    assert opaque > 200


# --------------------------------------------------------------------- pet GUI


def test_pet_can_use_the_full_body_renderer(qapp):
    """The drawn body stays fully functional as an explicit style choice."""
    from nora.nora_pet import NoraPet

    pet = NoraPet(rng=random.Random(2))
    pet._timer.stop()
    pet.set_appearance({"character_style": "body"})
    assert pet.character_style == "body"
    assert (pet.width(), pet.height()) == (132, 312)
    pet._tick_body()
    pose = pet.current_pose()
    assert pose is not None and isinstance(pose, Pose)
    assert not pet.grab().isNull()
    pet.shutdown()


def test_pet_perform_move_validates_and_falls_back(qapp):
    from nora.nora_pet import NoraPet

    pet = NoraPet(rng=random.Random(4))
    pet._timer.stop()
    assert pet.perform_move({"gesture": "wave"}) is True
    assert pet.perform_move({"gesture": "not_a_gesture"}) is True  # falls back
    assert pet.perform_move({"gesture": "not_a_gesture"}, fallback=False) is False
    assert pet.perform_move(None, fallback=False) is False
    pet.shutdown()


def test_pose_only_advances_for_the_body_renderer(qapp):
    from nora.nora_pet import NoraPet

    pet = NoraPet(rng=random.Random(6))
    pet._timer.stop()
    pet.set_appearance({"character_style": "pixel"})
    pet._tick_body()
    assert pet.current_pose() is None
    pet.shutdown()


# ------------------------------------------------------------- chat application


def test_chat_window_is_a_normal_large_centred_app(qapp, tmp_path):
    from nora.nora_ui import NoraApp, NoraOptions

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    window = app.chat_window
    flags = window.windowFlags()
    # Qt.Tool is a *window type* that shares the Window bit: compare the type
    # mask instead of doing a naive bitwise AND.
    assert (flags & Qt.WindowType_Mask) == Qt.Window
    assert not (flags & Qt.WindowStaysOnTopHint)
    app.show_chat()
    qapp.processEvents()
    assert window.width() >= 800 and window.height() >= 600
    screen = qapp.primaryScreen().availableGeometry()
    assert abs(window.geometry().center().x() - screen.center().x()) < 80
    assert abs(window.geometry().center().y() - screen.center().y()) < 80
    app.shutdown()


def test_closing_the_panel_hides_it_but_keeps_nora_alive(qapp, tmp_path):
    from nora.nora_ui import NoraApp, NoraOptions

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.show_chat()
    qapp.processEvents()
    app.chat_window.close()
    qapp.processEvents()
    assert not app.chat_window.isVisible()
    assert not app._closing
    app.shutdown()


def test_bubbles_are_wide_enough_for_a_desktop_window(qapp):
    from nora.nora_glass import BUBBLE_LABEL_MAX, GlassBubble

    bubble = GlassBubble("uzun bir mesaj " * 12, "bot")
    assert bubble.label.maximumWidth() == BUBBLE_LABEL_MAX
    assert BUBBLE_LABEL_MAX >= 400


def test_header_avatar_uses_the_same_character(qapp):
    from nora.nora_glass import AvatarDot

    dot = AvatarDot()
    dot.set_appearance({"hair_color": "#8a5f3f", "eye_color": "yesil"})
    assert dot._pixmap is not None and not dot._pixmap.isNull()
    assert dot._pixmap.width() == dot._pixmap.height()


def test_ai_move_reaches_the_pet(qapp, tmp_path):
    from nora.nora_brain import ChatReply
    from nora.nora_ui import NoraApp, NoraOptions

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    reply = ChatReply(
        "Selam!", "happy", move={"steps": [{"gesture": "wave", "intensity": 1.0}]}
    )
    app._apply_reply_motion(reply)
    if app.pet.character_style == "pixel":
        assert app.pet.state is not None
    elif app.pet.character_style == "sprite":
        # the illustrated character "performs" the move as a timed pose
        assert app.pet._sprite_artist.active_sprite() is not None
    else:
        assert app.pet._motion.busy or app.pet._motion.sustained == "wave"
    app.shutdown()


def test_invalid_ai_move_falls_back_to_emotional_body_language(qapp, tmp_path):
    from nora.nora_brain import ChatReply
    from nora.nora_ui import NoraApp, NoraOptions

    app = NoraApp(
        NoraOptions(
            wake_word=False, tts=False, proactive=False, offline=True, data_dir=tmp_path
        )
    )
    app.pet._timer.stop()
    app.pet.set_emotion("sad")
    app._apply_reply_motion(ChatReply("offff", "sad", move={"gesture": "nope"}))
    if app.pet.character_style in {"pixel", "sprite"}:
        assert app.pet.state is not None
    else:
        assert app.pet._motion.busy or app.pet._motion.sustained is not None
    app.shutdown()


def test_store_defaults_to_the_8_bit_character(tmp_path):
    from nora.nora_store import NoraStore

    store = NoraStore(tmp_path / "state.json")
    assert store.preference("character_style") == "pixel"
    # every style is still selectable, and a bogus one is refused
    for style in ("body", "realistic", "pixel"):
        store.set_preference("character_style", style)
        assert NoraStore(tmp_path / "state.json").preference("character_style") == style
    with pytest.raises(ValueError):
        store.set_preference("character_style", "anime")


# --------------------------------------------------------------- prompt wiring


def test_system_prompt_offers_the_move_tag_and_every_gesture():
    from nora.nora_personality import SYSTEM_PROMPT

    assert "[MOVE:" in SYSTEM_PROMPT
    for name in ("wave", "shrug", "tilt_head", "dance", "stretch", "bow"):
        assert name in SYSTEM_PROMPT
    # the character is described as a full body, not a chibi sprite
    assert "kolların" in SYSTEM_PROMPT
    assert "8-bit" not in SYSTEM_PROMPT


def test_move_tag_is_stripped_from_the_visible_text():
    from nora.nora_personality import parse_response

    raw = (
        "Tabii senpai! "
        '[CMD:{"command":"system_info"}] '
        '[MOVE:{"gesture":"shrug","intensity":0.7}] '
        "[EMO:smug]"
    )
    text, emotion, command, move = parse_response(raw)
    assert text == "Tabii senpai!"
    assert "[MOVE:" not in text
    assert emotion == "smug"
    assert command == {"command": "system_info"}
    assert move == {"gesture": "shrug", "intensity": 0.7}


def test_malformed_move_tag_is_ignored_without_breaking_the_reply():
    from nora.nora_personality import parse_response

    text, emotion, command, move = parse_response("Heh [MOVE:{bozuk json}] [EMO:happy]")
    assert move is None
    assert command is None
    assert emotion == "happy"
    assert text.startswith("Heh")


def test_brain_reply_carries_the_move():
    from nora.nora_brain import ChatReply

    reply = ChatReply("x", "happy", move={"gesture": "wave"})
    assert reply.move == {"gesture": "wave"}
    assert ChatReply("x").move is None


# ------------------------------------------------------------------- docs/assets


def test_reference_character_palette_is_used():
    from nora.nora_body import DEFAULT_EYE, DEFAULT_HAIR, OUTFITS, SUPPORTED_EYE_COLORS

    # caramel/light-brown hair and a green-leaning eye, as in the reference art
    assert DEFAULT_HAIR.lower() in {"#8a5f3f", "#7d5a44"}
    assert DEFAULT_EYE in SUPPORTED_EYE_COLORS.values()
    assert OUTFITS["cream"]["main"].lower() == "#f6efe2"  # turtleneck


def test_design_space_is_tall_enough_for_a_full_body():
    assert DESIGN_HEIGHT > DESIGN_WIDTH * 2
    assert math.isclose(GROUND, DESIGN_HEIGHT - 14, abs_tol=1.0)


def test_module_has_no_hardcoded_paths():
    source = Path("nora/nora_body.py").read_text(encoding="utf-8")
    assert "C:\\" not in source
    assert "/home/" not in source
