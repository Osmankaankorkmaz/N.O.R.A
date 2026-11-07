"""A scrollable, keyboard-accessible settings panel for Nora's local preferences."""

from __future__ import annotations

from typing import Any, Callable

from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .nora_store import NoraStore


class NoraSettingsDialog(QDialog):
    def __init__(
        self,
        store: NoraStore,
        *,
        on_apply: Callable[[dict[str, Any]], None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.on_apply = on_apply
        self.fields: dict[str, QWidget] = {}
        self.setWindowTitle("Nora · Ayarlar")
        self.setMinimumSize(460, 560)
        self.setStyleSheet(
            "QDialog { background: #24182f; } QLabel { color: #f7ecff; } QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit { background: #392447; color: white; padding: 5px; border: 1px solid #8655a0; border-radius: 5px; } QCheckBox { color: #f7ecff; } QPushButton { padding: 7px 15px; background: #7c4dff; color: white; border-radius: 6px; }"
        )
        root = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        form = QFormLayout(content)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)
        prefs = store.preferences
        self._combo(
            form,
            "tone",
            "Kişilik",
            (("tsundere", "Tsundere"), ("sweet", "Tatlı"), ("serious", "Ciddi")),
            prefs,
        )
        self._line(form, "address", "Hitap", prefs, 30)
        self._combo(
            form,
            "outfit",
            "Kıyafet",
            (
                ("classic", "Siyah elbise"),
                ("casual", "Günlük pembe"),
                ("night", "Gece mavisi"),
            ),
            prefs,
        )
        self._combo(
            form,
            "hair_color",
            "Saç rengi (wolfcut)",
            (
                ("#f5f3f0", "Beyaz wolfcut"),
                ("#33204d", "Mor"),
                ("#202b52", "Gece mavisi"),
                ("#4a2c32", "Kestane"),
                ("#6b3159", "Gül kurusu"),
            ),
            prefs,
        )
        self._combo(
            form,
            "accessory",
            "Aksesuar",
            (
                ("none", "Yok"),
                ("headphones", "Kulaklık"),
                ("glasses", "Gözlük"),
                ("ribbon", "Kurdele"),
            ),
            prefs,
        )
        self._check(form, "animations", "Dekoratif animasyonlar", prefs)
        self._check(form, "autonomous", "Kendiliğinden dolaşabilsin", prefs)
        self._check(form, "pet_reactions", "Okşama tepkileri", prefs)
        self._combo(
            form,
            "double_click_action",
            "Çift tıklama",
            (("chat", "Sohbet"), ("game", "Kelime oyunu"), ("pet", "Başını okşa")),
            prefs,
        )
        self._spin(form, "speech_rate", "Konuşma hızı", 100, 260, prefs)
        volume = QDoubleSpinBox()
        volume.setRange(0, 1)
        volume.setSingleStep(0.05)
        volume.setValue(float(prefs["speech_volume"]))
        self._add(form, "speech_volume", "Ses düzeyi", volume)
        self._line(form, "voice_id", "Ses kimliği (boş: otomatik)", prefs, 240)
        self._check(form, "tts", "Sesli yanıt", prefs)
        self._check(form, "wake_word", "Yerel Hey Nora bekçisi", prefs)
        self._check(form, "continuous_conversation", "Sürekli konuşma modu", prefs)
        self.fields["continuous_conversation"].setToolTip(
            "Açıkken Nora cevap verdikten sonra tekrar dinler. 'Dinlemeyi bırak' veya "
            "'sürekli konuşmayı kapat' ile durur. Mikrofon yalnızca dinleme sırasında açıktır."
        )
        self._check(form, "push_to_talk", "Bas-konuş tuşu", prefs)
        self._line(form, "ptt_key", "Bas-konuş kısayolu", prefs, 60)
        self.fields["push_to_talk"].setToolTip(
            "Tuşa basılı tutunca dinler, bırakınca cevaplar. Global kısayol için 'keyboard' "
            "paketi gerekir; bazı sistemlerde yönetici izni isteyebilir."
        )
        self._check(form, "proactive", "Proaktif konuşma", prefs)
        self._check(form, "quiet_hours", "Gece 02:00-06:00 daha sessiz ol", prefs)
        self._check(
            form, "auto_screen_watch", "Nora ara sıra ekranımı incelesin", prefs
        )
        self._check(
            form, "auto_camera_watch", "Nora ara sıra kameradan beni incelesin", prefs
        )
        self._check(
            form, "auto_media", "Nora kendi kendine müzik/video açabilsin", prefs
        )
        self._spin(form, "autonomy_minutes", "Otonomi aralığı (dakika)", 5, 120, prefs)
        self.fields["auto_screen_watch"].setToolTip(
            "Açıkken Nora seyrek aralıklarla ekran görüntüsü alıp Groq'a analiz için gönderebilir. "
            "Varsayılan kapalıdır; odak/sessiz modda ve gece daha az çalışır."
        )
        self.fields["auto_camera_watch"].setToolTip(
            "Açıkken Nora seyrek aralıklarla kameradan bir kare alıp Groq'a analiz için gönderebilir. "
            "Kamera izni gerekir; varsayılan kapalıdır."
        )
        self.fields["auto_media"].setToolTip(
            "Açıkken Nora canı isterse Spotify/YouTube araması açıp dans edebilir veya video izleme "
            "pozuna geçebilir. Varsayılan kapalıdır; tarayıcı/uygulama açılabilir."
        )
        self._combo(
            form,
            "stt_backend",
            "Komut ses tanıma",
            (("google", "Google (internet gerekir)"), ("local", "Whisper (yerel)")),
            prefs,
        )
        self.fields["stt_backend"].setToolTip(
            "Yalnızca Hey Nora/🎤 sonrası dinler. Nora adı Nova/no ra gibi duyulursa "
            "sınırlı komut bağlamında düzeltilir; Ses Tanıma Testi ile kontrol edebilirsin."
        )
        self._combo(
            form,
            "whisper_model",
            "Whisper modeli",
            (
                ("tiny", "Tiny · hızlı"),
                ("base", "Base"),
                ("small", "Small · önerilen"),
                ("medium", "Medium · güçlü PC"),
            ),
            prefs,
        )
        self._combo(
            form,
            "whisper_device",
            "Whisper cihazı",
            (("auto", "Otomatik"), ("cpu", "CPU"), ("cuda", "CUDA ekran kartı")),
            prefs,
        )
        self._spin(form, "focus_minutes", "Odak süresi (dakika)", 5, 120, prefs)
        self._spin(
            form, "hydration_minutes", "Su hatırlatması (0: kapalı)", 0, 240, prefs
        )
        self._spin(
            form, "break_minutes", "Mola hatırlatması (0: kapalı)", 0, 180, prefs
        )
        scroll.setWidget(content)
        root.addWidget(scroll)
        buttons = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Apply).setText("Uygula")
        buttons.button(QDialogButtonBox.Cancel).setText("Vazgeç")
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add(self, form: QFormLayout, key: str, label: str, widget: QWidget) -> None:
        widget.setAccessibleName(label)
        self.fields[key] = widget
        form.addRow(label, widget)

    def _combo(self, form, key, label, choices, prefs) -> None:
        widget = QComboBox()
        for value, title in choices:
            widget.addItem(title, value)
        index = widget.findData(prefs[key])
        widget.setCurrentIndex(max(0, index))
        self._add(form, key, label, widget)

    def _line(self, form, key, label, prefs, limit) -> None:
        widget = QLineEdit(str(prefs[key]))
        widget.setMaxLength(limit)
        self._add(form, key, label, widget)

    def _check(self, form, key, label, prefs) -> None:
        widget = QCheckBox()
        widget.setChecked(bool(prefs[key]))
        self._add(form, key, label, widget)

    def _spin(self, form, key, label, low, high, prefs) -> None:
        widget = QSpinBox()
        widget.setRange(low, high)
        widget.setValue(int(prefs[key]))
        self._add(form, key, label, widget)

    def values(self) -> dict[str, Any]:
        result = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QComboBox):
                result[key] = widget.currentData()
            elif isinstance(widget, QCheckBox):
                result[key] = widget.isChecked()
            elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
                result[key] = widget.value()
            elif isinstance(widget, QLineEdit):
                result[key] = widget.text().strip()
        return result

    def apply(self) -> None:
        try:
            values = self.values()
            for key, value in values.items():
                self.store.validate_preference(key, value)
            if self.on_apply:
                self.on_apply(values)
            self.accept()
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "Ayar kaydedilemedi", str(exc))
