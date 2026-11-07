"""Small application entry point: python main.py (or python -m nora.main)."""

from __future__ import annotations

import argparse
import logging
import os
import signal

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from . import __version__
from .nora_ui import NoraApp, NoraOptions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nora · masaüstü asistanı")
    parser.add_argument(
        "--no-wake-word", action="store_true", help="Sürekli mikrofon dinlemeyi kapat"
    )
    parser.add_argument("--no-tts", action="store_true", help="Sesli yanıtları kapat")
    parser.add_argument(
        "--no-proactive", action="store_true", help="Kendi kendine konuşmayı kapat"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Groq'a bağlanma; temel komutlar çalışır"
    )
    parser.add_argument("--version", action="version", version=f"Nora {__version__}")
    args = parser.parse_args(argv)
    log_level = getattr(
        logging, os.getenv("NORA_LOG_LEVEL", "INFO").upper(), logging.INFO
    )
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("comtypes").setLevel(logging.WARNING)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication([])
    app.setApplicationName("Nora")
    app.setOrganizationName("Nora")
    app.setQuitOnLastWindowClosed(False)
    options = NoraOptions(
        wake_word=False if args.no_wake_word else None,
        tts=False if args.no_tts else None,
        proactive=False if args.no_proactive else None,
        offline=args.offline,
    )
    nora = NoraApp(options)
    nora.start()
    signal.signal(signal.SIGINT, lambda *_: nora.shutdown())
    # Let Python deliver SIGINT while the Qt event loop is running.
    heartbeat = QTimer()
    heartbeat.start(250)
    heartbeat.timeout.connect(lambda: None)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
