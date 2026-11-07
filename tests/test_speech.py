import pytest

from nora.nora_commands import parse_direct_command
from nora.nora_speech import (
    SttCandidate,
    choose_transcript,
    google_candidates,
    repair_transcript,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Hey Nova, ikinci monitöre geç", "Hey Nora, ikinci monitöre geç"),
        ("hey no ra uyu", "Hey Nora, uyu"),
        ("Hey Noura, dans et", "Hey Nora, dans et"),
        ("Nora, uyu", "Hey Nora, uyu"),
        ("uyu, nora", "Hey Nora, uyu"),
        ("nova uyu", "uyu"),
        ("no ra zıpla", "zıpla"),
    ],
)
def test_spoken_name_repair_in_explicit_or_safe_bounded_context(text, expected):
    repair = repair_transcript(text, command_parser=parse_direct_command)
    assert repair.text == expected
    assert parse_direct_command(repair.text) is not None


@pytest.mark.parametrize(
    "text",
    [
        "nova nasılsın",
        "Nova hakkında konuşalım",
        "normal uyu",
        "hey normal uyu",
        "not al: Nora",
        "nova bilgisayarı kapat",
        "nova yerel ses modu",
        "noranın adı ne",
    ],
)
def test_free_text_and_sensitive_bare_commands_are_not_rewritten(text):
    repair = repair_transcript(text, command_parser=parse_direct_command)
    assert repair.text == text
    assert not repair.address_corrected


def test_explicit_address_repair_preserves_note_payload():
    repair = repair_transcript(
        "hey nova not al: Nora bugün kahve içti", command_parser=parse_direct_command
    )
    assert repair.text == "Hey Nora, not al: Nora bugün kahve içti"
    assert repair.address_corrected
    assert "Nora bugün kahve içti" in repair.text


def test_google_candidates_are_bounded_and_confidence_is_validated():
    raw = {
        "results": [
            {
                "alternatives": [
                    {"transcript": " uyu ", "confidence": 0.9},
                    {"transcript": "", "confidence": 2},
                    {"transcript": "dur", "confidence": "bad"},
                ]
            }
        ]
    }
    candidates = google_candidates(raw)
    assert candidates == [SttCandidate("uyu", 0.9), SttCandidate("dur", None)]


def test_alternative_rerank_is_conservative():
    candidates = [SttCandidate("bugün hava nasıl", 0.95), SttCandidate("uyu", 0.9)]
    assert choose_transcript(candidates, command_parser=parse_direct_command).text == (
        "bugün hava nasıl"
    )
    candidates = [SttCandidate("ııı", 0.4), SttCandidate("hey nova uyu", 0.9)]
    repair = choose_transcript(candidates, command_parser=parse_direct_command)
    assert repair.text == "Hey Nora, uyu"
    assert repair.selected_alternative == 1
    # A first-ranked sensitive command is never overridden by a movement guess.
    candidates = [
        SttCandidate("hey nora yerel ses modu", 0.9),
        SttCandidate("hey nora uyu", 0.99),
    ]
    assert choose_transcript(candidates, command_parser=parse_direct_command).text == (
        "Hey Nora, yerel ses modu"
    )


def test_canonical_address_normalization_does_not_add_noise():
    repair = repair_transcript("hey nora uyu", command_parser=parse_direct_command)
    assert repair.text == "Hey Nora, uyu"
    assert not repair.address_corrected
    assert repair.notice() == ""
