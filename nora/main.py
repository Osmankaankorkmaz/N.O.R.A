"""Small application entry point: python main.py (or python -m nora.main)."""

from __future__ import annotations

import argparse
import logging
import os
import signal

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Nora · masaüstü asistanı")
    parser.add_argument(
        "--no-wake-word",
        action="store_true",
        help="Yerel Hey Nora bekçisini kapat; yalnızca 🎤 dinler",
    )
    parser.add_argument("--no-tts", action="store_true", help="Sesli yanıtları kapat")
    parser.add_argument(
        "--no-proactive", action="store_true", help="Kendi kendine konuşmayı kapat"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Groq'a bağlanma; temel komutlar çalışır"
    )
    parser.add_argument(
        "--data-dir",
        help="Kalıcı ayar/not/model klasörü (varsayılan: kullanıcı veri dizini)",
    )
    parser.add_argument("--version", action="version", version=f"Nora {__version__}")
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="GUI/mikrofon/ağ açmadan kurulum teşhisi; zorunlu eksiklerde çıkış kodu 1",
    )
    parser.add_argument(
        "--check",
        action="append",
        choices=("local", "embeddings", "chat", "piper"),
        default=[],
        help="--doctor ile bir özelliğin paket/model dosyalarını da denetle (tekrarlanabilir)",
    )
    parser.add_argument(
        "--json", action="store_true", help="--doctor raporunu JSON yazdır"
    )
    args = parser.parse_args(argv)
    if args.check and not args.doctor:
        parser.error("--check yalnızca --doctor ile kullanılır")
    if args.json and not args.doctor:
        parser.error("--json yalnızca --doctor ile kullanılır")
    if args.doctor:
        # Keep headless diagnostics usable even when PyQt/PortAudio is broken.
        from .nora_diagnostics import format_report, run_diagnostics

        checks = run_diagnostics(args.data_dir, args.check)
        print(format_report(checks, as_json=args.json))
        return 1 if any(check.status == "fail" for check in checks) else 0

    from PyQt5.QtCore import Qt, QTimer
    from PyQt5.QtWidgets import QApplication

    from .nora_ui import NoraApp, NoraOptions

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
        data_dir=args.data_dir,
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
