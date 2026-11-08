"""Safe JSON command-pack plugins. Plugins never execute Python or shell code.

A manifest contains only metadata and bounded phrases mapped to the same safe
routine steps Nora already validates. Importing and enabling are explicit user
actions; running a pack always goes through the routine confirmation dialog.
Built-in deterministic commands cannot be shadowed by a plugin.
"""

from __future__ import annotations

import json
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .nora_commands import normalize_text, parse_direct_command
from .nora_personality import CommandError, _routine_step

MAX_PLUGINS = 20
MAX_COMMANDS = 12
MAX_FILE_BYTES = 64 * 1024
_ID_RE = re.compile(r"[a-z][a-z0-9-]{1,39}")
_VERSION_RE = re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}")


@dataclass(frozen=True)
class PluginCommand:
    name: str
    phrase: str
    reply: str
    steps: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    description: str
    commands: tuple[PluginCommand, ...]


def _string(value: Any, limit: int, *, empty: bool = False) -> str:
    if (
        not isinstance(value, str)
        or len(value) > limit
        or (not empty and not value.strip())
    ):
        raise CommandError(f"Eklenti metni en fazla {limit} karakter olmalı.")
    return value.strip()


def validate_manifest(data: Any) -> PluginManifest:
    if not isinstance(data, dict) or set(data) != {
        "schema",
        "id",
        "name",
        "version",
        "description",
        "commands",
    }:
        raise CommandError(
            "Eklenti biçimi geçersiz; yalnızca schema/id/name/version/description/commands alanları kullanılır."
        )
    if data["schema"] != 1 or isinstance(data["schema"], bool):
        raise CommandError("Eklenti schema sürümü 1 olmalı.")
    plugin_id = _string(data["id"], 40)
    if not _ID_RE.fullmatch(plugin_id):
        raise CommandError(
            "Eklenti kimliği küçük harf/rakam/tire içeren güvenli bir ad olmalı."
        )
    version = _string(data["version"], 20)
    if not _VERSION_RE.fullmatch(version):
        raise CommandError("Eklenti sürümü x.y.z olmalı.")
    raw_commands = data["commands"]
    if not isinstance(raw_commands, list) or not 1 <= len(raw_commands) <= MAX_COMMANDS:
        raise CommandError(f"Eklenti 1-{MAX_COMMANDS} komut içermeli.")
    commands = []
    phrases = set()
    names = set()
    for raw in raw_commands:
        if not isinstance(raw, dict) or set(raw) != {
            "name",
            "phrase",
            "reply",
            "steps",
        }:
            raise CommandError(
                "Eklenti komutu name/phrase/reply/steps alanları içermeli."
            )
        name = _string(raw["name"], 60)
        phrase = normalize_text(_string(raw["phrase"], 80))
        reply = _string(raw["reply"], 200, empty=True)
        steps = raw["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= 8:
            raise CommandError("Eklenti komutu 1-8 güvenli adım içermeli.")
        if parse_direct_command(phrase) is not None:
            raise CommandError("Eklenti yerleşik bir komutu gölgeleyemez.")
        if phrase in phrases or name.casefold() in names:
            raise CommandError("Eklenti içinde yinelenen komut/ifade var.")
        phrases.add(phrase)
        names.add(name.casefold())
        commands.append(
            PluginCommand(
                name, phrase, reply, tuple(_routine_step(step) for step in steps)
            )
        )
    return PluginManifest(
        plugin_id,
        _string(data["name"], 80),
        version,
        _string(data["description"], 300, empty=True),
        tuple(commands),
    )


class PluginRegistry:
    def __init__(self, directory: Path, store: Any) -> None:
        self.directory = Path(directory)
        self.store = store

    def _path(self, plugin_id: str) -> Path:
        if not _ID_RE.fullmatch(str(plugin_id)):
            raise CommandError("Geçersiz eklenti kimliği.")
        path = (self.directory / f"{plugin_id}.json").resolve()
        if path.parent != self.directory.resolve() or path.is_symlink():
            raise CommandError("Eklenti yolu güvenli değil.")
        return path

    def load_all(self) -> tuple[list[PluginManifest], list[str]]:
        manifests: list[PluginManifest] = []
        errors: list[str] = []
        if not self.directory.is_dir():
            return manifests, errors
        paths = sorted(self.directory.glob("*.json"))
        if len(paths) > MAX_PLUGINS:
            errors.append(
                f"Eklenti sınırı {MAX_PLUGINS}; fazla dosyalar güvenlik için yüklenmedi."
            )
            return manifests, errors
        seen_ids = set()
        for path in paths:
            try:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or path.stat().st_size > MAX_FILE_BYTES
                ):
                    raise CommandError(
                        "Eklenti dosyası güvenli boyutta normal bir JSON dosyası olmalı."
                    )
                manifest = validate_manifest(
                    json.loads(path.read_text(encoding="utf-8"))
                )
                if manifest.id != path.stem:
                    raise CommandError("Eklenti kimliği dosya adıyla eşleşmeli.")
                if manifest.id in seen_ids:
                    raise CommandError("Yinelenen eklenti kimliği.")
                seen_ids.add(manifest.id)
                manifests.append(manifest)
            except Exception as exc:
                errors.append(f"{path.name}: {exc}")
        return manifests, errors

    def enabled(self) -> list[PluginManifest]:
        enabled = set(self.store.enabled_plugins)
        return [manifest for manifest in self.load_all()[0] if manifest.id in enabled]

    def get(self, plugin_id: str) -> PluginManifest:
        path = self._path(plugin_id)
        if not path.is_file() or path.is_symlink():
            raise CommandError("Eklenti bulunamadı.")
        manifest = validate_manifest(json.loads(path.read_text(encoding="utf-8")))
        if manifest.id != plugin_id:
            raise CommandError("Eklenti kimliği dosya adıyla eşleşmeli.")
        return manifest

    def install(self, source: Path, *, overwrite: bool = False) -> PluginManifest:
        source = Path(source)
        if (
            source.is_symlink()
            or not source.is_file()
            or source.stat().st_size > MAX_FILE_BYTES
        ):
            raise CommandError(
                "Eklenti dosyası 64 KB altında normal bir JSON dosyası olmalı."
            )
        raw = json.loads(source.read_text(encoding="utf-8"))
        manifest = validate_manifest(raw)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(manifest.id)
        if target.exists() and not overwrite:
            raise CommandError(
                "Bu eklenti zaten kurulu; güncellemek için üzerine yazmayı onayla."
            )
        if (
            not target.exists()
            and len(list(self.directory.glob("*.json"))) >= MAX_PLUGINS
        ):
            raise CommandError(f"Eklenti sınırı {MAX_PLUGINS}.")
        existing, _errors = self.load_all()
        candidate_phrases = {command.phrase for command in manifest.commands}
        for other in existing:
            if other.id == manifest.id:
                continue
            overlap = candidate_phrases & {command.phrase for command in other.commands}
            if overlap:
                raise CommandError(
                    f"Eklenti ifadesi başka bir paketle çakışıyor ({other.id}): "
                    + ", ".join(sorted(overlap)[:3])
                )
        fd, temporary_name = tempfile.mkstemp(
            prefix=".plugin-", suffix=".tmp", dir=self.directory
        )
        temporary = Path(temporary_name)
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                json.dump(raw, handle, ensure_ascii=False, indent=2)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return manifest

    def delete(self, plugin_id: str) -> None:
        path = self._path(plugin_id)
        if path.is_file():
            path.unlink()
        self.store.set_plugin_enabled(plugin_id, False)

    def conflicts(self) -> dict[str, tuple[str, ...]]:
        owners: dict[str, list[str]] = {}
        for manifest in self.load_all()[0]:
            for command in manifest.commands:
                owners.setdefault(command.phrase, []).append(manifest.id)
        return {
            phrase: tuple(sorted(ids))
            for phrase, ids in owners.items()
            if len(set(ids)) > 1
        }

    def match(self, text: str) -> tuple[PluginManifest, PluginCommand] | None:
        phrase = normalize_text(text)
        enabled = self.enabled()
        conflicts = self.conflicts()
        if phrase in conflicts and any(
            command.phrase == phrase
            for manifest in enabled
            for command in manifest.commands
        ):
            raise CommandError(
                "Bu ifade birden fazla etkin eklentide çakışıyor; güvenlik için çalıştırmadım: "
                + ", ".join(conflicts[phrase])
            )
        for manifest in enabled:
            for command in manifest.commands:
                if command.phrase == phrase:
                    return manifest, command
        return None

    def command_steps(
        self, plugin_id: str, name: str
    ) -> tuple[PluginManifest, PluginCommand]:
        manifest = self.get(plugin_id)
        if manifest.id not in self.store.enabled_plugins:
            raise CommandError("Bu eklenti kapalı; önce açıkça etkinleştir.")
        conflicts = self.conflicts()
        for command in manifest.commands:
            if command.name.casefold() == str(name).casefold():
                if command.phrase in conflicts:
                    raise CommandError(
                        "Eklenti ifadesi başka paketlerle çakışıyor: "
                        + ", ".join(conflicts[command.phrase])
                    )
                return manifest, command
        raise CommandError("Eklenti komutu bulunamadı.")

    def listing(self) -> str:
        manifests, errors = self.load_all()
        enabled = set(self.store.enabled_plugins)
        lines = ["Eklentiler · JSON komut paketleri, Python çalıştırmaz 🧩"]
        if not manifests:
            lines.append(
                "Kurulu eklenti yok. Özellikler menüsünden JSON eklenti içe aktarabilirsin."
            )
        for manifest in manifests:
            state = "açık" if manifest.id in enabled else "kapalı"
            lines.append(
                f"• {manifest.id} · {manifest.name} v{manifest.version} · {state} · {len(manifest.commands)} komut"
            )
        conflicts = self.conflicts()
        if conflicts:
            lines.append(
                "Çakışan ifadeler (çalıştırılmaz):\n"
                + "\n".join(
                    f"• {phrase} → {', '.join(ids)}"
                    for phrase, ids in sorted(conflicts.items())[:5]
                )
            )
        if errors:
            lines.append("Okunamayan eklentiler:\n" + "\n".join(errors[:5]))
        return "\n".join(lines)
