"""Deterministic Turkish commands: these work without Groq or an internet connection.

Only an explicit, bounded command grammar is recognized here. Free-form chat is
still delegated to the model; arbitrary text never becomes a shell command.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any

from .nora_speech import normalize_spoken_address
from .nora_store import now_local

ORDINALS = {
    "birinci": 1,
    "bir": 1,
    "ikinci": 2,
    "iki": 2,
    "üçüncü": 3,
    "üç": 3,
    "dördüncü": 4,
    "dört": 4,
    "beşinci": 5,
    "beş": 5,
    "altıncı": 6,
    "altı": 6,
    "yedinci": 7,
    "yedi": 7,
    "sekizinci": 8,
    "sekiz": 8,
    "dokuzuncu": 9,
    "dokuz": 9,
    "onuncu": 10,
    "on": 10,
    "on birinci": 11,
    "on ikinci": 12,
    "on üçüncü": 13,
    "on dördüncü": 14,
    "on beşinci": 15,
    "on altıncı": 16,
}
WEEKDAYS = {
    "pazartesi": 0,
    "salı": 1,
    "çarşamba": 2,
    "perşembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}
ACTIONS = {
    "sleep": (
        "uyu",
        "uyur musun",
        "uyur",
        "uyku modu",
        "uyku moduna geç",
        "uyumaya başla",
        "biraz uyu",
        "uyu artık",
    ),
    "wake": ("uyan", "uyanır", "uyandır kendini", "uykudan çık", "ayağa kalk"),
    "walk": (
        "dolaş",
        "dolaşır mısın",
        "dolaşır",
        "yürü",
        "yürür müsün",
        "yürür",
        "gez",
        "dolaşmaya başla",
        "volta at",
        "sağa sola dolaş",
    ),
    "stop": (
        "dur",
        "olduğun yerde dur",
        "dolaşmayı durdur",
        "hareketi durdur",
        "bekle",
        "bekler",
        "durur",
        "hareketi kes",
    ),
    "jump": ("zıpla", "zıplar mısın", "zıplar", "bir zıpla", "hopla", "zıplama yap"),
    "dance": ("dans et", "dans eder misin", "dans eder", "oyna", "dans etmeye başla"),
    "sit": ("otur", "oturur", "biraz otur", "otursana"),
    "wave": ("selam ver", "el salla", "el sallar"),
    "yawn": ("esne", "esner", "bir esne"),
    "blink": ("göz kırp", "göz kırpar", "gözlerini kırp"),
}
ACTION_REPLIES = {
    "sleep": ("Uyku moduna geçiyorum senpai. z Z Z", "sleepy"),
    "wake": ("Uyandım senpai! Kahve hazır mı?", "happy"),
    "walk": ("Biraz dolaşıyorum. Ekranın kenarında görüşürüz~", "happy"),
    "stop": ("Tamam, olduğum yerde bekliyorum.", "happy"),
    "jump": ("Hop! İzle senpai~", "surprised"),
    "dance": ("Kedi dansı başlasın! Alay etme ama. 😼", "love"),
    "sit": ("Buraya oturdum senpai.", "smug"),
    "wave": (
        "Selam senpai~ El sallamak zorunda kaldım, sevinmiş falan değilim.",
        "happy",
    ),
    "yawn": ("Esnedim bile… Bu gece fazla kahve içtim galiba.", "sleepy"),
    "blink": ("Göz kırptım. Gördün mü, baka?", "smug"),
}


@dataclass(frozen=True)
class DirectCommand:
    command: dict[str, Any]
    reply: str = "Tamam senpai~"
    emotion: str = "happy"


def normalize_text(text: str) -> str:
    value = normalize_spoken_address(str(text))
    value = (
        unicodedata.normalize("NFKC", value)
        .translate(str.maketrans("Iİ", "ıi"))
        .lower()
        .strip()
    )
    value = re.sub(r"[^\w\s%#+=.:/-]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(?:hey\s+)?nora\s*[,!: -]*\s*", "", value)
    value = re.sub(r"^(?:lütfen|rica etsem)\s+", "", value).strip()
    value = re.sub(
        r"(?:\s+(?:lütfen|rica etsem|hadisene|bakalım|senpai|nora|olur mu|tamam mı|[.!?]))+$",
        "",
        value,
    ).strip()
    value = re.sub(
        r"\s+(?:abilir|ebilir|ır|ir|ur|ür)?\s*(?:mısın|misin|musun|müsün)$", "", value
    ).strip()
    return value


def _cmd(
    command_name: str,
    reply: str = "Tamam senpai~",
    emotion: str = "happy",
    **fields: Any,
) -> DirectCommand:
    return DirectCommand({"command": command_name, **fields}, reply, emotion)


def parse_due(text: str, now: datetime | None = None) -> tuple[datetime, str]:
    """Parse relative times, clock times and Turkish dates in the local timezone."""
    now = now or now_local()
    low = normalize_text(text)
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(saniye|dakika|saat|gün)\s*(?:sonra|sonrasına)", low
    )
    if match:
        amount = float(match.group(1).replace(",", "."))
        seconds = (
            amount
            * {"saniye": 1, "dakika": 60, "saat": 3600, "gün": 86400}[match.group(2)]
        )
        if not 1 <= seconds <= 31_536_000:
            raise ValueError("Hatırlatıcı süresi 1 saniye ile 1 yıl arasında olmalı.")
        return now + timedelta(seconds=seconds), "none"
    match = re.search(
        r"(?:(pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)\s+)?(?:saat\s+(\d{1,2})[.:](\d{2})|(\d{1,2}):(\d{2}))(?:\s*(?:de|da|te|ta))?",
        low,
    )
    recurrence = (
        "daily"
        if re.search(r"\bher gün\b", low)
        else "weekdays"
        if re.search(r"\bhafta içi\b", low)
        else "none"
    )
    weekday = None
    if match:
        hour, minute = (
            int(match.group(2) or match.group(4)),
            int(match.group(3) or match.group(5)),
        )
        if hour > 23 or minute > 59:
            raise ValueError("Saat 00:00-23:59 aralığında olmalı.")
        day = now.date()
        if re.search(r"\b(yarın|öbür gün)\b", low):
            day += timedelta(days=2 if "öbür gün" in low else 1)
        date_match = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?\b", low)
        if date_match:
            number_day, month = int(date_match.group(1)), int(date_match.group(2))
            year = int(date_match.group(3) or now.year)
            day = datetime(year, month, number_day).date()
            if not date_match.group(3) and day < now.date():
                day = datetime(year + 1, month, number_day).date()
        if match.group(1):
            weekday = WEEKDAYS[match.group(1)]
            day += timedelta(days=(weekday - day.weekday()) % 7)
            recurrence = (
                "weekly"
                if re.search(r"\bher\s+(?:hafta\s+)?" + match.group(1) + r"\b", low)
                else "none"
            )
        due = datetime.combine(day, time(hour, minute), tzinfo=now.tzinfo)
        if due <= now and not (date_match or weekday):
            due += timedelta(days=1)
        return due, recurrence
    raise ValueError(
        "Zamanı anlayamadım. Örnek: '10 dakika sonra su içmeyi hatırlat' veya 'yarın 10:00'da toplantıyı hatırlat'."
    )


def _strip_time(text: str) -> str:
    value = re.sub(
        r"\b(?:her\s+)?(?:gün|hafta içi|hafta|yarın|öbür gün|bugün|pazartesi|salı|çarşamba|perşembe|cuma|cumartesi|pazar)\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\b\d+(?:[.,]\d+)?\s*(?:saniye|dakika|saat|gün)\s*(?:sonra|sonrasına)\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\b\d{1,2}[./]\d{1,2}(?:[./]\d{4})?\b", "", value)
    value = re.sub(
        r"\b(?:saat\s*)?\d{1,2}[:.]\d{2}\s*(?:de|da|te|ta)?\b",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"^(?:bana\s+)?", "", value.strip())
    value = re.sub(
        r"\s*(?:hatırlat|hatırlatıcı kur|uyar)\s*[.!?]*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", value).strip(" ,:-") or "Hatırlatma zamanı senpai!"


def _appearance(low: str) -> DirectCommand | None:
    settings = {
        "gözlük tak": ("accessory", "glasses"),
        "kulaklık tak": ("accessory", "headphones"),
        "kurdele tak": ("accessory", "ribbon"),
        "aksesuarı çıkar": ("accessory", "none"),
        "klasik kıyafet": ("outfit", "classic"),
        "siyah elbise": ("outfit", "classic"),
        "beyaz saç": ("hair_color", "#f5f3f0"),
        "beyaz wolfcut": ("hair_color", "#f5f3f0"),
        "günlük kıyafet": ("outfit", "casual"),
        "gece kıyafeti": ("outfit", "night"),
        "tatlı mod": ("tone", "sweet"),
        "ciddi mod": ("tone", "serious"),
        "tsundere modu": ("tone", "tsundere"),
        "animasyonları kapat": ("animations", False),
        "animasyonları aç": ("animations", True),
        "kendiliğinden hareket etme": ("autonomous", False),
        "otonom hareketi kapat": ("autonomous", False),
        "otonom hareketi aç": ("autonomous", True),
        "çift tıklayınca oyun aç": ("double_click_action", "game"),
        "çift tıklayınca sohbet aç": ("double_click_action", "chat"),
        "yerel ses modu": ("stt_backend", "local"),
        "bulut ses modu": ("stt_backend", "google"),
    }
    if low in settings:
        key, value = settings[low]
        if key == "stt_backend":
            return _cmd("stt_backend", backend=value)
        return _cmd("settings", action="set", key=key, value=value)
    match = re.fullmatch(r"saç reng(?:i|ini)\s*(#[0-9a-f]{6})", low)
    if match:
        return _cmd("settings", action="set", key="hair_color", value=match.group(1))
    match = re.fullmatch(r"(?:ses hızı|konuşma hızı)\s*(\d+)", low)
    if match:
        return _cmd(
            "settings", action="set", key="speech_rate", value=int(match.group(1))
        )
    match = re.fullmatch(r"bana\s+(.+?)\s+(?:diye hitap et|de)", low)
    if match:
        return _cmd("settings", action="set", key="address", value=match.group(1)[:30])
    return None


def parse_direct_command(
    text: str, now: datetime | None = None
) -> DirectCommand | None:
    low = normalize_text(text)
    if not low or len(low) > 1000:
        return None
    # Monitor commands are matched before generic movement/chat.
    match = re.fullmatch(
        r"(?:(.+?)\s+)?(?:monitöre|monitör|ekrana|ekran)\s*(?:geç|geçer|git|gider|taşın|atla|dön|döner)",
        low,
    )
    if match:
        token = (match.group(1) or "").strip()
        token = re.sub(r"\s+(?:numaralı|numara|nolu)$", "", token).strip()
        target: Any = "next"
        if token in {"ana", "birincil", "primary"}:
            target = "primary"
        elif token in {"diğer", "sonraki", ""}:
            target = "next"
        elif token in {"önceki", "geri"}:
            target = "previous"
        elif token.isdigit() or re.fullmatch(r"\d+\.", token):
            target = int(token.rstrip("."))
        elif token in ORDINALS:
            target = ORDINALS[token]
        else:
            return None
        return _cmd(
            "move_monitor", "Monitörünü değiştiriyorum senpai~ 🖥️", target=target
        )
    match = re.fullmatch(
        r"(?:monitör|ekran)\s+(\d+)\s*(?:ye|ya|e|a)?\s*(?:geç|git|taşın)", low
    )
    if match:
        return _cmd("move_monitor", target=int(match.group(1)))
    for action, phrases in ACTIONS.items():
        if low in phrases:
            reply, emotion = ACTION_REPLIES[action]
            return _cmd("pet_action", reply, emotion, action=action)
    modes = {
        "çalışma modu": "focus",
        "odak modu": "focus",
        "odaklan": "focus",
        "oyun modu": "game",
        "sessiz mod": "quiet",
        "normal mod": "normal",
        "çalışma modundan çık": "normal",
        "oyun modundan çık": "normal",
    }
    if low in modes:
        return _cmd("mode", mode=modes[low])
    appearance = _appearance(low)
    if appearance:
        return appearance
    if low in {
        "hafızanda ne var",
        "hafızanı göster",
        "benim hakkımda ne biliyorsun",
        "kayıtlı bilgileri göster",
    }:
        return _cmd("memory", action="list")
    if low in {"hafızanı temizle", "benim hakkımdaki her şeyi unut"}:
        return _cmd("memory", action="clear")
    match = re.fullmatch(r"(?:bunu unut|şunu unut)\s*[:=-]?\s*(.+)", low)
    if match:
        return _cmd("memory", action="delete", key=match.group(1))
    match = re.fullmatch(
        r"(?:bunu hatırla|şunu hatırla|hafızana kaydet)\s*[:=-]?\s*(.+)", low
    )
    if match:
        value = match.group(1)
        parts = re.split(r"\s*[:=]\s*", value, maxsplit=1)
        key, value = (parts[0], parts[1]) if len(parts) == 2 else (value[:60], value)
        return _cmd(
            "memory",
            "Bunu açıkça kaydettim senpai; kendiliğinden sohbet kaydetmiyorum.",
            action="add",
            key=key,
            value=value,
        )
    if low in {
        "hatırlatıcılar",
        "hatırlatıcılarım",
        "hatırlatıcıları listele",
        "alarm listesi",
    }:
        return _cmd("reminder", action="list")
    match = re.fullmatch(r"(?:hatırlatıcı|alarm)\s+([\w-]+)\s*(?:iptal|sil)", low)
    if match:
        return _cmd("reminder", action="cancel", id=match.group(1))
    if re.search(r"(?:hatırlat|hatırlatıcı kur|uyar)$", low) and re.search(r"\d", low):
        try:
            due, recurrence = parse_due(low, now)
        except ValueError:
            return None
        return _cmd(
            "reminder",
            "Hatırlatıcıyı kalıcı olarak kaydediyorum. ⏰",
            action="add",
            text=_strip_time(low),
            due_at=due.isoformat(),
            recurrence=recurrence,
        )
    if low in {"görevler", "görevlerim", "yapılacaklar", "yapılacakları listele"}:
        return _cmd("task", action="list")
    match = re.fullmatch(r"(?:görev ekle|yapılacaklara ekle)\s*[:=-]?\s*(.+)", low)
    if match:
        return _cmd("task", action="add", text=match.group(1))
    match = re.fullmatch(
        r"([\w-]+)\s*(?:numaralı\s*)?görevi\s*(tamamla|bitir|sil|yeniden aç)", low
    )
    if match:
        action = {
            "tamamla": "complete",
            "bitir": "complete",
            "sil": "delete",
            "yeniden aç": "reopen",
        }[match.group(2)]
        return _cmd("task", action=action, id=match.group(1))
    match = re.fullmatch(r"([\w-]+)\s*(?:numaralı\s*)?notu görevlere çevir", low)
    if match:
        return _cmd("task", action="from_note", id=match.group(1))
    if low in {"bugünkü program", "bugün takvimde ne var", "bugünkü etkinlikler"}:
        return _cmd("calendar", action="today")
    if low in {"masaüstü düzenini kaydet", "pencere düzenini kaydet"}:
        return _cmd("desktop_layout", action="save", name="son")
    if low in {"masaüstü düzenini geri yükle", "pencereleri eski yerine koy"}:
        return _cmd("desktop_layout", action="restore", name="son")
    match = re.fullmatch(r"(.+?) düzenini kaydet", low)
    if match:
        return _cmd("desktop_layout", action="save", name=match.group(1))
    match = re.fullmatch(r"(.+?) düzenini geri yükle", low)
    if match:
        return _cmd("desktop_layout", action="restore", name=match.group(1))
    if low in {"bugün boş zamanım var mı", "boş zaman bul", "bugün boş zaman bul"}:
        return _cmd("calendar", action="free")
    match = re.fullmatch(r"bugün (\d+) dakika boş zaman bul", low)
    if match:
        return _cmd("calendar", action="free", duration_minutes=int(match.group(1)))
    if low in {"yaklaşan etkinlikler", "takvimim", "takvim listesi"}:
        return _cmd("calendar", action="upcoming")
    if low in {"rutinler", "rutinlerim", "rutinleri listele"}:
        return _cmd("routine", action="list")
    match = re.fullmatch(r"(.+?)\s+rutin(?:i|ini)?\s*(?:çalıştır|başlat|sil)", low)
    if match:
        action = "delete" if low.endswith("sil") else "run"
        return _cmd("routine", action=action, name=match.group(1))
    clipboard = {
        "panoyu özetle": "summarize",
        "panodaki metni özetle": "summarize",
        "panoyu düzenle": "rewrite",
        "panodaki metni düzenle": "rewrite",
        "panoyu biçimlendir": "format",
        "panoyu çevir": "translate",
        "panodaki metni çevir": "translate",
    }
    if low in clipboard:
        return _cmd("clipboard_help", action=clipboard[low])
    match = re.fullmatch(r"panoyu\s+(.+?)\s+çevir", low)
    if match:
        return _cmd(
            "clipboard_help", action="translate", target_language=match.group(1)
        )
    if low in {
        "ekrandaki yazıları oku",
        "ekran yazılarını oku",
        "ekrandaki yazıyı özetle",
        "ekranı ocr ile oku",
    }:
        return _cmd("screen_text")
    match = re.fullmatch(
        r"(?:indirilenlerde|belgelerde|masaüstünde)\s+(.+?)\s+(?:dosyalarını|dosyaları)?\s*(?:bul|ara)",
        low,
    )
    if match:
        directory = (
            "downloads"
            if low.startswith("indirilenlerde")
            else "documents"
            if low.startswith("belgelerde")
            else "desktop"
        )
        return _cmd("find_files", query=match.group(1), directory=directory)
    games = {
        "kelime oyunu": "start",
        "kelime oyunu başlat": "start",
        "oyunu başlat": "start",
        "kelime ipucu": "hint",
        "ipucu ver": "hint",
        "oyunun cevabı": "answer",
        "oyunu bitir": "stop",
        "oyunu durdur": "stop",
    }
    if low in games:
        action = games[low]
        return _cmd(
            "game",
            action=action,
            **({"answer": "__reveal__"} if action == "answer" else {}),
        )
    match = re.fullmatch(r"(?:kelime cevabım|cevabım|tahminim)\s*[:=-]?\s*(.+)", low)
    if match:
        return _cmd("game", action="answer", answer=match.group(1))
    match = re.fullmatch(
        r"([\d,\s]+)\s*numaralı\s*dosya(?:yı|ları|larını)?\s*(belgeler|indirilenler|masaüstü|resimler)(?:\s*(?:e|a|ye|ya))?\s*taşı",
        low,
    )
    if match:
        selection = [int(part) for part in re.findall(r"\d+", match.group(1))]
        destination = {
            "belgeler": "documents",
            "indirilenler": "downloads",
            "masaüstü": "desktop",
            "resimler": "pictures",
        }[match.group(2)]
        return _cmd("move_files", selection=selection, destination=destination)
    if low in {"dosya taşımayı geri al", "son taşımayı geri al"}:
        return _cmd("undo_files")
    match = re.fullmatch(r"([\w-]+)\s*(?:numaralı\s*)?notu sil", low)
    if match:
        return _cmd("note", action="delete", id=match.group(1))
    if low in {
        "sesli konuş",
        "sesli yanıtı aç",
        "sesli yanıtları aç",
        "sesli cevap ver",
        "konuşmaya başla",
    }:
        return _cmd("settings", action="set", key="tts", value=True)
    if low in {
        "sesli yanıtı kapat",
        "sesli yanıtları kapat",
        "sesli cevap verme",
        "sessiz konuş",
    }:
        return _cmd("settings", action="set", key="tts", value=False)
    if low in {"ses testi", "sesli yanıt testi", "ses durumu", "neden konuşmuyorsun"}:
        return _cmd("speech_test")
    if low in {
        "ses tanıma testi",
        "sesimi anlıyor musun",
        "dediklerimi anlıyor musun",
        "mikrofon tanıma testi",
    }:
        return _cmd("stt_test")
    if low in {"mikrofonu tamamen kapat", "hey nora bekçisini kapat"}:
        return _cmd("settings", action="set", key="wake_word", value=False)
    if low in {"hey nora bekçisini aç", "yerel mikrofon bekçisini aç"}:
        return _cmd("settings", action="set", key="wake_word", value=True)
    return None


def parse_direct_sequence(text: str) -> list[DirectCommand]:
    """At most four explicit commands joined by 've' or commas; never split chat."""
    parts = [
        part.strip()
        for part in re.split(r"\s+ve\s+|,", normalize_text(text))
        if part.strip()
    ]
    if not 2 <= len(parts) <= 4:
        return []
    commands = [parse_direct_command(part) for part in parts]
    return (
        [command for command in commands if command is not None]
        if all(commands)
        else []
    )
