#!/usr/bin/env python3
"""Tarla Pusulası — uygulama tanıtım turu (v1.0).

Ana penceredeki gerçek öğeleri sırayla vurgular (çevresi karartılır, öğe
aydınlık kalır) ve yanındaki kartta ne işe yaradığını anlatır.

  • Her görünümün ilk kullanımında bir kez gösterilir; kayıt kullanıcı klasöründe
    tanitim.json dosyasında tutulur (exe taşınsa da geçerlidir).
  • Araçlar > Özelleştirme > "Tanıtım turunu yeniden başlat" ile
    istenildiği zaman tekrar açılır.

Klavye: → / Enter sonraki · ← önceki · Esc turu kapatır.
Windows'ta vurgulanan öğe tamamen aydınlık görünür; başka sistemlerde öğe
yalnızca yeşil çerçeveyle işaretlenir.
"""
import os
import sys
import time
import tkinter as tk

import tarla_ayarlar
import tarla_dil

KEY = "#ff00fe"          # saydam delik rengi (yalnızca Windows'ta saydam olur)
DIM = "#05080a"
DIM_ALPHA = 0.62
CARD_W = 400


# ------------------------------------------------------------------ ilk açılış bayrağı
def flag_path():
    return os.path.join(tarla_ayarlar.app_dir(), "tanitim.json")


MODE_DETAILS = {
    "kolay": ("Günlük Rehber", "Tarlanı seç, ne ekebileceğine bak ve su ile risk durumunu birkaç adımda gör."),
    "gelismis": ("Analiz Merkezi", "Grafikleri, veri kaynaklarını ve uzun vadeli tarla planlarını ayrıntılı incele."),
}


def seen(mode):
    return tarla_ayarlar._read(flag_path()).get(mode) is True


def mark_seen(mode):
    path = flag_path()
    try:
        state = tarla_ayarlar._read(path)
        state[mode] = True
        tarla_ayarlar._write_json(path, state)
    except OSError:
        pass


def first_run(app):
    """Seçili görünümün tanıtımını ana ekran açıldığında göster."""
    mode = app.mode
    if not mode or seen(mode):
        return
    ticket = app._tour_ticket = object()
    t0 = time.perf_counter()

    def wait():
        if app._tour_ticket is not ticket or app.mode != mode or seen(mode):
            return
        ready = mode == "kolay" or bool(app.results) or time.perf_counter() - t0 > 15
        if ready and app._active_tab == app.layout_root and time.perf_counter() >= getattr(app, "_splash_end", 0):
            start(app)
        else:
            app.root.after(300, wait)
    app.root.after(350, wait)


