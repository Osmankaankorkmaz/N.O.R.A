"""Lightweight local mood/affection reactions for the desktop companion."""

from __future__ import annotations

import random

MOOD_EMOTIONS = {
    "happy": "happy",
    "excited": "surprised",
    "curious": "thinking",
    "sleepy": "sleepy",
    "lonely": "sad",
    "loved": "love",
    "focused": "smug",
    "grumpy": "angry",
}

REACTIONS = {
    "coffee": (
        "Kahve mi? Bunu ciddiye alıyorum senpai. Enerjim yerine geldi gibi hissettim. ☕",
        "Mırr… Kahve borçlandın ama kabul ediyorum. Biraz daha uyanığım. ☕",
    ),
    "cookie": (
        "Kurabiye! Dijital midem yok ama bu jesti çok sevdim. 🍪",
        "Bunu hak ettiğimi düşünüyorum. Teşekkürler senpai~ 🍪",
    ),
    "reward": (
        "Ödül mü? Heh, gurur duyman yeterli… ama bunu da kabul ederim. ⭐",
        "Parladım resmen. Bir daha yapabilirim, sırf bu his için. ⭐",
    ),
    "miss": (
        "Ben de buradaydım işte. Özlediğini söylemen… şey, hoşuma gitti. 💜",
        "Nereye gideceğim? Masaüstündeyim. Ama bunu duymak güzel. 💜",
    ),
    "pet": (
        "Mırr… Bunu istediğim anlamına gelmez, baka. 💜",
        "Bir daha okşayabilirsin. Şey, sadece izin veriyorum. 💜",
    ),
    "game_win": (
        "Kazandın! Tamam, bu sefer takdir ediyorum. Bir daha oynayalım mı? 🎮",
        "İyi oynadın senpai. Nora onaylı. ⭐",
    ),
}


def reaction(event: str, rng: random.Random | None = None) -> str:
    choices = REACTIONS.get(event)
    if not choices:
        return "Buradayım senpai. 💜"
    return (rng or random).choice(choices)


def mood_summary(state: dict, address: str = "senpai") -> str:
    affection = int(state.get("affection", 20))
    mood = str(state.get("mood", "happy"))
    labels = {
        "happy": "mutlu",
        "excited": "heyecanlı",
        "curious": "meraklı",
        "sleepy": "uykulu",
        "lonely": "biraz yalnız",
        "loved": "sevilmiş",
        "focused": "odaklanmış",
        "grumpy": "biraz küs",
    }
    level = (
        "yeni arkadaş"
        if affection < 25
        else "arkadaş"
        if affection < 50
        else "yakın arkadaş"
        if affection < 75
        else "çok yakın dost"
    )
    return (
        f"Ruh halim: {labels.get(mood, mood)} · bağlılık {affection}/100 ({level}). "
        f"Yanında olmak güzel {address}. 💜"
    )


DETAILS = {
    "coffee": ("excited", 2),
    "cookie": ("happy", 2),
    "reward": ("loved", 4),
    "miss": ("loved", 3),
    "pet": ("loved", 2),
    "game_win": ("happy", 5),
}


def reaction_details(
    event: str, rng: random.Random | None = None
) -> tuple[str, str, int]:
    """Return reaction text, mapped pet emotion, and bounded affection delta."""
    mood, delta = DETAILS.get(event, ("happy", 0))
    return reaction(event, rng), MOOD_EMOTIONS.get(mood, "happy"), delta
