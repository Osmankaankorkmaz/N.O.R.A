# Nora 💕 · Anime Kız Masaüstü Asistanı

Nora; masaüstünde gezen, Türkçe sohbet eden, sesli komut alan, ekran/kamera analizi yapan ve günlük işlerini organize eden PyQt5 asistanıdır. Karakter; **beyaz wolfcut saçlı, kırmızı gözlü, siyah elbiseli ve kırmızı ayakkabılı** daha tatlı bir **8-bit piksel chibi** olarak tamamı **QPainter ile kod içinde çizilir**; çalışma zamanında harici sprite veya resim dosyası kullanılmaz.

> **Groq model notu:** `llama-3.3-70b-versatile` free/developer hesapları için 16 Ağustos 2026’da emekliye ayrıldı. Varsayılan sohbet modeli `openai/gpt-oss-120b`, vision modeli `qwen/qwen3.8-27b` olarak güncellendi. Sağ tık → **🩺 Groq Bağlantısı** anahtarınla erişilebilen modelleri listeler. Kaynaklar: [1](https://console.groq.com/docs/deprecations) · [2](https://console.groq.com/docs/models.md) · [3](https://console.groq.com/docs/vision)

## Neler yapabilir?

### Karakter ve ses
- 120×150 şeffaf, always-on-top pet; 40×50 mantıksal ızgarada 3×3 keskin pikseller, keskin kenarlı 8-bit görünüm ve aynı tarzda tepsi ikonu. Varsayılan görünüm: beyaz wolfcut, kırmızı göz, siyah elbise, kırmızı ayakkabı; daha büyük parıltılı gözler, pembe yanaklar, kalp toka ve etek danteli. Yürüme, uyuma, zıplama, oturma, dans, esneme, göz kırpma, el sallama, sürüklenip düşme; piksel kalp, yıldız, nota ve uyku efektleri.
- Tüm poz/duygu PNG’leri ve animasyon GIF’leri `docs/character/` altında: 18 poz, 8 duygu, 24 animasyon, aksesuar/kıyafet varyantları ve `index.html` galerisi. Üretici: `python tools/export_character.py`. Bunlar önizleme/doc çıktısıdır; uygulama çizimi yine QPainter’dır.
- **Komutla hareket:** “ikinci monitöre geç”, “uyu”, “uyan”, “dolaş”, “dur”, “zıpla”, “dans et”, “otur”. Bu komutlar Groq/internet olmadan çalışır.
- “Uyu” ve “dolaş” siz değiştirene kadar sürer. “Zıpla ve uyu” gibi en fazla dört açık hareket komutu arka arkaya çalışabilir.
- Çoklu monitör algılama, numaralı/sonraki/ana monitöre geçme, kenarlara yapışma ve görev çubuğu üstünde oturma.
- Kıyafet, saç rengi, gözlük/kulaklık/kurdele, animasyon ve otonom hareket ayarları; baş okşama tepkisi ve çift tıklama davranışı.
- Yerel **“Hey Nora”** bekçisi; yalnızca tam ifade duyulunca veya 🎤 basılınca komut dinler. Sizin metniniz kafasının üzerinde mor **“Sen: …”** balonunda görünür.
- Komut dinlerken elini kulağına götürür. Google STT veya isteğe bağlı **yerel Whisper** ile Türkçe komut tanıma; pyttsx3 sesli yanıt, ses/hız seçimi. Komut dinleme sırasında “Nora” adı “Nova/no ra/Noura” gibi yazıya geçirilirse yalnızca açık hitap veya sınırlı güvenli komut bağlamında düzeltilir; ne dediği/neyi anladığı sohbette görünür. **🗣️ Ses Tanıma Testi** komut çalıştırmadan transkripti gösterir.
- **Sürekli konuşma modu:** Nora cevap verdikten sonra tekrar dinler; `dinlemeyi bırak` / `sürekli konuşmayı kapat` ile durur. İki kez sessizlik olursa kendiliğinden bırakır.
- **Bas-konuş:** Ayarlardan seçilen global kısayola (varsayılan `Ctrl+Alt+Space`) basılı tutunca dinler, bırakınca cevaplar. Global kısayol için `requirements-local.txt` içindeki `keyboard` paketi gerekir; bazı sistemlerde yönetici izni isteyebilir.
- **Otonomi (varsayılan kapalı):** Kullanıcı açıkça açarsa Nora ara sıra ekranını/kamerasını inceleyebilir veya Spotify/YouTube araması açıp dans edebilir/video izleme pozuna geçebilir. Odak/sessiz modda ve gece sessizliğinde çalışmaz; aralık ayarlanabilir.
- **Medya:** `müzik aç`, `spotifyda lofi aç`, `video aç` Spotify/YouTube araması açar; Nora dans eder veya mısır alıp izleme pozuna geçer.
- Havada uzun tutulunca rahatsız olup söylenir; düşüşte hareket çizgileri, yere inince kısa squash/toz animasyonu vardır. Video izleme ve landenme pozlarıPainter ile çizilir.
- Bot yanıtları merkezi sesli yanıt politikasından geçer; uzun yanıtlar kesilmeden cümlelere bölünür. Sohbet başlığındaki 🔊/🔇 göstergesi, tepsi **Sesli Yanıt Testi** ve “sesli yanıtı aç/kapat”, “ses testi” komutları sessiz kalma nedenini görünür kılar.

### Günlük yardımcılar
- **Kalıcı kişisel hafıza:** yalnızca “bunu hatırla” dediğiniz bilgiler saklanır; hitap ve kişilik tonu kişiselleştirilebilir.
- Kalıcı notlar, görev listeleri ve nottan görev çıkarma.
- **Kalıcı hatırlatıcılar:** göreli süre, saat/tarih, her gün, hafta içi ve her hafta; uygulama yeniden başlayınca kaybolmaz.
- Odak/çalışma, oyun, sessiz ve normal modlar. Odak sayacı; isteğe bağlı su/mola hatırlatmaları.
- Güvenli rutinler: uygulama/müzik açma, hareket, mod ve benzeri sınırlı adımları onaylı çalıştırma.
- Kelime/anagram oyunu; çift tıklayınca oyun açma seçeneği.
- Yerel **OCR** ile ekrandaki yazıları okuma; isterseniz okunan metni Groq’a ayrıca onayla analiz ettirme.
- Pano metnini özetleme/çevirme/düzenleme/biçimlendirme; pano geçmişi tutulmaz, gönderim onay ister.
- Standart kullanıcı klasörlerinde dosya bulma, önizlemeli ve onaylı taşıma, üzerine yazmadan son taşımayı geri alma.
- `.ics` takvim dosyası içe aktarma, bugünkü/yaklaşan etkinlikler, boş zaman bulma ve sınırlı tekrarlayan etkinlik açılımı.
- Windows’ta pencere konumlarını yerelde kaydetme ve açık pencereleri onaylı eski düzenine döndürme; uygulama açma/kapatma yok.
- Ekran/kamera vision analizi, CPU/RAM/disk/batarya bilgisi, ses/parlaklık, uygulama/URL/arama/müzik, hava durumu ve sistem araçları.

## Hızlı komut örnekleri

| Söyleyebileceğiniz şey | Sonuç |
|---|---|
| `Hey Nora, ikinci monitöre geç` / `2. ekrana git` | Nora ikinci monitöre taşınır |
| `ana ekrana dön` / `önceki ekrana geç` | Ana/önceki monitör |
| `uyu` / `uyan` / `dolaş` / `dur` / `zıpla` | Kalıcı uyku, uyanma, dolaşma, bekleme, zıplama |
| `dans et` / `otur` / `zıpla ve uyu` | Dans, oturma, sıralı hareket |
| `çalışma modu` / `oyun modu` / `sessiz mod` / `normal mod` | Nora’nın davranış modu değişir |
| `bunu hatırla: kahvem = şekersiz` | Açık kişisel bilgi kaydı |
| `hafızanda ne var` / `bunu unut: kahvem` | Hafıza listeleme/silme |
| `10 dakika sonra çayı hatırlat` | Kalıcı göreli hatırlatıcı |
| `yarın 10:00'da toplantıyı hatırlat` | Tarih/saatli hatırlatıcı |
| `her cuma 18:00'de haftayı özetlememi hatırlat` | Haftalık tekrar |
| `hatırlatıcılar` / `hatırlatıcı ID iptal` | Listeleme/iptal |
| `görev ekle: raporu bitir` / `görevler` | Görev ekleme/listeleme |
| `1 numaralı görevi tamamla` / `1 numaralı notu görevlere çevir` | Görev yönetimi |
| `gözlük tak` / `kulaklık tak` / `siyah elbise` / `beyaz saç` | 8-bit QPainter görünümü |
| `saç rengi #202b52` / `tatlı mod` / `bana Kaan diye hitap et` | Görünüm/kişilik |
| `panoyu özetle` / `panoyu İngilizce çevir` | Onaylı pano yardımı |
| `ekrandaki yazıları oku` | Yerel OCR; analiz gönderimi ayrıca onaylı |
| `indirilenlerde rapor dosyalarını bul` | Güvenli dosya araması |
| `1 numaralı dosyayı Belgeler'e taşı` | Önizleme + onay; silme/üzerine yazma yok |
| `dosya taşımayı geri al` | Değişmemiş son taşımayı geri alma |
| `kelime oyunu başlat` / `cevabım kedi` / `ipucu ver` | Mini oyun |
| `sabah rutini çalıştır` | Kayıtlı güvenli rutini onayla başlatma |
| `bugünkü program` / `yaklaşan etkinlikler` | İçe aktarılan takvim |
| `bugün boş zamanım var mı` / `bugün 30 dakika boş zaman bul` | Takvimde boşluk arama |
| `masaüstü düzenini kaydet` / `masaüstü düzenini geri yükle` | Windows pencere konumları |
| `yerel ses modu` / `bulut ses modu` | Whisper / Google STT seçimi |
| `ses tanıma testi` / `dediklerimi anlıyor musun` | Komut çalıştırmadan duyulan/anlaşılan metni gösterir |
| `sürekli konuşma modu` / `dinlemeyi bırak` | Cevap sonrası tekrar dinler / durdurur |
| `bas konuş modu` | Basılı tutunca dinleyen global kısayolu açar |
| `müzik aç` / `spotifyda lofi aç` / `video aç` | Spotify/YouTube araması + dans/izleme animasyonu |
| `ekranımı izle` / `kamera incelemesini aç` / `otomatik medyayı aç` | Açıkça opt-in otonomi |

Serbest sohbet ve daha esnek ifadeler için Groq gerekir. Hareket komutları deterministik olduğundan internet kesilse de çalışır. Bilgisayarı kapatma, kod çalıştırma ve etkin pencereye yazma gibi işlemler yine ayrıca onay ister; “ne dersem yapsın” güvenlik onaylarını kaldırmaz.

## Kurulum

Temel paket için Python **3.10+**. Yerel ses/OCR/takvim eklentileri için `requirements-local.txt` önerilir; RapidOCR üst paket kısıtı nedeniyle bu ek paket **Python 3.10–3.12** ister.

### Windows

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
# Tüm yerel özellikler (Whisper, OCR, .ics):
python -m pip install -r requirements-local.txt

$env:GROQ_API_KEY = "gsk_..."
python main.py
```

Yerel ses modelleri başlangıçta indirilmez. Kurulumdan sonra Nora sağ tık/tray → **Özellikler → Yerel ses modelini indir** adımını açıkça onaylayın; ardından **Ayarlar → Komut ses tanıma → Whisper** seçin. Model yoksa Nora sesinizi Google’a göndermez.

PyAudio kurulumu başarısız olursa güncel tekerleği veya eski Windows/Python kombinasyonlarında `pipwin` yöntemini deneyebilirsiniz. Windows’ta mikrofon ve masaüstü erişim izinlerini kontrol edin.

### Linux

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev portaudio19-dev espeak-ng \
  libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 libxcb-icccm4 libxcb-image0 \
  libxcb-keysyms1 libxcb-randr0 libxcb-render-util0 libxcb-shape0 \
  libxcb-xinerama0 libxcb-xfixes0 xclip scrot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-local.txt
export GROQ_API_KEY="gsk_..."
python main.py
```

X11 masaüstü otomasyonu en sorunsuz yoldur; Wayland’de pano/ekran yakalama kısıtlı olabilir. GNOME tray görünmüyorsa pet sağ tık menüsünü kullanın.

### macOS

```bash
brew install portaudio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-local.txt
export GROQ_API_KEY="gsk_..."
python main.py
```

Ekran kaydı, kamera, mikrofon ve erişilebilirlik izinlerini Sistem Ayarları’ndan verin.

## Ayarlar ve veri

Sağ tık → **Özellikler → Ayarlar** panelinden kişilik, hitap, kıyafet, wolfcut saç rengi, aksesuar, animasyon, ses, Whisper, odak süresi ve su/mola aralıkları değiştirilebilir. Kırmızı göz ve kırmızı ayakkabı tüm kıyafetlerde sabittir; varsayılan elbise siyahtır. Eski fabrika mor saç ayarı bir kez beyaz wolfcut’a taşınır, özel seçilmiş diğer saç renkleri korunur. Çift tıklama sohbet, oyun veya baş okşama olabilir.

Kalıcı veriler varsayılan olarak:
- Windows: `%LOCALAPPDATA%\Nora\state.json`
- Linux: `~/.local/share/nora/state.json`
- macOS: `~/Library/Application Support/Nora/state.json`

`NORA_DATA_DIR` veya `python main.py --data-dir D:\NoraVeri` ile değiştirilebilir. Yerel modeller bu klasörün `models/` altındadır.

**Saklananlar:** ayarlar, açıkça kaydedilen kişisel bilgiler, notlar, görevler, hatırlatıcılar, rutinler ve içe aktarılan takvim etkinlikleri. **Saklanmayanlar:** ham sohbet geçmişi, mikrofon sesi, pano geçmişi. Sohbet bağlamı oturumda son 30 mesajdır; “Sohbet Geçmişini Sıfırla” kişisel hafızayı silmez. Kişisel hafıza ayrı bir onaylı menüyle silinebilir.

## Gizlilik ve güvenlik sınırları

- “Hey Nora” bekçisi mikrofonu **yerel anahtar ifade tespiti** için açar; bu aşamada transkripsiyon/bulut yoktur. Metin kapısı yine tam olarak `hey nora` ister; yalnızca “Nora” sözcüğünün Türkçe telaffuz alternatifleri eklenmiştir. Hiç mikrofon açılmasın isterseniz `--no-wake-word` kullanın veya bekçiyi kapatın.
- Varsayılan komut STT’si Google’dır; yalnızca aktivasyon/🎤/bas-konuş sırasında ses gönderir. Yerel Whisper seçiliyse model hazır olmasa bile buluta gizlice geçilmez. İsim düzeltmesi ve STT alternatif seçimi yalnızca bu açık dinleme sonrasında, sınırlı düşük riskli komutlarda çalışır; serbest sohbet/not içeriği yeniden yazılmaz.
- Sürekli konuşma ve bas-konuş varsayılan kapalıdır; açıldığında mikrofon yalnızca dinleme sırasında kullanılır. Bas-konuş tuş vuruşlarını kaydetmez.
- Ekran/kamera otonomisi ve otomatik medya varsayılan kapalıdır. Açıkken bile seyrek aralıklarla çalışır; ekran/kamera görüntüleri Groq’a analiz için gönderilebilir, diske yazılmaz. İstediğin an ayarlardan veya komutla kapatabilirsin.
- Groq sohbet/vision isteği açıkça yaptığınız analizlerde kullanılır. OCR önce cihazda çalışır; okunan metnin Groq’a gönderilmesi ayrı onay ister. Pano analizi de onay ister.
- Dosya işlemleri yalnızca standart kullanıcı klasörlerinde çalışır; keyfi yol, silme, üzerine yazma veya kabuk komutu yoktur. Taşıma öncesi kaynak/hedef gösterilir.
- Rutinler kapatma/kod/dosya taşıma/pano gibi adımları içeremez. Modlar uygulamaları kendiliğinden kapatmaz veya işletim sistemi ayarlarını değiştirmez.
- `NORA_ALLOW_CODE=0` varsayılan kalır. Kod çalıştırma açık olsa bile her istek onaylıdır ve güvenlik sandbox’ı değildir.
- Takvim entegrasyonu seçtiğiniz `.ics` dosyasını yerelde okur; bulut hesap senkronizasyonu veya hesap bilgisi istemez.
- Pencere düzeni özelliği Windows’ta `pygetwindow` kullanır; yalnızca hâlâ açık ve başlığı eşleşen pencereleri taşır. Diğer platformlarda desteklenmediğini açıkça söyler.

## Ortam değişkenleri

`.env.example` yalnızca örnektir; otomatik yüklenmez. Değerleri kabuk ortamında ayarlayın.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `GROQ_API_KEY` | boş | Serbest sohbet/vision/metin analizi anahtarı |
| `NORA_CHAT_MODEL` | `openai/gpt-oss-120b` | Sohbet modeli |
| `NORA_VISION_MODEL` | `qwen/qwen3.8-27b` | Vision modeli |
| `NORA_WAKE_WORD` | `1` | Yerel Hey Nora bekçisi |
| `NORA_TTS` / `NORA_PROACTIVE` | `1` | Sesli yanıt / proaktif konuşma |
| `NORA_OFFLINE` | `0` | Groq bağlantısını kapat |
| `NORA_MICROPHONE_INDEX` | boş | PyAudio giriş cihazı |
| `NORA_WAKE_THRESHOLD` | `1e-20` | Yerel anahtar ifade eşiği |
| `NORA_DATA_DIR` | boş | Kalıcı veri/model klasörü |
| `NORA_ALLOW_CODE` | `0` | Onaylı Python çalıştırma opt-in |
| `NORA_LOG_LEVEL` | `INFO` | Log seviyesi |

## CLI

```bash
python main.py --no-wake-word       # yalnızca 🎤 ile komut dinle
python main.py --no-tts             # sesli yanıt kapalı
python main.py --no-proactive       # kendiliğinden konuşma kapalı
python main.py --offline            # Groq kapalı; yerel komutlar çalışır
python main.py --data-dir ./veri    # taşınabilir veri klasörü
python main.py --version
```

## Ses tanıma sorun giderme

- `Yerel wake word döngüsü hatası: TypeError` görürsen güncel sürümde PortAudio’dan gelen `bytearray/memoryview` verisi PocketSphinx için `bytes`’a çevrilir ve hata ayrıntısı loglanır. Yine olursa PyAudio/mikrofon cihazını kontrol et; 🎤 düğmesi çalışmaya devam eder.

- “Nora” adı “Nova”, “no ra”, “Noura” gibi anlaşılıyorsa önce **🗣️ Ses Tanıma Testi** ile `Hey Nora, uyu` deyin; Nora komutu çalıştırmadan duyduğu ve anladığı metni gösterir.
- Komut dinleme başladıktan sonra `Hey Nova, uyu` gibi açık hitaplar Nora olarak düzeltilir. Çıplak `Nora`/`Nova` arka planda aktivasyon yapmaz; yerel bekçi tam `hey nora` ister.
- Mikrofon seviyesi için **🎙️ Mikrofon Testi**, cihaz seçimi için **Mikrofon Seç** kullanın. Gürültülü ortamda yerel Whisper `small/medium` daha iyi olabilir; model indirme açık onay ister.
- Google STT internet kullanır; yerel Whisper seçiliyse ses buluta gönderilmez. Whisper’a Türkçe komut ve “Nora” ipucu verilir, önceki sohbet metni koşullandırma olarak kullanılmaz.

## Sesli yanıt sorun giderme

- Sohbet başlığında 🔇 görüyorsanız sesli yanıt kapalıdır. “sesli yanıtı aç” deyin veya tepsi menüsündeki **Sesli yanıt** kutusunu işaretleyin.
- Odak/sessiz mod sesli yanıtı bilerek kapatır. “normal mod” önceki ses ayarını geri yükler; gösterge bunu 🔇 olarak belirtir.
- “ses testi” / tepsi **🔊 Sesli Yanıt Testi** motor durumunu, ses düzeyini ve son hatayı yazar; ardından örnek cümleyi seslendirir.
- Uzun yanıtlar 1200 karakterde kesilmez; TTS kuyruğunda cümle parçaları halinde okunur. Ses motoru hata verirse bir kez temiz motorla yeniden denenir ve hata sohbet/tepside görünür.
- Windows’ta SAPI sesi, Linux’ta espeak-ng kurulu olmalıdır. Ses düzeyi 0 ise gösterge 🔇 olur; Ayarlar’dan konuşma sesini yükseltin.

## Dosya yapısı

```text
main.py
nora/
  main.py                 # CLI / QApplication
  nora_personality.py     # persona, duygu ve güvenli komut şeması
  nora_commands.py        # internetsiz Türkçe komut çözümleme
  nora_speech.py          # güvenli sesli transkript/isim düzeltme
  nora_hotkeys.py         # isteğe bağlı global bas-konuş kısayolu
  nora_brain.py           # Groq chat/vision/metin yardımı
  nora_voice.py           # yerel wake, Google/Whisper STT, TTS
  nora_pet.py             # 8-bit karakter, fizik, hareket, baloncuk
  nora_pixel_art.py       # QPainter piksel çizimi, paletler, tepsi ikonu
  nora_tools.py           # sistem/ekran/kamera/uygulama/not araçları
  nora_store.py           # atomik kalıcı yerel veri
  nora_activities.py      # hatırlatıcı zamanlayıcı, modlar, kelime oyunu
  nora_files.py           # sınırlı dosya bulma/taşıma/geri alma
  nora_calendar.py        # .ics okuma, etkinlik ve boş zaman listeleme
  nora_desktop.py         # Windows pencere düzeni kaydetme/geri yükleme
  nora_local_ai.py        # isteğe bağlı Whisper ve RapidOCR
  nora_settings_dialog.py # ayar paneli
  nora_proactive.py       # düşük frekanslı proaktif konuşma
  nora_ui.py              # sohbet/tray/worker entegrasyonu
tools/
  export_character.py     # QPainter çiziminden PNG/GIF galerisi üretir
docs/
  character/              # tüm poz, duygu, aksesuar, kıyafet ve animasyon çıktıları
tests/
requirements.txt
requirements-local.txt
requirements-dev.txt
.env.example
```

## Test ve geliştirme

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -r requirements-local.txt  # yerel özellik testleri için
python -m pytest -q
python -m compileall -q nora main.py tests
ruff check nora tests tools main.py
```

Bu sürümde **243 test** geçmiştir; offscreen GUI, 8-bit piksel ızgarası/keskinliği, tüm poz/animasyon dışa aktarımı, istenen siyah elbise-kırmızı ayakkabı-kırmızı göz-beyaz wolfcut paleti, eski görünüm migrasyonu, kıyafet-saç-aksesuar değişimi, tepsi ikonu, merkezi sesli yanıt politikası, TTS kuyruğu/yeniden deneme/hata görünürlüğü, komut şeması, sesli isim düzeltme/alternatif seçimi, ses tanıma testinin komut çalıştırmaması, bas-konuş/sürekli konuşma, opt-in otonomi, medya/dans/izleme, kaldırılma rahatsızlığı ve landenme animasyonu, kalıcı veri, hatırlatıcı tekrarları, modlar, dosya geri alma, takvim, gerçek sentetik görüntüyle OCR ve yerel STT’nin buluta geçmemesi kontrol edilmiştir. Fiziksel Windows mikrofonu, gerçek Groq anahtarı ve indirilmiş Whisper modeli bu ortamda canlı doğrulanamamıştır. Google’ın genel STT anahtarı ve üçüncü taraf servisler ileride değişebilir.