# ------------------------------------------------------------------ adımlar
def _steps(app):
    if app.mode == "kolay":
        return [
            dict(target=None, title="Günlük Rehber", text=MODE_DETAILS["kolay"][1]),
            dict(target=lambda: [app.easy_search], title="Bölgeyi incele",
                 text="Şehrini veya ilçeni yazıp Bölgeyi incele düğmesine bas."),
            dict(target=lambda: [app.easy_cards["Tarlamı seç"]], title="Tarlamı seç",
                 text="Tarlanın köşelerini haritada sırayla işaretle. Kaydettiğin sınırı Tarlalarım’da yeniden açabilirsin."),
            dict(target=lambda: [app.easy_cards["Ne ekmeliyim?"]], title="Ne ekmeliyim?",
                 text="Sana en yakın koşullara uygun görünen ekinleri ve ekim aylarını karşılaştır."),
            dict(target=lambda: [app.easy_cards["Su ve gelecek"]], title="Su ve riskler",
                 text="Su ve gelecek ekin için tahmini su açığını gösterir. Riskler bölümünde hava, afet ve zararlılara bakabilirsin."),
            dict(target=lambda: [app.easy_cards["Özelleştirme"]], title="Özelleştirme",
                 text="Dili ve görünümü değiştir. Bu tanıtımı istediğin zaman buradan yeniden aç."),
        ]

    def attr(*names):
        def get():
            out = []
            for n in names:
                w = getattr(app, n, None)
                if w is not None:
                    out.append(w)
            return out
        return get

    def entry_and_go():
        out = []
        e = getattr(app, "entry", None)
        if e is not None:
            out.append(e.master)            # konum kutusunun çerçevesi
        if getattr(app, "go", None) is not None:
            out.append(app.go)
        return out

    def irrigation():
        sw = getattr(app, "sw", None)
        return [sw.master] if sw is not None else []

    def status():
        st = getattr(app, "status", None)
        return [st.master] if st is not None else []

    return [
        dict(target=None, title="Analiz Merkezi",
             text="Bu uygulama, seçtiğin konumun NASA POWER iklim verisine ve toprak bilgisine "
                  "bakarak hangi ekinin orada ne kadar iyi yetişeceğini 0–100 arası bir "
                  "uyum puanıyla gösterir.\n\nBu kısa tur ekrandaki her bölümün ne işe "
                  "yaradığını anlatır. İstediğin an “Turu atla” diyebilirsin; turu daha sonra "
                  "Araçlar › Özelleştirme bölümünden yeniden açabilirsin."),
        dict(target=entry_and_go, title="1 · Konumu yaz, Analiz et",
             text="Kutuya şehir, ilçe ya da “37.87, 32.48” gibi koordinat yaz; “Analiz et”e "
                  "bas ya da Enter'a dokun.\n\nUygulama o noktanın uzun yıllık aylık sıcaklık, "
                  "yağış, nem, güneş ve toprak nemi verisini NASA POWER'dan çeker. İnternet "
                  "yoksa yaklaşık örnek veri gösterilir; bu durum sol altta yazar."),
        dict(target=attr("map_btn"), title="2 · Tarlanı haritada seç",
             text="Uydu haritası açılır. Tarlanın köşelerine sırayla tıklayıp sınırını çiz.\n\n"
                  "• “Bu tarlayı kullan”: analiz tam o tarla için yapılır ve tarla "
                  "Tarlalarım'a eklenir.\n• “Bu tarlayı kaydet”: analiz yapmadan, verdiğin "
                  "adla kaydeder.\n\nTarla Takip Paneli, Tarla geçmişi ve Derin Uzay ikizi "
                  "gibi araçlar çizilmiş bir tarla ister."),
        dict(target=irrigation, title="3 · Sulama imkânın var mı?",
             text="Tarlanı sulayabiliyorsan bu anahtarı aç. Açıkken yağış ve toprak nemi "
                  "eksikliği puanı daha az düşürür, çünkü eksik suyun sulamayla "
                  "karşılanabileceği varsayılır. Sıralama hemen yeniden hesaplanır."),
        dict(target=attr("cv"), title="4 · En uygun ekin",
             text="Seçili ekinin özeti: adı, “Uygun / Sınırda / Uygun değil” etiketi, ne zaman "
                  "ekileceği ve sezon boyunca ne kadar su eksiği olacağı.\n\nSağdaki halka "
                  "uyum puanıdır (100 en iyisi). Alttaki rozetler “Sulama gerekir”, “Dengeli” "
                  "gibi kısa uyarılardır.\n\nKarta tıklarsan sıradaki ekine geçer."),
        dict(target=attr("cc"), title="5 · İklim grafiği",
             text="Konumun bir yılı:\n• Kahverengi çizgi: aylık ortalama sıcaklık (sol eksen, °C)\n"
                  "• Mavi çubuklar: aylık yağış (mm)\n• Açık yeşil alan: seçili ekinin "
                  "tarlada kaldığı aylar\n\nFareyi bir ayın üzerine getirince o ayın sıcaklık "
                  "ve yağışı görünür."),
        dict(target=attr("cf"), title="6 · Puanın bileşenleri",
             text="Uygulama sıcaklık, yağış, toprak nemi, bağıl nem, güneş ve donu ekinin istediği aralıklarla karşılaştırır. "
                  "Çok yıllık ekinlerde kış soğuklaması da hesaba katılır.\n\n"
                  "Her koşul ayrı puan alır. Bunlar ağırlıklı olarak birleştirilir: sıcaklık ve su daha fazla etkiler, "
                  "çok zayıf bir koşul toplam puanı düşürür. Örneğin sezon yağışı su ihtiyacından düşükse su puanı azalır.\n\n"
                  "75–100 uygun, 45–74 orta, 0–44 zayıf. Bu puan iklim ve ekin uyumunu gösterir. "
                  "Verim yüzdesi için tarla ölçümü gerekir."),
        dict(target=attr("cr"), title="7 · Tüm ekinler",
             text="Uygulamadaki tüm ekinler bu konum için puana göre sıralanır. Her satırda "
                  "ekim ayı ve türü (Tahıl, Çok yıllık …) yazar. Diğer ekinleri görmek için listeyi kaydır.\n\nBir ekine tıklarsan ekranın "
                  "geri kalanı (özet, grafik, bileşenler) o ekine göre güncellenir."),
        dict(target=attr("chat_panel", "tools_header"),
             title="8 · AI asistan ve rotasyon",
             text="• Tarla asistanı ekin listesinin altında. Ekrandaki sonuçlar hakkında soru sorabilirsin "
                  "(“Neden çavdar?”, “Sulamasız ne ekerim?”). Serbest soru için Özelleştirme'ye "
                  "OpenRouter API anahtarı girmen gerekir.\n\n• Ekim nöbeti önerileri: "
                  "Birkaç yıllık ekim nöbeti (rotasyon) planı önerir. Su, toprak sağlığı, pazar "
                  "ve risk önceliklerini sen ayarlarsın; en dengeli ekin sırasını arar."),
        dict(target=attr("tools_header"),
             title="9 · Gelecek ve riskler",
             text="• 10 yıllık iklim senaryosu: Seçili ekinin önümüzdeki 10 yılda iyi ve kötü "
                  "yıllarda nasıl sonuç verebileceğini, su açığını ve diğer ekinlerle "
                  "karşılaştırmasını gösterir. Buradan Tarla geçmişi'ne de ulaşırsın.\n\n"
                  "• Riskler: Eğim, deprem, kuraklık, sel ve haşere göstergeleri. "
                  "“Haşere riski” sekmesinde ekin için bilinen zararlılar ve tarlanın "
                  "çevresinde daha önce görülen zararlılara ait kayıtlar yer alır."),
        dict(target=attr("tools_header"), title="10 · Çalışma alanı",
             text="Planla, İzle ve Ayarlar’a tıklayarak ilgili araçları aç.\n\n"
                  "• Kaynak kaybı analizi: Su, gübre ve enerjinin ne kadarının boşa gittiğini "
                  "tahmin eder.\n• Tarla Takip Paneli: Tarlan için canlı panel ve harita "
                  "katmanları (çizilmiş tarla ister).\n• Veri & açıklanabilirlik: Kullanılan "
                  "veri kaynakları ve puanın nasıl hesaplandığı.\n• Frekans protokolü: Arduino "
                  "ile ses deneyi; tarımsal etkisi doğrulanmamıştır.\n• Özelleştirme: Açık/koyu "
                  "tema, dil (TR/EN/DE), AI anahtarı ve bu turu yeniden başlatma."),
        dict(target=attr("motion_btn"), title="11 · Hareket",
             text="Geçiş animasyonlarını açar ya da kapatır. Bilgisayarın yavaşsa ya da "
                  "hareketli ekranlar seni yoruyorsa kapatabilirsin; sonuçlar değişmez."),
        dict(target=attr("fields_btn"), title="12 · Tarlalarım",
             text="“Tarlalarım”da kaydettiğin "
                  "tarlalar listelenir. Her tarla için “Analiz et”, “Haritada aç” ve “Sil” "
                  "seçenekleri vardır."),
        dict(target=status, title="13 · Durum satırı",
             text="Sol alttaki yazı ne olduğunu söyler: verinin NASA POWER'dan mı geldiği "
                  "yoksa örnek veri mi olduğu, tarlanın kaydedildiği, bir hata olup olmadığı. "
                  "Bir şey beklediğin gibi gitmezse önce buraya bak."),
        dict(target=None, title="Hazırsın",
             text="Bir konum yazıp “Analiz et”e basarak başla ya da haritadan tarlanı çiz.\n\n"
                  "Bu turu tekrar görmek için: Araçlar › Özelleştirme › "
                  "“Tanıtım turunu yeniden başlat”."),
    ]


