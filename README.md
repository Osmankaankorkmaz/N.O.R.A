# Nora 💕 · Anime Kız Masaüstü Asistanı

Nora; masaüstünde gezen, sohbet eden, sesli komut alan, ekran/kamera analizi yapan ve
sistem araçlarını çalıştıran Türkçe bir PyQt5 asistanıdır. Karakterin tamamı
**QPainter ile kod içinde çizilir**; harici sprite, resim veya ses dosyası gerekmez.

> **Önemli model notu:** `llama-3.3-70b-versatile` Groq’un free/developer
> hesapları için **16 Ağustos 2026’da emekliye ayrıldı**; önerilen yerine
> `openai/gpt-oss-120b` geçti. Varsayılan sohbet modeli artık budur. Enterprise
> sözleşmen varsa `NORA_CHAT_MODEL` ile eski modeli açıkça seçebilirsin. Vision tarafında
> eski `llama-3.2-90b-vision-preview` yerine `qwen/qwen3.8-27b` kullanılır.
> `NotFoundError` artık güvenli Groq hata ayrıntısını gösterir; sağ tık →
> **🩺 Groq Bağlantısı** anahtarınla erişilebilen modelleri listeler.
> Kaynaklar: [1](https://console.groq.com/docs/deprecations) · [2](https://console.groq.com/docs/models.md) · [1](https://console.groq.com/docs/vision)

---

## Özellikler

- 🐈 120×150 şeffaf, always-on-top masaüstü peti; yürüme, oturma, uyuma, zıplama,
  el sallama, sürüklenip düşme, göz kırpma, kuyruk/saç animasyonu ve duygu efektleri
- 💬 Ayrı, taşınabilir, koyu mor/pembe sohbet penceresi; seçilebilir mesaj balonları
- 🧠 Groq sohbeti, oturum içi son 30 mesajlık hafıza, duygu ve JSON komut protokolü
- 🎙️ “Hey Nora” wake word dinleyicisi, tek seferlik Türkçe STT, pyttsx3 TTS;
  dinlerken **elini kulağına götürür**, başını hafif eğer ve pembe ses dalgaları çıkarır
- 🎧 Mikrofon cihazı seçimi ve yerel **Mikrofon Testi** (ses seviyesi/algılama kontrolü)
- 📸 Ekran görüntüsü analizi — Nora’nın kendi pencereleri görüntüden önce gizlenir
- 📷 Kamera analizi — kare yakalandıktan sonra kamera hemen serbest bırakılır
- 💻 CPU/RAM/disk/batarya bilgisi ve proaktif sistem uyarıları
- 🔊 Ses, parlaklık, uygulama açma, URL/arama, YouTube müzik araması
- 📝 Oturum içi not defteri, ⏰ hatırlatıcılar, 🌤️ wttr.in hava durumu
- 😴 Gece 02:00–06:00 daha az konuşma ve daha fazla uyku davranışı
- 🖥️ Çoklu monitörde mevcut ekranı algılama, kenarlara yapışma, görev çubuğu üstüne oturma
- 🧩 System tray + pet sağ tık menüsü; hafıza sıfırlama ve güvenli kapatma

## Dosya yapısı

```text
.
├── main.py                  # Kök başlatıcı: python main.py
├── nora/
│   ├── main.py              # QApplication, High DPI, CLI seçenekleri
│   ├── nora_personality.py  # System prompt, duygular, komut şeması, proaktif replikler
│   ├── nora_brain.py        # Groq chat/vision, hafıza, çevrimdışı temel komutlar
│   ├── nora_voice.py        # TTS, STT, wake word thread’leri
│   ├── nora_pet.py          # QPainter karakter, fizik, davranış AI’ı, konuşma balonu
│   ├── nora_tools.py        # Sistem/kamera/ekran/uygulama/ses/not/hava/timer araçları
│   ├── nora_proactive.py    # 30 sn kontrol, 120 sn minimum aralık, 5 dk idle
│   └── nora_ui.py           # Chat, tray, worker thread’ler, tüm entegrasyon
├── tests/                   # pytest: personality, brain, tools, voice, proactive, GUI
├── requirements.txt
├── requirements-dev.txt
└── .env.example             # Örnek ortam değişkenleri; otomatik yüklenmez
```

---

## Kurulum

Python **3.10+** gerekir. Komutları depo kökünde çalıştır.

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

$env:GROQ_API_KEY = "gsk_..."
python main.py
```

PyAudio kurulumu başarısız olursa önce güncel tekerleği dene; eski Windows/Python
kombinasyonlarında belgedeki `pipwin` yöntemi hâlâ bir seçenek olabilir:

```powershell
python -m pip install PyAudio==0.2.14
# Gerekirse:
python -m pip install pipwin
pipwin install pyaudio
```

### Linux (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev espeak-ng \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
  libxcb-xinerama0 libxcb-xfixes0 xclip scrot

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

export GROQ_API_KEY="gsk_..."
python main.py
```

- Ses sentezi için `espeak-ng` (veya dağıtımının `pyttsx3` desteklediği motor) gerekir.
- Ses kontrolü `pactl` (PulseAudio/PipeWire) veya `amixer` kullanır.
- Masaüstü otomasyonu için X11 en sorunsuz yoldur. Wayland’de `pyautogui`, pano ve
  ekran yakalama kısıtlı olabilir.
- GNOME’da system tray görünmüyorsa AppIndicator desteği gerekebilir; pet sağ tık
  menüsü her zaman yedektir.

### macOS

```bash
brew install portaudio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export GROQ_API_KEY="gsk_..."
python main.py
```

Kamera, mikrofon, ekran kaydı ve erişilebilirlik izinlerini Sistem Ayarları’ndan
Python/terminal uygulamasına ver. `pyttsx3` macOS’ta sistem seslerini kullanır.

---

## Ortam değişkenleri

`.env.example` yalnızca örnektir; Nora `.env` dosyasını **otomatik okumaz**.
Değerleri kabuk ortamına aktar veya IDE çalıştırma ayarlarına ekle.

| Değişken | Varsayılan | Açıklama |
|---|---:|---|
| `GROQ_API_KEY` | yok | Groq anahtarı. Koda gömme, depoya commit’leme. |
| `NORA_CHAT_MODEL` | `openai/gpt-oss-120b` | Sohbet modeli |
| `NORA_VISION_MODEL` | `qwen/qwen3.8-27b` | Ekran/kamera analiz modeli |
| `NORA_WAKE_WORD` | `1` | Sürekli “Hey Nora” dinleyicisi |
| `NORA_TTS` | `1` | Sesli yanıt |
| `NORA_PROACTIVE` | `1` | Nora’nın kendi kendine konuşması |
| `NORA_OFFLINE` | `0` | Groq’a bağlanma; yalnızca temel deterministik komutlar |
| `NORA_ALLOW_CODE` | `0` | Python kod çalıştırmaya izin ver; her kod yine onay ister |
| `NORA_LOG_LEVEL` | `INFO` | Log ayrıntısı |
| `NORA_MICROPHONE_INDEX` | boş | PyAudio giriş cihazı indeksi; boşsa varsayılan cihaz |

Anahtar yoksa uygulama çökmez; çevrimdışı temel komut moduna geçer ve bunu açıkça
söyler. Serbest AI sohbeti ve görsel analiz için anahtar gerekir.

### CLI seçenekleri

```bash
python main.py --no-wake-word     # sürekli mikrofon dinleme kapalı
python main.py --no-tts           # sessiz mod
python main.py --no-proactive     # proaktif replikler kapalı
python main.py --offline          # Groq kapalı, temel komutlar açık
python main.py --version
python -m nora.main --version
```

---

## Kullanım

- Pet’e **sol tık**: sohbeti aç/kapat. **Çift tık**: sohbeti aç.
- Pet’i **sürükle**: bırakınca yerçekimiyle düşer.
- Pet’e **sağ tık**: tüm araçlar, duygular, hafıza ve kapatma menüsü.
- Sohbette **Enter** veya 💝 ile gönder.
- 📸 ekran analizi, 📷 kamera, 🎤 tek seferlik sesli komut, 💻 sistem bilgisi.
- Hızlı butonlar: 🔍 Ara, ⏰ Saat, 📝 Notlar, 🌤️ Hava.
- “Hey Nora chrome aç” → doğrudan komut; sadece “Nora” → “Efendim senpai?” + dinleme.
- Nora dinlerken elini kulağına götürür; 🎙️ **Mikrofon Testi** sesi Google’a göndermeden
  yerel seviye ölçer, 🎧 **Mikrofon Seç** giriş cihazını değiştirir.
- Sohbeti kapatmak uygulamayı kapatmaz. Tamamen kapatmak için tray/sağ tık → **Kapat**.

Örnek ifadeler:

```text
not al: yarın saat 10'da toplantı var
notlarımı göster
5 dakika sonra hatırlat çayım demlendi
Bursa hava durumu
sesi %40 yap
parlaklığı %60 yap
chrome aç
Python asyncio ara
ekranda ne var?
kamerada ne görüyorsun?
sistem bilgisi
kapatmayı iptal et
```

## Komut protokolü

Nora cevabının sonunda duygu, isteğe bağlı olarak da JSON komut üretir:

```text
Notunu aldım senpai~ [CMD:{"command":"note","action":"add","text":"toplantı"}] [EMO:happy]
```

Etiketler kullanıcıya gösterilmez; duygu pet animasyonunu değiştirir. Komutlar
çalıştırılmadan önce şema ve güvenlik doğrulamasından geçer.

| Komut | Örnek JSON |
|---|---|
| `open_app` | `{"command":"open_app","app":"chrome"}` |
| `search` | `{"command":"search","query":"Python asyncio"}` |
| `open_url` | `{"command":"open_url","url":"https://example.com"}` |
| `volume` | `{"command":"volume","level":50}` |
| `brightness` | `{"command":"brightness","level":60}` |
| `type_text` | `{"command":"type_text","text":"merhaba"}` |
| `clipboard_copy` | `{"command":"clipboard_copy","text":"metin"}` |
| `system_info` | `{"command":"system_info"}` |
| `screenshot` | `{"command":"screenshot","prompt":"ekranda ne var?"}` |
| `camera` | `{"command":"camera","prompt":"ne görüyorsun?"}` |
| `shutdown` | `{"command":"shutdown"}` |
| `cancel_shutdown` | `{"command":"cancel_shutdown"}` |
| `lock_screen` | `{"command":"lock_screen"}` |
| `set_timer` | `{"command":"set_timer","seconds":300,"message":"çay hazır"}` |
| `play_music` | `{"command":"play_music","query":"lofi hip hop"}` |
| `weather` | `{"command":"weather","city":"Bursa"}` |
| `note` | `{"command":"note","action":"add","text":"not"}` / `{"command":"note","action":"list"}` |
| `run_code` | `{"command":"run_code","language":"python","code":"print(2+2)"}` |

---

## Gizlilik ve güvenlik

- **Sürekli dinleme varsayılan olarak açıktır** (proje belgesindeki davranış).
  Sohbet başlığındaki 🎙️ simgesi ve tray menüsündeki “Hey Nora dinleyicisi” anahtarı
  bunu görünür/kontrol edilebilir kılar. Başlangıçta `--no-wake-word` ile kapatabilirsin.
- Wake word ve 🎤 dinlemesi sesi **Google Speech Recognition** servisine gönderir.
  Nora ses kaydını diske yazmaz. İnternet yoksa STT çalışmaz.
- Sohbet Groq’a; ekran/kamera görselleri yalnızca sen istediğinde Groq vision’a gider.
  Kamera karesi yakalanır yakalanmaz serbest bırakılır. Ekran görüntüsünde Nora’nın
  kendi pencereleri önce gizlenir.
- `run_code` varsayılan **kapalıdır**. `NORA_ALLOW_CODE=1` açsan bile her çalıştırma
  modal onay ister. Bu bir sandbox değildir: kod senin kullanıcı yetkilerinle çalışır.
- `shutdown` onay ister ve 60 saniye gecikmeli planlanır; `cancel_shutdown` iptal eder.
- `type_text` etkin pencereye yazmadan önce onay ister. Türkçe metin pano üzerinden
  yapıştırılır ve pano içeriği değişebilir.
- Uygulama açma `shell=True` kullanmaz; bilinmeyen adlar yalnızca PATH’teki tek bir
  yürütülebilir olarak çözülür. URL’lerde yalnızca http/https kabul edilir.
- Notlar ve sohbet hafızası oturum belleğindedir; uygulama kapanınca kaybolur.

## Test

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python -m ruff check nora tests main.py
```

Testler Qt’yi offscreen çalıştırır; GUI kütüphaneleri yoksa GUI testleri atlanır.
Bu depodaki geliştirme ortamında personality, brain, tools, voice, proactive ve
offscreen GUI testleri çalıştırıldı. Gerçek Windows ses API’si, fiziksel mikrofon,
kamera, parlaklık ve çoklu monitör davranışı hedef masaüstünde doğrulanmalıdır.

## Sorun giderme

| Belirti | Kontrol |
|---|---|
| `PyAudio` kurulmuyor | PortAudio başlıkları: `portaudio19-dev` / `brew install portaudio`; Windows’ta güncel wheel veya pipwin |
| Ses yok | Windows SAPI sesi, Linux `espeak-ng`, macOS sistem sesi; tray’de “Sesli yanıt” açık mı? |
| Mikrofon yok | OS mikrofon izni, doğru cihaz, PyAudio; 🎙️ dinleyiciyi kapatıp 🎤 ile dene |
| “Hey Nora” tetiklenmiyor | Önce 🎙️ Mikrofon Testi: ses algılanıyor mu? 🎧 Mikrofon Seç ile doğru giriş cihazını seç; Windows Ses → Giriş seviyesi; internet (Google STT); Nora konuşurken dinleme duraklar |
| Ses geldi ama anlayamadı | Mikrofon seviyesi/gürültü; Windows varsayılan iletişim cihazı; `NORA_MICROPHONE_INDEX`; Google STT dil/anahtar sınırları |
| Tray görünmüyor | Linux AppIndicator/extension; pet sağ tık menüsünü kullan |
| Ekran/klavye çalışmıyor | Wayland kısıtları, macOS ekran kaydı/erişilebilirlik izinleri, X11 oturumu |
| Parlaklık değişmiyor | Harici ekran/DDR desteği değişir; `screen-brightness-control` uyumluluğu |
| Groq `NotFoundError` | Sağ tık → 🩺 Groq Bağlantısı. `llama-3.3-70b-versatile` free/dev için 16.08.2026’da kapatıldı; `openai/gpt-oss-120b` kullan [1](https://console.groq.com/docs/deprecations) |
| `comtypes` INFO logları | Windows COM önbelleği bilgilendirmesidir; artık WARNING seviyesine çekildi, hata değildir |
| `libGL.so.1` hatası | Linux’ta `libgl1`/Mesa kur; sanal makinede offscreen test için Qt GUI paketleri gerekir |
| OpenCV çakışması | Aynı ortamda hem `opencv-python` hem `opencv-python-headless` kurma; birini seç |

## Bilinen sınırlar

- Wake word yerel bir anahtar kelime modeli değil, bulut STT ile çalışır; gecikme ve
  internet bağımlılığı vardır. Google’ın genel test anahtarı ileride değişebilir.
- `pyautogui` ekran görüntüsü öncelikli olarak birincil ekranı yakalar; pet çoklu
  monitörde mevcut ekranı algılar ama tüm sanal masaüstünü tek görüntüde analiz etmez.
- Windows ses/parlaklık/kapatma birinci sınıf hedeflerdir; Linux/macOS araçları
  dağıtım, masaüstü ortamı ve izinlere göre best-effort çalışır.
- `pyttsx3` ses kalitesi işletim sisteminin ses motoruna bağlıdır.
- Proaktif motor en az 120 saniyede bir konuşur; gece daha seyrek, sistem uyarılarında
  öncelikli ve tekrarları için soğuma süreli davranır.
