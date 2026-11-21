"""Bounded, preview-first file discovery and reversible organization.

Only standard user folders are exposed. No deletion, overwriting, executable
launching, arbitrary destination path or shell expansion is supported.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from PyQt5.QtCore import QStandardPaths

from .nora_personality import FILE_EXTENSIONS


class NoraFiles:
    LOCATIONS = {
        "downloads": QStandardPaths.DownloadLocation,
        "documents": QStandardPaths.DocumentsLocation,
        "desktop": QStandardPaths.DesktopLocation,
        "pictures": QStandardPaths.PicturesLocation,
        "music": QStandardPaths.MusicLocation,
        "videos": QStandardPaths.MoviesLocation,
    }
    LABELS = {
        "downloads": "İndirilenler",
        "documents": "Belgeler",
        "desktop": "Masaüstü",
        "pictures": "Resimler",
        "music": "Müzik",
        "videos": "Videolar",
        "home": "Ana klasör",
    }

    def __init__(self) -> None:
        self._results: list[Path] = []
        self._last_move: list[tuple[Path, Path]] = []

    def root(self, name: str) -> Path:
        if name == "home":
            return Path.home().resolve()
        if name not in self.LOCATIONS:
            raise ValueError("Bu klasör desteklenmiyor.")
        location = QStandardPaths.writableLocation(self.LOCATIONS[name])
        fallback = {
            "downloads": "Downloads",
            "documents": "Documents",
            "desktop": "Desktop",
            "pictures": "Pictures",
            "music": "Music",
            "videos": "Videos",
        }[name]
        return (Path(location) if location else Path.home() / fallback).resolve()

    def find(
        self,
        query: str,
        directory: str = "downloads",
        extension: str = "",
        limit: int = 10,
    ) -> str:
        if (
            not query.strip()
            or len(query) > 100
            or any(part in query for part in ("/", "\\", ".."))
        ):
            raise ValueError("Dosya adı parçası kullan; yol veya .. kullanma.")
        if extension and extension not in FILE_EXTENSIONS:
            raise ValueError("Bu dosya türü desteklenmiyor.")
        root = self.root(directory)
        if not root.is_dir():
            return f"{self.LABELS[directory]} klasörü bulunamadı senpai."
        needle = query.translate(str.maketrans("Iİ", "ıi")).casefold()
        matches = []
        visited = 0
        deadline = time.monotonic() + 3
        for path in root.rglob("*"):
            visited += 1
            if visited > 10000 or time.monotonic() > deadline:
                break
            try:
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or any(
                        part.startswith(".") for part in path.relative_to(root).parts
                    )
                ):
                    continue
                if extension and path.suffix.lower() != "." + extension:
                    continue
                if needle in path.name.translate(str.maketrans("Iİ", "ıi")).casefold():
                    matches.append((path.stat().st_mtime, path.resolve()))
            except OSError:
                continue
        matches.sort(key=lambda item: (-item[0], str(item[1])))
        self._results = [path for _, path in matches[: max(1, min(limit, 20))]]
        if not self._results:
            return f"{self.LABELS[directory]} içinde '{query}' bulunamadı senpai."
        lines = [f"📁 {self.LABELS[directory]} · en yeni eşleşmeler"]
        for index, path in enumerate(self._results, 1):
            stamp = time.strftime(
                "%d.%m.%Y %H:%M", time.localtime(path.stat().st_mtime)
            )
            lines.append(f"{index}. {path.name} · {stamp}")
        lines.append(
            "Taşımak için: '1 numaralı dosyayı Belgeler'e taşı' de. Önce önizleme ve onay gösteririm."
        )
        if visited > 10000 or time.monotonic() > deadline:
            lines.append(
                "Not: Büyük klasörde tarama sınırı nedeniyle ilk bölüm tarandı."
            )
        return "\n".join(lines)

    def preview_move(
        self, selection: list[int], destination: str, folder: str = "Nora Düzenli"
    ) -> tuple[list[tuple[Path, Path]], list[str]]:
        if not self._results:
            raise ValueError(
                "Önce dosya ara senpai; taşıyacağım dosyaları tahmin etmem."
            )
        if not 1 <= len(selection) <= 20 or any(
            not 1 <= index <= len(self._results) for index in selection
        ):
            raise ValueError("Dosya arama sonuçlarındaki geçerli numaraları seç.")
        if (
            any(char in folder for char in ("/", "\\", ".."))
            or folder.startswith(".")
            or not folder.strip()
        ):
            raise ValueError("Hedef tek bir güvenli klasör adı olmalı.")
        root = self.root(destination)
        target = root / folder.strip()
        if target.is_symlink() or (target.exists() and not target.is_dir()):
            raise ValueError("Hedef klasör güvenli değil.")
        moves, conflicts = [], []
        for index in dict.fromkeys(selection):
            source = self._results[index - 1].resolve()
            allowed = any(
                source.is_relative_to(self.root(name))
                for name in (*self.LOCATIONS, "home")
            )
            if source.is_symlink() or not source.is_file() or not allowed:
                conflicts.append(
                    f"{source.name}: kaynak artık güvenli/bir dosya değil."
                )
                continue
            destination_path = target / source.name
            if destination_path.exists() and source == destination_path.resolve():
                conflicts.append(f"{source.name}: zaten hedefte.")
            elif destination_path.exists():
                conflicts.append(
                    f"{source.name}: hedefte aynı ad var; üzerine yazılmayacak."
                )
            else:
                moves.append((source, destination_path))
        return moves, conflicts

    def move(
        self, selection: list[int], destination: str, folder: str = "Nora Düzenli"
    ) -> str:
        moves, conflicts = self.preview_move(selection, destination, folder)
        if not moves:
            return "Taşınacak güvenli dosya yok. " + " ".join(conflicts)
        moves[0][1].parent.mkdir(parents=True, exist_ok=True)
        moved = []
        for source, target in moves:
            try:
                if target.exists() or source.is_symlink() or not source.is_file():
                    conflicts.append(f"{source.name}: değişmiş; atlandı.")
                    continue
                shutil.move(str(source), str(target))
                moved.append((source, target))
            except OSError:
                conflicts.append(f"{source.name}: taşınamadı; izinleri kontrol et.")
        self._last_move = moved
        lines = [
            f"{len(moved)} dosyayı {moves[0][1].parent} klasörüne taşıdım. Dosyalar silinmedi; 'dosya taşımayı geri al' diyebilirsin. 📁"
        ]
        lines.extend(conflicts)
        return "\n".join(lines)

    def undo(self) -> str:
        restored, failed = 0, 0
        for original, current in reversed(self._last_move):
            try:
                if (
                    current.is_file()
                    and not current.is_symlink()
                    and not original.exists()
                ):
                    shutil.move(str(current), str(original))
                    restored += 1
                else:
                    failed += 1
            except OSError:
                failed += 1
        self._last_move.clear()
        return f"{restored} taşımayı geri aldım senpai." + (
            f" {failed} dosya değişmiş/erişilemiyor; üzerine yazmadım."
            if failed
            else ""
        )
