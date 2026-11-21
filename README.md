# Nora 💕 · Anime Kız Masaüstü Asistanı

Nora; masaüstünde yaşayan, Türkçe sohbet eden, ekran/kamera analizi yapan ve günlük işlerini organize eden PyQt5 asistanıdır. Karakter **8-bit piksel bir kızdır**: kumral bob saç, **iri yeşil gözler**, krem balıkçı yaka, pileli etek, **kolları, elleri, bacakları ve ayakkabılarıyla tam vücut**, 40×54'lük gerçek bir piksel ızgarasından 3× büyütmeyle çizilir — yani her blok keskin bir karedir, görsel büyütülmüş bir resim değildir. **Hangi duyguyu/hareketi göstereceğine yapay zeka her cevapta anlık karar verir.** Uygulama **Ollama gibi büyük bir sohbet penceresi** olarak açılır; karakter o an **logonun içindedir**. Logoya basınca Nora logodan **çıkıp masaüstüne konar**, tek başına yaşar ve konuşur; sohbet penceresi açık kalır. **Tek tık onu gıdıklar** (kıkır kıkır güler), **çift tık cam görünümlü kişisel paneli** açar (ruh hâli, anılar, özel tercihler). Mikrofon **kapalıdır**: yazarak konuşursun, Nora sesli yanıt verir. Görseller çalışma zamanında ağdan inmez.

## 1.14.0 · 8-bit karakter, logodan çıkan Nora, gıdıklama ve kişisel panel

- **Karakter artık gerçek 8-bit:** 40×54 mantıksal ızgaranın her hücresi 3×3 piksel olarak boyanır; `canvas.scale` ve tam sayı sallanma/bob ile hiçbir kenar bulanıklaşmaz. Kumral bob (`#a9743f`), **zümrüt yeşili iris** (`#46ab45`), krem balıkçı yaka, beyaz pileli etek, kahverengi loafer — ayaklar yere basar, kollar ve eller gövdeden ayrı çizilir.
- **Uygulama önce, karakter sonra:** açılışta yalnızca büyük sohbet penceresi görünür; Nora **logo rozetinin içinde** durur. Rozete basınca masaüstüne çıkar, tekrar basınca içeri girer. Sohbet penceresi hiçbir zaman kapanmaz.
- **Tek tık = gıdıklama:** Nora kıkırdar (`giggle` durumu, 26 karelik animasyon) ve rastgele bir gıdıklanma cümlesi söyler. Havadayken gıdıklama reddedilir.
- **Çift tık = kişisel panel:** aynı cam dilinde, 460×520 boyutunda ayrı bir pencere. Üç sekme: **Ruh hâli** (8 duygu, anında karaktere yansır), **Anılar** (silinebilir satırlar), **Özel** (takma ad, ilişki tonu, konuşma tarzı). Panel karakterin yanına konumlanır.
- **AI jestleri 8-bit modda da çalışır:** `[MOVE]` etiketindeki 27 jestin her biri en yakın piksel durumuna eşlenir ve süreli oynatılır; geçersiz jest duyguya göre yedeğe düşer. Yeni `sad` ve `cheer` durumları eklendi.
- **Mikrofon kapalı:** `MICROPHONE_ENABLED = False`. Mikrofon düğmesi artık "Mikrofon kapalı — yazarak konuş" der ve dürüstçe açıklama gösterir; uyandırma sözcüğü dinleyicisi hiç başlamaz. **Sesli yanıt (TTS) açık kalır.**
- **Düzeltmeler:** tepsi ikonu bloğu tuvale yarım piksel kayıyordu (bulanıklık) — ofset artık tam blok; oturma pozunda nefes bobu yoktu (animasyonun iki karesi aynıydı); iris kirpik ve bebek altında kalıp ~4 yeşil piksel bırakıyordu; başlıkta iki avatar vardı, logo tek avatar oldu; `deleteLater()` satırları `findChildren`'da yaşıyordu ve kişisel panel uygulamadan uzun yaşıyordu — ikisi de pencere sızıntısı ve yeniden başlatmalarda çökme nedeniydi.

## 1.13.0 · Çizim karakter (AI illüstrasyon), kaldır-bırak fiziği, yandan yürüme

- **Karakter artık elle çizilmiş illüstrasyon:** QPainter ile prosedürel çizim yerine, `docs/character/ai/` altındaki **AI ile üretilmiş tam vücut illüstrasyonlar** kullanılıyor. Kumral bob, iri yeşil gözler, krem balıkçı yaka, pileli etek — referans görselin birebir tarzı, cel-shading ve kalın çizgi. Varsayılan stil `sprite`.
- **Duyguya göre 10 ayrı çizim:** mutlu (el sallıyor), üzgün, düşünen, şaşkın, kızgın, sevgi dolu, uykulu, utangaç, gülen, dans eden. AI'nın her cevapta seçtiği duygu doğrudan bu çizimlere eşleniyor; **yumuşak çapraz geçiş** ile değişiyor, ani zıplama yok.
- **Yandan yürüme/koşma döngüsü:** gerçek faz kareleri + **yatay aynalama** ile 4 fazlı doğal yürüme. Sola giderken otomatik aynalanıyor.
- **Kaldır-bırak fiziği (yeni):** Nora'yı fareyle **tutup kaldırabilirsin** — havada sarkma çizimi, bırakınca düşme, yere çarpınca çömelme ve doğrulma kareleri sırayla oynar. Yüksekten bırakılırsa "kendini koruma" pozu devreye girer. Duvarlara çarpınca sekmez, ekrandan çıkmaz.
- **Beyaz arka plan otomatik silinir:** illüstrasyonların beyaz fonu, **flood-fill** ile şeffafa çevriliyor; kazak/etek üzerindeki beyaz yüzeyler korunuyor (global renk filtresi kullanılmıyor).
- **Ayakkabılar yere basar:** kırpma ve ölçekleme alt kenara hizalı; pencere boyutu değişse de karakter zeminde durur.
- **Dürüst geri dönüş:** çizim dosyaları yoksa uygulama **prosedürel gövde çizimine** düşer, hata vermez veya boş pencere göstermez.
- **Tepsi ikonu ve sohbet avatarı** aynı illüstrasyondan yüz kırpmasıyla üretiliyor; saç rengi tercihi tepsi ikonuna da uygulanıyor (ton eşlemesi).
- **`[MOVE]` jestleri çizim modunda da çalışır:** 27 jestin her biri en yakın çizime eşlenir ve süreli poz olarak oynatılır; geçersiz jest yine duyguya göre yedeğe düşer.
- **Düzeltmeler:** ilk açılışta boş pencere (çizim hiç seçilmiyordu); uzun süre gizli kalan pencerede aşamanın yarıda kalması (zaman bütçesi artık aşamalar arasında tüketiliyor); bilinmeyen duygunun geçerli pozu ezmesi; ölü `speed` değişkeni.