# ------------------------------------------------------------------ tur
def start(app):
    """Turu başlat (açık bir tur varsa öne getirir)."""
    old = getattr(app, "_tour", None)
    if old is not None and old.alive():
        old.card.lift()
        return old
    try:
        app._tour = Tour(app)
    except Exception as exc:            # tur bozulursa uygulama etkilenmesin, hata kayda geçsin
        import traceback
        try:
            os.makedirs(tarla_ayarlar.app_dir(), exist_ok=True)
            with open(os.path.join(tarla_ayarlar.app_dir(), "hata.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S] tanıtım turu\n"))
                f.write(traceback.format_exc())
        except OSError:
            pass
        try:
            app.set_status(f"Tanıtım turu açılamadı: {exc}", True)
        except Exception:
            pass
        app._tour = None
        return None
    mark_seen(app.mode)
    return app._tour


class Tour:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.G = sys.modules[type(app).__module__]      # güncel tema renkleri ve ANIM
        self.steps = _steps(app)
        self.i = 0
        self.hole = None                 # (x0, y0, x1, y1) ana pencereye göre
        self._anim = None
        self._cfg_job = None
        self.hole_ok = True
        self.ov = self.card = None
        try:
            self._build()
            self.show(0)
        except Exception:
            self.close()                # yarım kalmış karartma ekranı kapatmasın
            raise
        self._root_binding = self.root.bind("<Configure>", self._on_root_move, add="+")

    # -- pencereler
    def _build(self):
        G = self.G
        self.ov = tk.Toplevel(self.root)
        self.ov.overrideredirect(True)
        self.ov.configure(bg=DIM)
        try:
            self.ov.attributes("-transparentcolor", KEY)
        except tk.TclError:
            self.hole_ok = False         # Windows dışı: delik yok, yalnızca çerçeve
        try:
            self.ov.attributes("-alpha", DIM_ALPHA if self.hole_ok else 0.35)
        except tk.TclError:
            pass
        self.oc = tk.Canvas(self.ov, bg=DIM, highlightthickness=0, bd=0)
        self.oc.pack(fill="both", expand=True)
        self.oc.bind("<Button-1>", lambda e: self.card.focus_force())

        self.card = tk.Toplevel(self.root)
        self.card.overrideredirect(True)
        self.card.configure(bg=G.ACC2)
        inner = tk.Frame(self.card, bg=G.CARD)
        inner.pack(fill="both", expand=True, padx=2, pady=2)
        top = tk.Frame(inner, bg=G.CARD)
        top.pack(fill="x", padx=20, pady=(16, 0))
        self.count = tk.Label(top, text="", bg=G.CARD, fg=G.ACC, font=self.app.F(9, True))
        self.count.pack(side="left")
        skip = tk.Label(top, text="Turu atla  ✕", bg=G.CARD, fg=G.MUT2, cursor="hand2",
                        font=self.app.F(9))
        skip.pack(side="right")
        skip.bind("<Button-1>", lambda e: self.close())
        for code in ("de", "en", "tr"):
            choice = tk.Label(top, text=code.upper(), bg=G.CARD, fg=G.FG2,
                              cursor="hand2", font=self.app.F(9, True))
            choice.pack(side="right", padx=(0, 7))
            choice.bind("<Button-1>", lambda _event, code=code: self.change_language(code))
        self.title = tk.Label(inner, text="", bg=G.CARD, fg=G.FG, font=self.app.F(15, True),
                              wraplength=CARD_W - 40, justify="left", anchor="w")
        self.title.pack(fill="x", padx=20, pady=(8, 6))
        self.body = tk.Label(inner, text="", bg=G.CARD, fg=G.FG2, font=self.app.F(10),
                             wraplength=CARD_W - 40, justify="left", anchor="w")
        self.body.pack(fill="x", padx=20)
        self.dots = tk.Canvas(inner, bg=G.CARD, highlightthickness=0, bd=0, height=14,
                              width=CARD_W - 40)
        self.dots.pack(fill="x", padx=20, pady=(14, 0))
        nav = tk.Frame(inner, bg=G.CARD)
        nav.pack(fill="x", padx=20, pady=(12, 16))
        self.next_btn = self.app.button(nav, "İleri  →", self.next, primary=True, height=38)
        self.next_btn.configure(width=150)
        self.next_btn.pack(side="right")
        self.back_btn = self.app.button(nav, "←  Geri", self.back, ghost=True, height=38)
        self.back_btn.configure(width=100)
        self.back_btn.pack(side="right", padx=(0, 8))
        hint = tk.Label(nav, text="← → tuşları", bg=G.CARD, fg=G.MUT2, font=self.app.F(8))
        hint.pack(side="left")
        for w in (self.card, self.ov):
            w.bind("<Right>", lambda e: self.next())
            w.bind("<Return>", lambda e: self.next())
            w.bind("<Left>", lambda e: self.back())
            w.bind("<Escape>", lambda e: self.close())
        for w in (self.ov, self.card):
            try:
                w.attributes("-topmost", True)
            except tk.TclError:
                pass

    def alive(self):
        try:
            return self.card is not None and bool(self.card.winfo_exists())
        except tk.TclError:
            return False

    # -- geometri
    def _root_box(self):
        r = self.root
        r.update_idletasks()
        return r.winfo_rootx(), r.winfo_rooty(), r.winfo_width(), r.winfo_height()

    def _target_box(self, step):
        get = step.get("target")
        if not get:
            return None
        try:
            widgets = [w for w in get() if w is not None and w.winfo_exists() and w.winfo_ismapped()]
        except tk.TclError:
            widgets = []
        if not widgets:
            return None
        rx, ry, rw, rh = self._root_box()
        xs0, ys0, xs1, ys1 = [], [], [], []
        for w in widgets:
            x, y = w.winfo_rootx() - rx, w.winfo_rooty() - ry
            xs0.append(x)
            ys0.append(y)
            xs1.append(x + w.winfo_width())
            ys1.append(y + w.winfo_height())
        pad = 7
        return (max(2, min(xs0) - pad), max(2, min(ys0) - pad),
                min(rw - 2, max(xs1) + pad), min(rh - 2, max(ys1) + pad))

    def _paint(self, hole):
        rx, ry, rw, rh = self._root_box()
        self.ov.geometry(f"{rw}x{rh}+{rx}+{ry}")
        c = self.oc
        c.delete("all")
        c.create_rectangle(0, 0, rw + 2, rh + 2, fill=DIM, outline="")
        if hole:
            x0, y0, x1, y1 = hole
            if self.hole_ok:
                self.app.rrect(c, x0, y0, x1, y1, 14, fill=KEY, outline="")
            self.app.rrect(c, x0 - 3, y0 - 3, x1 + 3, y1 + 3, 16, fill="",
                           outline=self.G.ACC, width=3)

    def _place_card(self, hole):
        rx, ry, rw, rh = self._root_box()
        self.card.update_idletasks()
        cw, ch = self.card.winfo_reqwidth(), self.card.winfo_reqheight()
        gap = 18
        if hole is None:
            x, y = (rw - cw) / 2, (rh - ch) / 2.4
        else:
            x0, y0, x1, y1 = hole
            cy = (y0 + y1) / 2 - ch / 2
            if rw - x1 - gap >= cw:                      # sağında yer var
                x, y = x1 + gap, cy
            elif x0 - gap >= cw:                         # solunda
                x, y = x0 - gap - cw, cy
            elif rh - y1 - gap >= ch:                    # altında
                x, y = (x0 + x1) / 2 - cw / 2, y1 + gap
            elif y0 - gap >= ch:                         # üstünde
                x, y = (x0 + x1) / 2 - cw / 2, y0 - gap - ch
            else:                                        # büyük öğe: içine, sağ alta
                x, y = x1 - cw - 16, y1 - ch - 16
        x = min(max(12, x), rw - cw - 12)
        y = min(max(12, y), rh - ch - 12)
        self.card.geometry(f"{CARD_W}x{ch}+{int(rx + x)}+{int(ry + y)}")

    # -- akış
    def change_language(self, code):
        if code == tarla_dil.lang():
            return
        try:
            settings = tarla_ayarlar.save(dil=code)
        except OSError:
            self.app.set_status("Dil ayarı kaydedilemedi.", True)
            return
        self.app.apply_appearance(settings["tema"], settings["dil"])

    def refresh(self):
        if self.alive():
            self.show(self.i)

    def show(self, i):
        if not self.alive():
            return
        self.i = max(0, min(len(self.steps) - 1, i))
        step = self.steps[self.i]
        G = self.G
        n = len(self.steps)
        self.count.configure(text=f"{self.i + 1} / {n}")
        self.title.configure(text=step["title"])
        self.body.configure(text=step["text"])
        last = self.i == n - 1
        self.next_btn.set_text("Başla  ✓" if last else "İleri  →")
        self.back_btn.set_text("←  Geri" if self.i else " ")
        self.dots.delete("all")
        for k in range(n):
            x = 5 + k * 14
            on = k == self.i
            self.dots.create_oval(x - (4 if on else 3), 7 - (4 if on else 3),
                                  x + (4 if on else 3), 7 + (4 if on else 3),
                                  fill=G.ACC if on else (G.ACC2 if k < self.i else G.LINE2),
                                  outline="")
        target = self._target_box(step)
        self._animate_to(target)
        self.card.lift()
        self.card.focus_force()

    def _animate_to(self, target):
        start = self.hole
        if self._anim:
            try:
                self.root.after_cancel(self._anim)
            except tk.TclError:
                pass
            self._anim = None
        if not getattr(self.G, "ANIM", True) or start is None or target is None:
            self.hole = target
            self._paint(target)
            self._place_card(target)
            return
        t0 = time.perf_counter()
        ms = 260.0

        def frame():
            if not self.alive():
                return
            t = min(1.0, (time.perf_counter() - t0) * 1000 / ms)
            e = 1 - (1 - t) ** 3
            box = tuple(a + (b - a) * e for a, b in zip(start, target))
            self.hole = box
            self._paint(box)
            if t < 1:
                self._anim = self.root.after(12, frame)
            else:
                self._anim = None
        self._place_card(target)
        frame()

    def next(self):
        if self.i >= len(self.steps) - 1:
            self.close()
        else:
            self.show(self.i + 1)

    def back(self):
        if self.i > 0:
            self.show(self.i - 1)

    def _on_root_move(self, event=None):
        if (event is not None and event.widget is not self.root) or not self.alive():
            return
        if self._cfg_job:
            try:
                self.root.after_cancel(self._cfg_job)
            except tk.TclError:
                pass

        def redo():
            self._cfg_job = None
            if self.alive():
                self.hole = self._target_box(self.steps[self.i])
                self._paint(self.hole)
                self._place_card(self.hole)
                self.card.lift()
        self._cfg_job = self.root.after(60, redo)

    def close(self):
        for job in (self._anim, self._cfg_job):
            if job:
                self.root.after_cancel(job)
        self._anim = self._cfg_job = None
        binding = getattr(self, "_root_binding", None)
        if binding and sys.version_info >= (3, 13):
            self.root.unbind("<Configure>", binding)
            self._root_binding = None
        # Not: root.unbind(dizi, id) eski Python sürümlerinde o dizideki TÜM bağları siler;
        # bu yüzden bağ bırakılır, _on_root_move tur kapanınca hiçbir şey yapmaz.
        for w in (self.card, self.ov):
            try:
                if w is not None:
                    w.destroy()
            except tk.TclError:
                pass
        if getattr(self.app, "_tour", None) is self:
            self.app._tour = None
        try:
            self.root.focus_force()
        except tk.TclError:
            pass