## 1.12.0 · Tam vücut karakter, yapay zekâ seçimli anlık hareket, büyük sohbet uygulaması

- **Tam vücut karakter (yeni varsayılan):** Baş, boyun, gövde, iki omuz, dirsekli kollar, eller, etek, iki bacak, dizler ve ayakkabılı ayaklar — hepsi prosedürel olarak çizilir. Referanstaki gibi kumral bob saç, iri yeşil iris, krem balıkçı yaka ve pileli etek. 3× süper örnekleme ile yumuşak, "VTuber" hissi veren bir görünüm.
- **Hareketleri yapay zekâ anlık seçer:** Model artık her cevapta isteğe bağlı bir `[MOVE:{...}]` etiketi üretir (24 farklı jest: el sallama, omuz silkme, baş eğme, dans, gerinme, eğilme, alkış, düşünme…). Yeni **hareket motoru** (`nora/nora_motion.py`) bu seçimi 30 fps'te pürüzsüz ara karelerle üretir; önceden kaydedilmiş animasyon oynatılmaz. Etiket yoksa veya geçersizse duyguya uygun hareket **rastgele** seçilir — karakter asla donmaz.
- **Model girdisi sıkı doğrulanır:** Bilinmeyen jest adı reddedilir, `intensity` 0.35–1.35 ve `duration` 0.6–6 s aralığına kırpılır, en fazla 3 adım zincirlenir; sayı olmayan değerler sessizce yutulmaz.
- **Sohbet paneli artık normal bir uygulama:** 820×620 (ekranın ~%66'sı) boyutunda, **ekranın ortasında**, görev çubuğunda sekmesi olan, başlık çubuğu ve boyutlandırma tutamacı olan gerçek bir pencere. Karakterin yanına yapışmıyor, kullanıcı taşıdıktan sonra yerini koruyor. Kapatınca yalnızca gizlenir, Nora sistem tepsisinde çalışmaya devam eder.
- **Karakter küçük:** Masaüstünde 132×312 px — sohbeti kapatmadan yanda durabilir.
- **Geniş balonlar:** Mesaj balonları 560 px'e kadar genişleyebilir; dar pencerede eskisi gibi küçülür.
- **Tek karakter, tek çizim:** Sistem tepsisi ikonu, sohbet başlığındaki avatar ve galeri görselleri aynı tam vücut çizicisinden üretilir.
- **Ayarlar:** Karakter stili artık üç seçenekli — *Tam vücut* (önerilen), *Portre*, *8-bit chibi*.
- **Düzeltmeler:** Yürüme/dans gibi sürekli hareketler artık gerçekten ilerliyor (sürekli katman saati duruyordu); göz kırpma 130 ms'de kapanıp açılıyor; kapalı göz çizimi irisi tamamen örtüyor; portre kırpması kare ve doğru boyutta.

## 1.11.0 · Gerçekçi karakter, cam sohbet paneli, tek dosya kurulum

- **Gerçekçi VTuber avatarı (varsayılan):** 260×360 yarı boy portre; kumral saç, yeşilimsi ela iris, yumuşak cilt gölgeleri, gerçek kirpik/çene/anatomik oranlar. 3× süper örnekleme + yumuşak ölçekleme ile "gerçekçi animasyon" hissi. Göz rengi, saç tonu, kıyafet ve aksesuar ayarlardan değişir; tüm pozlar (uyku, dans, izleme, dinleme, konuşma, sürüklenme…) korunur. Eski 8-bit chibi `NORA_CHARACTER=pixel` veya **Ayarlar → Karakter stili** ile geri gelir.
- **Cam (glass) sohbet paneli:** ChatGPT masaüstü tarzı; yuvarlatılmış saydam kart, arkasındaki ekranın bulanık kopyası, üst kenarda ince ışık çizgisi, yumuşak dış gölge, saydam mesaj balonları, animasyonlu "yazıyor" noktaları ve fade-in. Windows'ta gerçek DWM blur/acrylic denenir, desteklenmezse bulanık ekran anlık görüntüsü, o da olmazsa yalnızca saydam degrade kullanılır — hiçbir durumda donma/pencere kaybı yok.
- **Groq bağlantısı düzeltildi:** Anahtar artık ortam değişkeni şartı olmadan **sağ tık → 🔑 Groq Anahtarı Gir** veya **Ayarlar** üzerinden girilebilir; işletim sistemi anahtar kasasında (keyring) saklanır, `state.json`'a asla yazılmaz. Kasa yoksa anahtarın yalnızca oturum belleğinde tutulduğu açıkça söylenir. Bağlantı testi modele istek atmadan model listesini yoklar; 401/403/429/404/timeout için ayrı Türkçe mesajlar verir. Ayarlarda Groq sohbet modeli adı düzenlenebilir.
- **Tek dosya kurulum:** `python install.py` tek komutla sanal ortamı kurar, zorunlu paketleri + Piper'ı yükler ve `--doctor` teşhisini çalıştırır. `--full`, `--base`, `--features chat,piper`, `--no-venv`, `--doctor-only`, `--dev` seçenekleri vardır. Hiçbir model dosyası indirilmez, yönetici izni istenmez; Linux sistem paketleri **çalıştırılmadan** kopyalanabilir komut olarak yazdırılır. İsteğe bağlı bir özellik derlenemezse yalnızca o özellik atlanır.
- **Spotify: uygulama + gerçek çalma:** "spotify aç ve back in black çal", "back in black'i spotify'da çal", "spotify uygulamasını aç ve … çal" komutları artık şarkı adını ayıklar, masaüstü Spotify uygulamasını başlatır ve Web API bağlıysa **parçayı doğrudan uygulamada çalar** (`/me/player/play`, aktif cihaz seçimi). API yoksa uygulama araması açılır ve bunun bir arama olduğu açıkça söylenir; "çalıyorum" denip çalınmaması imkânsızdır.
- **Doküman/teşhis:** `--doctor` Groq anahtarının nereden geldiğini (ortam/kasa) değerini yazmadan bildirir. Karakter galerisi `docs/character/realistic/` altında yeni avatarla yeniden üretilir (`python tools/export_character.py`).

## 1.10.0 · Yerel model yönetimi ve iptal

- **İptal edilebilir yerel üretim:** GGUF yanıtları token akışıyla üretilir; sohbet/metin işlerinde ⏹ düğmesi güvenli noktada durdurur. İptal edilen yerel yanıt buluta gönderilmez, sohbet geçmişine yazılmaz. Bulut isteği ağda sürebilir ama iptal sonrası yanıtı kullanılmaz.
- **Model kataloğu:** GGUF/Piper içe aktarmaları `<model>.nora.json` yan dosyasında SHA-256, boyut, kaynak dosya/URL ve isteğe bağlı lisans notu tutar. `yerel modeller`, `gguf model bilgi/seç/doğrula`, `piper model bilgi/seç/doğrula` ve Özellikler menüsünden liste/seçim/doğrulama/not/silme yapılabilir. SHA-256 değişmemiş dosyayı gösterir; güvenlik/lisans kanıtı değildir.
- **Bağlam ve yanıt limiti:** Ayarlarda yerel bağlam 1024–8192, yanıt 128–2048 token; yanıt bağlamdan en az 128 token küçük olmalıdır. Eski geçmiş mesajları bütçeye göre kırpılır, en yeni kullanıcı mesajı korunur.
- **Güvenli içe aktarma/silme:** Kopyalama parça parça ve iptal edilebilir; yan dosya geçici alanda üretilip birlikte yerleştirilir. Üzerine yazma açık onay ister, başarısız değişimde önceki dosyalar korunur. Silme seçili modeli kaldırır ve geri alınamaz uyarısı gösterir.
- **Eklenti çakışma sınırı:** Aynı ifade başka pakette varsa kurulum reddedilir; elle yerleştirilmiş çakışmalarda ilk eşleşme sessizce çalışmaz, hata gösterilir. Dosya adı/kimlik eşleşmesi ve 20 paket sınırı doğrulanır.
- **Teşhis düzeltmesi:** `--doctor` GGUF/Piper/embedding dosyalarını gerçek `models/chat`, `models/piper`, `models/embeddings` alt klasörlerinde arar ve bütünlük kaydı durumunu raporlar.

## 1.9.1 · Kurulum ve kararlılık

- **Windows kurulum yardımcısı:** `tools/setup_windows.ps1` temel/local/embeddings/chat/piper/all seçenekleriyle sanal ortam kurar; yönetici izni, kalıcı execution-policy değişikliği veya otomatik model indirmesi yapmaz.
- **Başsız teşhis:** `python main.py --doctor [--check piper] [--json]` paket/model dosyası/veri klasörünü kontrol eder; PyQt, mikrofon, hoparlör, ağ veya Spotify kasası açmaz. Eksik zorunlu bileşenlerde çıkış kodu 1’dir.
- **Ayrı özellik paketleri:** Bir C++ derleme hatası tüm yerel özellikleri engellemesin diye `requirements-embeddings.txt`, `requirements-chat.txt`, `requirements-piper.txt` eklendi.
- **Ses kesme yarışı düzeltildi:** İptal edilen eski TTS işçisi yeni yanıtın kuyruğunu bozmaz; mikrofon, ses motoru gerçekten durmadan açılmaz. Kesme zaman aşımı görünürdür.
- **Model içe aktarma:** GGUF başlığı ve Piper JSON alanları doğrulanır; kopyalar geçici alanda hazırlanır, başarısız çok dosyalı değişimde önceki dosyalar geri yüklenir. Yerel sohbet üretimi sırasında kapatma arayüzü kilitlemez.
- **Dürüst durumlar:** Pano izleyicisi başlamazsa ayar geri kapatılır; Spotify oturumu kapatılır; token kasadan silinemediyse bu açıkça söylenir. Denetim kaydı yalnızca izinli eylem meta verisini yazar.
- Windows/Linux Python 3.11 CI iş akışı eklendi; gerçek cihaz/model/hesap testlerinin yerini tutmaz.

## 1.9.0 · İsteğe bağlı gelişmiş entegrasyonlar

- **Spotify Web API:** OAuth PKCE, sistem anahtar kasasında token, çalan parça/cihazlar ve gerçek çal-duraklat/sonraki/önceki kontrolü. Client secret yok; bağlantı yoksa durum açıkça söylenir.
- **Yerel anlam araması:** isteğe bağlı fastembed/MiniLM embedding modeli; not/hafıza/görevlerde hibrit arama. Model indirilmezse kelime aramasına döner, buluta geçmez.
- **Yerel sohbet:** kullanıcı tarafından içe aktarılan GGUF + llama-cpp-python. Yerel mod seçiliyken Groq’a sessiz fallback yok.
- **Piper TTS:** kullanıcı `.onnx` + `.onnx.json` modelini içe aktarır; kesilebilir yerel ses üretimi. Piper seçiliyken sistem sesine gizlice dönmez.
- **Sözünü kesme:** varsayılan kapalı; açıkken Nora konuşurken de tam yerel `hey nora` bekçisi dinler ve sesi keser. Kulaklık önerilir.
- **Pano geçmişi:** varsayılan kapalı, yalnızca bellek, 20 kayıt/30 dakika, hassas görünen metinleri atlama.
- **Eklentiler:** Python çalıştırmayan, doğrulanmış JSON komut paketleri; içe aktarma/etkinleştirme/çalıştırma onaylı. Örnek: `docs/plugins/study-pack.json`.

## 1.8.0 · Yerel companion ve güven paketi

- Windows wake-word `MicrophoneStream.read() got an unexpected keyword argument 'exception_on_overflow'` hatası düzeltildi; SpeechRecognition sarmalayıcısı ve PyAudio stilleri uyumlu okunur.
- Sabah brifingi, gün sonu özeti ve haftalık odak planı yalnızca yerel not/görev/hatırlatıcı/takvimden üretilir.
- Ruh hali + bağlılık puanı, kahve/kurabiye/ödül/özledim tepkileri; sayı tahmin mini oyunu.
- İzin merkezi, son 200 komutluk yerel denetim kaydı ve JSON veri dışa aktarma.
- Spotify OAuth olmadan işletim sistemi medya tuşlarıyla çal/duraklat/sonraki/önceki/durdur; çalan şarkı için pencere başlığı okunur, okunamazsa API gerektiği açıkça söylenir.
- Not/hafıza/görevlerde Türkçe bulanık yerel arama; son güvenli komutları rutin olarak kaydetme.

## Neler yapabilir?

### Karakter ve ses
- 120×150 şeffaf, always-on-top pet; 40×50 mantıksal ızgarada 3×3 keskin pikseller, keskin kenarlı 8-bit görünüm ve aynı tarzda tepsi ikonu. Varsayılan görünüm: beyaz wolfcut, kırmızı göz, siyah elbise, kırmızı ayakkabı; daha büyük parıltılı gözler, pembe yanaklar, kalp toka ve etek danteli. Yürüme, uyuma, zıplama, oturma, dans, esneme, göz kırpma, el sallama, sürüklenip düşme; piksel kalp, yıldız, nota ve uyku efektleri.
- Tüm poz/duygu PNG’leri ve animasyon GIF’leri `docs/character/` altında: 18 poz, 8 duygu, 24 animasyon, aksesuar/kıyafet varyantları ve `index.html` galerisi. Gerçekçi avatar çıktıları `docs/character/realistic/` altındadır. Üretici: `python tools/export_character.py` (`--style realistic|pixel|all`). Bunlar önizleme/doc çıktısıdır; uygulama çizimi yine QPainter’dır.
- **Karakter stili:** Varsayılan **tam vücut** (132×312). Diğerleri: **portre** (260×360) ve **8-bit chibi** (120×150) — **Ayarlar → Karakter stili** veya `NORA_CHARACTER=body|realistic|pixel`. Pencere boyutu stile göre değişir ve ayaklar yerde kalır.
- **Hareketler:** Sağ tık → **🐾 Hareketler** menüsünden jestler elle de tetiklenebilir; normalde her cevapta yapay zekâ seçer.
- **Komutla hareket:** “ikinci monitöre geç”, “uyu”, “uyan”, “dolaş”, “dur”, “zıpla”, “dans et”, “otur”. Bu komutlar Groq/internet olmadan çalışır.
- “Uyu” ve “dolaş” siz değiştirene kadar sürer. “Zıpla ve uyu” gibi en fazla dört açık hareket komutu arka arkaya çalışabilir.
- Çoklu monitör algılama, numaralı/sonraki/ana monitöre geçme, kenarlara yapışma ve görev çubuğu üstünde oturma.
- Kıyafet, saç rengi, gözlük/kulaklık/kurdele, animasyon ve otonom hareket ayarları; baş okşama tepkisi ve çift tıklama davranışı.
- Yerel **“Hey Nora”** bekçisi; yalnızca tam ifade duyulunca veya 🎤 basılınca komut dinler. Sizin metniniz kafasının üzerinde mor **“Sen: …”** balonunda görünür.
- Komut dinlerken elini kulağına götürür. Google STT veya isteğe bağlı **yerel Whisper** ile Türkçe komut tanıma; pyttsx3 sesli yanıt, ses/hız seçimi. Komut dinleme sırasında “Nora” adı “Nova/no ra/Noura” gibi yazıya geçirilirse yalnızca açık hitap veya sınırlı güvenli komut bağlamında düzeltilir; ne dediği/neyi anladığı sohbette görünür. **🗣️ Ses Tanıma Testi** komut çalıştırmadan transkripti gösterir.
- **Sürekli konuşma modu:** Nora cevap verdikten sonra tekrar dinler; `dinlemeyi bırak` / `sürekli konuşmayı kapat` ile durur. İki kez sessizlik olursa kendiliğinden bırakır.
- **Bas-konuş:** Ayarlardan seçilen global kısayola (varsayılan `Ctrl+Alt+Space`) basılı tutunca dinler, bırakınca cevaplar. Global kısayol için `requirements-local.txt` içindeki `keyboard` paketi gerekir; bazı sistemlerde yönetici izni isteyebilir.
- **Otonomi (varsayılan kapalı):** Kullanıcı açıkça açarsa Nora ara sıra ekranını/kamerasını inceleyebilir veya Spotify/YouTube araması açıp dans edebilir/video izleme pozuna geçebilir. Odak/sessiz modda ve gece sessizliğinde çalışmaz; aralık ayarlanabilir.
- **Medya:** `spotify aç ve back in black çal` Spotify masaüstü uygulamasını açar; API bağlıysa parçayı uygulamada çalar, değilse uygulama aramasını açar ve bunu söyler. `müzik aç`, `spotifyda lofi aç`, `video aç` arama açar; Nora dans eder veya mısır alıp izleme pozuna geçer. Spotify API bağlıysa `duraklat`, `sonraki şarkı`, `önceki şarkı`, `müziği durdur`, `şu an ne çalıyor` gerçek Web API kontrolüdür. API bağlı değilse OS medya tuşları kullanılır; API seçili ama token yoksa Nora bunu açıkça söyler.
- Havada uzun tutulunca rahatsız olup söylenir; düşüşte hareket çizgileri, yere inince kısa squash/toz animasyonu vardır. Video izleme ve landenme pozlarıPainter ile çizilir.
- Bot yanıtları merkezi sesli yanıt politikasından geçer; uzun yanıtlar kesilmeden cümlelere bölünür. Sohbet başlığındaki 🔊/🔇 göstergesi, tepsi **Sesli Yanıt Testi** ve “sesli yanıtı aç/kapat”, “ses testi” komutları sessiz kalma nedenini görünür kılar.

### Günlük yardımcılar
- **Kalıcı kişisel hafıza:** yalnızca “bunu hatırla” dediğiniz bilgiler saklanır; hitap ve kişilik tonu kişiselleştirilebilir.
- Kalıcı notlar, görev listeleri ve nottan görev çıkarma.
- **Kalıcı hatırlatıcılar:** göreli süre, saat/tarih, her gün, hafta içi ve her hafta; uygulama yeniden başlayınca kaybolmaz.
- Odak/çalışma, oyun, sessiz ve normal modlar. Odak sayacı; isteğe bağlı su/mola hatırlatmaları.
- Güvenli rutinler: uygulama/müzik açma, hareket, mod ve benzeri sınırlı adımları onaylı çalıştırma.
- Kelime/anagram oyunu ve 1-100 sayı tahmin oyunu; çift tıklayınca oyun açma seçeneği.
- **Companion:** `modun nasıl`, `kahve ver`, `kurabiye ver`, `ödül ver`, `seni özledim`; bağlılık 0-100 arasında yerelde saklanır.
- **Brifing:** `günaydın brifingi`, `gün sonu özeti`, `haftalık plan`; isteğe bağlı açılış brifingi.
- **Yerel arama:** `notlarımda kahve ara`, `hafızamda … ara`, `görevlerimde … ara`, `yerel ara …`; Türkçe normalize + bulanık eşleşme. `anlamsal ara …` veya ayar açıkken indirilmiş yerel embedding modeliyle hibrit arama; model yoksa yerel kelime araması.
- **Pano geçmişi:** `pano geçmişini aç/kapat`, `panoyu geçmişe ekle`, `pano geçmişi`, `pano 1 kopyala`, `pano geçmişi temizle`. İzleme varsayılan kapalı; kayıtlar diske yazılmaz.
- **Eklentiler:** `eklentiler`, `eklenti <id> aç/kapat`, `eklenti <id> <komut> çalıştır`; JSON komut paketleri yerleşik komutları gölgeleyemez, başka paketlerle aynı ifadeyi paylaşamaz ve Python/shell çalıştıramaz.
- **Sözünü kesme:** `sus` / `sözünü kes` anında TTS’i durdurur. `sözümü kesmeyi aç` ile konuşma sırasında tam `hey nora` da sesi keser; bu özellik mikrofonu konuşma boyunca açık tutar.
- **İzin/veri:** `izinleri göster`, `son işlemleri göster`, `denetim kaydını temizle`, `verilerimi dışa aktar`.
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
| `duraklat` / `sonraki şarkı` / `önceki şarkı` / `müziği durdur` | OS medya tuşları; OAuth yok |
| `şu an ne çalıyor` | Spotify pencere başlığı; okunamazsa dürüst uyarı |
| `günaydın brifingi` / `gün sonu özeti` / `haftalık plan` | Yerel görev/takvim/hatırlatıcı özeti |
| `kahve ver` / `kurabiye ver` / `ödül ver` / `modun nasıl` | Companion ruh hali ve bağlılık |
| `notlarımda kahve ara` / `yerel ara rapor` | Not/hafıza/görevlerde bulanık yerel arama |
| `sayı oyunu başlat` / `sayı tahminim 42` / `sayı oyununu bitir` | 1-100 tahmin oyunu |
| `izinleri göster` / `son işlemleri göster` / `verilerimi dışa aktar` | İzin merkezi, denetim kaydı, JSON export |
| `son komutları rutin kaydet: sabah` | Son güvenli komutları rutinleştirme |
| `spotify bağlan` / `spotify durumu` / `spotify cihazları` | OAuth PKCE bağlantısı ve cihaz listesi |
| `spotify bağlantısını kes` | Yerel token kaydını temizleme |
| `anlamsal arama modelini indir` / `yerel ai durumu` | Yerel embedding modeli ve durum |
| `spotify aç ve back in black çal` | Spotify uygulamasını açar ve parçayı çalar |
| `back in black'i spotify'da çal` | Aynı işlem, doğal Türkçe sıralamasıyla |
| `yerel modeller` / `model listesi` | GGUF + Piper model kataloğu |
| `gguf model seç` / `piper model seç v.onnx` | Yerel model seçimi |
| `gguf model bilgi a.gguf` / `piper model doğrula v.onnx` | Model meta verisi / SHA-256 doğrulaması |
| `yerel sohbet modu` / `bulut sohbet modu` | GGUF / Groq sohbet seçimi |
| `piper ses modu` / `sistem ses modu` | Piper / sistem TTS seçimi |
| `sus` / `sözünü kes` | Konuşmayı anında durdur |
| `sözümü kesmeyi aç/kapat` | Konuşurken tam `hey nora` ile kesme |
| `pano geçmişini aç` / `pano geçmişi` / `pano 1 kopyala` | Onaylı, bellek-içi pano geçmişi |
| `eklentiler` / `eklenti study-pack aç` | JSON eklenti yönetimi |
| `ekranımı izle` / `kamera incelemesini aç` / `otomatik medyayı aç` | Açıkça opt-in otonomi |

Serbest sohbet ve daha esnek ifadeler için Groq gerekir. Hareket komutları deterministik olduğundan internet kesilse de çalışır. Bilgisayarı kapatma, kod çalıştırma ve etkin pencereye yazma gibi işlemler yine ayrıca onay ister; “ne dersem yapsın” güvenlik onaylarını kaldırmaz.

### Gelişmiş isteğe bağlı paketler

Spotify token kasası temel paketteki `keyring` ile çalışır. Diğer özellikleri ayrı kurabilirsin:

| Özellik | Dosya | İçerik |
|---|---|---|
| Yerel ses/OCR/takvim/kısayol | `requirements-local.txt` | Whisper, RapidOCR, icalendar, keyboard |
| Anlam araması | `requirements-embeddings.txt` | fastembed |
| Yerel sohbet | `requirements-chat.txt` | llama-cpp-python |
| Piper TTS | `requirements-piper.txt` | piper-tts, sounddevice |
| Tümü | `requirements-ai.txt` | Yukarıdakilerin tümü |

```bash
# Tek komut: sanal ortam + zorunlu paketler + Piper + teşhis
python install.py

# Diğer seçenekler
python install.py --full             # tüm isteğe bağlı özellikleri dene
python install.py --base             # en küçük kurulum
python install.py --features chat    # yalnızca GGUF sohbeti
python install.py --doctor-only      # kurulum yapmadan teşhis

# İstersen eski yöntem de çalışır
python -m pip install -r requirements-piper.txt
python main.py --doctor --check piper
```

**Kurulum notları:** `install.py` model indirmez, yönetici izni istemez ve bir
özellik derlenemezse yalnızca onu atlar. Linux'ta Qt/PortAudio için gereken
`apt-get` satırı **çalıştırılmadan** yazdırılır.

### Groq anahtarı (2 dakika)

1. [console.groq.com/keys](https://console.groq.com/keys) adresinde ücretsiz anahtar oluştur.
2. Nora'yı aç → **sağ tık → 🔑 Groq Anahtarı Gir** (veya sohbet paneli → ⋯ → Groq anahtarı gir).
3. Anahtar işletim sistemi kasasına yazılır; `state.json`'a **girmez**.
4. **🩺 Groq Bağlantısı** ile model erişimini doğrula. Bağlanamıyorsan: 401 → anahtar yanlış, 404 → model adı eskimiş (Ayarlar → Groq sohbet modeli), 429 → hız limiti, timeout → ağ/proxy.

- `llama-cpp-python` bazı sistemlerde C++ derleme araçları isteyebilir; hazır wheel yoksa kurulum belgesi gerekir.
- Embedding modeli yaklaşık 220 MB olabilir; Nora açılışta indirmez. **Özellikler → Embedding modelini indir** açık onay ister.
- GGUF ve Piper modelleri otomatik indirilmez. **GGUF sohbet modeli içe aktar** / **Piper modeli içe aktar** ile dosyaları seçersin; Piper için `.onnx.json` yanında olmalıdır. İçe aktarma SHA-256 yan dosyası oluşturur; **Model bütünlüğü doğrula** dosyayı değiştirmeden kontrol eder, **Model kaynak/lisans notu** URL/lisans notunu yerelde saklar. SHA-256 modelin güvenli veya lisanslı olduğunu kanıtlamaz; model kartını kendin kontrol etmelisin.
- Spotify için kendi Developer uygulamanın Client ID’sini gir; redirect URI olarak `http://127.0.0.1:8765/callback` ekle. Gizli client secret istenmez. PKCE ve loopback kuralları: [1](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow) · [2](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri).

## Kurulum

Temel paket için Python **3.10+**. Yerel ses/OCR/takvim eklentileri için `requirements-local.txt` önerilir; RapidOCR üst paket kısıtı nedeniyle bu ek paket **Python 3.10–3.12** ister.

### Windows

Önerilen yardımcı (Python 3.10–3.12; yönetici gerekmez):

```powershell
# Temel kurulum. Özellik için: -Feature local / embeddings / chat / piper / all
powershell -ExecutionPolicy Bypass -File .\tools\setup_windows.ps1 -Feature base
.venv\Scripts\python.exe main.py --doctor
$env:GROQ_API_KEY = "gsk_..."
.venv\Scripts\python.exe main.py
```

`Bypass` yalnızca bu PowerShell süreci içindir; sistem politikasını kalıcı değiştirmez. Elle kurulum:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py --doctor
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

**Saklananlar:** ayarlar, açıkça kaydedilen kişisel bilgiler, notlar, görevler, hatırlatıcılar, rutinler, içe aktarılan takvim etkinlikleri, companion bağlılık/ruh hali, etkin eklenti kimlikleri, içe aktarılan GGUF/Piper modellerinin SHA-256/kaynak/lisans yan dosyaları ve isteğe bağlı son 200 komutluk denetim kaydı. Denetim kaydı komut metinlerini/pano içerğini değil eylem türünü yazar. Spotify ve Groq tokenları/anahtarı mümkünse sistem anahtar kasasında tutulur; JSON state’e yazılmaz. Groq anahtarı girildiğinde yalnızca `keyring` kaydı oluşur, `state.json` içinde anahtar araması boş döner. **Saklanmayanlar:** ham sohbet geçmişi, mikrofon sesi, kalıcı pano geçmişi. Pano geçmişi açıkça açılırsa yalnızca bellekte 30 dakika tutulur.
 Sohbet bağlamı oturumda son 30 mesajdır; “Sohbet Geçmişini Sıfırla” kişisel hafızayı silmez. Kişisel hafıza ayrı bir onaylı menüyle silinebilir.

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
| `GROQ_API_KEY` | boş | Serbest sohbet/vision/metin analizi anahtarı (ayarlardan girilen anahtarı geçersiz kılar) |
| `NORA_CHARACTER` | `sprite` | `sprite` (çizim), `body`, `realistic` veya `pixel` |
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
python main.py --doctor             # GUI/mikrofon/ağ açmadan kurulum teşhisi
python main.py --doctor --check piper --check chat  # özellik paket/model dosyaları
python main.py --doctor --json      # makinece okunabilir rapor
python main.py --version
```

## Gelişmiş özellik sorun giderme

- **Spotify:** `spotify bağlan` tarayıcıda izin ister. 8765 portu meşgulse başka uygulamayı kapat veya redirect ayarını kontrol et. 403 Premium/izin kısıtı, 404 aktif cihaz yok demektir; Nora sessizce başka hesaba/servise geçmez.
- **Piper:** `.onnx` ve `.onnx.json` birlikte olmalı. Piper seçiliyken model/ses cihazı hatası varsa sistem sesine gizlice dönmez; hatayı gösterir.
- **Yerel sohbet:** GGUF dosyası ve `llama-cpp-python` gerekir. Yerel modda model yoksa Groq’a geçilmez. RAM ve dosya boyutunu kontrol et. Uzun üretimde ⏹ ile iptal edebilirsin; iptal tokenlar arasında gerçekleşir, modelin o anki token hesabı bitmeden kesilmeyebilir. Bağlam/yanıt limiti ayarlarını modelin RAM kapasitesine göre seç.
- **Model bütünlüğü:** `gguf model doğrula a.gguf` / `piper model doğrula v.onnx` içe aktarma kaydındaki SHA-256 ile karşılaştırır. Kayıt yoksa veya dosya değiştiyse modeli kullanmadan önce güvenli kaynaktan yeniden içe aktar. Bu kontrol zararlı model içeriğini veya lisans uygunluğunu denetlemez.
- **Sözünü kesme:** hoparlör sesi mikrofona kaçarsa yanlış tetiklenebilir; kulaklık önerilir. Yalnızca tam `hey nora` kabul edilir, çıplak `Nora` kabul edilmez. Sistem TTS motorunun kesme desteği platforma göre değişebilir; bas-konuş ve `sus` her zaman alternatifdir.
- **Pano geçmişi:** parola/anahtar/kart/OTP gibi görünen metinler atlanır. Bu sezgisel bir filtredir; çok hassas ortamlarda izlemeyi kapalı tut.

## Ses tanıma sorun giderme

- `Yerel wake word döngüsü hatası: TypeError` görürsen güncel sürümde PortAudio’dan gelen `bytearray/memoryview` verisi PocketSphinx için `bytes`’a çevrilir ve hata ayrıntısı loglanır. Yine olursa PyAudio/mikrofon cihazını kontrol et; 🎤 düğmesi çalışmaya devam eder.
- `Microphone.MicrophoneStream.read() got an unexpected keyword argument 'exception_on_overflow'` hatası 1.8.0’da düzeltildi: SpeechRecognition sarmalayıcısı yalnızca `read(size)` kabul ettiği için Nora önce anahtar sözcükle dener, bu özel `TypeError` dışında hata yutmaz ve uyumluysa konumsal `read(size)` çağrısına düşer.

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
install.py                # tek dosya kurulum (venv + paketler + teşhis)
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
  nora_activities.py      # hatırlatıcı zamanlayıcı, modlar, kelime/sayı oyunu
  nora_briefing.py        # yerel sabah/gün sonu/haftalık brifing
  nora_companion.py       # ruh hali, bağlılık ve companion tepkileri
  nora_local_search.py    # not/hafıza/görevlerde Türkçe bulanık yerel arama
  nora_files.py           # sınırlı dosya bulma/taşıma/geri alma
  nora_calendar.py        # .ics okuma, etkinlik ve boş zaman listeleme
  nora_desktop.py         # Windows pencere düzeni kaydetme/geri yükleme
  nora_local_ai.py        # isteğe bağlı Whisper ve RapidOCR
  nora_embeddings.py      # isteğe bağlı yerel çok dilli embedding
  nora_sprite.py          # AI illüstrasyonları: yükleme, şeffaflık, duygu/jest eşleme
  nora_physics.py         # kaldırma/düşme/iniş aşama makinesi + atış fiziği
  nora_body.py            # tam vücut karakter çizicisi (yedek stil)
  nora_motion.py          # iskelet/hareket motoru; jestler zamana bağlı üretilir
  nora_avatar.py          # yarım boy gerçekçi portre (alternatif stil)
  nora_glass.py           # saydam camsı sohbet paneli (glassmorphism)
  nora_secrets.py         # Groq anahtarı: keyring/ortam, JSON'a yazılmaz
  nora_local_llm.py       # kullanıcı GGUF modeliyle akış/iptal destekli yerel sohbet
  nora_model_catalog.py   # GGUF/Piper SHA-256, kaynak/lisans yan dosyaları
  nora_piper.py           # kesilebilir yerel Piper TTS
  nora_spotify.py         # OAuth PKCE + Spotify Web API
  nora_clipboard.py       # onaylı, bellek-içi pano geçmişi
  nora_plugins.py         # güvenli JSON komut paketi eklentileri
  nora_diagnostics.py     # ağ/cihaz açmayan kurulum teşhisi
  nora_model_files.py     # model başlık doğrulama ve geçici kopyalı içe aktarma
  nora_settings_dialog.py # ayar paneli
  nora_proactive.py       # düşük frekanslı proaktif konuşma
  nora_ui.py              # sohbet/tray/worker entegrasyonu
tools/
  export_character.py     # QPainter çiziminden PNG/GIF galerisi üretir
  setup_windows.ps1       # ayrı özellikli Windows sanal ortam kurulumu
docs/
  character/              # tüm poz, duygu, aksesuar, kıyafet ve animasyon çıktıları
tests/
requirements.txt
requirements-local.txt
install.py
requirements-dev.txt
requirements-ai.txt
requirements-embeddings.txt
requirements-chat.txt
requirements-piper.txt
.github/workflows/tests.yml
docs/plugins/
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

Yerel tam ortamda **477 test** geçmiştir; offscreen GUI, 8-bit piksel ızgarası/keskinliği, tüm poz/animasyon dışa aktarımı, istenen siyah elbise-kırmızı ayakkabı-kırmızı göz-beyaz wolfcut paleti, eski görünüm migrasyonu, kıyafet-saç-aksesuar değişimi, tepsi ikonu, merkezi sesli yanıt politikası, TTS kuyruğu/yeniden deneme/hata görünürlüğü, komut şeması, sesli isim düzeltme/alternatif seçimi, ses tanıma testinin komut çalıştırmaması, bas-konuş/sürekli konuşma, opt-in otonomi, medya/dans/izleme, kaldırılma rahatsızlığı ve landenme animasyonu, kalıcı veri, hatırlatıcı tekrarları, modlar, dosya geri alma, takvim, gerçek sentetik görüntüyle OCR ve yerel STT’nin buluta geçmemesi, 1.8.0 mikrofon okuma uyumluluğu, brifing/companion/yerel arama/izin-denetim-export, sayı oyunu, Spotify PKCE/state/token kasası, yerel embedding/GGUF/Piper, pano geçmişi sınırları, JSON eklenti güvenliği ve sözünü kesme kontrol edilmiştir. 1.14.0 kapsamı: 8-bit ızgaranın bulanıksız çizilmesi, tam vücut (ayak/kol/el), logodan çıkma-içeri girme akışı, tek tıkta gıdıklanma ve kıkırdama, çift tıkta cam kişisel panel (ruh hâli/anılar/özel) ve panelin uygulamayla birlikte kapanması, AI jestlerinin piksel durumlarına eşlenmesi, mikrofonun kapalı olması ve TTS'in açık kalması, tepsi ikonunun tam blok hizası, oturma nefes animasyonu, yeşil irisin görünür olması, başlıkta tek avatar. 1.13.0 kapsamı: illüstrasyon sprite'larının yüklenmesi/şeffaflaştırılması/kırpılması, duygu→çizim eşlemesi, çapraz geçiş, yürüme ve koşma döngüsü + aynalama, kaldır/havada tut/bırak/düş/iniş/doğrul aşamaları, zaman bütçesinin aşamalar arasında tüketilmesi, atış fiziği ve duvar sınırları, çizim yokken dürüst yedek, ilk açılışta boş pencere hatası, `[MOVE]` jestlerinin çizim moduna eşlenmesi, tepsi ikonu/başlık avatarının aynı çizimden üretilmesi ve saç rengi tonlaması. Önceki kapsam: tam vücut çizimi (ayak/kollar/eller), 24 jestin her birinin poz üretmesi, zaman tabanlı hareket (fps'ten bağımsız), yürüme/dans katman saatinin ilerlemesi, göz kırpma, jest geçişlerinde sıçrama olmaması, `[MOVE:]` ayrıştırma/doğrulama (bilinmeyen jest, aşırı adım, sayı olmayan değer reddi), AI hareketinin pet'e ulaşması ve geçersizde duyguya göre yedek, sohbet panelinin normal büyük pencere olması (Qt.Tool değil), ekran ortasında açılması, kapatınca yalnızca gizlenmesi, geniş balonlar. Önceki kapsam: gerçekçi avatarda kumral saç/yeşil iris renk analizi, blink-dışı kare farkı, stil geçişinde pencere boyutu, cam panel saydamlığı, tipte "yazıyor" göstergesi, Groq anahtarının state.json'a yazılmaması ve kasa yokken dürüst uyarı, Spotify aç-ve-çal komutlarının şarkı adını doğru ayıklaması, API bağlı/bağlı değil davranışı, installer'ın sudo çalıştırmaması ve eski Python'u reddetmesi. Önceki kapsam: GGUF akış/iptal ve bağlam bütçesi, iptalin buluta geçirmemesi/geçmişe yazmaması, model SHA-256 doğrulama/silme/kaynak notu, iptal edilebilir kopyalama ve yan dosya commit'i, token limiti çapraz doğrulaması, Türkçe model komutları, eklenti ifade çakışması/dosya adı sınırı, teşhis alt klasörleri ve GUI iptal düğmesi. Fiziksel Windows mikrofonu, gerçek Groq anahtarı, indirilmiş Whisper/GGUF/Piper/embedding modelleri ve Spotify hesabı bu ortamda canlı doğrulanamamıştır. Windows/Linux CI iş akışı eklendi; uzak çalışma sonucu ayrı doğrulanır. Google’ın genel STT anahtarı ve üçüncü taraf servisler ileride değişebilir.
