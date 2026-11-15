#!/usr/bin/env python3
"""Tarla Pusulası — premium masaüstü arayüzü (tkinter, ek kurulum yok).

Çalıştırma:  python tarla_masaustu.py
Aynı klasörde tarla_pusulasi.py ve ai_asistan.py bulunmalı.
"""
import json
import math
import queue
import re
import sys
import threading
import time
import tkinter as tk
import unicodedata
import webbrowser
from datetime import date, timedelta
from tkinter import font as tkfont, ttk
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import tarla_pusulasi as tp
import tarla_harita
import tarla_hasere
import tarla_tanitim
import tarla_gorsel
import tarla_ekin_simgeleri
import tarla_risk
import tarla_ikiz
import tarla_optimizer
import tarla_saha
import tarla_mc
import ai_asistan
import arduino_baglanti as ab
import tarla_arayuz
import tarla_pencere
import tarla_toprak
import tarla_ayarlar
import tarla_dil
import tarla_gorunum
import tarla_kaynak
import tarla_kayip
import tarla_anim as anim
from tarla_dil import NoTr
import os

# ------------------------------------------------------------------ tema
PALETTES = {
    # Koyu tema: neredeyse siyah, hafif yeşil zemin + nane yeşili vurgu
    "koyu": dict(
        BG="#10161e", SIDE="#151d27", CARD="#1b2530", CARD2="#222e3b", CARD3="#2b3948",
        LINE="#1d2622", LINE2="#2a3630", FG="#f2f6f3", FG2="#cdd8d1", MUT="#8b9c92",
        MUT2="#63746a", ACC="#7cf0a8", ACC2="#37a06b", ACC_SOFT="#16241d", GOLD="#e8c07d",
        WATER="#6fb8e8", BAD="#ee8874", GLOW="#132019", SHADOW="#050807", BAND="#24543c",
        ACC_HOVER="#8bf5b4", ON_ACC="#06130c", ERR_BG="#1d1412",
        EASY_BG="#0b0e0d", EASY_CARD="#131916", EASY_HOVER="#1b2520", EASY_EDGE="#304039",
        EASY_ACC="#8cebb0", EASY_ACTION="#399968", EASY_ACTION_HOVER="#51b780", EASY_INK="#06160e"),
    # Açık tema: beyaz yüzeyler; yeşiller yeşil kalır, beyaz zeminde okunacak tonda
    "acik": dict(
        BG="#f0f3f6", SIDE="#f8fafc", CARD="#ffffff", CARD2="#eaf0f5", CARD3="#dce8ef",
        LINE="#dfe6e2", LINE2="#c3d0c8", FG="#0d1712", FG2="#2b3a32", MUT="#56675d",
        MUT2="#69796f", ACC="#15854a", ACC2="#1a9656", ACC_SOFT="#e2f4e9", GOLD="#9a6408",
        WATER="#22689f", BAD="#c0412b", GLOW="#e3f3e9", SHADOW="#d9e1dc", BAND="#c8e9d5",
        ACC_HOVER="#1a9656", ON_ACC="#ffffff", ERR_BG="#fbeae6",
        EASY_BG="#f0f6f2", EASY_CARD="#fbfdfb", EASY_HOVER="#e7f2eb", EASY_EDGE="#b8cfc2",
        EASY_ACC="#176540", EASY_ACTION="#21764d", EASY_ACTION_HOVER="#195e3e", EASY_INK="#f4fff9"),
}
ACCENT_PALETTES = {
    "varsayilan": ("Varsayılan", {}),
    "okyanus": ("Mavi ve turkuaz", {"koyu": ("#86C3F8", "#65DCC9"), "acik": ("#185A96", "#11776B")}),
    "lavanta": ("Mor ve pembe", {"koyu": ("#C9AEFF", "#F5A6CB"), "acik": ("#633BA0", "#A03370")}),
    "toprak": ("Kehribar ve zeytin", {"koyu": ("#F3BC68", "#B7D27E"), "acik": ("#8D5409", "#526D28")}),
    "sahil": ("Adaçayı ve mercan", {"koyu": ("#A9D5B1", "#F2A794"), "acik": ("#37684D", "#A44838")}),
    "gunbatimi": ("Gül kurusu ve lacivert", {"koyu": ("#F1AAC2", "#A9B9EF"), "acik": ("#963F61", "#3B538F")}),
}
THEME = {"name": "koyu", "accent": "varsayilan"}


def apply_theme(name, accent="varsayilan"):
    """Renk sabitlerini seçili temaya çevirir. Sonraki tüm çizimler yeni renkleri kullanır."""
    name = name if name in PALETTES else "koyu"
    accent = accent if accent in ACCENT_PALETTES else "varsayilan"
    THEME.update(name=name, accent=accent)
    colors = PALETTES[name].copy()
    pair = ACCENT_PALETTES[accent][1].get(name)
    if pair:
        primary, secondary = pair
        colors.update(ACC=primary, ACC2=primary, ACC_HOVER=primary, WATER=secondary, EASY_ACC=primary)
    globals().update(colors)
    tarla_gorunum.set_theme(name, PALETTES, colors)


apply_theme("koyu")
MON = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"]
# Türkiye'nin nüfus ve tarımsal üretim açısından en büyük şehirleri
# Türkiye'nin en büyük 8 şehri (nüfus + tarımsal üretim)
CACHE = {}
HIST_CACHE = {}        # (enlem, boylam) -> geçmiş yıl sapmaları (10 yıllık senaryo)
PARCEL_SLOPE_CACHE = {}  # (enlem, boylam) -> parsel eğimi (%)
SLOPE_CACHE = {}       # (enlem, boylam) -> eğim (Copernicus DEM; optimizasyon erozyonu)
YEAR0 = 2026
MIN_FONT = 10            # arayüzdeki en küçük yazı boyutu (punto)
ANIM = True             # açılış / geçiş animasyonları (kapatmak için False)
WIN_ANIM_MS = 260       # pencere açılış süresi (ms)
UI = 1.0                # ekran ölçeği: %125 (120 dpi) ve altı = 1.0; %150 = 1.2 (App kurulunca ayarlanır)


def dpx(value):
    """Arayüz %125 Windows ölçeğine göre çizildi. Yazılar (punto) ekran ölçeğiyle büyüdüğü
    için sabit piksel ölçüleri de aynı oranda büyütülür; %125 ve altında değer değişmez."""
    return value * UI


def dipx(value):
    return int(round(value * UI))

FACTOR_LABELS = [("sicaklik", "Sıcaklık"), ("su", "Su (yağış)"), ("toprak_nemi", "Toprak nemi"),
                 ("nem", "Bağıl nem"), ("gunes", "Güneş"), ("don", "Don riski"),
                 ("soguklama", "Soğuklama")]


def f0(x):
    return str(int(round(x)))


def f1(x):
    value = f"{x:.1f}"
    return value if tarla_dil.lang() == "en" else value.replace(".", ",")


def md_blocks(text):
    """Asistan yanıtını sade bloklara ayır: ('h' başlık | 'li' madde | 'p' paragraf, metin)."""
    plain = lambda t: re.sub(r"\*\*(.+?)\*\*", r"\1", t).replace("`", "").strip()
    out = []
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        li = re.match(r"^[-*•]\s+(.*)$", line)
        if li:
            out.append(("li", plain(li.group(1))))
        elif re.match(r"^#{1,4}\s+", line) or re.fullmatch(r"\*\*[^*]+\*\*:?", line):
            out.append(("h", plain(re.sub(r"^#+\s+", "", line))))
        else:
            out.append(("p", plain(line)))
    return out


def tier_of(s):
    return "Uygun" if s >= 75 else "Orta" if s >= 45 else "Zayıf"


def tier_color(s):
    return ACC if s >= 75 else GOLD if s >= 45 else BAD


def lerp(c1, c2, t):
    a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def window_label(r):
    if not r["ekim_ayi"]:
        return "yıl boyu"
    a, b = r["aylar"][0], r["aylar"][-1]
    return f"{MON[a]}–{MON[b]} ({r['sure_ay']} ay)"


def factor_rows(r):
    k, f = r["kriter"], r["faktorler"]
    rows = [
        ("Sıcaklık", f["sicaklik"], f"{f1(r['ortalama_sicaklik'])} °C",
         f"ideal {k['t'][1]}–{k['t'][2]} °C"),
        ("Su (yağış)", f["su"], f"{f0(r['toplam_yagis_mm'])} mm",
         f"ihtiyaç ≈ {f0(k['need'])} mm"),
        ("Toprak nemi", f["toprak_nemi"], f"%{f0(r['kok_bolgesi_nemi'] * 100)}",
         f"ideal %{f0(k['soil'][1] * 100)}–%{f0(min(k['soil'][2], 1) * 100)}"),
        ("Bağıl nem", f["nem"], f"%{f0(r['bagil_nem'])}",
         f"ideal %{k['rh'][1]}–{k['rh'][2]}"),
        ("Güneş", f["gunes"], f"{f1(r['ortalama_gunes'])} kWh/m²",
         f"en az {f1(k['sun'])}"),
        ("Don riski", f["don"], f"{f1(r['en_soguk_gece'])} °C",
         f"en az {k['frost']} °C"),
    ]
    if r["ekim_ayi"] is None:
        rows.append(("Soğuklama", f["soguklama"], f"{f0(r['soguklama'])} birim",
                     "kış dinlenmesi"))
    return rows


# ------------------------------------------------------------------ kayıtlı tarlalar
def fields_path():
    """Kayıtlı tarlalar kullanıcı klasöründe saklanır (ayarlarla aynı yer)."""
    return os.path.join(tarla_ayarlar.app_dir(), "tarlalarim.json")


_fields_lock = threading.Lock()


def load_fields():
    try:
        with open(fields_path(), encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return []
        fields = []
        for record in data:
            if not isinstance(record, dict):
                continue
            try:
                geometry = tarla_harita.describe_field(record.get("noktalar"))
            except ValueError:
                continue
            if geometry["kose"] >= 3:
                fields.append(dict(record, **geometry))
        return fields
    except (OSError, ValueError):
        return []


def write_fields(fields):
    tarla_ayarlar._write_json(fields_path(), [field_record(field) for field in fields])


def points_key(points):
    return tuple(sorted((round(p[0], 5), round(p[1], 5)) for p in (points or [])))


def field_record(field):
    """Tarla kaydının JSON'a yazılabilen kısmı (uydu görseli gibi nesneler atlanır)."""
    rec = {}
    for k, v in (field or {}).items():
        if k == "gorsel":
            continue
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            continue
        rec[k] = v
    return rec


class App:
    def __init__(self, root):
        self.root = root
        global UI
        try:            # %150 ve üstü ölçeklerde sabit pikseller yazıyla birlikte büyüsün
            ratio = root.winfo_fpixels("1i") / 120.0
            UI = 1.0 if ratio < 1.05 else min(2.0, ratio)
        except tk.TclError:
            UI = 1.0
        root.title("Tarla Pusulası · NASA Space Apps 2026")
        root.minsize(1000, 700)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        w = min(1340, sw - 40)
        h = min(880, sh - 90)
        root.geometry(f"{w}x{h}+{max(0, (sw - w) // 2)}+{max(0, (sh - h) // 3)}")
        root.configure(bg=BG)
        fams = set(tkfont.families())
        self.fam = next((c for c in ("Segoe UI", "Inter",
                                     "Helvetica Neue", "Ubuntu", "DejaVu Sans") if c in fams),
                        "TkDefaultFont")
        self._fonts = {}
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont',
                     'TkCaptionFont', 'TkSmallCaptionFont', 'TkIconFont', 'TkTooltipFont'):
            tkfont.nametofont(name).configure(family=self.fam, size=10)
        self.q = queue.Queue()
        self.busy = False
        self.irr = False
        self.clim = self.name = self.kaynak = self.soil = None
        self.results = []
        self.sel = None
        self.hover = None
        self.hits = []
        self.ai_msgs, self.ai_ctx_key = [], None
        self.last_outlook = None                    # son 10 yıllık senaryo (asistan bağlamı)
        self.page = 0
        self.lat = self.lon = None      # son analiz edilen konum
        self.field = None               # haritadan seçilen tarla (yoksa None)
        self.map_server = None
        self.ring_t = 1.0               # halka + faktör çubukları dolma oranı (animasyon)
        self.intro_t = 1.0              # sıralama ve yağış çubukları (analiz sonrası)
        self.last_risk = None           # son afet/erozyon değerlendirmesi (asistan bağlamı)
        self.last_opt = None            # son rotasyon optimizasyonu (asistan + saha modu)
        self.opt_prefs = None           # optimizasyon penceresi tercihleri
        self.mode = tarla_ayarlar.load()["mod"]
        self.location_query = tk.StringVar(root, "Konya")
        # ---- animasyon durumu
        self.ticker = anim.Ticker(root, lambda: ANIM)
        self.swap_t = 1.0               # seçili ekin değişince içerik kayarak gelir
        self.card_t = 1.0               # yeni analizde kartlar sırayla yükselir
        self._sw_k = 0.0                # sulama anahtarı topuzu (0 kapalı, 1 açık)
        self._hov_y = self._sel_y = None   # sıralamadaki kayan vurgu kutuları
        self._target_hov = self._target_sel = None
        self._tip = None                # iklim grafiği ipucu {x, tx, m}
        self._logo_spin = -10.0         # logo iğnesinin dönüş başlangıcı
        self._t_start = time.perf_counter()
        self._freq_init()
        self._build_tabs()
        self._tour = None               # açık tanıtım turu
        self._build()
        self._build_easy_home()
        if self.mode:
            self._apply_mode(self.mode)
        self.wheel_router = tarla_arayuz.WheelRouter(root)
        root.protocol("WM_DELETE_WINDOW", self.close_app)
        self.apply_layout()
        if self.mode:
            self._splash()
        else:
            self._show_mode_picker()
        self._fade_in(root, ms=180)
        self.ticker.add("ambient", self._ambient)
        self.root.after(100, self._poll)
        self._show_startup_example()
        if "--demo" not in sys.argv:
            self.analyze("Konya", fallback=True)
        if self.mode:
            tarla_tanitim.first_run(self)

    def _show_mode_picker(self):
        home_layout = [(widget, widget.pack_info()) for widget in self.root.pack_slaves()]
        for widget, _ in home_layout:
            widget.pack_forget()
        page = tk.Frame(self.root, bg=BG, takefocus=True)
        page.place(relwidth=1, relheight=1)
        page.lift()
        panel = tk.Frame(page, bg=BG)
        panel.place(relx=.5, rely=.49, anchor="center", relwidth=.80)
        tk.Label(panel, text="Tarla Pusulası", bg=BG, fg=ACC, font=self.F(13, True)).pack(pady=(0, 12))
        tk.Label(panel, text="Nereden başlamak istersin?", bg=BG, fg=FG, font=self.F(28, True)).pack()
        tk.Label(panel, text="İki görünüm de aynı tarla verilerini kullanır.", bg=BG, fg=FG2,
                 font=self.F(12)).pack(pady=(8, 22))
        error = tk.Label(panel, text="", bg=BG, fg=BAD, font=self.F(10))

        def choose(mode):
            try:
                tarla_ayarlar.save(mod=mode)
            except OSError as exc:
                error.configure(text="Ayarlar kaydedilemedi: " + str(exc))
                return
            page.destroy()
            for widget, placement in home_layout:
                widget.pack(**placement)
            self._apply_mode(mode)
            self._tabs[self.layout_root][2].focus_set()
            tarla_tanitim.first_run(self)

        options = tk.Frame(panel, bg=BG)
        options.pack(fill="x")
        buttons = []
        for column, (mode, (title, detail)) in enumerate(tarla_tanitim.MODE_DETAILS.items()):
            options.columnconfigure(column, weight=1, uniform="mode")
            box = tk.Frame(options, bg=CARD, padx=19, pady=18, highlightthickness=1, highlightbackground=LINE2)
            box.grid(row=0, column=column, sticky="nsew", padx=6)
            tk.Label(box, text=title, bg=CARD, fg=ACC, font=self.F(18, True)).pack(anchor="w")
            desc = tk.Label(box, text=detail, bg=CARD, fg=FG2, font=self.F(11), justify="left")
            desc.pack(anchor="w", pady=(8, 18))
            box.bind("<Configure>", lambda e, label=desc: label.configure(wraplength=max(120, e.width - 44)))
            button = self.button(box, "Bu görünümle başla", lambda mode=mode: choose(mode), primary=True, height=44)
            button.pack(side="bottom", fill="x")
            buttons.append(button)
        tk.Label(panel, text="İstersen Özelleştirme’den görünümü değiştirebilirsin.", bg=BG, fg=FG2,
                 font=self.F(11)).pack(pady=(18, 0))
        error.pack(pady=(6, 0))
        buttons[0].focus_set()
        if ANIM:
            self._tween(430, lambda t: panel.place_configure(y=round(22 * (1 - t))), page)

    # ------------------------------------------------------------ yardımcı
    def F(self, size, bold=False):
        size = max(size, MIN_FONT)      # küçük yazılar gözü yorar: alt sınır
        key = (size, bold)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(family=self.fam, size=size,
                                           weight="bold" if bold else "normal")
        return self._fonts[key]

    def tw(self, text, size, bold=False):
        return self.F(size, bold).measure(tarla_dil.tr(text))     # ekrandaki (çevrilmiş) hâli

    @staticmethod
    def fitted_text(text, font, width):
        if font.measure(text) <= width:
            return text
        while text and font.measure(text.rstrip() + "…") > width:
            text = text[:-1]
        return text.rstrip() + "…" if text else ""

    @staticmethod
    def rrect(c, x0, y0, x1, y1, r, **kw):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1,
               x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return c.create_polygon(pts, smooth=True, **kw)

    def panel(self, c, x0, y0, x1, y1, r=16, fill=None, outline=None, glow=False):
        fill = CARD if fill is None else fill
        outline = LINE if outline is None else outline
        """Gölgeli kart zemini: katmanlı yumuşak gölge + kenarlık + üstte ince ışık."""
        bg = c["bg"] if isinstance(c["bg"], str) and c["bg"].startswith("#") else BG
        for k, (dy, t) in enumerate(((5, .35), (3, .7))):
            self.rrect(c, x0 + 2 - k, y0 + dy, x1 - 2 + k, y1 + dy, r,
                       fill=lerp(bg, SHADOW, t), outline="")
        if glow:
            self.rrect(c, x0 - 1, y0 - 1, x1 + 1, y1 + 1, r + 1, fill="", outline=outline, width=1)
        self.rrect(c, x0, y0, x1, y1, r, fill=fill, outline=outline, width=1)
        # üst kenarda ince ışık çizgisi: kart hafif kabarık görünür
        c.create_line(x0 + r, y0 + 1.5, x1 - r, y0 + 1.5,
                      fill=lerp(fill, FG, .07 if THEME["name"] == "koyu" else .0), width=1)

    def pill(self, c, x, y, text, color, size=8, filled=False, dot=False):
        w = self.tw(text, size, True) + (34 if dot else 24)
        self.rrect(c, x, y, x + w, y + 26, 13,
                   fill=color if filled else ACC_SOFT if color == ACC else CARD2,
                   outline="" if filled else LINE2, width=1)
        tx = x + w / 2
        if dot:
            c.create_oval(x + 12, y + 11, x + 20, y + 19, fill=color, outline="")
            tx = x + w / 2 + 6
        c.create_text(tx, y + 13, text=text,
                      fill=BG if filled else color, font=self.F(size, True))
        return x + w + 8

    def chip(self, c, x, y, text, color, size=8):
        w = self.tw(text, size) + 22
        self.rrect(c, x, y, x + w, y + 24, 8, fill=CARD2, outline="")
        c.create_text(x + w / 2, y + 12, text=text, fill=color, font=self.F(size))
        return x + w + 7

    def card(self, parent, **kw):
        return tk.Canvas(parent, bg=BG, highlightthickness=0, bd=0, **kw)

    def button(self, parent, text, cmd, primary=False, small=False, ghost=False, icon="",
               height=None, radius=None, icon_size=10):
        """Yuvarlak köşeli (hap biçimli) buton: Canvas üzerine çizilir.

        Fareyle üzerine gelince renk ~120 ms'de yumuşakça geçer; basılıyken koyulaşır.
        Basıp düğmenin dışında bırakılırsa komut çalışmaz.
        """
        min_height = dipx(height or (30 if small else 42))
        bg = ACC if primary else (SIDE if ghost else CARD2)
        border = "" if (primary or ghost) else LINE2
        fg = ON_ACC if primary else (MUT if ghost else FG2)
        cv = tk.Canvas(parent, bg=parent["bg"], highlightthickness=0, bd=0,
                       height=min_height, cursor="hand2", takefocus=True)
        label = text
        font = self.F(10, primary)
        state = {"bg": bg, "fg": fg, "hover": False, "pressed": False, "active": False,
                 "border": border, "k": 0.0, "target": 0.0, "job": None,
                 "ripple": None, "busy": False}
        key = "btn%d" % id(cv)

        def paint():
            try:
                cv.delete("all")
                w = cv.winfo_width()
            except tk.TclError:
                return
            if w < 4:
                return
            translated = tarla_dil.tr(label)
            has_mark = bool(icon or state["busy"]) and w >= 100
            inset_text = dpx(32) if has_mark else 7
            text_width = max(1, w - inset_text - 8)
            probe = cv.create_text(0, 0, text=NoTr(translated), font=font, width=text_width)
            bounds = cv.bbox(probe)
            cv.delete(probe)
            h = max(min_height, bounds[3] - bounds[1] + 12)
            if cv.winfo_pixels(cv.cget("height")) != h:
                cv.configure(height=h)
            r = min(radius if radius is not None else 11, w / 2, h / 2)
            blend()
            bb = state["bg"]
            if state["pressed"]:
                bb = lerp(bb, "#000000", .18)
            inset = 1.5 if state["pressed"] else 0      # basınca hafifçe içe çöker
            x0 = (2 if state["hover"] and state["border"] else 1) + inset
            edge = ACC2 if state["active"] else state["border"]
            if edge and state["k"] > 0 and not state["active"]:
                edge = lerp(edge, MUT2, state["k"] * .6)
            if primary and state["k"] > 0:              # birincil buton: hover'da dış hale
                self.rrect(cv, 0, 0, w, h, r, fill="", outline=lerp(cv["bg"], ACC, .45 * state["k"]),
                           width=1)
            self.rrect(cv, x0, 1 + inset, w - x0, h - 1 - inset, max(2, r - inset),
                       fill=bb, outline=edge)
            rp = state["ripple"]
            if rp is not None:                          # tıklama dalgası (buton biçiminde)
                e = anim.clamp((time.perf_counter() - rp[1]) / .45)
                R = anim.out_cubic(e) * (w + 20)
                a0, a1 = max(x0, rp[0] - R), min(w - x0, rp[0] + R)
                if a1 - a0 > 4:
                    shine = lerp(bb, "#ffffff" if THEME["name"] == "koyu" else "#000000",
                                 .22 if primary else .12)
                    self.rrect(cv, a0, 1 + inset, a1, h - 1 - inset,
                               min(max(2, r - inset), (a1 - a0) / 2),
                               fill=lerp(shine, bb, anim.in_cubic(e)), outline="")
            busy = state["busy"]
            cv.create_text(inset_text + text_width / 2, h / 2, text=label, fill=state["fg"], font=font,
                           width=text_width, justify="center")
            if has_mark and busy:
                ang = (time.perf_counter() * 420) % 360 if ANIM else 0
                cv.create_arc(10, h / 2 - 6, 22, h / 2 + 6, start=-ang, extent=110,
                              style="arc", outline=state["fg"], width=2)
            elif has_mark:
                cv.create_text(dpx(17), h / 2, text=icon, fill=state["fg"], font=("Segoe UI Symbol", icon_size))

        def live(now):
            try:
                if not cv.winfo_exists():
                    return False
            except tk.TclError:
                return False
            rp = state["ripple"]
            if rp is not None and now - rp[1] > .45:
                state["ripple"] = rp = None
            paint()
            return bool(state["busy"] or rp is not None)

        def wake():
            if ANIM:
                self.ticker.add(key, live)

        def blend():
            base_bg = ACC_SOFT if state["active"] else ACC if primary else SIDE if ghost else CARD2
            base_fg = ACC if state["active"] else ON_ACC if primary else MUT if ghost else FG2
            hover = ACC_HOVER if primary else CARD3
            fg_h = ON_ACC if primary else FG
            state["border"] = "" if primary or ghost else LINE2
            state["bg"] = lerp(base_bg, hover, state["k"])
            state["fg"] = lerp(base_fg, fg_h, state["k"])

        def glide(target):
            state["target"] = target
            if not ANIM:
                state["k"] = target
                blend()
                paint()
                return
            if state["job"]:
                return

            def step():
                try:
                    if not cv.winfo_exists():
                        return
                except tk.TclError:
                    return
                d = state["target"] - state["k"]
                if abs(d) < .03:
                    state["k"], state["job"] = state["target"], None
                else:
                    state["k"] += d * .38
                    state["job"] = cv.after(16, step)
                blend()
                paint()
            step()

        def release(e):
            state["pressed"] = False
            paint()
            if 0 <= e.x <= cv.winfo_width() and 0 <= e.y <= cv.winfo_height():
                cmd()

        cv.bind("<Return>", lambda _e: cmd())
        cv.bind("<space>", lambda _e: cmd())
        cv.bind("<Configure>", lambda e: paint())
        cv.bind("<Enter>", lambda e: (state.update(hover=True), glide(1.0)))
        cv.bind("<Leave>", lambda e: (state.update(hover=False, pressed=False), glide(0.0)))
        def press(e):
            state["pressed"] = True
            if ANIM:
                state["ripple"] = (e.x, time.perf_counter())
                wake()
            paint()
            return "break"
        cv.bind("<ButtonPress-1>", press)
        cv.bind("<ButtonRelease-1>", release)

        def set_busy(on):
            state["busy"] = bool(on)
            wake() if on else None
            paint()
        cv.set_busy = set_busy

        def set_active(on):
            state["active"] = on
            blend()
            paint()
        cv.set_active = set_active

        def _set(t):                    # set_text etiketi değiştirsin
            nonlocal label
            label = t
            paint()
        cv.set_text = _set
        cv._bg = bg
        return cv

    # ------------------------------------------------------------ arayüz
    def _build(self):
        self.advanced_home = tk.Frame(self.layout_root, bg=BG)
        sidebar = tk.Canvas(self.advanced_home, bg=SIDE, width=dipx(252), bd=0,
                            highlightthickness=0, yscrollincrement=26)
        sidebar.pack(side="left", fill="y")
        side = tk.Frame(sidebar, bg=SIDE)
        sidebar_window = sidebar.create_window(0, 0, window=side, anchor="nw")
        sidebar.bind("<Configure>", lambda e: sidebar.itemconfigure(sidebar_window, width=e.width))
        side.bind("<Configure>", lambda e: sidebar.configure(scrollregion=(0, 0, e.width, e.height)))
        tk.Frame(self.advanced_home, bg=LINE, width=1).pack(side="left", fill="y")

        # ---------------- marka
        brand = tk.Frame(side, bg=SIDE)
        brand.pack(fill="x", padx=16, pady=(18, 0))
        brand.columnconfigure(1, weight=1)
        logo = tk.Canvas(brand, width=42, height=42, bg=SIDE, highlightthickness=0)
        logo.grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.logo = logo
        self.draw_logo(0.0)
        tb = tk.Frame(brand, bg=SIDE)
        tb.grid(row=0, column=1, sticky="nsew")
        brand_title = tk.Label(tb, text="Tarla Pusulası", bg=SIDE, fg=FG,
                              font=self.F(13, True), anchor="w", justify="left")
        brand_title.pack(fill="x")
        brand_note = tk.Label(tb, text="Veriye dayalı tarla rehberi", bg=SIDE, fg=MUT,
                             font=self.F(10), anchor="w", justify="left")
        brand_note.pack(fill="x", pady=(3, 0))
        tb.bind('<Configure>', lambda e: [label.configure(wraplength=max(80,e.width-4))
                                         for label in (brand_title,brand_note)])

        # ---------------- konum
        tk.Label(side, text="KONUM", bg=SIDE, fg=MUT2,
                 font=self.F(8, True)).pack(anchor="w", padx=22, pady=(16, 8))
        entry_host = tk.Frame(side, bg=SIDE)
        entry_host.pack(fill="x", padx=22)
        entry_cv = tk.Canvas(entry_host, bg=SIDE, highlightthickness=0, bd=0, height=dipx(44))
        entry_cv.pack(fill="x")

        def paint_entry(event=None):
            entry_cv.delete("all")
            ww = entry_cv.winfo_width()
            eh = dipx(44)
            self.rrect(entry_cv, 1, 1, ww - 1, eh - 1, 14, fill=CARD2, outline=LINE2)
            entry_cv.create_text(dpx(16), eh / 2, text="◉", fill=MUT2, anchor="w", font=self.F(9))
            entry_cv.create_window(dpx(34), eh / 2, window=self.entry, anchor="w",
                                   width=max(60, ww - dpx(50)), height=dipx(26))
        self.entry = tk.Entry(entry_cv, bg=CARD2, fg=FG, insertbackground=ACC, relief="flat",
                              textvariable=self.location_query,
                              font=self.F(11), bd=0, highlightthickness=0,
                              disabledbackground=CARD2)
        self.entry.bind("<Return>", lambda e: self.analyze(self.entry.get()))
        entry_cv.bind("<Configure>", paint_entry)
        entry_cv.bind("<Button-1>", lambda e: self.entry.focus_set())
        self.entry.bind("<FocusIn>", lambda e: entry_cv.delete("focusring") or
                        entry_cv.create_rectangle(1, 1, entry_cv.winfo_width() - 1, dipx(44) - 1,
                                                  outline=ACC2, width=1, tags="focusring"))
        self.entry.bind("<FocusOut>", lambda e: entry_cv.delete("focusring"))
        self._paint_entry = paint_entry

        self.go = self.button(side, "Analiz et", lambda: self.analyze(self.entry.get()),
                              primary=True, height=44)
        self.go.pack(fill="x", padx=22, pady=(10, 0))
        self.map_btn = self.button(side, "Tarlamı haritada seç", self.open_map,
                                   icon="⌖", height=36)
        self.map_btn.pack(fill="x", padx=22, pady=(8, 0))

        # ---------------- sulama anahtarı (kart)
        sw_host = tk.Frame(side, bg=SIDE)
        sw_host.pack(fill="x", padx=22, pady=(16, 0))
        sw_cv = tk.Canvas(sw_host, bg=SIDE, highlightthickness=0, bd=0, height=44,
                          cursor="hand2")
        sw_cv.pack(fill="x")

        def paint_sw_card(event=None):
            sw_cv.delete("all")
            ww = sw_cv.winfo_width()
            font = self.F(9, self.irr)
            item = sw_cv.create_text(dpx(58), 7, text="Sulama imkânım var", anchor="nw",
                                     fill=ACC if self.irr else FG2, width=max(1, ww - dpx(67)), font=font)
            h = max(dipx(44), sw_cv.bbox(item)[3] + 7)
            sw_cv.configure(height=h)
            bg = self.rrect(sw_cv, 1, 1, ww - 1, h - 1, 12, fill=CARD2, outline=LINE2)
            sw_cv.tag_lower(bg)
            sw_cv.create_window(12, h / 2, window=self.sw, anchor="w")
        sw_cv.bind("<Configure>", paint_sw_card)
        sw_cv.bind("<Button-1>", lambda e: self.toggle_irr())
        self._paint_sw = paint_sw_card
        self.sw = tk.Canvas(sw_cv, width=38, height=20, bg=CARD2, highlightthickness=0,
                            cursor="hand2")
        self.sw.bind("<Button-1>", lambda e: self.toggle_irr())
        self.draw_switch()

        # ---------------- çalışma alanı
        tools_section = self.tools_header = tk.Frame(side, bg=SIDE)
        tools_section.pack(fill="x", padx=22, pady=(16, 6))
        tk.Label(tools_section, text="ÇALIŞMA ALANI", bg=SIDE, fg=MUT2,
                 font=self.F(8, True)).pack(anchor="w", pady=(0, 7))

        groups = (
            ("Planla", "→", (
                ("Ekim nöbeti önerileri", self.open_optimizer),
                ("10 yıllık iklim senaryosu", self.open_simulation),
                ("Kaynak kaybı analizi", self.open_resource_loss),
            )),
            ("İzle", "⌁", (
                ("Riskler", self.open_risk),
                ("Telegram sohbeti", self.open_telegram),
                ("Tarla Takip Paneli", self.open_mission_control),
                ("Sesli saha modu", self.open_field_mode),
            )),
            ("Ayarlar", "⚙", (
                ("Veri & açıklanabilirlik", self.open_method_details),
                ("Frekans protokolü", self.open_frequency),
                ("Özelleştirme", self.open_settings),
            )),
        )
        panels = {}
        headers = {}
        active_group = None

        def toggle_group(key):
            nonlocal active_group
            active_group = None if active_group == key else key
            for name, panel in panels.items():
                is_open = name == active_group
                if is_open:
                    panel.pack(fill="x", pady=(3, 0))
                else:
                    panel.pack_forget()
                headers[name].set_active(is_open)
                headers[name].set_text(name + ("  ▴" if is_open else "  ▾"))

        for key, icon, actions in groups:
            group = tk.Frame(tools_section, bg=SIDE)
            group.pack(fill="x", pady=(0, 5))
            header = self.button(group, key + "  ▾", lambda key=key: toggle_group(key),
                                 icon=icon, height=34, radius=10, icon_size=13)
            header.pack(fill="x")
            panel = tk.Frame(group, bg=SIDE)
            panels[key] = panel
            headers[key] = header
            for label, command in actions:
                button = self.button(panel, label, lambda label=label, command=command:
                                     self._open_menu_tool(label, command), primary=label == "Özelleştirme",
                                     height=30, radius=8)
                button.pack(fill="x", padx=(10, 0), pady=(0, 3))

        for key, header in headers.items():
            header.configure(takefocus=True)
            header.bind("<Return>", lambda _event, key=key: toggle_group(key))
            header.bind("<space>", lambda _event, key=key: toggle_group(key))

        settings = tk.Frame(side, bg=SIDE)
        settings.pack(fill="x", padx=22, pady=(2, 0))
        self.motion_btn = self.button(settings, "Hareket: açık", self.toggle_motion,
                                      ghost=True, height=32)
        self.motion_btn.configure(width=1)
        self.motion_btn.pack(side="left", fill="x", expand=True)

        # ---------------- kayıtlı tarlalar
        self.fields_btn = self.button(side, "Tarlalarım", self.open_my_fields, icon="▤",
                                      height=36)
        self.fields_btn.pack(fill="x", padx=22, pady=(10, 0))

        # ---------------- alt durum
        foot = tk.Frame(side, bg=SIDE)
        foot.pack(side="bottom", fill="x", padx=22, pady=(0, 12))
        self.status = tk.Label(foot, text="", bg=SIDE, fg=MUT, font=self.F(8),
                               wraplength=258, justify="left")
        self.status.pack(anchor="w")
        self.src = tk.Label(foot, text="", bg=SIDE, fg=MUT2, font=self.F(8, True))
        self.src.pack(anchor="w", pady=(6, 0))
        self.status.configure(wraplength=dipx(206))
        self.src.configure(wraplength=dipx(206), justify='left')
        tk.Button(foot, text='Kaynaklar ve hesap', command=self.open_sources,
                  bg=SIDE, fg=ACC, relief='flat', anchor='w', cursor='hand2',
                  font=self.F(10)).pack(anchor='w', pady=(6,0))

        spacing = []
        for widget in side.pack_slaves():
            padding = widget.pack_info()["pady"]
            spacing.append((widget, tuple(map(int, padding)) if isinstance(padding, tuple)
                            else tuple(map(int, str(padding).split()))))

        def resize_sidebar(event):
            sidebar.itemconfigure(sidebar_window, width=event.width)
            factor = min(1.0, max(.15, (event.height - dpx(540)) / dpx(240)))
            for widget, padding in spacing:
                widget.pack_configure(pady=tuple(round(value * factor) for value in padding))

        sidebar.bind("<Configure>", resize_sidebar)

        # ---------------- ana alan
        main = tk.Frame(self.advanced_home, bg=BG)
        main.pack(side="left", fill="both", expand=True, padx=10, pady=9)
        main.columnconfigure(0, weight=65, uniform="c")
        main.columnconfigure(1, weight=35, uniform="c")
        main.rowconfigure(1, weight=1)

        self.main_area = main
        self.cv = self.card(main, height=134)
        self.cv.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.cc = self.card(main)
        self.cc.grid(row=1, column=0, sticky="nsew", pady=(0, 6))
        self.cf = self.card(main, height=196)
        self.cf.grid(row=2, column=0, sticky="ew")
        right = tk.Frame(main, bg=BG)
        right.grid(row=0, column=1, rowspan=3, sticky="nsew", padx=(10, 0))
        crop_box = tk.Frame(right, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        crop_box.pack(fill="x", pady=(0, 8))
        tk.Label(crop_box, text="TÜM EKİNLER", bg=CARD, fg=FG, font=self.F(11, True)).pack(
            anchor="w", padx=12, pady=(7, 4))
        crop_rows = tk.Frame(crop_box, bg=CARD)
        crop_rows.pack(fill="x")
        self.cr = tk.Canvas(crop_rows, bg=CARD, highlightthickness=0, bd=0)
        crop_scroll = tk.Scrollbar(crop_rows, command=self.cr.yview)
        self.cr.configure(yscrollcommand=crop_scroll.set)
        crop_scroll.pack(side="right", fill="y")
        self.cr.pack(side="left", fill="x", expand=True)
        self.chat_panel = tk.Frame(right, bg=BG, highlightthickness=1, highlightbackground=LINE)
        self.chat_panel.pack(fill="both", expand=True)
        self._build_chat(self.chat_panel)

        for c, fn in ((self.cv, self.draw_verdict), (self.cc, self.draw_chart),
                      (self.cf, self.draw_factors), (self.cr, self.draw_rank)):
            c.bind("<Configure>", lambda e, fn=fn: fn())
        self.cr.bind("<Button-1>", self.on_click)
        self.cr.bind("<Motion>", self.on_move)
        self.cr.bind("<Leave>", lambda e: self.set_hover(None))
        self.cv.bind("<Button-1>", lambda e: self.cycle_suggestion(e))
        self.cv.bind("<Motion>", self.on_verdict_move)
        self.cc.bind("<Motion>", self.on_chart_move)
        self.cc.bind("<Leave>", self.on_chart_leave)

    def _build_easy_home(self):
        self.easy_home = page = tk.Canvas(self.layout_root, bg=EASY_BG, highlightthickness=0,
                                          yscrollincrement=28, bd=0)
        body = tk.Frame(page, bg=EASY_BG, padx=22, pady=16)
        content = page.create_window(0, 0, window=body, anchor="nw")
        page.bind("<Configure>", lambda e: page.itemconfigure(content, width=e.width))
        body.bind("<Configure>", lambda e: page.configure(scrollregion=(0, 0, e.width, e.height)))
        hero = tk.Frame(body, bg=EASY_BG)
        hero.pack(fill="x")
        easy_logo = tk.Canvas(hero, bg=EASY_BG, width=46, height=44, highlightthickness=0)
        easy_logo.pack(side="left", padx=(0, 10))
        easy_logo.create_line(23, 35, 23, 17, fill=EASY_ACC, width=2)
        easy_logo.create_line(23, 20, 13, 19, 5, 8, 15, 8, 23, 14, 23, 20,
                              fill=EASY_ACC, width=2, smooth=True)
        easy_logo.create_line(23, 25, 34, 24, 42, 13, 31, 13, 23, 18, 23, 25,
                              fill=EASY_ACC, width=2, smooth=True)
        easy_logo.create_arc(9, 29, 37, 47, start=0, extent=180, fill=EASY_ACC, outline="")
        tk.Label(hero, text="Tarla Pusulası", bg=EASY_BG, fg=FG, font=self.F(28, True)).pack(side="left")
        tk.Label(body, text="Tarlanla ilgili her şey burada. Ne yapmak istersin?", bg=EASY_BG,
                 fg=FG2, font=self.F(13)).pack(anchor="w", pady=(6, 14))

        self.easy_search = search = tk.Frame(body, bg=EASY_CARD, highlightthickness=1, highlightbackground=EASY_EDGE)
        search.pack(fill="x")
        tk.Label(search, text="Şehrin veya ilçen", bg=EASY_CARD, fg=FG,
                 font=self.F(12, True)).pack(side="left", padx=14)
        easy_entry = tk.Entry(search, textvariable=self.location_query, bg=EASY_HOVER, fg=FG,
                              insertbackground=FG, relief="flat", font=self.F(13))
        visit = lambda: self.analyze(self.location_query.get())
        self.easy_go = tk.Button(search, text="Bölgeyi incele", command=visit, bg=EASY_ACTION,
                                 fg=EASY_INK, activebackground=EASY_ACTION_HOVER,
                                 activeforeground=EASY_INK, font=self.F(12, True),
                                 cursor="hand2", relief="flat", padx=18, pady=8)
        self.easy_go.pack(side="right", padx=8, pady=8)
        easy_entry.pack(side="left", fill="x", expand=True, ipady=7, pady=8)
        easy_entry.bind("<Return>", lambda e: visit())

        cards = tk.Frame(body, bg=EASY_BG)
        self.easy_cards = {}
        cards.pack(fill="x", pady=(10, 4))
        for column in range(2):
            cards.columnconfigure(column, weight=1, uniform="card")
        items = (
            ("⌖", "Tarlamı seç", "Haritadan tarlanı işaretle.", self.open_map),
            ("✿", "Ne ekmeliyim?", "Bölgene uygun ekinleri ve ne zaman ekileceğini gör.",
             lambda: self._open_menu_tool("Ne ekmeliyim?", self.open_easy_crops)),
            ("▱", "Tarlalarım", "Kaydettiğin tarlaları aç.", self.open_my_fields),
            ("⚠", "Tarlamda risk var mı?", "Hava, afet ve zararlı risklerini incele.",
             lambda: self._open_menu_tool("Riskler", self.open_risk)),
            ("◈", "Su ve gelecek", "Önümüzdeki yıllarda ekinin ne kadar suya ihtiyaç duyabileceğini gör.",
             lambda: self._open_menu_tool("Su ve gelecek", self.open_easy_water)),
            ("⚙", "Özelleştirme", "Modunu, rengini ve dilini değiştir.", self.open_settings),
        )
        for index, (icon, title, detail, command) in enumerate(items):
            card = tk.Frame(cards, bg=EASY_CARD, highlightthickness=1, highlightbackground=EASY_EDGE,
                            highlightcolor=EASY_ACC, takefocus=True, cursor="hand2")
            card.grid(row=index // 2, column=index % 2, sticky="nsew", padx=5, pady=5)
            self.easy_cards[title] = card
            heading = tk.Label(card, text=f"{icon}  {title}", bg=EASY_CARD, fg=EASY_ACC, font=self.F(16, True),
                               justify="left", anchor="w", cursor="hand2")
            heading.pack(fill="x", padx=17, pady=(14, 4))
            caption = tk.Label(card, text=detail, bg=EASY_CARD, fg=FG2, font=self.F(11),
                               justify="left", anchor="w", cursor="hand2")
            caption.pack(fill="x", padx=17, pady=(0, 15))
            card.bind("<Configure>", lambda e, labels=(heading, caption): [
                label.configure(wraplength=max(1, e.width - 38)) for label in labels])

            def hover(event, host=card, labels=(heading, caption)):
                x, y = event.x_root - host.winfo_rootx(), event.y_root - host.winfo_rooty()
                inside = 0 <= x < host.winfo_width() and 0 <= y < host.winfo_height()
                bg = EASY_HOVER if inside else EASY_CARD
                for widget in (host, *labels):
                    widget.configure(bg=bg)

            for widget in (card, heading, caption):
                widget.bind("<Enter>", hover)
                widget.bind("<Leave>", hover)
                widget.bind("<ButtonRelease-1>", lambda e, action=command: action())
            card.bind("<Return>", lambda e, action=command: action())
            card.bind("<space>", lambda e, action=command: action())

        self.easy_status = tk.Label(body, bg=EASY_BG, fg=MUT, anchor="w", justify="left", font=self.F(10))
        self.easy_status.pack(fill="x", padx=5, pady=(4, 5))
        body.bind("<Configure>", lambda e: self.easy_status.configure(wraplength=max(100, e.width - 60)),
                  add="+")

    def _apply_mode(self, mode):
        self.mode = mode
        if mode == "kolay":
            if self._tour is not None:
                self._tour.close()
            self._after_field = None
            allowed = {"Tarlanı haritada işaretle", "Tarlalarım", "Riskler", "Özelleştirme",
                       "Ne ekmeliyim?", "Su ve gelecek", "Kaynaklar ve hesap dayanakları"}
            for tab in tuple(self._tabs):
                if tab != self.layout_root and tab.tool_title not in allowed:
                    tab.request_close()
            self.advanced_home.pack_forget()
            self.easy_home.pack(fill="both", expand=True)
        else:
            self.easy_home.pack_forget()
            self.advanced_home.pack(fill="both", expand=True)
        self._paint_tabs()

    def _easy_results_tab(self, title, intro):
        win = self._window(title)
        tk.Label(win, text=title, bg=BG, fg=FG, font=self.F(22, True)).pack(
            anchor="w", padx=26, pady=(20, 4))
        tk.Label(win, text=intro, bg=BG, fg=FG2, font=self.F(12), justify="left").pack(
            anchor="w", padx=26, pady=(0, 14))
        tk.Label(win, text=NoTr(self.name if self.kaynak == "nasa" else "Konya"), bg=BG, fg=FG2,
                 font=self.F(11, True), justify="left").pack(anchor="w", padx=26, pady=(0, 8))
        return win

    def open_easy_crops(self):
        if self.busy or not self.results:
            self.set_status("Bölge inceleniyor. Sonuç gelince tekrar dene." if self.busy
                            else "Önce konum analizi yapın.", not self.busy)
            return
        title = "Ne ekmeliyim?"
        win = self._easy_results_tab(title, "Bölgene en uygun görünen ekinler en üstte.")
        win._analysis_context = id(self.clim), self.name, self.irr
        bar = tk.Frame(win, bg=BG)
        bar.pack(side="bottom", fill="x", padx=26, pady=(6, 12))
        source = ("Dayanak: NASA POWER iklim ortalamaları ve uygulamanın ekin ve toprak modeli."
                  if self.kaynak == "nasa" else
                  "Dayanak: Konya için örnek iklim verisi ve uygulamanın ekin ve toprak modeli.")
        tk.Label(bar, text=source, bg=BG, fg=MUT, font=self.F(10), justify="left").pack(anchor="w")
        colors = {"Uygun": ACC, "Sınırda": GOLD, "Uygun değil": BAD}
        for result in self.results[:3]:
            card = tk.Frame(win, bg=CARD, highlightthickness=1, highlightbackground=LINE, padx=15, pady=8)
            card.pack(fill="x", padx=26, pady=(0, 7))
            icon = tk.Canvas(card, width=28, height=28, bg=CARD, bd=0, highlightthickness=0)
            tarla_ekin_simgeleri.draw(icon, result["ekin"], 14, 14, ACC)
            icon.pack(side="left", padx=(0, 9))
            rating = tier_of(result["puan"])
            tk.Label(card, text=result["ekin"], bg=CARD, fg=FG, font=self.F(15, True)).pack(side="left")
            tk.Label(card, text=rating, bg=CARD, fg=colors.get(rating, FG), font=self.F(11, True)).pack(
                side="right", padx=(8, 0))
            month = result["ekim_ayi"]
            tk.Label(card, text=f"Ekim ayı: {month}" if month else "Çok yıllık ekin",
                     bg=CARD, fg=FG2, font=self.F(11)).pack(side="right", padx=14)

    def open_easy_water(self):
        result = self.current()
        if self.busy or not result:
            self.set_status("Bölge inceleniyor. Sonuç gelince tekrar dene." if self.busy
                            else "Önce konum analizi yapın.", not self.busy)
            return
        title = "Su ve gelecek"
        crop = result["ekin"]
        options = [row["ekin"] for row in self.results]
        clim, soil, irr, lat, lon = self.clim, self.soil, self.irr, self.lat, self.lon
        live = self.kaynak == "nasa"
        win = self._easy_results_tab(title, "Yağıştan sonra ekin için ne kadar su eksik kalabilir?")
        win._analysis_context = id(clim), self.name, irr
        row = tk.Frame(win, bg=BG)
        row.pack(fill="x", padx=26)
        tk.Label(row, text="Ekin seç", bg=BG, fg=FG, font=self.F(11, True)).pack(side="left", padx=(0, 10))
        choice = ttk.Combobox(row, font=self.F(11), state="readonly", width=24)
        choice.pack(side="left")
        tk.Label(win, text="Orta değişim", bg=BG, fg=MUT, font=self.F(11)).pack(
            anchor="w", padx=26, pady=(12, 4))
        numbers = [tk.Label(win, bg=CARD, fg=FG, font=self.F(13, True), anchor="w", padx=16, pady=8)
                   for _ in range(3)]
        for label in numbers:
            label.pack(fill="x", padx=26, pady=3)
        status = tk.Label(win, bg=BG, fg=MUT, justify="left", font=self.F(10))
        status.pack(anchor="w", padx=26, pady=(10, 6))
        tk.Label(win, text="1 mm su açığı = dekara 1 m³ net su karşılığı. Uygulama kayıpları hariç.",
                 bg=BG, fg=MUT, justify="left", font=self.F(10)).pack(anchor="w", padx=26)
        job = None
        results = queue.Queue()

        def localize_choices():
            choice.configure(values=tuple(tarla_dil.tr(name) for name in options))
            choice.current(options.index(crop))
        win._appearance_refresh = localize_choices
        localize_choices()

        def load_crop():
            nonlocal crop, job
            crop = options[choice.current()]
            selected = crop
            job = object()
            request = job
            for year, label in zip((0, 5, 10), numbers):
                label.configure(text=f"{YEAR0 + year}    …")
            status.configure(text="Hesaplanıyor… geçmiş yıllar alınıyor.", fg=MUT)

            def calculate():
                try:
                    history = self._outlook_history(live, lat, lon)
                    out = tp.simulate_outlook(selected, clim, irr, soil, history=history, include_crops=False)
                    results.put((request, out, None))
                except Exception as exc:
                    results.put((request, None, str(exc)))
            threading.Thread(target=calculate, daemon=True).start()

        def poll():
            try:
                while True:
                    request, out, error = results.get_nowait()
                    if request is not job:
                        continue
                    if error is not None:
                        status.configure(text="Su tahmini hesaplanamadı.", fg=BAD)
                        log_error("su tahmini: " + error)
                        continue
                    years = out["senaryolar"][1]["yillar"]
                    for year, label in zip((0, 5, 10), numbers):
                        label.configure(text=f"{YEAR0 + year}    ·    {years[year]['su_p50']} mm")
                    notes = ("NASA POWER aylık iklimi" if live else "Örnek iklim",
                             "NASA POWER geçmişi" if out["gecmis"] else "Varsayılan yıllık değişkenlik")
                    status.configure(text=" · ".join(notes) + " · " +
                                     "Model tahmini. Sulama öncesi toprağın nemini kontrol et.", fg=MUT)
            except queue.Empty:
                pass
            win.after(120, poll)

        choice.bind("<<ComboboxSelected>>", lambda e: load_crop())
        load_crop()
        win.after(120, poll)

    def _build_tabs(self):
        self._tabs = {}
        self._active_tab = None
        self._closing_app = False
        strip = tk.Frame(self.root, bg=SIDE)
        strip.pack(fill="x")
        tk.Frame(self.root, height=1, bg=LINE2).pack(fill="x")
        self._tab_host = tk.Frame(self.root, bg=BG)
        self._tab_host.pack(fill="both", expand=True)
        self._tab_host.pack_propagate(False)

        self._home_header = tk.Frame(strip, bg=SIDE)
        self._home_header.pack(side="left", padx=(8, 0))
        self._tab_canvas = canvas = tk.Canvas(strip, bg=SIDE, height=62,
                                               highlightthickness=0, xscrollincrement=1)
        scroll_buttons = []
        for direction, symbol in ((1, "›"), (-1, "‹")):
            button = tk.Button(strip, text=symbol, bg=SIDE, fg=FG, activebackground=CARD2,
                               activeforeground=FG, relief="flat", width=2, font=self.F(12, True),
                               command=lambda step=direction: canvas.xview_scroll(155 * step, "units"))
            button.pack(side="right", fill="y")
            scroll_buttons.append(button)
        canvas.pack(side="left", fill="x", expand=True)
        self._tab_headers = tk.Frame(canvas, bg=SIDE)
        canvas.create_window(0, 0, window=self._tab_headers, anchor="nw")

        def scroll_state(first, last):
            scroll_buttons[0].configure(state="normal" if float(last) < 1 else "disabled")
            scroll_buttons[1].configure(state="normal" if float(first) > 0 else "disabled")
        canvas.configure(xscrollcommand=scroll_state)

        def update_scroll(_event=None):
            canvas.configure(scrollregion=(0, 0, self._tab_headers.winfo_reqwidth(), 62))
            if self._active_tab in self._tabs:
                self._reveal_tab(self._active_tab)
        self._tab_headers.bind("<Configure>", update_scroll)
        canvas.bind("<Configure>", update_scroll)

        self.layout_root = tk.Frame(self._tab_host, bg=BG)
        self._register_tab(self.layout_root, "Ana ekran")
        self._help_button(strip, "Ana ekran").pack(side="right", before=scroll_buttons[0], padx=(4, 6))

        def cycle(step):
            tabs = list(self._tabs)
            self._show_tab(tabs[(tabs.index(self._active_tab) + step) % len(tabs)])
            return "break"

        def close_current(_event):
            if isinstance(self._active_tab, tarla_arayuz.ToolTab):
                self._active_tab.request_close()
            return "break"

        self.root.bind("<Control-Tab>", lambda _event: cycle(1))
        self.root.bind("<Control-Shift-Tab>", lambda _event: cycle(-1))
        self.root.bind("<Control-w>", close_current)

    def _register_tab(self, page, title):
        home = page == self.layout_root
        header = tk.Frame(self._home_header if home else self._tab_headers, bg=LINE2)
        header.pack(side="left", padx=(0, 6), pady=(6, 3), fill="y")
        surface = tk.Frame(header, bg=CARD2)
        surface.pack(fill="both", expand=True, padx=1, pady=(1, 3))
        button = tk.Button(surface, text=title, relief="flat", bd=0, padx=12,
                           pady=5, wraplength=230, justify="left", font=self.F(10, True), cursor="hand2",
                           command=lambda: self._show_tab(page))
        button.pack(side="left")
        close = None
        if isinstance(page, tarla_arayuz.ToolTab):
            close = tk.Button(surface, text="×", relief="flat", bd=0, width=2,
                              font=self.F(11), cursor="hand2", command=page.request_close)
            close.pack(side="right", fill="y", padx=(0, 3))
            page.bind("<Destroy>", lambda event: self._remove_tab(page)
                      if event.widget == page else None, add="+")
            drag = {"start": None, "active": False}

            def press(event):
                drag.update(start=event.x_root, active=False)

            def move(event):
                if drag["start"] is None or (not drag["active"] and abs(event.x_root - drag["start"]) < 8):
                    return
                drag["active"] = True
                button.configure(cursor="fleur")
                host = self._tab_headers
                x = event.x_root - host.winfo_rootx()
                headers = host.pack_slaves()
                index = headers.index(header)
                for i, other in enumerate(headers):
                    if other is header:
                        continue
                    middle = other.winfo_x() + other.winfo_width() / 2
                    if (i < index and x < middle) or (i > index and x > middle):
                        header.pack_configure(**({"before": other} if i < index else {"after": other}))
                        reverse = {parts[0]: tab for tab, parts in self._tabs.items()}
                        order = [self.layout_root] + [reverse[h] for h in host.pack_slaves()]
                        self._tabs = {tab: self._tabs[tab] for tab in order}
                        break

            def release(event):
                if drag["active"]:
                    button.configure(cursor="hand2", relief="flat", state="normal")
                    drag.update(start=None, active=False)
                    self._show_tab(page)
                    return "break"
                drag["start"] = None

            button.bind("<ButtonPress-1>", press, add="+")
            button.bind("<B1-Motion>", move, add="+")
            button.bind("<ButtonRelease-1>", release, add="+")
        self._tabs[page] = (header, surface, button, close)
        self._show_tab(page)

    def _reveal_tab(self, page):
        if page == self.layout_root:
            return
        header = self._tabs[page][0]
        canvas = self._tab_canvas
        total = self._tab_headers.winfo_reqwidth()
        left, width = canvas.canvasx(0), canvas.winfo_width()
        start = header.winfo_x()
        end = start + header.winfo_width() + 5
        if start < left:
            canvas.xview_moveto(start / max(1, total))
        elif end > left + width:
            canvas.xview_moveto(max(0, end - width) / max(1, total))

    def _show_tab(self, page):
        if page not in self._tabs:
            return
        if page != self._active_tab:
            help_card = getattr(self.root, "_tool_help_card", None)
            if help_card is not None and help_card.winfo_exists():
                help_card.destroy()
            if self._active_tab is not None:
                self._active_tab.pack_forget()
            page.pack(fill="both", expand=True)
            self._active_tab = page
            self._tabs[page][2].focus_set()
        self._paint_tabs()
        self.root.after_idle(lambda: self._reveal_tab(page) if page == self._active_tab else None)

    def _paint_tabs(self):
        for page, (header, surface, button, close) in self._tabs.items():
            selected = page == self._active_tab
            bg = ACC_SOFT if selected else CARD2
            header.configure(bg=ACC2 if selected else SIDE)
            surface.configure(bg=bg)
            button.configure(bg=bg, fg=ACC if selected else FG2,
                             activebackground=ACC_SOFT, activeforeground=ACC)
            if close is not None:
                close.configure(bg=bg, fg=MUT, activebackground=LINE2, activeforeground=FG)

    def _remove_tab(self, page):
        pages = list(self._tabs)
        index = pages.index(page)
        header = self._tabs.pop(page)[0]
        if self._closing_app:
            return
        header.destroy()
        if page == self._active_tab:
            self._active_tab = None
            self._show_tab(pages[index + 1] if index + 1 < len(pages) else pages[index - 1])

    def _open_menu_tool(self, label, command):
        if self.mode == "kolay" and self.busy and label in ("Ne ekmeliyim?", "Su ve gelecek", "Riskler"):
            self.set_status("Bölge inceleniyor. Sonuç gelince tekrar dene.")
            return
        title = {"Sesli saha modu": "Saha modu · sesli asistan"}.get(label, label)
        if label == "10 yıllık iklim senaryosu" and self.current():
            title = f"{self.current()['ekin']} · 10 yıllık senaryo"
        for tab in tuple(self._tabs):
            if getattr(tab, "tool_title", None) == title:
                context = getattr(tab, "_analysis_context", None)
                if context is not None and context != (id(self.clim), self.name, self.irr):
                    tab.request_close()
                    break
                if getattr(tab, "_web_failed", False):
                    tab.request_close()
                    break
                self._show_tab(tab)
                return
        command()

    def close_app(self):
        self._closing_app = True
        settings = getattr(self, "settings_win", None)
        if settings is not None and settings.winfo_exists():
            settings.request_close()
        if getattr(self, "_frequency_stop", None):
            self._frequency_stop()
        if self.map_server:
            threading.Thread(target=self.map_server.stop, daemon=True).start()
        ab.BUZZER.close()
        self.root.destroy()

    def open_web_window(self, title, url):
        win = self._window(title)
        # Web sekmeleri: başlık ve tek yardım düğmesi her zaman görünür.
        # İçerikte eklenen taşan/sarkan soru işaretinin yerine geçer.
        page_header = tk.Frame(win, bg=BG)
        page_header.pack(fill="x", padx=18, pady=(5, 3))
        tk.Label(page_header, text=title, bg=BG, fg=FG,
                 font=self.F(13, True), anchor="w").pack(side="left", padx=(0, 10))
        if title != "Saha modu · sesli asistan":
            self._help_button(page_header, title).pack(side="left")
        status_bar = tk.Frame(win, bg=BG)
        status_bar.pack(fill="x")
        host = tk.Frame(win, bg=BG)
        host.pack(fill="both", expand=True)
        host._wheel_boundary = True
        win.update_idletasks()
        note = tk.Label(status_bar, text="Sayfa yükleniyor…", bg=BG, fg=MUT, font=self.F(10))
        note.pack(side="left", padx=16, pady=8)
        # Web içeriği kendi HTML yardımını ana başlığında gösterir.
        tk.Button(status_bar, text="Tarayıcıda aç", command=lambda: webbrowser.open(url),
                  bg=CARD2, fg=FG, relief="flat").pack(side="right", padx=10)

        def retry():
            win.destroy()
            self.open_web_window(title, url)

        tk.Button(status_bar, text="Yeniden dene", command=retry, bg=CARD2, fg=FG,
                  relief="flat").pack(side="right", padx=4)

        def failed(message):
            win._web_ready = False
            win._web_failed = True
            note.configure(text=message)
            status_bar.pack(fill="x", before=host)
            host.pack_forget()

        try:
            process = tarla_pencere.launch(title, url, host.winfo_id())
        except (RuntimeError, OSError) as exc:
            failed(str(exc))
            return False

        hwnd = host.winfo_id()
        started = time.monotonic()
        job = None

        def release(event):
            if event.widget == host:
                if job is not None:
                    host.after_cancel(job)
                if process.poll() is None:
                    process.terminate()

        def resize(_event=None):
            return tarla_pencere.resize_embedded(hwnd)

        def check():
            nonlocal job
            job = None
            if process.poll() is not None:
                failed("Sayfa açılamadı. Microsoft Edge WebView2 Runtime kurulumunu kontrol edin.")
                return
            status = tarla_pencere.load_status(hwnd)
            if not win._web_ready and status == 1:
                win._web_ready = True
                status_bar.pack_forget()
            elif not win._web_ready and (status == 2 or time.monotonic() - started > 25):
                process.terminate()
                failed("Sayfa yüklenemedi. Yeniden deneyin veya tarayıcıda açın.")
                return
            job = host.after(1000 if win._web_ready else 80, check)

        win._web_ready = False
        host.bind("<Destroy>", release, add="+")
        host.bind("<Configure>", resize)
        host.bind("<Map>", resize)
        job = host.after(80, check)
        return True

    def toggle_motion(self):
        global ANIM
        ANIM = not ANIM
        tarla_gorunum.MOTION = ANIM
        self.motion_btn.set_text("Hareket: " + ("açık" if ANIM else "kapalı"))
        self._ring_id = getattr(self, "_ring_id", 0) + 1
        self.ring_t = self.intro_t = self.swap_t = 1.0
        self._sw_k = 1.0 if self.irr else 0.0
        self._hov_y = self._sel_y = None
        for key in list(self.ticker.jobs):
            if key not in ("ambient", "loading") and not (isinstance(key, tuple) and key[0] == "optimizer"):
                self.ticker.remove(key)
        if self._tip:
            self._tip.update(x=self._tip["tx"], a=1.0)
        self.draw_logo(0.0)
        self.draw_switch()
        self.redraw_all()

    def apply_layout(self):
        self.cf.grid()
        self.main_area.rowconfigure(1, weight=1, minsize=150)
        self.redraw_all()

    # ------------------------------------------------------------ özelleştirme
    def open_settings(self):
        """Kullanım modu, görünüm, dil ve OpenRouter API anahtarı.

        Her değişiklik ANINDA kaydedilir ve uygulanır; ayrıca "kaydet" düğmesi yoktur.
        """
        old = getattr(self, "settings_win", None)
        try:
            if old is not None and old.winfo_exists():
                old.lift()
                return
        except Exception:
            pass
        cfg = tarla_ayarlar.load()
        sel = {"tema": cfg["tema"], "show": False, "t": 1.0,
               "prev_tema": None, "save_job": None, "busy": False}
        win = self.settings_win = self._window("Özelleştirme")

        def close():
            flush_key()
            self.settings_win = None
            win.destroy()
        win.on_close = close
        win.bind("<Escape>", lambda e: close())

        tk.Label(win, text="Özelleştirme", bg=BG, fg=FG,
                 font=self.F(20, True)).pack(anchor="w", padx=28, pady=(22, 2))
        sub = tk.Label(win, text="Değişiklikler hemen uygulanır ve kaydedilir.", bg=BG, fg=MUT,
                       font=self.F(10))
        sub.pack(anchor="w", padx=28, pady=(0, 10))

        # ---- alt: kapat (önce yerleşir; pencere küçük de olsa görünür kalır)
        foot = tk.Frame(win, bg=BG)
        foot.pack(side="bottom", fill="x", padx=28, pady=(8, 20))
        close_btn = self.button(foot, "Kapat", close, primary=True, height=42)
        close_btn.configure(width=160)
        close_btn.pack(side="left")
        tk.Label(foot, text="Ayarlar bu bilgisayarda kullanıcı klasörünüzde saklanır; exe nereye "
                            "taşınırsa taşınsın geçerlidir.", bg=BG, fg=MUT2, font=self.F(9),
                 wraplength=380, justify="left").pack(side="left", padx=(14, 0))

        # içerik kaydırılabilir: yazı ölçeği büyük olsa da hiçbir şey kesilmez
        body_cv = tk.Canvas(win, bg=BG, highlightthickness=0, bd=0)
        body_cv.pack(fill="both", expand=True)
        body = tk.Frame(body_cv, bg=BG)
        body_id = body_cv.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda e: body_cv.configure(scrollregion=body_cv.bbox("all")))
        def fit_body(_event):
            width = body_cv.winfo_width()
            if width > 1:
                body_cv.itemconfigure(body_id, width=width)

        body_cv.bind("<Configure>", fit_body)

        def section(title):
            tk.Label(body, text=title, bg=BG, fg=MUT2, font=self.F(9, True)).pack(
                anchor="w", padx=28, pady=(12, 8))

        def flush_key():
            return True

        def apply_now(**change):
            """Ayarı kaydet ve arayüzü hemen yeni tema/dille yeniden kur."""
            if sel["busy"]:
                return
            sel["busy"] = True
            flush_key()
            try:
                cfg2 = tarla_ayarlar.save(**change)
            except Exception as exc:
                sel["busy"] = False
                sub.configure(text="Ayarlar kaydedilemedi: " + str(exc), fg=BAD)
                return
            if "palet" in change:
                win.after_idle(lambda: apply_accent(cfg2))
            else:
                if "mod" in change:
                    self._apply_mode(cfg2["mod"])
                    self.apply_appearance(cfg2["tema"], cfg2["dil"])
                    close()
                    self._show_tab(self.layout_root)
                    tarla_tanitim.first_run(self)
                    return
                self.apply_appearance(cfg2["tema"], cfg2["dil"], reopen_settings=True)

        mode_var = tk.StringVar(win, value=cfg["mod"])
        mode_box = tk.Frame(body, bg=CARD, padx=16, pady=10, highlightthickness=1,
                            highlightbackground=LINE)
        mode_box.pack(fill="x", padx=28, pady=(4, 8))
        tk.Label(mode_box, text="Uygulamayı nasıl kullanmak istersiniz?", bg=CARD, fg=FG,
                 font=self.F(14, True)).pack(anchor="w", pady=(0, 5))
        for mode, (label, description) in tarla_tanitim.MODE_DETAILS.items():
            tk.Radiobutton(mode_box, text=label, value=mode, variable=mode_var, bg=CARD, fg=FG,
                           selectcolor=BG, activebackground=CARD, activeforeground=ACC,
                           highlightbackground=CARD, font=self.F(12, True), cursor="hand2",
                           command=lambda: apply_now(mod=mode_var.get()) if mode_var.get() != cfg["mod"] else None
                           ).pack(anchor="w", pady=(3, 0))
            tk.Label(mode_box, text=description, bg=CARD, fg=FG2, font=self.F(10),
                     justify="left").pack(anchor="w", padx=(24, 0), pady=(0, 6))

        section("DİL")
        language_row = tk.Frame(body, bg=BG)
        language_row.pack(fill="x", padx=28)
        lang_var = tk.StringVar(win, value=cfg["dil"])
        for index, (code, label) in enumerate(tarla_dil.LANG_NAMES.items()):
            language_row.columnconfigure(index, weight=1, uniform="language")
            tk.Radiobutton(language_row, text=NoTr(label), value=code, variable=lang_var, indicatoron=False,
                           bg=CARD, fg=FG, selectcolor=ACC_SOFT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=LINE, highlightcolor=ACC,
                           activebackground=CARD2, activeforeground=FG, font=self.F(11, True),
                           cursor="hand2", pady=6,
                           command=lambda: apply_now(dil=lang_var.get()) if lang_var.get() != cfg["dil"] else None
                           ).grid(row=0, column=index, sticky="ew", padx=(0, 6))

        # ---- tanıtım turu
        section("TANITIM TURU")

        def replay_tour():
            close()
            self._show_tab(self.layout_root)
            win_mode = self.mode
            self.root.after_idle(lambda: tarla_tanitim.start(self) if self.mode == win_mode else None)
        tour_row = tk.Frame(body, bg=BG)
        tour_row.pack(fill="x", padx=28)
        self.button(tour_row, "Tanıtım turunu yeniden başlat", replay_tour, icon="▶", height=40).pack(fill="x")
        tk.Label(body, text="Seçili görünümün tanıtımını açar.",
                 bg=BG, fg=MUT2, font=self.F(9), justify="left").pack(anchor="w", padx=28, pady=(6, 4))

        # ---- görünüm: iki küçük önizleme kartı
        section("GÖRÜNÜM")
        themes = tk.Frame(body, bg=BG)
        themes.pack(fill="x", padx=28)
        theme_cvs = {}

        def draw_theme(name):
            cv = theme_cvs[name]
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 60:
                return
            cv.delete("all")
            P = PALETTES[name]
            on = sel["tema"] == name
            k = sel["t"] if on else (1 - sel["t"]) if sel["prev_tema"] == name else 0.0
            self.rrect(cv, 1, 1, w - 1, h - 1, 14, fill=CARD,
                       outline=lerp(LINE2, ACC, k), width=1 + round(k))
            px0, py0, px1, py1 = 14, 14, w - 14, h - 42
            self.rrect(cv, px0, py0, px1, py1, 8, fill=P["BG"], outline=P["LINE2"])
            cv.create_rectangle(px0 + 4, py0 + 4, px0 + 40, py1 - 4, fill=P["SIDE"], outline="")
            self.rrect(cv, px0 + 8, py0 + 10, px0 + 36, py0 + 18, 4, fill=P["ACC"], outline="")
            for j in range(3):
                cv.create_rectangle(px0 + 8, py0 + 26 + j * 9, px0 + 34, py0 + 30 + j * 9,
                                    fill=P["LINE2"], outline="")
            self.rrect(cv, px0 + 48, py0 + 8, px1 - 8, py1 - 8, 6, fill=P["CARD"],
                       outline=P["LINE"])
            for j, (frac, col) in enumerate(((.8, P["ACC"]), (.55, P["GOLD"]), (.35, P["BAD"]))):
                yy = py0 + 22 + j * 14
                cv.create_rectangle(px0 + 58, yy, px0 + 58 + (px1 - px0 - 76) * frac, yy + 5,
                                    fill=col, outline="")
            cv.create_text(16, h - 21, text="Koyu" if name == "koyu" else "Açık", anchor="w",
                           fill=FG if on else FG2, font=self.F(11, on))
            if k > .05:
                r = 9 * k
                cv.create_oval(w - 26 - r, h - 21 - r, w - 26 + r, h - 21 + r, fill=ACC,
                               outline="")
                if k > .6:
                    cv.create_text(w - 26, h - 21, text="✓", fill=ON_ACC, font=self.F(9, True))

        def pick_theme(name):
            if sel["tema"] == name or sel["busy"]:
                return
            sel.update(prev_tema=sel["tema"], tema=name, t=0.0)

            def frame(e):
                sel["t"] = e
                for n in theme_cvs:
                    draw_theme(n)
                if e >= 1:
                    apply_now(tema=name)
            self._tween(160, frame, win)

        for i, name in enumerate(("koyu", "acik")):
            cv = tk.Canvas(themes, bg=BG, height=150, highlightthickness=0, bd=0, cursor="hand2")
            cv.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 10, 0))
            themes.columnconfigure(i, weight=1, uniform="t")
            cv.bind("<Configure>", lambda e, n=name: draw_theme(n))
            cv.bind("<Button-1>", lambda e, n=name: pick_theme(n))
            cv._ui_fixed_palette = True
            theme_cvs[name] = cv

        section("RENK PALETLERİ")
        accent_grid = tk.Frame(body, bg=BG)
        accent_grid.pack(fill="x", padx=28)
        accent_buttons = {}
        for index, (key, (label, pair)) in enumerate(ACCENT_PALETTES.items()):
            tile = tk.Frame(accent_grid, bg=BG)
            column = index % 2
            tile.grid(row=index // 2, column=column, sticky="ew", padx=4, pady=4)
            accent_grid.columnconfigure(column, weight=1, uniform="accent")
            swatch = tk.Canvas(tile, height=12, bg=BG, highlightthickness=0, cursor="hand2")
            swatch._ui_fixed_palette = True
            swatch.pack(fill="x")
            base = PALETTES[cfg["tema"]]
            primary, secondary = pair.get(cfg["tema"], (base["ACC"], base["WATER"]))

            def draw_swatch(_event, canvas=swatch, left=primary, right=secondary):
                width = canvas.winfo_width()
                canvas.delete("all")
                canvas.create_rectangle(0, 0, width / 2, 12, fill=left, outline="")
                canvas.create_rectangle(width / 2, 0, width, 12, fill=right, outline="")

            swatch.bind("<Configure>", draw_swatch)
            swatch.bind("<Button-1>", lambda _event, key=key: apply_now(palet=key))
            button = self.button(tile, label, lambda key=key: apply_now(palet=key), height=30)
            button.pack(fill="x")
            button.set_active(cfg["palet"] == key)
            accent_buttons[key] = button

        def apply_accent(updated):
            if not win.winfo_exists():
                return
            self.apply_appearance(updated["tema"], updated["dil"], accent=updated["palet"])
            for key, button in accent_buttons.items():
                button.set_active(key == updated["palet"])
            sel["busy"] = False

        if self.mode == "kolay":
            return

        # ---- AI anahtarı (yazıldıkça kaydedilir)
        section("AI ASİSTAN · OPENROUTER")
        box = tk.Frame(body, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        box.pack(fill="x", padx=28)
        tk.Label(box, text="API anahtarı", bg=CARD, fg=FG2, font=self.F(10, True)).grid(
            row=0, column=0, sticky="w", padx=16, pady=(14, 4))
        key_var = tk.StringVar(value=cfg["api_key"])
        key_entry = tk.Entry(box, textvariable=key_var, show="•", bg=CARD2, fg=FG,
                             insertbackground=ACC, relief="flat", font=self.F(10),
                             highlightthickness=1, highlightbackground=LINE2,
                             highlightcolor=ACC2)
        key_entry.grid(row=1, column=0, sticky="ew", padx=(16, 8), ipady=7)

        def toggle_show():
            sel["show"] = not sel["show"]
            key_entry.configure(show="" if sel["show"] else "•")
            show_btn.set_text("Gizle" if sel["show"] else "Göster")
        show_btn = self.button(box, "Göster", toggle_show, small=True, height=34)
        show_btn.configure(width=96)
        show_btn.grid(row=1, column=1, padx=(0, 16))
        tk.Label(box, text="Model", bg=CARD, fg=FG2, font=self.F(10, True)).grid(
            row=2, column=0, sticky="w", padx=16, pady=(12, 4))
        model_var = tk.StringVar(value=cfg["model"])
        model_entry = tk.Entry(box, textvariable=model_var, bg=CARD2, fg=FG, insertbackground=ACC,
                               relief="flat", font=self.F(10), highlightthickness=1,
                               highlightbackground=LINE2, highlightcolor=ACC2)
        model_entry.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, ipady=7)
        box.columnconfigure(0, weight=1)
        acts = tk.Frame(box, bg=CARD)
        acts.grid(row=4, column=0, columnspan=2, sticky="ew", padx=16, pady=(12, 6))
        key_note = tk.Label(box, text="", bg=CARD, fg=MUT, font=self.F(9), justify="left",
                            wraplength=500)
        key_note.grid(row=5, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 14))

        def clean_key(raw):
            """Yapıştırırken gelen boşluk, tırnak ve 'Bearer ' önekini temizle."""
            k = (raw or "").strip().strip('"').strip("'").strip()
            if k.lower().startswith("bearer "):
                k = k[7:].strip()
            return "".join(k.split())

        def describe_key(saved=False):
            key = clean_key(key_var.get())
            if not key:
                key_note.configure(fg=MUT, text="Anahtar girilmedi; asistan çevrimdışı özet gösterir.")
            elif not key.startswith("sk-or-"):
                key_note.configure(fg=BAD, text="Bu bir OpenRouter anahtarı değil (sk-or- ile başlamalı).")
            else:
                key_note.configure(fg=ACC if saved else MUT,
                                   text=("✓ " if saved else "") + tarla_dil.tr("Anahtar kayıtlı:")
                                   + " " + tarla_ayarlar.mask(key))

        def flush_key():
            """Bekleyen anahtar/model kaydını hemen yaz."""
            if sel["save_job"]:
                try:
                    win.after_cancel(sel["save_job"])
                except Exception:
                    pass
                sel["save_job"] = None
            key = clean_key(key_var.get())
            model = model_var.get().strip() or tarla_ayarlar.DEFAULT_MODEL
            cur = tarla_ayarlar.load()
            if key == cur["api_key"] and model == cur["model"]:
                return True
            try:
                tarla_ayarlar.save(api_key=key, model=model)
            except Exception as exc:
                key_note.configure(text=tarla_dil.tr("Ayarlar kaydedilemedi:") + " " + str(exc),
                                   fg=BAD)
                return False
            ai_asistan.reset_model()
            try:
                if win.winfo_exists():
                    describe_key(saved=True)
            except Exception:
                pass
            return True

        def on_change(*_a):
            describe_key()
            if sel["save_job"]:
                try:
                    win.after_cancel(sel["save_job"])
                except Exception:
                    pass
            sel["save_job"] = win.after(500, flush_key)     # yazmayı bitirince kaydet
        key_var.trace_add("write", on_change)
        model_var.trace_add("write", on_change)
        for e_ in (key_entry, model_entry):
            e_.bind("<FocusOut>", lambda e: flush_key())
            e_.bind("<Return>", lambda e: flush_key())
        describe_key()
        test_state = {"busy": False}

        def test():
            if test_state["busy"]:
                return
            key = clean_key(key_var.get())
            if not key.startswith("sk-or-"):
                describe_key()
                return
            flush_key()
            test_state["busy"] = True
            test_btn.set_text("Deneniyor…")
            key_note.configure(text="Deneniyor…", fg=MUT)
            res = {}

            def work():
                try:
                    res["r"] = ai_asistan.test_key(key, model_var.get().strip())
                except Exception as exc:
                    res["r"] = (False, str(exc) or exc.__class__.__name__)

            def check():
                if "r" not in res:
                    self.root.after(120, check)
                    return
                test_state["busy"] = False
                try:
                    if not win.winfo_exists():
                        return
                except Exception:
                    return
                test_btn.set_text("Anahtarı dene")
                ok, msg = res["r"]
                key_note.configure(text=("✓ " if ok else "✕ ") + msg, fg=ACC if ok else BAD)
            threading.Thread(target=work, daemon=True).start()
            self.root.after(120, check)

        def clear_key():
            key_var.set("")
            flush_key()
        test_btn = self.button(acts, "Anahtarı dene", test, small=True, height=34)
        test_btn.configure(width=150)
        test_btn.pack(side="left")
        del_btn = self.button(acts, "Anahtarı sil", clear_key, small=True, ghost=True, height=34)
        del_btn.configure(width=130)
        del_btn.pack(side="left", padx=(8, 0))
        tk.Label(body, text="Anahtar openrouter.ai/keys adresinden alınır; sk-or- ile başlar.",
                 bg=BG, fg=MUT2, font=self.F(9)).pack(anchor="w", padx=28, pady=(8, 12))

    def apply_appearance(self, theme, lang, reopen_settings=False, accent=None):
        """Açık pencereleri ve kullanıcı girdilerini koruyarak görünümü güncelle."""
        previous_lang = tarla_dil.lang()
        apply_theme(theme, THEME["accent"] if accent is None else accent)
        tarla_dil.set_lang(lang)
        ai_asistan.set_language(lang)
        tarla_gorunum.refresh(self.root, previous_lang)
        self._paint_tabs()
        self.root.configure(bg=BG)
        self.redraw_all()
        # Canvas çizimleri yeni dilde metin genişliklerini yeniden hesaplasın.
        def redraw(widget):
            for child in widget.winfo_children():
                if isinstance(child, tk.Canvas):
                    child.event_generate("<Configure>", width=child.winfo_width(), height=child.winfo_height())
                redraw(child)
        redraw(self.root)
        tour = getattr(self, "_tour", None)
        if tour is not None:
            tour.refresh()
        self.set_status("Ayarlar uygulandı.")
        if reopen_settings:
            old = getattr(self, "settings_win", None)
            if old is not None and old.winfo_exists():
                old.destroy()
            self.settings_win = None
            self.root.after(30, self.open_settings)

    def _loading_frame(self):
        """Analiz sürerken: butonda dönen çark; kartlarda iskelet parıltısı ya da
        (önceki sonuç ekrandaysa) seçili ekin kartının üstünde akan ilerleme şeridi."""
        self.go.set_text("İnceleniyor")
        self.go.set_busy(True)

        def frame(now):
            if not self.busy:
                for c in (self.cv, self.cc, self.cr):
                    c.delete("skel", "prog")
                self.go.set_busy(False)
                if not self.results:
                    self.redraw_all()
                return False
            if not ANIM:
                return True
            try:
                if self.results:
                    self._draw_progress(now)
                else:
                    self._draw_skeleton(now)
            except tk.TclError:
                return False
            return True
        self.ticker.add("loading", frame)
        if not ANIM:
            frame(time.perf_counter())

    def _draw_progress(self, now):
        c = self.cv
        c.delete("prog")
        w = c.winfo_width()
        if w < 60:
            return
        span = w - 44
        ph = (now * .9) % 1.0
        a = 22 + span * anim.in_out(anim.clamp(ph * 1.4 - .4))
        b = 22 + span * anim.in_out(anim.clamp(ph * 1.4))
        c.create_line(22, 3, w - 22, 3, fill=LINE2, width=3, capstyle="round", tags="prog")
        if b - a > 1:
            c.create_line(a, 3, b, 3, fill=ACC, width=3, capstyle="round", tags="prog")

    def _draw_skeleton(self, now):
        """İlk veri gelene kadar kartlarda kayan ışıklı yer tutucular."""
        sweep = (now * .8) % 1.6 - .3

        def bar(c, w, x0, y0, x1, y1, r=6):
            d = abs((x0 + x1) / 2 / max(1, w) - sweep)
            k = max(0.0, 1 - d / .25)
            self.rrect(c, x0, y0, x1, y1, r, fill=lerp(CARD2, CARD3, k), outline="", tags="skel")

        c = self.cv
        w, h = c.winfo_width(), c.winfo_height()
        if w > 80 and h > 80:
            c.delete("all")
            self.panel(c, 1, 1, w - 1, h - 1, r=16, fill=CARD, outline=LINE)
            bar(c, w, 26, 22, 180, 42, 10)
            bar(c, w, 26, 60, min(w - 200, 340), 88, 8)
            bar(c, w, 26, 102, min(w - 200, 460), 114)
            bar(c, w, 26, 122, min(w - 200, 400), 134)
            bar(c, w, 26, h - 42, 160, h - 16, 13)
            bar(c, w, 172, h - 42, 300, h - 16, 13)
            cx, cy = w - 88, h / 2 + 2
            ang = (now * 300) % 360
            c.create_arc(cx - 50, cy - 50, cx + 50, cy + 50, start=0, extent=359.9, style="arc",
                         outline=LINE2, width=8, tags="skel")
            c.create_arc(cx - 50, cy - 50, cx + 50, cy + 50, start=-ang, extent=70, style="arc",
                         outline=ACC2, width=8, tags="skel")
        c = self.cc
        w, h = c.winfo_width(), c.winfo_height()
        if w > 120 and h > 120:
            c.delete("all")
            self.panel(c, 1, 1, w - 1, h - 1, r=16, fill=CARD, outline=LINE)
            bar(c, w, 24, 20, 120, 36)
            bar(c, w, 24, 46, 320, 58)
            L, B, T = 52, h - 56, 86
            cw = (w - 112) / 12
            for m in range(12):
                hh = (B - T) * (.35 + .3 * math.sin(m * .9 + 1))
                bar(c, w, L + m * cw + cw * .3, B - hh, L + m * cw + cw * .7, B, 4)
        c = self.cr
        w, h = c.winfo_width(), c.winfo_height()
        if w > 80 and h > 80:
            c.delete("all")
            self.panel(c, 1, 1, w - 1, h - 1, r=16, fill=CARD, outline=LINE)
            bar(c, w, 22, 22, 150, 38)
            y = 70
            while y + 60 < h:
                bar(c, w, 26, y + 10, 42, y + 24, 4)
                bar(c, w, 50, y + 10, w * .62, y + 26)
                bar(c, w, 50, y + 34, w * .42, y + 44, 5)
                bar(c, w, w - 60, y + 10, w - 24, y + 30)
                bar(c, w, 50, y + 52, w - 24, y + 56, 2)
                y += 72

    def draw_logo(self, ang, glow=0.0):
        """Kenar çubuğundaki pusula: iğne açısı (radyan) ve analiz parıltısı."""
        c = self.logo
        c.delete("all")
        c.create_oval(1, 1, 41, 41, fill=lerp(ACC_SOFT, ACC2, glow * .5),
                      outline=lerp(LINE2, ACC, glow))
        for d in range(0, 360, 90):
            rr = math.radians(d)
            c.create_line(21 + 15 * math.sin(rr), 21 - 15 * math.cos(rr),
                          21 + 18 * math.sin(rr), 21 - 18 * math.cos(rr), fill=MUT2)
        rot = lambda px, py: (21 + px * math.cos(ang) - py * math.sin(ang),
                              21 + px * math.sin(ang) + py * math.cos(ang))
        n, e_, s_, w_ = rot(0, -13), rot(5, 0), rot(0, 13), rot(-5, 0)
        c.create_polygon(*n, *e_, *w_, fill=ACC, outline="")
        c.create_polygon(*s_, *e_, *w_, fill=ACC2, outline="")
        c.create_oval(18, 18, 24, 24, fill=ACC_SOFT, outline="")

    def draw_switch(self):
        c = self.sw
        c.delete("all")
        c.configure(bg=CARD2)
        k = self._sw_k
        e = anim.clamp(k)
        self.rrect(c, 1, 2, 37, 18, 8, fill=lerp(LINE2, ACC, e), outline="")
        x = 11 + 16 * k                     # out_back ile hafif taşar
        stretch = 3 * math.sin(math.pi * e) # hareket ederken topuz uzar
        c.create_oval(x - 7 - stretch / 2, 3, x + 7 + stretch / 2, 17,
                      fill=lerp(MUT, ON_ACC, e), outline="")
        if hasattr(self, "_paint_sw"):
            self._paint_sw()

    def _animate_switch(self):
        target = 1.0 if self.irr else 0.0
        if not ANIM:
            self._sw_k = target
            self.draw_switch()
            return
        start, t0 = self._sw_k, time.perf_counter()

        def step(now):
            t = (now - t0) / .32
            self._sw_k = start + (target - start) * anim.out_back(t, 2.2)
            if t >= 1:
                self._sw_k = target
            try:
                self.draw_switch()
            except tk.TclError:
                return False
            return t < 1
        self.ticker.add("switch", step)

    def _ambient(self, now):
        """Sürekli, hafif canlılık: logo iğnesi, skor halesi nabzı, vurgu parıltısı."""
        if not ANIM or self._active_tab != self.layout_root:
            return True
        if now - getattr(self, "_amb_last", 0) < .033:     # ~30 fps yeter
            return True
        self._amb_last = now
        t = now - self._t_start
        # logo: hafif salınım + analiz sırasında dönüş, bitince sönümlü oturma
        if self.busy:
            ang = (now * 5.0) % (2 * math.pi)
            self._logo_spin = now
            self._logo_from = ang
            glow = .5 + .5 * math.sin(now * 6)
        else:
            d = now - self._logo_spin
            base = .06 * math.sin(t * 1.3)
            if d < 1.6:
                frm = getattr(self, "_logo_from", 0.0)
                frm = (frm + math.pi) % (2 * math.pi) - math.pi
                ang = base + frm * math.exp(-3.2 * d) * math.cos(8 * d)
                glow = max(0.0, 1 - d / .8)
            else:
                ang, glow = base, 0.0
        try:
            self.draw_logo(ang, glow)
        except tk.TclError:
            return False
        if self.intro_t < 1:            # kartlar yerine otururken konumlar değişiyor
            return True
        c = self.cv
        try:
            # skor halesi nabız atar
            col = getattr(self, "_halo_col", None)
            if col:
                p = .5 + .5 * math.sin(t * 2.4)
                for i, item in enumerate(c.find_withtag("halo")):
                    c.itemconfigure(item, outline=lerp(CARD, col, (.10 + .22 * p) / (i + 1)))
                geo = getattr(self, "_spark", None)
                if geo:
                    cx, cy, rad, ang0 = geo
                    s = 4 + 1.6 * p
                    x = cx + rad * math.cos(ang0)
                    y = cy - rad * math.sin(ang0)
                    c.coords("spark", x - s, y - s, x + s, y + s)
                    c.coords("sparkglow", x - s - 4, y - s - 4, x + s + 4, y + s + 4)
                    c.itemconfigure("sparkglow", outline=lerp(CARD, col, .25 + .35 * p))
            # seçili ekin kartının üst çizgisinde gezen parıltı
            sh = getattr(self, "_shine", None)
            if sh:
                x0, x1 = sh
                ph = (t % 3.2) / 1.4
                if ph <= 1:
                    cx_ = x0 + (x1 - x0) * anim.in_out(ph)
                    c.coords("shine", max(x0, cx_ - 60), 1, min(x1, cx_ + 60), 1)
                    c.itemconfigure("shine", fill=lerp(ACC, "#ffffff", .55 if THEME["name"] == "koyu" else .0))
                else:
                    c.coords("shine", x0, 1, x0, 1)
            # seçili sıra çubuğu hafifçe parlar
            self.cr.itemconfigure("selbar", fill=lerp(ACC2, ACC, .5 + .5 * math.sin(t * 3)))
        except tk.TclError:
            pass
        return True

    def redraw_all(self):
        self.draw_verdict()
        self.draw_chart()
        self.draw_factors()
        self.draw_rank()
        if hasattr(self, "_chat_redraw"):
            self._chat_redraw()

    # ------------------------------------------------------------ eylemler
    def demo(self):
        self.analyze("", demo=True)

    def _show_startup_example(self):
        self.name, self.clim, self.kaynak = "Konya (örnek veri)", tp.DEMO, "ornek"
        self.soil = tp.soil_for(self.name)
        self.results = tp.rank(self.clim, self.irr, self.soil)
        self.sel = self.results[0]["ekin"]
        self.src.configure(text="○ ÖRNEK VERİ", fg=MUT)
        self.set_status("Yaklaşık örnek veri gösteriliyor (NASA verisi değil).")
        self.redraw_all()

    def toggle_irr(self):
        self.irr = not self.irr
        self._animate_switch()
        if self.clim:
            keep = self.sel
            self.results = tp.rank(self.clim, self.irr, self.soil)
            self.sel = keep if any(r["ekin"] == keep for r in self.results) else None
            self._ring_anim(650, full=True)     # sıralama yeniden kayarak dizilir

    # ------------------------------------------------------------ harita
    def open_soil_heatmap(self):
        self.open_soil_map()

    def open_map(self, archive_date=None, field=None):
        """Tarayıcıda uydu haritasını aç; kullanıcı tarlasının sınırını çizer.

        field: verilirse (ör. Tarlalarım'dan) harita o tarlanın sınırıyla açılır.
        """
        try:
            if self.map_server is None:
                # Geri çağrı sunucu iş parçacığında çalışır: yalnızca kuyruğa bırak.
                self.map_server = tarla_harita.MapServer(
                    lambda f: self.q.put(("field", f, False)))
            self.map_server.on_save = self._save_field_from_map
            center = (self.lat, self.lon) if self.lat is not None else None
            if field:
                center, pts = (field["lat"], field["lon"]), field["noktalar"]
            else:
                pts = self.field["noktalar"] if field is None and self.field else None
            active_field = self.field if field is None else field
            self.map_server.prepare(center=center, points=pts,
                                    name=(active_field or {}).get("kayit_adi", ""))
            url = self.map_server.url
            if archive_date is not None:
                url += "&date=" + archive_date.isoformat()
            # Aynı harita sekmesi ikinci kez açılmasın: eskisini kapatıp güncel tarla ile aç.
            for tab in tuple(self._tabs):
                if getattr(tab, "tool_title", None) == "Tarlanı haritada işaretle":
                    tab.request_close()
            opened = self.open_web_window("Tarlanı haritada işaretle", url)
        except Exception as exc:
            self.set_status(f"Harita açılamadı: {exc}", True)
            return
        if opened:
            self.set_status("Harita sekmesi açıldı. Tarlanızın köşelerini işaretleyip "
                            "“Bu tarlayı kullan” veya “Bu tarlayı kaydet” düğmesine basın.")
        else:
            self.set_status("Harita penceresi için build_exe.bat ile uygulamayı yeniden derleyin.", True)

    def on_field(self, field):
        """Haritadan gelen tarlayı analiz et (ana iş parçacığında çağrılır)."""
        if self.busy:                   # süren analiz bitince tekrar dene
            self.root.after(300, lambda: self.on_field(field))
            return
        coords = f"{field['lat']:.5f}, {field['lon']:.5f}"
        self.entry.delete(0, "end")
        self.entry.insert(0, coords)
        self.analyze(coords, field=field)
        if getattr(self._active_tab, "tool_title", None) == "Tarlanı haritada işaretle":
            self._show_tab(self.layout_root)
        try:                            # pencereyi öne getir
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except Exception:
            pass

    def field_status(self):
        f = self.field
        alan = tarla_harita.area_label(f)
        return ("Haritadan seçilen tarla" + (f" · {alan}" if alan else " (tek nokta)")
                + f" · {f['lat']:.4f}, {f['lon']:.4f}. NASA POWER aylık iklim ortalamaları kullanıldı.")

    def field_note(self):
        """AI bağlamı ve veri ekranı için tarla özeti; tarla yoksa boş."""
        if not self.field:
            return ""
        f = self.field
        alan = tarla_harita.area_label(f) or "alan çizilmedi (tek nokta)"
        return (f"haritadan seçildi; merkez {f['lat']:.5f}, {f['lon']:.5f}; "
                f"{alan}; {f['kose']} köşe")

    # ------------------------------------------------------------ tarlalarım
    def save_field(self, field, name=None):
        """Tarlayı kaydeder; aynı sınır zaten kayıtlıysa yalnızca adını günceller."""
        rec = field_record(tarla_harita.describe_field(field.get("noktalar")))
        if rec["kose"] < 3 or rec["alan_m2"] <= 0:
            raise ValueError("Kaydetmek için tarlanın en az 3 köşesini işaretleyin.")
        key = points_key(rec["noktalar"])
        name = " ".join((name or "").split())[:60]
        with _fields_lock:
            fields = load_fields()
            old = next((f for f in fields if points_key(f["noktalar"]) == key), None)
            if old is not None:
                if name and name != old.get("kayit_adi"):
                    old["kayit_adi"] = name
                    write_fields(fields)
                rec = old
            else:
                rec["kayit_adi"] = name or f"Tarla {len(fields) + 1}"
                rec["id"] = str(time.time_ns())
                rec["kayit_tarihi"] = date.today().isoformat()
                fields.append(rec)
                write_fields(fields)
        return rec, old is not None

    def _save_field_from_map(self, field):
        rec, _ = self.save_field(field, field.get("kayit_adi"))
        self.q.put(("field_saved", rec, False))
        return rec

    def _refresh_my_fields(self):
        win = getattr(self, "fields_win", None)
        try:
            if win is not None and win.winfo_exists():
                win._refresh_fields()
        except Exception:
            pass

    def open_my_fields(self):
        """Kayıtlı tarlalar: analiz et, haritada aç, sil; ekrandaki tarlayı kaydet."""
        old = getattr(self, "fields_win", None)
        try:
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:
            pass
        win = self.fields_win = self._window("Tarlalarım")
        tk.Label(win, text="Tarlalarım", bg=BG, fg=FG,
                 font=self.F(20, True)).pack(anchor="w", padx=28, pady=(22, 2))
        sub = tk.Label(win, text="", bg=BG, fg=MUT, font=self.F(10))
        sub.pack(anchor="w", padx=28, pady=(0, 12))

        # ---- alt: düğmeler (önce yerleşir; pencere küçülse de görünür kalır)
        foot = tk.Frame(win, bg=BG)
        foot.pack(side="bottom", fill="x", padx=28, pady=(8, 20))

        def draw_new():
            win.destroy()
            self.open_map(field={})
        nb = self.button(foot, "Yeni tarla çiz", draw_new, primary=True, icon="⌖", height=42)
        nb.configure(width=220)
        nb.pack(side="left")
        cb = self.button(foot, "Kapat", win.destroy, ghost=True, height=42)
        cb.configure(width=110)
        cb.pack(side="left", padx=(8, 0))

        # ---- ekrandaki tarlayı kaydet kutusu
        save_box = tk.Frame(win, bg=CARD, highlightthickness=1, highlightbackground=LINE)
        save_box.pack(fill="x", padx=28, pady=(0, 14))

        # ---- liste (kaydırılabilir)
        list_cv = tk.Canvas(win, bg=BG, highlightthickness=0, bd=0, yscrollincrement=24)
        list_cv.pack(fill="both", expand=True, padx=(28, 20))
        rows = tk.Frame(list_cv, bg=BG)
        rows_id = list_cv.create_window(0, 0, window=rows, anchor="nw")
        rows.bind("<Configure>", lambda e: list_cv.configure(scrollregion=list_cv.bbox("all")))
        list_cv.bind("<Configure>", lambda e: list_cv.itemconfigure(rows_id, width=e.width - 8))
        win.bind("<MouseWheel>", lambda e: list_cv.yview_scroll(-2 if e.delta > 0 else 2, "units"))
        win.bind("<Button-4>", lambda e: list_cv.yview_scroll(-2, "units"))
        win.bind("<Button-5>", lambda e: list_cv.yview_scroll(2, "units"))

        def build_save_box():
            for wdg in save_box.winfo_children():
                wdg.destroy()
            if not self._has_field():
                tk.Label(save_box, text="Ekranda kaydedilecek bir tarla yok. Haritada tarlanı çiz, "
                                        "“Bu tarlayı kaydet”e bas; tarla buraya gelir.",
                         bg=CARD, fg=MUT, font=self.F(10), wraplength=660,
                         justify="left").pack(anchor="w", padx=16, pady=14)
                return
            alan = tarla_harita.area_label(self.field) or ""
            saved = any(points_key(f.get("noktalar")) == points_key(self.field["noktalar"])
                        for f in load_fields())
            tk.Label(save_box, text="EKRANDAKİ TARLA" + (f" · {alan}" if alan else "")
                     + (" · kayıtlı" if saved else ""),
                     bg=CARD, fg=MUT2, font=self.F(9, True)).grid(
                row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6))
            name_var = tk.StringVar(value=self.field.get("kayit_adi", ""))
            ent = tk.Entry(save_box, textvariable=name_var, bg=CARD2, fg=FG, insertbackground=ACC,
                           relief="flat", font=self.F(11), highlightthickness=1,
                           highlightbackground=LINE2, highlightcolor=ACC2)
            ent.grid(row=1, column=0, sticky="ew", padx=(16, 8), pady=(0, 6), ipady=7)
            save_box.columnconfigure(0, weight=1)
            note = tk.Label(save_box, text="Tarlaya bir ad ver (örn. Pınarbaşı tarlası).",
                            bg=CARD, fg=MUT, font=self.F(9))
            note.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 12))

            def do_save():
                try:
                    rec, existed = self.save_field(self.field, name_var.get())
                except (OSError, ValueError) as exc:
                    note.configure(text="Kaydedilemedi: " + str(exc), fg=BAD)
                    return
                self.field["kayit_adi"] = rec["kayit_adi"]
                refresh()
                self.set_status(f"“{rec['kayit_adi']}” " + ("güncellendi." if existed
                                                             else "Tarlalarım'a kaydedildi."))
            sb = self.button(save_box, "Güncelle" if saved else "Bu tarlayı kaydet", do_save,
                             primary=not saved, height=38)
            sb.configure(width=180)
            sb.grid(row=1, column=1, padx=(0, 16), pady=(0, 6))
            ent.bind("<Return>", lambda e: do_save())

        def analyze_rec(rec):
            win.destroy()
            self.on_field(dict(rec))

        def map_rec(rec):
            win.destroy()
            self.open_map(field=rec)

        def delete_rec(rec):
            # Uygulama temasıyla uyumlu, geri dönülebilir karar penceresi.
            dialog = tk.Toplevel(win)
            dialog.title("Tarlayı sil")
            dialog.configure(bg=BG)
            dialog.transient(win)
            dialog.resizable(False, False)
            dialog.geometry("480x335")
            dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
            # Önce eylem satırını pencerenin altına sabitle: hiçbir font boyutunda kaybolmasın.
            actions = tk.Frame(dialog, bg=BG)
            actions.pack(side="bottom", fill="x", padx=25, pady=(8, 22))
            top = tk.Frame(dialog, bg=BG)
            top.pack(side="top", fill="both", expand=True, padx=25, pady=(22, 4))
            # Kırmızı başlık artık gerçek bir silme eylemi; alt kısımda gizli ikinci düğme yok.
            delete = tk.Button(top, text="✕  TARLAYI SİL", command=lambda: confirm_delete(),
                               bg=BAD, fg="#ffffff", activebackground="#aa2525",
                               activeforeground="#ffffff", font=self.F(11, True),
                               relief="flat", bd=0, padx=16, pady=9,
                               anchor="center", cursor="hand2")
            delete.pack(anchor="w", pady=(0, 2))
            tk.Label(top, text="Bu tarlayı kaldırmak istiyor musun?", bg=BG, fg=FG,
                     font=self.F(15, True), anchor="w", wraplength=380,
                     justify="left").pack(fill="x", pady=(12, 6))
            tk.Label(top, text=rec.get("kayit_adi") or "Adsız tarla", bg=CARD2, fg=FG2,
                     font=self.F(11, True), anchor="w", padx=12, pady=10,
                     wraplength=360).pack(fill="x")
            tk.Label(top, text="Bu işlem kayıtlı tarla sınırını siler ve geri alınamaz.",
                     bg=BG, fg=MUT, font=self.F(9), anchor="w",
                     wraplength=380).pack(fill="x", pady=(8, 0))
            def confirm_delete():
                key = points_key(rec.get("noktalar"))
                try:
                    with _fields_lock:
                        write_fields([f for f in load_fields() if points_key(f["noktalar"]) != key])
                except (OSError, ValueError) as exc:
                    self.set_status("Tarla silinemedi: " + str(exc), True)
                    dialog.destroy()
                    return
                dialog.destroy()
                refresh()
                self.set_status("Tarla kaydı silindi.")
            cancel = self.button(actions, "Vazgeç", dialog.destroy, height=38)
            cancel.pack(side="left", fill="x", expand=True)
            dialog.update_idletasks()
            x = win.winfo_rootx() + max(0, (win.winfo_width()-dialog.winfo_width())//2)
            y = win.winfo_rooty() + max(0, (win.winfo_height()-dialog.winfo_height())//2)
            dialog.geometry(f"+{x}+{y}")
            dialog.grab_set()
            delete.focus_set()
            dialog.bind("<Escape>", lambda _e: dialog.destroy())
            dialog.bind("<Return>", lambda _e: confirm_delete())

        def build_rows():
            for wdg in rows.winfo_children():
                wdg.destroy()
            fields = load_fields()
            sub.configure(text=f"{len(fields)} kayıtlı tarla" if fields else
                          "Henüz kayıtlı tarla yok.")
            if not fields:
                tk.Label(rows, text="Kaydettiğin tarlalar burada listelenir. Bir tarlaya tek "
                                    "tıkla yeniden analiz yapabilir, sınırını haritada "
                                    "düzenleyebilirsin.",
                         bg=BG, fg=MUT2, font=self.F(10), wraplength=640,
                         justify="left").pack(anchor="w", pady=(18, 0))
                return
            cur = points_key(self.field["noktalar"]) if self._has_field() else None
            for rec in reversed(fields):            # en yeni en üstte
                on = points_key(rec.get("noktalar")) == cur
                card = tk.Frame(rows, bg=CARD, highlightthickness=1,
                                highlightbackground=ACC2 if on else LINE)
                card.pack(fill="x", pady=(0, 10))
                left = tk.Frame(card, bg=CARD)
                left.pack(side="left", fill="x", expand=True, padx=16, pady=12)
                tk.Label(left, text=NoTr(rec.get("kayit_adi") or "Tarla"), bg=CARD, fg=FG,
                         font=self.F(13, True)).pack(anchor="w")
                alan = tarla_harita.area_label(rec)
                n = rec.get("kose") or len(rec.get("noktalar") or [])
                bits = ([alan] if alan else []) + [f"{n} " + tarla_dil.tr("köşe"),
                                                   f"{rec['lat']:.4f}, {rec['lon']:.4f}"]
                if rec.get("kayit_tarihi"):
                    bits.append(tarla_dil.tr("kayıt") + " " + rec["kayit_tarihi"])
                tk.Label(left, text=NoTr(" · ".join(bits)), bg=CARD, fg=MUT,
                         font=self.F(9)).pack(anchor="w", pady=(3, 0))
                if on:
                    tk.Label(left, text="● ekranda analiz edilen tarla", bg=CARD, fg=ACC,
                             font=self.F(8, True)).pack(anchor="w", pady=(4, 0))
                acts = tk.Frame(card, bg=CARD)
                acts.pack(side="right", padx=(0, 14))
                for label, fn, kw, wd in (("Sil", delete_rec, dict(ghost=True), 64),
                                          ("Haritada aç", map_rec, {}, 122),
                                          ("Analiz et", analyze_rec, dict(primary=True), 110)):
                    b = self.button(acts, label, lambda fn=fn, rec=rec: fn(rec), small=True,
                                    height=34, **kw)
                    b.configure(width=wd)
                    b.pack(side="right", padx=(6, 0))

        def refresh():
            if not win.winfo_exists():
                return
            build_save_box()
            build_rows()

        win._refresh_fields = refresh
        win._appearance_refresh = refresh
        refresh()

    def set_status(self, text, err=False):
        """Yeni mesaj vurgu rengiyle belirir, ~0,7 sn'de normal rengine döner."""
        self.easy_status.configure(text=text, fg=BAD if err else FG2)
        rest = BAD if err else MUT
        self.status.configure(text=text, fg=FG if err else ACC)
        self._status_id = my = getattr(self, "_status_id", 0) + 1

        def frame(e):
            if my == self._status_id:
                try:
                    self.status.configure(fg=lerp(FG if err else ACC, rest, e))
                except tk.TclError:
                    pass
        if ANIM:
            # daktilo: çevrilmiş metin harf harf yazılır, sonunda asıl metne döner
            full = tarla_dil.tr(text)
            t0 = time.perf_counter()

            def type_(now):
                if my != self._status_id:
                    return False
                n = int((now - t0) * 140)
                try:
                    if n >= len(full):
                        self.status.configure(text=text)
                        self.root.after(250, lambda: self._tween(700, frame))
                        return False
                    self.status.configure(text=NoTr(full[:n] + "▍"))
                except tk.TclError:
                    return False
                return True
            self.status.configure(text=NoTr(""))
            self.ticker.add("status", type_)
        else:
            frame(1.0)

    def analyze(self, query, demo=False, fallback=False, field=None):
        """field: haritadan gelen tarla kaydı; None ise yazılan yer adı kullanılır."""
        query = (query or "").strip()
        if self.busy:
            return
        self._last_query = query
        if not query and not demo:
            self.set_status("Önce bir yer adı yazın.", True)
            return
        self.busy = True
        self.easy_go.configure(text="İnceleniyor", state="disabled")
        self._loading_frame()
        self.set_status("Örnek veri yükleniyor…" if demo
                        else "NASA POWER verisi alınıyor, birkaç saniye sürebilir…")
        threading.Thread(target=self._work, args=(query, demo, fallback, field),
                         daemon=True).start()

    def _work(self, query, demo, fallback, field=None):
        try:
            if demo:
                out = ("Konya (örnek veri)", tp.DEMO, "ornek", None, None, None)
            else:
                if field:
                    lat, lon = field["lat"], field["lon"]
                    yer = tarla_harita.reverse_name(lat, lon)
                    field = dict(field, yer=yer or "")
                    kayit = (field.get("kayit_adi") or "").strip()     # Tarlalarım'daki ad
                    ad = (kayit + " · " if kayit else "Tarlam · ") + (yer or f"{lat:.3f}, {lon:.3f}")
                else:
                    ad, lat, lon = tp.geocode(query)
                key = (round(lat, 3), round(lon, 3))
                if key not in CACHE:
                    CACHE[key] = tp.fetch_nasa(lat, lon)
                out = (ad, CACHE[key], "nasa", lat, lon, field)
            self.q.put(("ok", out, fallback))
        except SystemExit as e:
            self.q.put(("err", str(e.code), fallback))
        except Exception as e:
            self.q.put(("err", f"Veri alınamadı: {e}", fallback))

    def _poll(self):
        try:
            while True:
                kind, payload, fallback = self.q.get_nowait()
                if kind == "field":     # haritadan tarla geldi (sunucu iş parçacığından)
                    self.on_field(payload)
                    continue
                if kind == "field_saved":
                    if self._has_field() and points_key(self.field["noktalar"]) == points_key(payload["noktalar"]):
                        self.field["kayit_adi"] = payload["kayit_adi"]
                    self._refresh_my_fields()
                    self.set_status(f"“{payload['kayit_adi']}” Tarlalarım'a kaydedildi.")
                    continue
                self.busy = False
                self.easy_go.configure(text="Bölgeyi incele", state="normal")
                self.go.set_busy(False)
                self.go.set_text("Analiz et")
                if kind == "ok":
                    self.name, self.clim, self.kaynak, self.lat, self.lon, self.field = payload
                    if self.field:      # tarla: önce il adından, olmazsa en yakın profil
                        self.soil = tp.soil_for(self.field.get("yer", ""))
                        if self.soil["label"] == tp.SOIL_DEFAULT["label"]:
                            self.soil = tp.soil_near(self.lat, self.lon)
                    else:
                        self.soil = tp.soil_for(self.name)
                    self.results = tp.rank(self.clim, self.irr, self.soil)
                    self.sel = self.results[0]["ekin"]
                    self.cr.yview_moveto(0)
                    added = ""
                    if self._has_field():   # haritadan seçilen tarla Tarlalarım'a da düşer
                        try:
                            rec, existed = self.save_field(self.field,
                                                           self.field.get("kayit_adi"))
                            self.field["kayit_adi"] = rec["kayit_adi"]
                            if not existed:
                                added = f" “{rec['kayit_adi']}” Tarlalarım'a eklendi."
                        except (OSError, ValueError):
                            log_error("tarla otomatik kaydı")
                    self.set_status(self.field_status() + added if self.field
                                    else "NASA POWER aylık iklim ortalamaları kullanıldı."
                                    if self.kaynak == "nasa"
                                    else "Yaklaşık örnek veri gösteriliyor (NASA verisi değil).")
                    self.map_btn.set_text("Tarlamı düzenle" if self.field
                                          else "Tarlamı haritada seç")
                    self._refresh_my_fields()   # açık Tarlalarım penceresi yeni tarlayı görsün
                    self.src.configure(text="● NASA POWER · İKLİM" if self.kaynak == "nasa"
                                       else "○ ÖRNEK VERİ",
                                       fg=ACC if self.kaynak == "nasa" else MUT)
                    self._hov_y = self._sel_y = None
                    wait = getattr(self, "_splash_end", 0) - time.perf_counter()
                    if ANIM and wait > 0:       # açılış perdesi kalkarken kartlar yükselsin
                        self._ring_id = getattr(self, "_ring_id", 0) + 1
                        self.ring_t = self.intro_t = self.swap_t = 0.0
                        self.redraw_all()
                        self.root.after(int(wait * 1000), lambda: self._ring_anim(1100, full=True))
                    else:
                        self._ring_anim(1100, full=True)
                    pending = getattr(self, "_after_field", None)
                    if pending and self._has_field():     # "önce tarlanı seç" ile bekleyen araç
                        self._after_field = None
                        self.root.after(500, pending)
                else:
                    if fallback and self.results and self.kaynak == "ornek":
                        self.set_status("NASA POWER verisi alınamadı. Örnek veri gösteriliyor.", True)
                    else:
                        self.set_status(payload, True)
                    if fallback and not self.results:
                        self.analyze("", demo=True)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self._poll)

    def current(self):
        if not self.results:
            return None
        return next((r for r in self.results if r["ekin"] == self.sel), self.results[0])

    # ------------------------------------------------------------ pencereler
    def _help_button(self, parent, title):
        def show():
            owner = parent.winfo_toplevel()
            old = getattr(owner, "_tool_help_card", None)
            if old is not None and old.winfo_exists():
                old.destroy()
                if old.tool_title == title:
                    return
            help_title = "Günlük Rehber" if title == "Ana ekran" and self.mode == "kolay" else title
            steps = tarla_gorunum.tool_help(help_title)
            card = owner._tool_help_card = tk.Toplevel(owner, bg=ACC2)
            card.tool_title = title
            card.withdraw()
            card.overrideredirect(True)
            card.transient(owner)
            inner = tk.Frame(card, bg=CARD)
            inner.pack(fill="both", expand=True, padx=2, pady=2)
            header = tk.Frame(inner, bg=CARD)
            header.pack(fill="x", padx=14, pady=(10, 8))
            tk.Button(header, text="×", command=card.destroy, bg=CARD, fg=FG2, relief="flat",
                      cursor="hand2", font=self.F(12, True)).pack(side="right")
            tk.Label(header, text=title, bg=CARD, fg=FG, font=self.F(17, True),
                     wraplength=305, justify="left").pack(side="left")
            for index, step in enumerate(steps, 1):
                row = tk.Frame(inner, bg=CARD)
                row.pack(fill="x", padx=14, pady=(0, 10))
                badge = tk.Canvas(row, width=25, height=25, bg=CARD, highlightthickness=0)
                badge.pack(side="left", anchor="n", padx=(0, 8))
                badge.create_oval(2, 2, 23, 23, fill=ACC_SOFT, outline=ACC2)
                badge.create_text(12.5, 12.5, text=str(index), fill=ACC, font=self.F(9, True))
                tk.Label(row, text=step, bg=CARD, fg=FG2, font=self.F(10),
                         wraplength=300, justify="left", anchor="nw").pack(side="left", fill="x")

            def position():
                card.update_idletasks()
                x = button.winfo_rootx() + button.winfo_width() - card.winfo_reqwidth()
                y = button.winfo_rooty() + button.winfo_height() + 6
                screen_width = card.winfo_screenwidth()
                screen_height = card.winfo_screenheight()
                if y + card.winfo_reqheight() > screen_height - 28:
                    y = button.winfo_rooty() - card.winfo_reqheight() - 6
                x = max(8, min(x, screen_width - card.winfo_reqwidth() - 8))
                card.geometry(f"+{x}+{max(8, y)}")

            card._appearance_refresh = position
            card.bind("<Escape>", lambda _event: card.destroy())
            position()
            card.deiconify()
            card.lift()
            card.focus_set()

        button = tk.Button(parent, text="?", command=show, bg=CARD2, fg=ACC, cursor="hand2",
                           relief="flat", width=2, padx=5, pady=3, font=self.F(17, True))
        return button

    def _window(self, title):
        win = tarla_arayuz.ToolTab(self._tab_host, self._show_tab, bg=BG)
        win.tool_title = title
        self._register_tab(win, title)
        source_bar = tk.Frame(win, bg=CARD2)
        source_bar.pack(side='bottom', fill='x')
        source_link = tk.Button(source_bar, text='Kaynaklar ve hesap', command=self.open_sources,
                                relief='flat', bg=CARD2, fg=ACC, font=self.F(10), cursor='hand2')
        source_link.pack(side='right', padx=12, pady=8)
        source_note = tk.Label(source_bar, text=tarla_kaynak.context_note(title),
                               bg=CARD2, fg=MUT, font=self.F(10), justify='left', anchor='w')
        source_note.pack(side='left', fill='x', expand=True, padx=16, pady=8)
        source_note.bind('<Configure>', lambda e: source_note.configure(wraplength=max(100,e.width-8)))
        def wrap_labels(event=None):
            def walk(parent):
                for child in parent.winfo_children():
                    if isinstance(child, tk.Label) and child.winfo_manager() == "pack":
                        info = child.pack_info()
                        if info.get("side") in ("top", "bottom"):
                            def fit_label(event=None, label=child, host=parent):
                                if label.winfo_exists() and not getattr(label, "_help_owns_wrap", False):
                                    width = max(160, host.winfo_width() - 60)
                                    if label.winfo_pixels(label.cget("wraplength") or 0) != width:
                                        label.configure(wraplength=width, justify="left")
                            if not getattr(child, "_wrap_bound", False):
                                parent.bind("<Configure>", fit_label, add="+")
                                child._wrap_bound = True
                            fit_label()
                    if isinstance(child, tk.Frame):
                        walk(child)
            if win.winfo_exists():
                walk(win)
        win.bind("<Configure>", lambda e: wrap_labels() if e.widget == win else None, add="+")
        win.after(100, wrap_labels)
        # Sayfa yardımını alt çubukta değil, sayfanın ana başlığının hemen yanında göster.
        if title not in ("Telegram sohbeti", "Saha modu · sesli asistan"):
            def attach_page_help():
                if not win.winfo_exists():
                    return
                aliases = {
                    "Rotasyon planlayıcı": "Rotasyon stratejileri",
                    "Veri & açıklanabilirlik": "Veri kaynakları ve varsayımlar",
                    "Derin Uzay ikizi · termodinamik tarla": "Termodinamik ve besin dengeleme ikizi",
                }
                expected = aliases.get(title, title)
                matches = []
                def scan(node, depth=0):
                    if depth > 7:
                        return
                    for child in node.winfo_children():
                        if isinstance(child, tk.Label):
                            try:
                                caption = str(child.cget("text"))
                                if caption in (expected, title, tarla_dil.tr(expected), tarla_dil.tr(title)):
                                    size = abs(tkfont.Font(font=child.cget("font")).actual("size"))
                                    matches.append((size, child))
                            except tk.TclError:
                                pass
                        elif isinstance(child, (tk.Frame, tarla_arayuz.ToolTab)):
                            scan(child, depth + 1)
                scan(win)
                if not matches:
                    # Bazı araçların içerik başlığı HTML içinde ya da farklı
                    # adla oluşturuluyor: yardım erişimini yine görünür tut.
                    fallback = tk.Frame(win, bg=BG)
                    children = [c for c in win.pack_slaves() if c is not fallback]
                    if children:
                        fallback.pack(fill="x", padx=22, pady=(5, 1), before=children[0])
                    else:
                        fallback.pack(fill="x", padx=22, pady=(5, 1))
                    tk.Label(fallback, text=title, bg=BG, fg=FG,
                             font=self.F(13, True)).pack(side="left", padx=(0, 10))
                    win._heading_help = self._help_button(fallback, title)
                    win._heading_help.pack(side="left")
                    return
                _, heading = max(matches, key=lambda pair: pair[0])
                heading._help_owns_wrap = True
                current = getattr(win, "_heading_help", None)
                if current is not None and current.winfo_exists():
                    current.place_forget()
                    current.destroy()
                button = self._help_button(heading.master, title)
                win._heading_help = button
                def align(_event=None):
                    if not button.winfo_exists() or not heading.winfo_exists():
                        return
                    try:
                        # Gerçek yazı genişliğine göre hizala; label'ın kapladığı
                        # boş alanı başlık zannedip yardım düğmesini aşağı düşürme.
                        host = heading.master
                        host_width = host.winfo_width()
                        bw = button.winfo_reqwidth()
                        font = heading.cget("font")
                        text_width = heading.tk.call("font", "measure", font, str(heading.cget("text")))
                        x0 = heading.winfo_x()
                        gap = 10
                        available = host_width - x0 - bw - gap - 18
                        if available <= 0:
                            return
                        wrap = available if text_width > available else 0
                        if heading.winfo_pixels(heading.cget("wraplength") or 0) != wrap:
                            heading.configure(wraplength=wrap, justify="left")
                        xx = x0 + min(text_width, available) + gap + 4
                        linespace = heading.tk.call("font", "metrics", font, "-linespace")
                        yy = heading.winfo_y() + max(heading.winfo_height(), linespace) // 2
                        button.place(x=xx, y=yy, anchor="w")
                        button.lift()
                    except tk.TclError:
                        pass
                heading.bind("<Configure>", align, add="+")
                heading.master.bind("<Configure>", align, add="+")
                align()
            win.after(350, attach_page_help)
        return win

    def open_sources(self):
        for tab in self._tabs:
            if getattr(tab, 'tool_title', '') == 'Kaynaklar ve hesap dayanakları':
                self._show_tab(tab)
                return
        if self.map_server is None:
            self.map_server = tarla_harita.MapServer(lambda f: self.q.put(('field', f, False)))
        self.open_web_window('Kaynaklar ve hesap dayanakları', self.map_server.page_url('/kaynaklar'))

    # ------------------------------------------------------------ animasyon
    def _fade_in(self, win, x=None, y=None, ms=WIN_ANIM_MS, rise=22):
        """Pencere açılışı: saydamdan görünüre geçiş + yaylanarak yukarı kayma.

        Süre, pencerenin içeriği kurulduktan sonraki ilk boş anda başlar; böylece
        ağır pencerelerde de geçiş görünür ve kısa kalır.
        """
        if not ANIM:
            return
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            return
        clock = {"t0": None}

        def step():
            try:
                if not win.winfo_exists():
                    return
                if clock["t0"] is None:
                    clock["t0"] = time.perf_counter()
                t = min(1.0, (time.perf_counter() - clock["t0"]) * 1000 / ms) if ANIM else 1.0
                win.attributes("-alpha", anim.out_cubic(t * 1.4))
                if x is not None:
                    win.geometry(f"+{x}+{int(round(y + rise * (1 - anim.out_back(t, 1.4))))}")
                if t < 1:
                    win.after(12, step)
            except Exception:
                pass
        win.after_idle(step)

    def _splash(self):
        """Açılış ekranı: pusula iğnesi sallanıp kuzeye oturur, sonra perde yukarı kayar."""
        if not ANIM:
            return
        ov = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0, cursor="hand2")
        ov.place(x=0, y=0, relwidth=1, relheight=1)
        ov._ui_fixed_palette = True
        t0 = [time.perf_counter()]
        HOLD, OUT = 2.0, 0.55
        self._splash_end = t0[0] + HOLD + OUT * .3
        title_full = tarla_dil.tr("Tarla Pusulası")
        sub_full = tarla_dil.tr("NASA verisiyle tarlana yön bul")
        # tıklayınca beklemeden kapanır
        def skip(e=None):
            t0[0] = min(t0[0], time.perf_counter() - HOLD)
            self._splash_end = time.perf_counter()
        ov.bind("<Button-1>", skip)
        # sabit "yıldız tozu": her açılışta aynı desen
        import random
        rnd = random.Random(7)
        dust = [(rnd.random(), rnd.random(), rnd.uniform(.4, 1.0), rnd.uniform(0, 6.28))
                for _ in range(46)]

        def frame():
            try:
                if not ov.winfo_exists():
                    return
                t = time.perf_counter() - t0[0]
                w, h = ov.winfo_width(), ov.winfo_height()
                if t >= HOLD + OUT:
                    ov.destroy()
                    return
                fade = 1.0
                if t > HOLD:                       # perde: hızlanarak yukarı kayar
                    k = (t - HOLD) / OUT
                    ov.place_configure(y=-int(h * anim.in_out(k)))
                    fade = 1 - anim.out_cubic(k)
                ov.delete("all")
                if w > 60 and h > 60:
                    cx, cy, R = w / 2, h / 2 - 46, 56
                    a = anim.out_cubic(t / .5) * fade
                    # yıldız tozu: yavaşça süzülen, göz kırpan noktalar
                    for px, py, s, ph in dust:
                        x = px * w
                        y = (py * h - t * 14 * s) % h
                        tw = .5 + .5 * math.sin(t * 3 * s + ph)
                        col = lerp(BG, ACC if s > .8 else MUT2, a * (.25 + .55 * tw))
                        r_ = 1 + s
                        ov.create_oval(x - r_, y - r_, x + r_, y + r_, fill=col, outline="")
                    # dışa doğru yayılan sonar halkaları
                    for i in range(3):
                        p = ((t - .25) * .7 - i / 3) % 1.0 if t > .25 else 0
                        if t > .25:
                            rr = R + 10 + p * 170
                            ov.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                           outline=lerp(BG, ACC2, (1 - p) * .55 * fade), width=2)
                    # yumuşak hale
                    for i in range(5, 0, -1):
                        rr = R + i * 7
                        ov.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                       fill=lerp(BG, GLOW, a * (1 - i / 6)), outline="")
                    ov.create_oval(cx - R, cy - R, cx + R, cy + R, fill=lerp(BG, ACC_SOFT, a),
                                   outline="")
                    # çember kendini çizer
                    sweep = anim.out_cubic((t - .1) / .7)
                    if sweep > 0:
                        ov.create_arc(cx - R, cy - R, cx + R, cy + R, start=90,
                                      extent=-359.9 * sweep, style="arc",
                                      outline=lerp(BG, ACC, fade), width=3)
                    # yörüngede dönen 3 uydu
                    for i in range(3):
                        ang_o = t * 1.6 + i * 2.094
                        ro = R + 26
                        ox, oy = cx + ro * math.cos(ang_o), cy + ro * math.sin(ang_o) * .9
                        ov.create_oval(ox - 3, oy - 3, ox + 3, oy + 3,
                                       fill=lerp(BG, WATER if i == 1 else ACC, a), outline="")
                    # pusula çizgileri sırayla belirir
                    for j, d in enumerate(range(0, 360, 30)):
                        e = anim.out_back((t - .25 - j * .04) / .3) * fade
                        if e <= 0:
                            continue
                        rr = math.radians(d)
                        r0 = R - (12 if d % 90 == 0 else 6) * min(1.2, e)
                        ov.create_line(cx + r0 * math.sin(rr), cy - r0 * math.cos(rr),
                                       cx + (R - 3) * math.sin(rr), cy - (R - 3) * math.cos(rr),
                                       fill=lerp(BG, ACC if d % 90 == 0 else MUT2, min(1, e)),
                                       width=2 if d % 90 == 0 else 1)
                    # iğne: hızlı dönüş, sonra sönümlü salınımla kuzeye oturur
                    ang = (6.0 * math.exp(-2.6 * t) * math.cos(7.5 * t)
                           + 4 * math.pi * anim.clamp(1 - t / .6) ** 2)
                    sc = anim.out_back(t / .45, 2.4)
                    rot = lambda px, py: (cx + sc * (px * math.cos(ang) - py * math.sin(ang)),
                                          cy + sc * (px * math.sin(ang) + py * math.cos(ang)))
                    n, e_, s_, w_ = rot(0, -38), rot(9, 0), rot(0, 38), rot(-9, 0)
                    ov.create_polygon(*n, *e_, *w_, fill=lerp(BG, ACC, fade), outline="")
                    ov.create_polygon(*s_, *e_, *w_, fill=lerp(BG, ACC2, fade), outline="")
                    ov.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=lerp(BG, FG, fade), outline="")
                    # başlık harf harf, sonra alt başlık ve ilerleme çubuğu
                    n_ch = int(anim.clamp((t - .45) / .55) * len(title_full))
                    ty = cy + R + 34
                    if n_ch:
                        title = ov.create_text(cx, ty, anchor="n", text=NoTr(title_full[:n_ch]),
                                               fill=lerp(BG, FG, fade), font=self.F(24, True))
                        ty = ov.bbox(title)[3] + 10
                    else:
                        ty += 44
                    sa = anim.out_cubic((t - 1.0) / .4) * fade
                    if sa > 0:
                        ov.create_text(cx, ty + 6 * (1 - sa), anchor="n", text=NoTr(sub_full),
                                       fill=lerp(BG, MUT, sa), font=self.F(11))
                    bw = 180
                    by = ty + 44
                    ov.create_line(cx - bw / 2, by, cx + bw / 2, by, fill=lerp(BG, LINE2, a),
                                   width=3, capstyle="round")
                    pr = anim.in_out(t / HOLD)
                    if pr > 0:
                        ov.create_line(cx - bw / 2, by, cx - bw / 2 + bw * pr, by,
                                       fill=lerp(BG, ACC, fade), width=3, capstyle="round")
                ov.after(16, frame)
            except Exception:
                try:
                    ov.destroy()
                except Exception:
                    pass
        frame()

    def _tween(self, ms, fn, owner=None, ease=anim.out_cubic):
        """fn(e) çağrısını ms süresince e: 0→1 (yumuşak yavaşlama) ile yinele."""
        if not ANIM:
            fn(1.0)
            return
        t0 = time.perf_counter()

        def step():
            try:
                if owner is not None and not owner.winfo_exists():
                    return
            except Exception:
                return
            t = min(1.0, (time.perf_counter() - t0) * 1000 / ms) if ANIM else 1.0
            fn(ease(t))
            if t < 1:
                self.root.after(16, step)
        step()

    def _ring_anim(self, ms=520, full=False):
        """Uygunluk halkası ve faktör çubukları dolar; full=True ise tüm ekran canlanır."""
        self._ring_id = my = getattr(self, "_ring_id", 0) + 1

        def frame(e):
            if my != self._ring_id:         # daha yeni bir animasyon başladı
                return
            self.ring_t = e
            self.swap_t = e
            if full:
                self.intro_t = e
                self.redraw_all()
            else:
                self.draw_verdict()
                self.draw_chart()
                self.draw_factors()
        if not full:
            self.intro_t = 1.0
            ms = max(ms, 520)
        self._tween(ms, frame)

    def _move_in(self, c, k):
        """Yeni analizde k. kart aşağıdan yükselerek gelir (tüm öğeler birlikte kayar)."""
        if self.intro_t >= 1:
            return
        e = anim.out_back(anim.stagger(self.intro_t, k, .1, .62), 1.2)
        dy = (1 - e) * 26
        if abs(dy) > .3:
            c.move("all", 0, dy)

    def _select(self, ekin):
        if ekin == self.sel:
            return
        self.sel = ekin
        self.draw_rank()
        self._chat_redraw()
        self._glide_rank()
        self._ring_anim(560)

    def _glide_rank(self):
        """Sıralamada vurgu kutuları hedef satıra yaylanarak kayar."""
        if not ANIM:
            self._hov_y = self._sel_y = None
            self.draw_rank()
            return

        def step(now):
            moving = False
            for name, target in (("_sel_y", self._target_sel), ("_hov_y", self._target_hov)):
                cur = getattr(self, name)
                if target is None or cur is None:
                    setattr(self, name, target)
                    continue
                d = target - cur
                if abs(d) < .5:
                    setattr(self, name, target)
                else:
                    setattr(self, name, cur + d * .24)
                    moving = True
            try:
                self.draw_rank()
            except tk.TclError:
                return False
            return moving
        self.ticker.add("rankglide", step)

    def _freq_init(self):
        self.freq_state = {"connected": False, "playing": False, "arduino": False,
                           "label": "", "left": "", "port": None}

    def open_frequency(self):
        """Frekans protokolü penceresi: Arduino deneme tonları ve çalma denetimleri."""
        old = getattr(self, "freq_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            return
        win = self.freq_win = self._window("Frekans protokolü")
        lat, lon = self.lat, self.lon
        clim = self.clim
        moist = (clim or {}).get("gwetroo") or (clim or {}).get("gwetro") or 45
        try:
            moist = float(moist)
        except Exception:
            moist = 45

        risk, dur, rit = "Deneysel ses çıkışı", "10 dk × 3 tekrar", "Deney protokolü"

        # içerik sabit genişlikte tutulur: hiçbir öğe sağdan taşmaz
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill="both", expand=True)
        inner_w = 1016 - 2 * 28
        body = tk.Frame(outer, bg=BG, width=inner_w)
        body.pack(fill="both", expand=True, padx=28)
        body.pack_propagate(False)
        head = tk.Frame(body, bg=BG)
        head.pack(fill="x", pady=(16, 0))
        head.pack_propagate(True)
        tk.Label(head, text="Frekans protokolü", bg=BG, fg=FG,
                 font=self.F(20, True)).pack(anchor="w")
        tk.Label(head, text=f"  {self.name} · {self.current()['ekin'] if self.current() else 'ekin seçilmedi'}",
                 bg=BG, fg=MUT, font=self.F(10), wraplength=680, justify="left").pack(anchor="w", pady=(6, 0))

        # Arduino durumu kutusu (tıkla: bağlan / kopar)
        ar = tk.Canvas(head, width=220, height=34, bg=BG, highlightthickness=0,
                       cursor="hand2")
        ar.pack(side="right")

        ar_state = {"busy": False}

        def draw_ar():
            ar.delete("all")
            on = ab.BUZZER.connected
            self.rrect(ar, 1, 0, 219, 33, 16, fill=ACC_SOFT if on else CARD2,
                       outline=ACC2 if on else LINE2)
            ar.create_oval(14, 12, 22, 20, fill=ACC if on else GOLD if ar_state["busy"] else MUT2,
                           outline="")
            txt = ("Bağlanıyor…" if ar_state["busy"] else
                   ("Arduino · " + str(ab.BUZZER.port)) if on else
                   ("Arduino bağla" if ab.HAVE_SERIAL else "Arduino · pyserial yok"))
            ar.create_text(30, 16, text=txt, anchor="w", fill=FG2 if on else MUT,
                           font=self.F(9))

        def toggle_ar(event=None):
            if ar_state["busy"]:
                return
            if not ab.HAVE_SERIAL:
                self.set_status("Arduino için: pip install pyserial", True)
                return
            if ab.BUZZER.connected:
                if play["on"]:                  # bağlantı kesilmeden önce sesi kes
                    stop(sync=True)
                ab.BUZZER.close()
                self.freq_state.update(connected=False, port=None)
                self.set_status("Arduino bağlantısı kesildi.")
                draw_ar()
                self.refresh_freq_strip()
                return
            ar_state["busy"] = True             # bağlanma ~2 sn sürer: pencere donmasın
            draw_ar()

            def done(ok, msg):
                ar_state["busy"] = False
                self.freq_state.update(connected=ok, port=ab.BUZZER.port)
                self.set_status(msg, not ok)
                if alive():
                    draw_ar()
                self.refresh_freq_strip()
            in_background(ab.BUZZER.connect, done)

        ar.bind("<Button-1>", toggle_ar)
        draw_ar()

        # ---- oynatma durumu (animasyon ve düğmeler bunu okur)
        SECONDS, REPEAT = 600, 3
        TOTAL = SECONDS * REPEAT + (REPEAT - 1)         # Arduino: 3 × 10 dk, aralarda 1 sn
        play = {"on": False, "fq": None, "left": 0, "phase": 0.0, "loop": False}

        def alive():
            try:
                return bool(win.winfo_exists())
            except Exception:
                return False

        # ---- bugün kartı
        card = tk.Canvas(body, bg=CARD, height=178, highlightthickness=1,
                         highlightbackground=LINE, bd=0)
        card.pack(fill="x", pady=(14, 12))
        card.pack_propagate(False)

        def paint_card(event=None):
            w = card.winfo_width()
            if w < 200:
                return
            card.delete("all")
            bx = max(300, w - 274)
            ph = play["phase"]
            glow = (0.5 + 0.5 * math.sin(ph * 2.2)) if play["on"] else 0.0
            card.create_rectangle(0, 16, 3, 134, fill=lerp(ACC2, ACC, glow) if play["on"] else ACC,
                                  outline="")
            def paragraph(y, text, font, color):
                item = card.create_text(24, y, text=text, anchor="nw", fill=color, font=font,
                                        width=max(90, bx - 48))
                return card.bbox(item)[3] + 6
            end = paragraph(15, "ŞU AN ÇALIYOR" if play["on"] else "SES TESTİ", self.F(8, True), ACC)
            end = paragraph(end, risk, self.F(17, True), FG)
            end = paragraph(end, "Bu ekran Arduino ses çıkışını denemek içindir. Tarımsal etki ölçümü değildir.",
                            self.F(9), FG2)
            end = paragraph(end, "Bir protokol seçin; bağlantıyı kontrol edip başlatın.", self.F(9), MUT)
            # sağdaki özet

            idx = next((i for i, pick in enumerate(picks) if play["on"] and pick[2] == play["fq"]),
                       selected["i"])
            fq = picks[idx][2]
            card.create_text(bx + 16, 34, text="SEÇİLİ FREKANS", anchor="w", fill=MUT2,
                             font=self.F(8, True))
            card.create_text(bx + 16, 62, text=f"{fq} Hz", anchor="w", fill=ACC,
                             font=self.F(18, True))
            # ses dalgası: çalarken hareket eder, dururken düz çizgi
            x0, x1, cy = max(bx + 130, bx + 23 + self.tw(f"{fq} Hz", 18, True)), w - 38, 62
            n = 14 if x1 - x0 >= 45 else 0
            for k in range(n):
                x = x0 + (x1 - x0) * k / (n - 1)
                if play["on"]:
                    amp = 4 + 13 * abs(math.sin(ph * (2.4 + min(fq / 4000, 4)) + k * 0.55)) \
                        * (0.55 + 0.45 * math.sin(ph * 1.3 + k * 0.9) ** 2)
                else:
                    amp = 3 + 5 * math.sin(k * .52 + ph) ** 2
                card.create_line(x, cy - amp, x, cy + amp, width=4, capstyle="round",
                                 fill=ACC if play["on"] else LINE2)
            if play["on"]:
                left = play["left"]
                card.create_text(bx + 16, 92, anchor="w", fill=FG, font=self.F(9),
                                 text=f"kalan {left // 60}:{left % 60:02d}")
                frac = 1 - left / TOTAL
                self.rrect(card, bx + 16, 112, w - 38, 118, 3, fill=LINE2, outline="")
                if frac > 0.004:
                    self.rrect(card, bx + 16, 112, bx + 16 + (w - 54 - bx) * frac, 118, 3,
                               fill=ACC, outline="")
            else:
                card.create_text(bx + 16, 90, text=dur, anchor="w", fill=FG, font=self.F(9))
                card.create_text(bx + 16, 109, text=rit, anchor="w",
                                 fill=MUT, font=self.F(8))
            actual = tarla_dil.tr("25000 Hz için güncel Arduino kodu gerekir.") if fq == 25000 else tarla_dil.tr("Arduino test sinyali")
            label = card.create_text(bx + 16, 129, text=NoTr(actual), anchor="nw", fill=MUT,
                                     font=self.F(8), width=w - bx - 42)
            box_bottom = max(168, card.bbox(label)[3] + 10)
            summary_bg = self.rrect(card, bx, 16, w - 22, box_bottom, 12, fill=CARD2,
                                     outline=lerp(LINE2, ACC2, glow) if play["on"] else LINE2)
            card.tag_lower(summary_bg)
            needed = max(box_bottom + 6, end + 15)
            if card.winfo_pixels(card.cget("height")) != needed:
                card.configure(height=needed)

        card.bind("<Configure>", paint_card)

        # ---- Deneme kartları
        grid = tk.Frame(body, bg=BG)
        grid.pack(fill="x")
        picks = [("KURAKLIK", "Deneme frekansı", 4000, "Arduino deneme tonu", ACC, True),
                 ("ISI DALGASI", "Deneme frekansı", 1000, "Arduino deneme tonu", GOLD, False),
                 ("HAŞERE", "Deneme frekansı", 25000, "Arduino deneme tonu", WATER, False)]
        reasons = (
            "Kuraklık denemesi: 4000 Hz ses çıkışını sınar. Bitkinin daha fazla su aldığı kanıtlanmış değildir; fakat tarımda ses denemeleri yapılan yerler vardır.",
            "Isı dalgası denemesi: 1000 Hz çıkış sinyalidir. Sıcaklık stresini azalttığı doğrulanmamıştır; fakat deneysel ses uygulamaları kullanılan yerler vardır.",
            "Haşere denemesi: 25000 Hz ultrasonik test değeridir. Zararlıları uzaklaştırdığı kanıtlanmış değildir; fakat ultrason denemeleri kullanılan yerler vardır. Uygun donanım gerekir.")
        selected = {"i": 0, "prev": None, "t": 1.0, "hover": None}

        def draw_pick(i, cv, active=None):
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 80:
                return
            cv.delete("all")
            title, goal2, fq, du, col, _ = picks[i]
            k = selected["t"] if i == selected["i"] else \
                (1 - selected["t"]) if i == selected["prev"] else 0.0
            hov = 0.5 if selected["hover"] == i and k < 1 else 0.0
            self.rrect(cv, 1, 1, w - 1, h - 1, 14, fill=lerp(CARD, CARD2, max(k, hov * .6)),
                       outline=lerp(LINE2, ACC2, max(k, hov * .5)))
            cv.create_text(20, 22, text=title, anchor="w", fill=MUT2, font=self.F(8, True),
                           width=max(30, w - 65))
            cv.create_text(20, 46, text=goal2, anchor="w", fill=FG2, font=self.F(9),
                           width=max(1, w - 36))
            value = f"{fq} Hz"
            size = 24 if self.tw(value, 24, True) <= w - 36 else 18
            cv.create_text(20, 82, text=value, anchor="w", fill=col, font=self.F(size, True))
            playing_this = play["on"] and play["fq"] == fq
            cv.create_rectangle(20, 111, w - 20, 114, fill=lerp(LINE2, col, k), outline="")
            cv.create_text(20, 121, anchor="nw", fill=col, font=self.F(9),
                           width=max(30, w - 38), text=reasons[i])
            if playing_this:
                cv.create_text(w - 20, 22, anchor="e", fill=col, font=self.F(8, True),
                               text="Çalıyor")
            if k > 0.02:                          # seçili kartın sağ üstünde onay işareti
                r = 9 * k
                cv.create_oval(w - 26 - r, 22 - r, w - 26 + r, 22 + r, fill=col, outline="")
                if k > 0.6:
                    cv.create_line(w - 31, 22, w - 27, 26, w - 21, 18, fill=BG, width=2)

        pick_cvs = []

        def redraw_picks():
            for k_, cv_ in enumerate(pick_cvs):
                draw_pick(k_, cv_)

        def set_hover(i):
            if selected["hover"] != i:
                selected["hover"] = i
                redraw_picks()

        for i, p_ in enumerate(picks):
            cv = tk.Canvas(grid, bg=BG, height=205, highlightthickness=0, bd=0,
                           cursor="hand2")
            cv.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))
            cv.grid_propagate(False)
            grid.columnconfigure(i, weight=1)
            cv.bind("<Configure>", lambda e, i=i, cv=cv: draw_pick(i, cv))
            cv.bind("<Button-1>", lambda e, i=i: choose(i))
            cv.bind("<Enter>", lambda e, i=i: set_hover(i))
            cv.bind("<Leave>", lambda e: set_hover(None))
            pick_cvs.append(cv)

        def choose(i):
            if i == selected["i"]:
                return
            selected.update(prev=selected["i"], i=i, t=0.0)
            if not play["on"]:
                paint_card()
            self._tween(170, lambda e: (selected.update(t=e), redraw_picks()), win)

        def repaint(event=None):
            paint_card()
            redraw_picks()

        def fit(event=None):
            try:
                body.configure(width=win.winfo_width(), height=win.winfo_height())
            except Exception:
                pass
            repaint()

        win.bind("<Configure>", fit, add="+")
        win.after(120, repaint)
        win.after(420, repaint)
        win.bind("<Map>", lambda e: repaint())

        # ---- alt: durum + butonlar (pencerenin altına sabitlenir, hiçbir zaman gizlenmez)
        bottom = tk.Frame(body, bg=BG)
        dot = tk.Canvas(bottom, width=18, height=18, bg=BG, highlightthickness=0)
        dot.pack(side="left", padx=(0, 8))
        state_lbl = tk.Label(bottom, text="Çalmıyor", bg=BG, fg=FG, font=self.F(12, True))
        state_lbl.pack(side="left")
        info_lbl = tk.Label(bottom, text="  ·  son protokol yok", bg=BG, fg=MUT,
                            font=self.F(9))
        info_lbl.pack(side="left", fill="x", expand=True)
        info_lbl.configure(anchor="w", justify="left")
        info_lbl.bind("<Configure>", lambda e: info_lbl.configure(wraplength=max(40, e.width - 5)))

        def paint_dot():
            dot.delete("all")
            if play["on"]:
                pr = (play["phase"] * 0.8) % 1.0          # dışa doğru yayılan halka
                r = 4 + 5 * pr
                dot.create_oval(9 - r, 9 - r, 9 + r, 9 + r, outline=lerp(ACC, BG, pr), width=2)
                dot.create_oval(5, 5, 13, 13, fill=ACC, outline="")
            else:
                dot.create_oval(5, 5, 13, 13, fill=MUT2, outline="")

        def anim_loop():
            """Çalarken ~25 fps: dalga, nabız ve geri sayım çubuğu."""
            if not alive() or not play["on"] or not ANIM:
                play["loop"] = False
                if alive():
                    paint_card()
                    paint_dot()
                return
            play["phase"] += 0.06
            paint_card()
            paint_dot()
            win.after(40, anim_loop)

        def start_anim():
            if not play["loop"]:
                play["loop"] = True
                anim_loop()

        tick = {"job": None}
        pending = {"stop": 0}

        def cancel_tick():
            if tick["job"]:
                try:
                    win.after_cancel(tick["job"])
                except Exception:
                    pass
                tick["job"] = None

        def in_background(job, done):
            """Seri port işi arka planda; sonuç pencere iş parçacığında işlenir."""
            box = {}

            def work():
                try:
                    box["r"] = job()
                except Exception as exc:
                    box["r"] = (False, str(exc))

            def check():
                if "r" not in box:
                    self.root.after(40, check)
                    return
                done(*box["r"])
            threading.Thread(target=work, daemon=True).start()
            self.root.after(40, check)

        def start():
            cancel_tick()
            i = selected["i"]
            title, _, fq, du, _, _ = picks[i]
            play.update(on=True, fq=fq, left=TOTAL)
            self.freq_state.update(connected=ab.BUZZER.connected, playing=True,
                                   label=f"{fq} Hz", left=f"{TOTAL // 60}:{TOTAL % 60:02d}",
                                   port=ab.BUZZER.port or self.freq_state.get("port"))
            state_lbl.configure(text=f"Çalıyor · {fq} Hz", fg=ACC)
            base = f"  ·  {title.lower()} · {du}"
            if ab.BUZZER.connected:
                info_lbl.configure(text=base + " · Arduino'ya gönderiliyor…")

                def sent(ok, msg):
                    if alive() and play["on"] and play["fq"] == fq:
                        info_lbl.configure(text=base + (" · Arduino: " + msg if ok
                                                        else " · Arduino hatası: " + msg))
                in_background(lambda: ab.BUZZER.send(fq, SECONDS, REPEAT), sent)
            else:
                info_lbl.configure(text=base + " · Arduino bağlı değil, yalnızca simülasyon")
            start_btn.set_text("↻  Yeniden başlat")
            stop_btn.set_active(True)
            redraw_picks()
            start_anim()
            self.refresh_freq_strip()

            def countdown():
                play["left"] -= 1
                if play["left"] <= 0:
                    stop()
                    return
                self.freq_state["left"] = f"{play['left'] // 60}:{play['left'] % 60:02d}"
                self.refresh_freq_strip()
                if not ANIM:
                    paint_card()
                tick["job"] = win.after(1000, countdown)
            tick["job"] = win.after(1000, countdown)

        def finish_ui(text, color, info):
            play.update(on=False, fq=None)
            self.freq_state.update(connected=ab.BUZZER.connected, playing=False, label="", left="")
            if alive():
                state_lbl.configure(text=text, fg=color)
                info_lbl.configure(text="  ·  " + info)
                start_btn.set_text("▶  Protokolü çal")
                stop_btn.set_active(False)
                redraw_picks()
                paint_card()
                paint_dot()
            self.refresh_freq_strip()

        def stop(sync=False):
            """Sayaç anında durur; Arduino'ya durdurma arka planda gönderilir."""
            cancel_tick()
            was_playing = play["on"]
            if not ab.BUZZER.connected:
                finish_ui("Durduruldu" if was_playing else "Çalmıyor", GOLD if was_playing else FG,
                          "Simülasyon durduruldu." if was_playing else "Zaten çalmıyordu.")
                return
            if sync:                                  # pencere/uygulama kapanırken: bekle
                ok, msg = ab.BUZZER.stop()
                finish_ui("Durduruldu" if ok else "Durdurulamadı", GOLD if ok else BAD, msg)
                return
            pending["stop"] += 1
            my = pending["stop"]
            finish_ui("Durduruluyor…", GOLD, "Arduino'ya durdurma komutu gönderiliyor…")

            def done(ok, msg):
                if my == pending["stop"] and not play["on"]:
                    finish_ui("Durduruldu" if ok else "Durdurulamadı", GOLD if ok else BAD, msg)
            in_background(ab.BUZZER.stop, done)

        def close_frequency():
            stop(sync=True)
            self.freq_win = None
            self._frequency_stop = None
            win.destroy()
        self._frequency_stop = lambda: stop(sync=True)
        win.on_close = close_frequency
        win.bind("<Escape>", lambda e: close_frequency())
        btns = tk.Frame(body, bg=BG)
        controls = []
        for i, (label, detail, action, primary) in enumerate((
                ("Protokolü çal", "Seçili deneme tonunu başlatır.", start, True),
                ("Durdur", "Sesi ve sayacı durdurur.", stop, False),
                ("Kapat", "Sesi durdurur ve sekmeyi kapatır.", close_frequency, False))):
            cell = tk.Frame(btns, bg=BG)
            cell.grid(row=0, column=i, sticky="nsew", padx=(0, 10))
            btns.columnconfigure(i, weight=1, uniform="freq")
            button = self.button(cell, label, action, primary=primary, height=40)
            button.configure(width=1)
            button.pack(fill="x")
            caption = tk.Label(cell, text=detail, bg=BG, fg=MUT, font=self.F(9),
                               anchor="w", justify="left")
            caption.pack(fill="x", pady=(4, 0))
            cell.bind("<Configure>", lambda e, widget=caption: widget.configure(wraplength=max(30, e.width - 4)))
            controls.append(button)
        start_btn, stop_btn, _ = controls

        foot2 = tk.Label(body, text="Gösterim değerleri için tarımsal etkinlik doğrulanmadı.",
                         bg=BG, fg=MUT2, font=self.F(8), wraplength=inner_w - 40,
                         justify="left")
        cmd_lbl = tk.Label(body, text=f"Arduino komutu:   F<frekans>,{SECONDS},{REPEAT}      →  "
                                      f"frekans · {SECONDS} sn · {REPEAT} tekrar   ·   durdurma F0,0,0",
                           bg=BG, fg=MUT2, font=self.F(8))
        # Alttan yukarı: dipnot, komut, düğmeler, durum. Hepsi üstteki kartlardan ÖNCE
        # yerleşir; pencere küçük ya da yazılar büyük olsa da düğmeler görünür kalır.
        for wdg, pad in ((foot2, (0, 10)), (cmd_lbl, (0, 4)), (btns, (6, 10)), (bottom, (12, 0))):
            wdg.pack(side="bottom", anchor="w", fill="x", pady=pad, before=head)
        paint_dot()

        def idle_preview():
            if ANIM and win.winfo_ismapped() and not play["on"]:
                play["phase"] += .12
                paint_card()
            win.after(100, idle_preview)
        win.after(100, idle_preview)

    def refresh_freq_strip(self):
        """Şeridin içeriğini duruma göre yeniden çiz."""
        cv = getattr(self, "_freq_cv", None)
        if cv is None:
            return
        cv.delete("all")
        st = self.freq_state
        W = 262
        self.rrect(cv, 1, 1, W - 1, 29, 14,
                   fill=ACC_SOFT if st["playing"] else CARD2,
                   outline=ACC2 if st["playing"] else LINE2)
        dot = ACC if st["connected"] else MUT2
        cv.create_oval(13, 11, 21, 19, fill=dot, outline="")
        cv.create_text(30, 15, text="Frekans", anchor="w",
                       fill=ACC if st["connected"] else MUT, font=self.F(9, True))
        if not st["connected"]:
            cv.create_text(84, 15, text="· Arduino bağlı değil", anchor="w",
                           fill=MUT2, font=self.F(8))
        elif st["playing"]:
            cv.create_text(84, 15, text="· " + st["label"], anchor="w",
                           fill=FG, font=self.F(9, True))
            cv.create_text(W - 34, 15, text=st["left"], anchor="e",
                           fill=ACC, font=self.F(8))
            cv.create_text(W - 18, 15, text="■", anchor="center",
                           fill=ACC, font=self.F(8, True))
        else:
            cv.create_text(84, 15, text="· hazır", anchor="w", fill=MUT, font=self.F(8))
            cv.create_text(W - 20, 15, text="›", anchor="center", fill=MUT,
                           font=self.F(10))

    @staticmethod
    def _outlook_history(live, lat, lon):
        if not live or lat is None or lon is None:
            return None
        key = (round(lat, 3), round(lon, 3))
        if key not in HIST_CACHE:
            try:
                HIST_CACHE[key] = tp.fetch_history(lat, lon)
            except Exception:
                return None  # Geçmiş seri alınamazsa model varsayılan değişkenliği kullanır.
        return HIST_CACHE.get(key)

    def open_simulation(self):
        """On yıllık risk, su, ekin seçenekleri ve temsili tarla görünümü."""
        r = self.current()
        if not r or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        crop = r["ekin"]
        clim, irr, soil = self.clim, self.irr, self.soil
        lat, lon, live = self.lat, self.lon, self.kaynak == "nasa"
        win = self._window(f"{crop} · 10 yıllık senaryo")
        win._analysis_context = id(clim), self.name, irr

        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=26, pady=(20, 0))
        history_btn = self.button(head, "Tarla geçmişi", self.open_field_history,
                                  icon="◷", height=36)
        history_btn.configure(width=205)
        history_btn.pack(side="right")
        tk.Label(head, text=crop, bg=BG, fg=FG, font=self.F(22, True)).pack(anchor="w")
        tk.Label(head, text=f"  {self.name} · {YEAR0}–{YEAR0 + 10} · sulama "
                            f"{'var' if irr else 'yok'}",
                 bg=BG, fg=MUT, font=self.F(10), wraplength=860, justify="left").pack(anchor="w", pady=(6, 0))
        note = tk.Label(win, text="Hesaplanıyor… geçmiş yıllar alınıyor.",
                        bg=BG, fg=GOLD, font=self.F(9), wraplength=960, justify="left")
        note.pack(anchor="w", padx=26, pady=(6, 10))

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill="x", padx=26, pady=(0, 10))
        advice = tk.Label(win, bg=ACC_SOFT, fg=FG, font=self.F(10, True),
                          anchor="w", justify="left", padx=12, pady=7)
        advice.pack(fill="x", padx=26, pady=(0, 8))
        foot = tk.Label(win, text="", bg=BG, fg=FG2, font=self.F(9), wraplength=960,
                        justify="left")
        foot.pack(side="bottom", anchor="w", padx=26, pady=(0, 10))
        plot = tk.Frame(win, bg=BG)
        plot.pack(fill="both", expand=True, padx=26, pady=(0, 12))
        cv = tk.Canvas(plot, bg=CARD, highlightthickness=1, highlightbackground=LINE, bd=0)
        scroll = tk.Scrollbar(plot, command=cv.yview)
        scroll.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        cv.configure(yscrollcommand=scroll.set)

        SC_NAMES = ("Hafif değişim", "Orta değişim", "Güçlü değişim")
        VIEWS = ("Risk ve su", "Ekin seçenekleri", "Tarla planı")
        state = {"sc": 1, "view": 1, "data": None, "t": 1.0,
                 "fy": 10}
        sgn = lambda v, d=1: ("+" if v >= 0 else "−") + (f1(abs(v)) if d else f0(abs(v)))
        end_year = YEAR0 + 10

        def scenario_colors():
            return WATER, ACC, BAD

        def tens(u, o, z):
            """Üç payı 10 kutuya dağıt (en büyük kalan yöntemi): (uygun, orta, zayıf)."""
            raw = [u * 10, o * 10, z * 10]
            base = [int(x) for x in raw]
            for i in sorted(range(3), key=lambda i: raw[i] - base[i], reverse=True)[:10 - sum(base)]:
                base[i] += 1
            return base

        def draw_risk(w, h):
            d, t = state["data"], state["t"]
            years = d["senaryolar"][state["sc"]]["yillar"]
            picks = [(0, f"{YEAR0} · bugün"), (len(years) // 2, str(YEAR0 + len(years) // 2)),
                     (len(years) - 1, str(end_year))]
            L, GX = 26, 135
            rh, sq = 38, min(24, max(12, int((w - 450) / 14)))
            heading = cv.create_text(L, 14, anchor="nw", width=w - 52, fill=FG2, font=self.F(11, True),
                                     text="Model sonuçlarının uygunluk dağılımı")
            y = cv.bbox(heading)[3] + 6
            legend = cv.create_text(L, y, anchor="nw", width=w - 52, fill=MUT, font=self.F(9),
                                    text="Uygun ≥75  ·  Orta 45–74  ·  Zayıf <45")
            y = cv.bbox(legend)[3] + 12
            for idx, lab in picks:
                yy = years[idx]
                u, o, z = tens(yy["uygun"], yy["orta"], yy["zayif"])
                cols = [ACC2] * u + [GOLD] * o + [BAD] * z
                cv.create_text(L, y + sq / 2, text=lab, fill=FG2, anchor="w", font=self.F(10))
                for j, col in enumerate(cols):
                    if j < t * 10:
                        x0 = GX + j * (sq + 8)
                        self.rrect(cv, x0, y, x0 + sq, y + sq, 7, fill=col, outline="")
                if t >= 1:
                    cv.create_text(GX + 10 * (sq + 8) + 10, y, anchor="nw", fill=MUT,
                                   width=max(95, w - GX - 10 * (sq + 8) - 28),
                                   font=self.F(9), text=f"%{f1(yy['uygun'] * 100)} uygun · "
                                   f"%{f1(yy['orta'] * 100)} orta · %{f1(yy['zayif'] * 100)} zayıf")
                y += rh
            y += 22
            heading = cv.create_text(L, y - 12, anchor="nw", fill=FG2, font=self.F(11, True),
                                     width=w - 52, text="Sezonda eksik kalan su")
            legend = cv.create_text(L, cv.bbox(heading)[3] + 4, anchor="nw", fill=MUT,
                                    font=self.F(9), width=w - 52,
                                    text="Tipik / yüksek açık · çubuk / çizgi")
            y = cv.bbox(legend)[3] + 12
            top = max(50, max(years[i]["su_p90"] for i, _ in picks))
            bw = max(80, w - GX - 200)
            for idx, lab in picks:
                yy = years[idx]
                cy = y + sq / 2
                cv.create_text(L, cy, text=lab, fill=FG2, anchor="w", font=self.F(10))
                self.rrect(cv, GX, cy - 6, GX + bw, cy + 6, 6, fill=LINE, outline="")
                fill_w = bw * yy["su_p50"] / top * t
                if fill_w >= 6:
                    self.rrect(cv, GX, cy - 6, GX + fill_w, cy + 6, 6, fill=WATER, outline="")
                mx = GX + bw * yy["su_p90"] / top
                cv.create_line(mx, cy - 11, mx, cy + 11, fill=FG2, width=2)
                cv.create_text(GX + bw + 14, cy, anchor="w", fill=FG, font=self.F(10, True),
                               text=f"{f0(yy['su_p50'] * t)} / {yy['su_p90']} mm")
                y += rh
            footnote = cv.create_text(L, y + 5, anchor="nw", width=w - 52, fill=MUT2, font=self.F(9),
                                      text="1 mm su açığı = dekara 1 m³ net su karşılığı. Uygulama kayıpları hariç.")
            cv.configure(scrollregion=(0, 0, w, max(h, cv.bbox(footnote)[3] + 16)))

        # ---------------------------------------------------------- görünüm 3: ekinler
        def draw_crops(w, h):
            d, t = state["data"], state["t"]
            all_rows = d["senaryolar"][state["sc"]]["ekinler"]
            ranked_by = state["crop_order"]
            ranking = sorted(all_rows, key=lambda e: (-e[ranked_by], -e["p50"]))
            rows = ranking[:8]
            if all(e["ekin"] != crop for e in rows):
                rows[-1] = next(e for e in all_rows if e["ekin"] == crop)
            X0, X1 = max(215, w * .3), w - 185
            B = h - 14
            title = cv.create_text(24, 12, anchor="nw", fill=FG2, font=self.F(15, True),
                                   width=w - 48, text=f"{end_year} · {tarla_dil.tr('Ekin seçenekleri')}")
            key = cv.create_text(24, cv.bbox(title)[3] + 4, anchor="nw", fill=MUT,
                                 font=self.F(9), width=w - 48,
                                 text="Çubuk: tipik koşul · dik çizgi: bugünkü iklim")
            T = cv.bbox(key)[3] + 10
            rh = max(39, (B - T) / len(rows))
            cv.configure(scrollregion=(0, 0, w, max(h, T + rh * len(rows) + 14)))
            for i, e in enumerate(rows):
                y = T + (i + .5) * rh
                me = e["ekin"] == crop
                if me:
                    self.rrect(cv, 10, y - rh / 2 + 1, w - 10, y + rh / 2 - 1, 8,
                               fill=ACC_SOFT, outline=ACC2)
                col = tier_color(e["p50"])
                cv.create_text(24, y, text=e["ekin"], fill=FG if me else FG2, anchor="w",
                               font=self.F(13, me), width=X0 - 39)
                self.rrect(cv, X0, y - 4, X1, y + 4, 4, fill=LINE, outline="")
                fw = (X1 - X0) * min(100, e["p50"]) / 100 * t
                if fw >= 6:
                    self.rrect(cv, X0, y - 4, X0 + fw, y + 4, 4, fill=col, outline="")
                tx = X0 + (X1 - X0) * min(100, e["bugun"]) / 100
                cv.create_line(tx, y - 8, tx, y + 8, fill=FG, width=2)
                cv.create_text(X1 + 58, y, text=f1(e['p50'] * t), fill=col, anchor="e",
                               font=self.F(11, True))
                cv.create_text(w - 24, y, anchor="e", font=self.F(9),
                               text=f"Zayıf: {f1(e['p10'])}", fill=FG2)

        # ---------------------------------------------------------- görünüm 4: tarla
        def draw_field(w, h):
            scenario = state["data"]["senaryolar"][state["sc"]]
            yy = scenario["yillar"][state["fy"]]
            field = self.field or {}
            score = yy["p50"]
            title = cv.create_text(w / 2, 14, anchor="n", width=w - 40, font=self.F(15, True),
                                   fill=FG, text=f"{YEAR0 + yy['yil']} · {SC_NAMES[state['sc']]}")
            top = cv.bbox(title)[3] + 10
            caption = cv.create_text(w / 2, h - 12, anchor="s", width=w - 48, justify="center",
                                     font=self.F(9), fill=MUT,
                                     text="Temsili renk, modelin tipik uygunluk puanını gösterir. Geleceğe ait uydu görüntüsü değildir.")
            bottom = cv.bbox(caption)[1] - 12
            points = field.get("noktalar")
            if not points or len(points) < 3:
                cv.create_text(w / 2, (top + bottom) / 2, width=w - 52, justify="center",
                               fill=MUT, font=self.F(11), text="Görsel tahmin için tarlanı haritada seç.")
                return
            image = field.get("gorsel")
            if image is not None:
                scale = min((w - 44) / image.w, (bottom - top) / image.h, 1.5)
                iw, ih = max(1, int(image.w * scale)), max(1, int(image.h * scale))
                key = (image, iw, ih, score)
                if state.get("photo_key") != key:
                    png = image.resized(iw, ih).png_simulated(score / 100)
                    state["photo"] = tk.PhotoImage(data=tarla_gorsel.b64(png))
                    state["photo_key"] = key
                cv.create_image(w / 2, (top + bottom) / 2, image=state["photo"])
                return
            projected, *_ = tarla_harita._project(points)
            low_x, high_x = min(x for x, _ in projected), max(x for x, _ in projected)
            low_y, high_y = min(y for _, y in projected), max(y for _, y in projected)
            ratio = min((w - 90) / max(1, high_x - low_x), (bottom - top - 20) / max(1, high_y - low_y))
            cx, cy = w / 2, (top + bottom) / 2
            for fraction in (.25, .5, .75):
                line_y = top + (bottom - top) * fraction
                cv.create_line(35, line_y, w - 35, line_y, fill=LINE, dash=(3, 5))
            coords = [(cx + (x - (low_x + high_x) / 2) * ratio,
                       cy - (y - (low_y + high_y) / 2) * ratio) for x, y in projected]
            cv.create_polygon(*[v for point in coords for v in point],
                              fill="#%02x%02x%02x" % tarla_gorsel.ramp(score / 100),
                              outline=FG2, width=2)

        def summary():
            sc = state["data"]["senaryolar"][state["sc"]]
            base, end = sc["yillar"][0], sc["yillar"][-1]
            if state["view"] == 1:
                if end["su_p90"] == 0:
                    return "Modelde su açığı görünmüyor. Ekimden önce tarla nemini ve güncel yağışı kontrol edin."
                action = ("Sulama kapasitenizi yüksek açıktaki değerle karşılaştırın." if irr else
                          "Sulama yoksa yüksek açığa karşı daha düşük su isteyen ekinleri karşılaştırın.")
                return f"Yüksek su açığı {f0(end['su_p90'])} mm. {action}"
            if state["view"] == 2:
                rows = sc["ekinler"]
                top = rows[0]
                resilient = max(rows, key=lambda e: (e["p10"], e["p50"]))
                return (f"Tipik koşulda {tarla_dil.tr(top['ekin'])} ({f1(top['p50'])}), "
                        f"zayıf koşulda {tarla_dil.tr(resilient['ekin'])} ({f1(resilient['p10'])}). "
                        "Çeşit ve ekim takvimini yerel verilerle doğrulayın.")
            return ""

        def draw():
            cv.delete("all")
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 200 or h < 45:
                return
            if not state["data"]:
                cv.create_text(w / 2, h / 2, text="Senaryolar hesaplanıyor…", fill=MUT,
                               font=self.F(11))
                return
            draw_h = max(h, {1: 400, 2: 340, 3: 305}[state["view"]])
            cv.configure(scrollregion=(0, 0, w, draw_h), yscrollincrement=28)
            {1: draw_risk, 2: draw_crops, 3: draw_field}[state["view"]](w, draw_h)
            if state["view"] != 3:
                advice.configure(text=summary(), wraplength=max(320, win.winfo_width() - 80))

        def animate():
            """Sekme/senaryo değişince grafiği yumuşakça yeniden aç."""
            state["aid"] = my = state.get("aid", 0) + 1
            if state["view"] == 3 or not state["data"]:
                state["t"] = 1.0
                draw()
                return

            def frame(e):
                if my == state["aid"]:
                    state["t"] = e
                    draw()
            self._tween(560, frame, win)

        # ---------------------------------------------------------- sekmeler
        sc_tabs, view_tabs = [], []

        def paint_tabs():
            for j, b in enumerate(sc_tabs):
                on = j == state["sc"]
                b.configure(bg=scenario_colors()[j] if on else CARD2, fg=ON_ACC if on else FG)
            for j, b in enumerate(view_tabs):
                on = j + 1 == state["view"]
                b.configure(bg=ACC_SOFT if on else BG, fg=ACC if on else MUT)

        def pick(kind, i):
            state["fy" if kind == "manual_year" else kind] = i
            visual_only = state["view"] == 3
            if (kind == "view" and not visual_only) or kind == "manual_year":
                stop_years()
            for widget in (advice, foot):
                widget.pack_forget()
            if visual_only:
                if not field_tools.winfo_manager():
                    field_tools.pack(fill="x", padx=26, pady=(0, 8), before=plot)
            else:
                field_tools.pack_forget()
                advice.pack(fill="x", padx=26, pady=(0, 8), before=plot)
                foot.pack(side="bottom", anchor="w", padx=26, pady=(0, 10), before=plot)
            if state["view"] == 2 and not crop_tools.winfo_manager():
                crop_tools.pack(fill="x", padx=26, pady=(0, 8), before=advice)
            elif state["view"] != 2:
                crop_tools.pack_forget()
            cv.yview_moveto(0)
            paint_tabs()
            animate()

        scenario_row = tk.Frame(bar, bg=BG)
        scenario_row.pack(fill="x")
        view_row = tk.Frame(bar, bg=BG)
        view_row.pack(fill="x", pady=(8, 0))
        field_tools = tk.Frame(win, bg=BG)
        state["crop_order"] = "p50"
        crop_tools = tk.Frame(win, bg=BG)
        tk.Label(crop_tools, text="Sırala", bg=BG, fg=FG).pack(side="left", padx=(0, 8))
        ordering = tk.StringVar(win, "p50")
        for value, label in (("p50", "Tipik koşul"), ("p10", "Zayıf koşul")):
            tk.Radiobutton(crop_tools, text=label, value=value, variable=ordering,
                           command=lambda: pick("crop_order", ordering.get()), bg=BG, fg=FG,
                           activebackground=BG, activeforeground=FG, selectcolor=CARD2,
                           highlightthickness=0).pack(side="left", padx=(0, 8))
        tk.Label(field_tools, text="Yıl", bg=BG, fg=FG).pack(side="left")
        year = tk.IntVar(win, value=end_year)
        year_menu = tk.OptionMenu(field_tools, year, *range(YEAR0, end_year + 1),
                                  command=lambda value: pick("manual_year", value - YEAR0))
        year_menu.configure(bg=CARD2, fg=FG, relief="flat", highlightthickness=0)
        year_menu.pack(side="left", padx=8)
        playback = {"job": None}

        def stop_years():
            if playback["job"] is not None:
                win.after_cancel(playback["job"])
                playback["job"] = None
            play_years.set_text("Yılları oynat")

        def show_year(value):
            year.set(YEAR0 + value)
            pick("fy", value)
            if value < 10:
                playback["job"] = win.after(1050, lambda: show_year(value + 1))
            else:
                playback["job"] = None
                play_years.set_text("Yılları oynat")

        def play_or_pause():
            if playback["job"] is not None:
                stop_years()
            elif state["data"]:
                play_years.set_text("Duraklat")
                show_year(0)

        play_years = self.button(field_tools, "Yılları oynat", play_or_pause, primary=True, height=34)
        play_years.configure(width=190)
        play_years.pack(side="left", padx=(0, 8))

        map_button = self.button(field_tools, "Tarlamı haritada seç", self.open_map, height=32)
        map_button.configure(width=205)
        map_button.pack(side="left", padx=8)

        for i, name in enumerate(SC_NAMES):
            b = tk.Button(scenario_row, text=name, bg=CARD2, fg=FG, font=self.F(9, True),
                          padx=14, pady=5, cursor="hand2", relief="flat",
                          command=lambda i=i: pick("sc", i))
            b.pack(side="left", padx=(0, 8))
            sc_tabs.append(b)
        for i, name in reversed(list(enumerate(VIEWS, 1))):
            b = tk.Button(view_row, text=name, bg=BG, fg=MUT, font=self.F(9, True),
                          padx=12, pady=7, cursor="hand2", relief="flat", wraplength=160,
                          command=lambda i=i: pick("view", i))
            b.pack(side="right", fill="x", expand=True, padx=(6, 0))
            view_tabs.append(b)
        view_tabs.reverse()
        paint_tabs()
        win._appearance_refresh = lambda: (paint_tabs(), draw())
        cv.bind("<Configure>", lambda e: draw())

        # ---------------------------------------------------------- hesap (arka planda)
        box = {}

        def work():
            hist = self._outlook_history(live, lat, lon)
            try:
                box["data"] = tp.simulate_outlook(crop, clim, irr, soil, history=hist)
            except Exception as exc:
                box["err"] = str(exc) or exc.__class__.__name__

        def wait():
            if not win.winfo_exists():
                return
            if "err" in box:
                note.configure(text="Senaryo hesaplanamadı: " + box["err"], fg=BAD)
                return
            if "data" not in box:
                self.root.after(120, wait)
                return
            d = state["data"] = box["data"]
            self.last_outlook = ((crop, self.name, irr), d)     # AI asistan bağlamı için
            g = d["gecmis"]
            history = (f"NASA POWER geçmişi {g['baslangic']}–{g['bitis']}"
                       if g else "Varsayılan yıllık değişkenlik")
            baseline = "NASA POWER aylık iklimi" if live else "Örnek iklim"
            soil_source = (soil or {}).get("source") or "Varsayılan toprak profili"
            note.configure(text=f"{tarla_dil.tr(baseline)} · {tarla_dil.tr(history)} · "
                                f"{tarla_dil.tr(soil_source)} · {d['calistirma']} "
                                + tarla_dil.tr("örnek/yıl"),
                           fg=MUT)
            foot.configure(text="Isınma ve yağış değişimleri uygulamanın varsayımlarıdır. "
                                "Zayıf / tipik / iyi uygunluk: %10 / %50 / %90 eşikleri.")
            animate()

        threading.Thread(target=work, daemon=True).start()
        self.root.after(120, wait)

    def open_field_history(self):
        if not self._require_field(self.open_field_history, "Tarla geçmişi",
                                   "için haritada en az üç köşeyle bir tarla seçin."):
            return
        field = self.field
        points = field["noktalar"]
        lat, lon = field["lat"], field["lon"]
        win = self._window("Tarla geçmişi")
        tk.Label(win, text="Tarla geçmişi", bg=BG, fg=FG, font=self.F(22, True)).pack(
            anchor="w", padx=24, pady=(18, 2))
        tk.Label(win, text=f"{self.name} · {tarla_harita.area_label(field)}",
                 bg=BG, fg=MUT, font=self.F(10)).pack(anchor="w", padx=24)
        controls = tk.Frame(win, bg=CARD, padx=14, pady=12)
        controls.pack(fill="x", padx=24, pady=12)
        controls.columnconfigure(1, weight=1)
        year = tk.StringVar(value=str(date.today().year - 1))
        crop = tk.StringVar()
        notice = tk.Label(win, bg=BG, fg=MUT, font=self.F(9), justify="left")
        notice.pack(anchor="w", padx=24, pady=(0, 8))
        for row, label, variable in ((0, "Yıl", year), (1, "Ekilen ürün", crop)):
            tk.Label(controls, text=label, bg=CARD, fg=FG, font=self.F(10)).grid(
                row=row, column=0, sticky="w", padx=(0, 12), pady=4)
            tk.Entry(controls, textvariable=variable, bg=CARD2, fg=FG, insertbackground=FG,
                     relief="flat", font=self.F(11)).grid(row=row, column=1, sticky="ew", pady=4, ipady=5)

        state = {"observations": {}, "records": tarla_ayarlar.field_crops(points), "t": 1.0,
                 "loaded": False, "animation": 0}
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        chart = tk.Canvas(body, bg=CARD, highlightthickness=0, height=165)
        chart.pack(fill="x", pady=(0, 8))
        rows = tk.Frame(body, bg=CARD)
        rows.pack(fill="both", expand=True)
        data = tk.Listbox(rows, bg=CARD, fg=FG, selectbackground=ACC_SOFT, selectforeground=FG,
                          relief="flat", highlightthickness=0, font=self.F(10), exportselection=False)
        scroll = tk.Scrollbar(rows, command=data.yview)
        scroll.pack(side="right", fill="y")
        data.pack(side="left", fill="both", expand=True, padx=12, pady=8)
        data.configure(yscrollcommand=scroll.set)
        shown_years = []

        def selected_year():
            try:
                value = int(year.get())
                if 1900 <= value <= date.today().year:
                    return value
            except ValueError:
                pass
            notice.configure(text="Geçerli bir yıl girin.", fg=BAD)
            return None

        def draw_history(_event=None):
            chart.delete("all")
            w, h = chart.winfo_width(), chart.winfo_height()
            series = list(state["observations"].values())
            if w < 80:
                return
            if not series:
                text = "Geçmiş iklim verisi alınamadı." if state["loaded"] else "NASA geçmiş verisi yükleniyor…"
                chart.create_text(w / 2, h / 2, text=text, fill=MUT, font=self.F(10),
                                  width=w - 30, justify="center")
                return
            chart.create_text(16, 18, text="NASA POWER · Yıllık yağış (mm)", fill=FG,
                              anchor="w", font=self.F(10, True))
            peak = max(1, max(item["yagis"] for item in series))
            slot = (w - 32) / len(series)
            for i, item in enumerate(series):
                x = 16 + i * slot
                height = (h - 62) * item["yagis"] / peak * state["t"]
                chart.create_rectangle(x + 2, h - 27 - height, x + slot - 2, h - 27,
                                       fill=WATER, outline="")
            for item, x, anchor in ((series[0], 16, "w"), (series[-1], w - 16, "e")):
                chart.create_text(x, h - 13, text=item["yil"], anchor=anchor, fill=MUT, font=self.F(9))

        def refresh_rows():
            shown_years[:] = sorted(set(state["observations"]) | set(map(int, state["records"])), reverse=True)
            data.delete(0, "end")
            for y in shown_years:
                item = state["observations"].get(y)
                weather = f"{f1(item['sicaklik'])} °C   ·   {f0(item['yagis'])} mm" if item else "—"
                planted = state["records"].get(str(y)) or tarla_dil.tr("Ekim kaydı yok")
                data.insert("end", f"  {y}    |    {weather}    |    {planted}")

        def save_crop():
            y = selected_year()
            value = crop.get().strip()
            if y is None:
                return
            if not value or len(value) > 80:
                notice.configure(text="1–80 karakterlik bir ürün adı girin.", fg=BAD)
                return
            try:
                state["records"] = tarla_ayarlar.field_crops(points, y, value)
            except OSError:
                notice.configure(text="Ekim kaydı kaydedilemedi.", fg=BAD)
                return
            refresh_rows()
            notice.configure(text="Ekim kaydı bu bilgisayara kaydedildi.", fg=ACC)

        def open_image():
            y = selected_year()
            if y is not None and y >= 2000:
                self.open_map(min(date(y, 7, 1), date.today() - timedelta(days=2)))
            elif y is not None:
                notice.configure(text="MODIS arşivi 2000 yılından başlar.", fg=BAD)

        def select_row(_event):
            selected = data.curselection()
            if selected:
                y = shown_years[selected[0]]
                year.set(str(y))
                crop.set(state["records"].get(str(y), ""))

        for row, label, command in ((0, "Uydu arşivini aç", open_image), (1, "Ekim kaydını kaydet", save_crop)):
            button = self.button(controls, label, command, primary=row == 0, height=35)
            button.configure(width=215)
            button.grid(row=row, column=2, sticky="ew", padx=(12, 0), pady=4)
        data.bind("<<ListboxSelect>>", select_row)
        chart.bind("<Configure>", draw_history)
        win._appearance_refresh = lambda: (draw_history(), refresh_rows())
        notice.configure(text="İklim verisi bölgeseldir. Ekim kayıtları elle eklenir.")
        refresh_rows()
        result = {}

        def load_history():
            key = (round(lat, 3), round(lon, 3))
            try:
                hist = HIST_CACHE.get(key) or tp.fetch_history(lat, lon)
                HIST_CACHE[key] = hist
                result["rows"] = hist.get("gozlemler", [])
            except Exception:
                result["rows"] = []

        def finish():
            if "rows" not in result:
                win.after(120, finish)
                return
            state["loaded"] = True
            state["observations"] = {row["yil"]: row for row in result["rows"]}
            refresh_rows()
            self._tween(720, lambda e: (state.update(t=e), draw_history()), win)

        threading.Thread(target=load_history, daemon=True).start()
        win.after(120, finish)

    def open_risk(self):
        """Afet, erozyon ve haşere göstergelerini ortak listede göster."""
        if not self.current() or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        clim, soil, name = self.clim, self.soil, self.name
        selected_crop = self.current()["ekin"]
        lat, lon, live = self.lat, self.lon, self.kaynak == "nasa"
        win = self._window("Riskler")
        win._analysis_context = id(clim), name, self.irr
        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=26, pady=(20, 0))
        tk.Label(head, text="Riskler", bg=BG, fg=FG,
                 font=self.F(22, True)).pack(anchor="w")
        tk.Label(head, text="  " + name, bg=BG, fg=MUT, font=self.F(10)).pack(side="left",
                                                                           pady=(8, 0))
        tabs = tk.Frame(win, bg=BG)
        tabs.pack(fill="x", padx=26, pady=(10, 0))
        buttons = {}
        for key, label in (("climate", "Afet ve erozyon"), ("pest", "Haşere riski")):
            button = self.button(tabs, label, lambda key=key: switch(key), small=True, height=32)
            button.configure(width=165)
            button.pack(side="left", padx=(0, 8))
            buttons[key] = button
        filters = tk.Frame(win, bg=BG)
        crop = tk.StringVar(win, selected_crop)
        month = tk.StringVar(win, tp.MONTHS[date.today().month - 1])
        choices = tuple(item["name"] for item in tp.CROPS)
        search = tk.StringVar(win)
        matching = choices
        tk.Label(filters, text="Ürün ara", bg=BG, fg=FG, font=self.F(10)).pack(side="left", padx=(0, 5))
        search_entry = tk.Entry(filters, textvariable=search, width=13, bg=CARD2, fg=FG,
                                insertbackground=FG, font=self.F(10), relief="flat")
        search_entry.pack(side="left", padx=(0, 10), ipady=3)
        tk.Label(filters, text="Ürün", bg=BG, fg=FG, font=self.F(10)).pack(side="left", padx=(0, 5))
        crop_menu = ttk.Combobox(filters, state="readonly", height=10, width=22, font=self.F(10))
        crop_menu.pack(side="left", padx=(0, 10))
        def choose_crop(_event):
            index = crop_menu.current()
            if index >= 0:
                crop.set(matching[index])

        def search_key(value):
            value = unicodedata.normalize("NFKD", value.casefold().replace("ı", "i"))
            return "".join(char for char in value if not unicodedata.combining(char))

        def refresh_crop_menu(*_args):
            nonlocal matching
            query = search_key(search.get().strip())
            matching = tuple(item for item in choices if query in search_key(item)
                             or query in search_key(tarla_dil.tr(item)))
            crop_menu.configure(values=tuple(tarla_dil.tr(item) for item in matching),
                                state="readonly" if matching else "disabled")
            if crop.get() in matching:
                crop_menu.current(matching.index(crop.get()))
            else:
                crop_menu.set(tarla_dil.tr("Ürün seçin" if matching else "Eşleşen ürün yok"))

        def select_first_match(_event):
            if matching:
                crop_menu.current(0)
                crop.set(matching[0])
            return "break"

        crop_menu.bind("<<ComboboxSelected>>", choose_crop)
        search_entry.bind("<Return>", select_first_match)
        search.trace_add("write", refresh_crop_menu)
        refresh_crop_menu()
        tk.Label(filters, text="Ay", bg=BG, fg=FG, font=self.F(10)).pack(side="left", padx=(0, 5))
        menu = tk.OptionMenu(filters, month, *tp.MONTHS)
        menu.configure(bg=CARD2, fg=FG, highlightthickness=0, font=self.F(10), relief="flat")
        menu.pack(side="left", padx=(0, 10))
        fetch_button = tk.Button(filters, text="Bölge Geçmişini Tara", command=lambda: fetch_pests(force=True),
                                 bg=CARD2, fg=FG, disabledforeground=MUT2, font=self.F(9))
        fetch_button.pack(side="left")
        tk.Label(filters, text="Bölgede daha önce görüldü mü?", bg=BG, fg=MUT,
                 font=self.F(9), wraplength=155, justify="left").pack(side="left", padx=(8, 0))
        note = tk.Label(win, text="Eğim, deprem ve geçmiş iklim verileri alınıyor…", bg=BG,
                        fg=GOLD, font=self.F(10), wraplength=840, justify="left")
        note.pack(anchor="w", padx=26, pady=(6, 12))
        footer = tk.Label(win, bg=BG, fg=MUT2, font=self.F(9), wraplength=840, justify="left")
        footer.pack(side="bottom", anchor="w", padx=26, pady=(0, 12))
        stats = tk.Canvas(win, bg=BG, highlightthickness=0, bd=0, height=118)
        stats.pack(fill="x", padx=26, pady=(0, 12))
        list_host = tk.Frame(win, bg=BG)
        list_host.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        cv = tk.Canvas(list_host, bg=BG, highlightthickness=0, bd=0, yscrollincrement=28)
        scroll = tk.Scrollbar(list_host, command=cv.yview)
        cv.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        state = {"risks": None, "t": 0.0, "phase": 0, "view": "climate"}
        LEVEL_COL = (ACC, GOLD, BAD)
        pest_levels = ("Bitki uyumu", "Orta risk", "Yüksek risk")
        pest_results = {}
        pest_pending = set()
        climate_note = ("Eğim, deprem ve geçmiş iklim verileri alınıyor…", GOLD)

        def active_rows():
            if state["view"] == "climate":
                return state["risks"]
            number = tp.MONTHS.index(month.get()) + 1
            temperature, _, _ = tarla_hasere.climate_month(clim, number)
            return tarla_hasere.risk_rows(crop.get(), temperature if live else None,
                                        pest_results.get((crop.get(), number), {}))

        def refresh_pest():
            number = tp.MONTHS.index(month.get()) + 1
            key = crop.get(), number
            candidates = tarla_hasere.for_crop(crop.get())
            can_fetch = lat is not None and lon is not None and candidates
            fetch_button.configure(state="normal" if can_fetch and key not in pest_pending else "disabled")
            if state["view"] == "pest":
                temperature, humidity, rain = tarla_hasere.climate_month(clim, number)
                values = [f"Sıcaklık {f1(temperature)} °C" if temperature is not None else "Sıcaklık —",
                          f"Nem %{f0(humidity)}" if humidity is not None else "Nem —",
                          f"Yağış {f0(rain)} mm" if rain is not None else "Yağış —"]
                message = (f"{len(candidates)} tür · " + tarla_dil.tr(month.get()) + " · "
                           + ("NASA POWER aylık ortalaması" if live else "Örnek iklim")
                           + " · " + " / ".join(values))
                if key in pest_pending:
                    message += " · Bölge geçmişi taranıyor…"
                elif lat is None or lon is None:
                    message += " · Bölge geçmişi için konum seçin."
                note.configure(fg=MUT, text=message)
                draw()

        def switch(view):
            state["view"] = view
            for key, button in buttons.items():
                button.set_active(key == view)
            if view == "pest":
                filters.pack(fill="x", padx=26, pady=(8, 0), before=note)
                footer.configure(text="En çok bulgu olan zararlılar üstte. GBIF taraması seçili ay için son 10 takvim "
                                      "yılını ve yaklaşık 200 × 200 km’lik çevreyi kapsar. Tarladaki durumu yerinde kontrol edin.")
                fetch_pests()
                refresh_pest()
            else:
                filters.pack_forget()
                footer.configure(text="Gösterge ve geçmiş sıklıklardır; resmi afet haritası değildir. "
                                      "Önemli kararlar için AFAD ve il tarım müdürlüğü verilerine bakın.")
                note.configure(text=climate_note[0], fg=climate_note[1])
                draw()
            cv.yview_moveto(0)

        def fetch_pests(force=False):
            key = crop.get(), tp.MONTHS.index(month.get()) + 1
            candidates = tarla_hasere.for_crop(key[0])
            if (key in pest_pending or (key in pest_results and not force)
                    or lat is None or lon is None or not candidates):
                return
            pest_pending.add(key)
            refresh_pest()
            result = queue.Queue()

            def query():
                found = {}
                def lookup(pest):
                    try:
                        return tarla_hasere.observations(pest, lat, lon, key[1])
                    except (OSError, ValueError, TypeError, AttributeError):
                        return ()
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=4) as pool:
                    found.update(zip(candidates, pool.map(lookup, candidates)))
                result.put(found)

            def receive():
                try:
                    pest_results[key] = result.get_nowait()
                except queue.Empty:
                    win.after(150, receive)
                    return
                pest_pending.discard(key)
                refresh_pest()

            threading.Thread(target=query, daemon=True).start()
            win.after(150, receive)

        def fit(text, size, maxw):
            """Metni genişliğe sığdır; sığmazsa sonunu … ile kes."""
            if self.tw(text, size) <= maxw:
                return text
            while len(text) > 1 and self.tw(text + "…", size) > maxw:
                text = text[:-1]
            return text.rstrip(" ,") + "…"

        # ---- üstte üç kutu: kaç risk yüksek / orta / düşük
        def draw_stats():
            stats.delete("all")
            risks, w = active_rows(), stats.winfo_width()
            if risks is None or w < 200:
                return
            pest_view = state["view"] == "pest"
            t, gap = (1.0 if pest_view else state["t"]), 12
            cw = (w - 2 * gap) / 3
            labels = ("BİTKİ UYUMU", "ORTA RİSKLİ ZARARLI", "YÜKSEK RİSKLİ ZARARLI") if pest_view else (
                "DÜŞÜK RİSK", "ORTA RİSK", "YÜKSEK RİSK")
            for i, lvl in enumerate((2, 1, 0)):
                lab = labels[lvl]
                names = [r["ad"].split(" (")[0] for r in risks if r["duzey"] == lvl]
                col = LEVEL_COL[lvl] if names else MUT2
                x = i * (cw + gap)
                self.rrect(stats, x + 1, 1, x + cw - 1, 115, 14, fill=CARD,
                           outline=col if (lvl == 2 and names) else LINE)
                stats.create_text(x + 18, 21, text=lab, fill=MUT2, anchor="w",
                                  font=self.F(9, True))
                stats.create_text(x + 18, 49, text=f0(len(names) * min(1.0, t * 1.6)), fill=col,
                                  anchor="w", font=self.F(20, True))
                subtitles = (
                    "Bitkiye konukçu olabilir; sıcaklık/kayıt desteği az.",
                    "Ürün uyumlu; sıcaklık veya bölge kaydı risk işareti.",
                    "Ürün uyumlu; sıcaklık ve bölge kaydı birlikte destekliyor.")
                caption = subtitles[lvl] if pest_view else ", ".join(names) or "yok"
                stats.create_text(x + 18, 73, anchor="nw", fill=MUT, font=self.F(9),
                                  width=max(50, cw - 36), text=caption)

        pest_photos = {}

        def pest_photo(row):
            species = row.get("species")
            if not species:
                return None
            if species not in pest_photos:
                try:
                    pest_photos[species] = tk.PhotoImage(
                        file=resource_path(f"assets/hasere/{species}.png"))
                except tk.TclError:
                    pest_photos[species] = None
            return pest_photos[species]

        # ---- liste: en yüksek risk en üstte; her satırda aynı 3 kademeli gösterge
        def draw():
            cv.delete("all")
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 200:
                return
            pest_view = state["view"] == "pest"
            risks = active_rows()
            draw_stats()
            if risks is None:
                cv.create_text(w / 2, max(60, h / 2), fill=MUT, font=self.F(11),
                               text="Hesaplanıyor" + "." * (1 + state["phase"] % 3))
                return
            if not risks:
                cv.create_text(w / 2, 32, fill=MUT, font=self.F(11),
                               text="Bu ürün için katalogda tür yok. Yerel bitki sağlığı kayıtlarını kontrol edin.")
                cv.configure(scrollregion=(0, 0, w, h))
                return
            order = sorted(risks, key=lambda r: (r["duzey"] is None, -(r["duzey"] or 0),
                                                 -r["oran"]))
            meter = w >= 700 and not pest_view
            y = 4
            for i, rk in enumerate(order):
                t = 1.0 if pest_view else min(1.0, max(0.0, state["t"] * 1.7 - i * 0.1))
                known = rk["duzey"] is not None
                lvl = rk["duzey"] if known else -1
                col = LEVEL_COL[lvl] if known else MUT2
                # ayrıntı satırı yalnızca dikkat isteyen risklerde (orta / yüksek / veri yok)
                detail = None
                if pest_view or lvl != 0:
                    detail = rk["aciklama"]
                    if "gelecek" in rk:
                        n10, f10 = int(round(rk["oran"] * 10)), int(round(rk["gelecek"] * 10))
                        if f10 != n10:
                            detail += f"  ·  {YEAR0 + 10}'da 10 yılda ~{f10} yıl"
                lab = (pest_levels if pest_view else tarla_risk.LEVELS)[lvl] if known else "Veri yok"
                pw = min(w * .38, self.tw(lab, 9, True) + 26)
                photo = pest_photo(rk) if pest_view else None
                left = 118 if photo else 62 if pest_view else 24
                title = cv.create_text(left, y + 13, text=rk["ad"], fill=FG if known else MUT,
                                       anchor="nw", font=self.F(12, True),
                                       width=max(38, w - left - pw - 35))
                badge = cv.create_text(w - 21, y + 14, text=lab, fill=col, anchor="ne",
                                       justify="right", width=pw, font=self.F(9, True))
                text_y = max(cv.bbox(title)[3], cv.bbox(badge)[3]) + 5
                if photo:
                    cv.create_image(20, y + 14, anchor="nw", image=photo)
                    credit = cv.create_text(20, y + 82, width=80, anchor="nw", fill=MUT,
                                            font=self.F(8), text=tarla_hasere.PHOTO_CREDITS.get(rk["species"], ""))
                    photo_bottom = cv.bbox(credit)[3] + 10
                elif pest_view:
                    cx, cy = 40, y + 26
                    cv.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, fill=ACC_SOFT, outline="")
                    for offset in (-5, 0, 5):
                        cv.create_line(cx - 9, cy + offset - 2, cx - 4, cy + offset,
                                       cx + 4, cy + offset, cx + 9, cy + offset - 2, fill=ACC2, width=2)
                    cv.create_oval(cx - 5, cy - 7, cx + 5, cy + 8, fill=ACC2, outline="")
                    cv.create_line(cx, cy - 3, cx, cy + 7, fill=ACC_SOFT)
                if known:
                    val = rk["deger"]
                    if rk["grup"] == "Deprem":
                        val = "10 yılda " + val
                    value = cv.create_text(left, text_y, text=val, fill=FG2, anchor="nw",
                                           width=w - left - 28, font=self.F(10))
                    text_y = cv.bbox(value)[3] + 6
                if meter and known:     # Düşük · Orta · Yüksek: dolu kutu sayısı = düzey
                    mx = left
                    for j in range(3):
                        on = j <= lvl and t * 3 > j
                        self.rrect(cv, mx + j * 44, text_y, mx + j * 44 + 38, text_y + 6, 3,
                                   fill=col if on else LINE2, outline="")
                    text_y += 13
                if detail:
                    details = cv.create_text(left, text_y, text=detail, fill=MUT, anchor="nw",
                                             font=self.F(10), width=w - left - 26)
                    text_y = cv.bbox(details)[3] + 8
                bottom = max(y + 62, text_y + 10, photo_bottom if photo else 0)
                background = self.rrect(cv, 4, y, w - 4, bottom, 14, fill=CARD,
                                        outline=col if lvl == 2 else LINE)
                cv.tag_lower(background)
                cv.create_rectangle(4, y + 14, 8, bottom - 14, fill=col, outline="")
                y = bottom + 8
            cv.configure(scrollregion=(0, 0, w, max(y + 4, h)))

        cv.bind("<Configure>", lambda e: draw())
        stats.bind("<Configure>", lambda e: draw_stats())
        box = {}
        def filters_changed(*_args):
            if state["view"] == "pest":
                fetch_pests()
                refresh_pest()
                cv.yview_moveto(0)

        crop.trace_add("write", filters_changed)
        month.trace_add("write", filters_changed)
        switch("climate")
        win._appearance_refresh = lambda: (refresh_crop_menu(), draw())

        def work():
            hist = slope = quakes = None
            if live and lat is not None:
                key = (round(lat, 3), round(lon, 3))
                if key not in HIST_CACHE:
                    try:
                        HIST_CACHE[key] = tp.fetch_history(lat, lon)
                    except Exception:
                        pass
                hist = HIST_CACHE.get(key)
                try:
                    slope = tarla_risk.fetch_slope(lat, lon)
                except Exception:
                    pass
                try:
                    quakes = tarla_risk.fetch_quakes(lat, lon, YEAR0)
                except Exception:
                    pass
            try:
                box["r"] = tarla_risk.assess(clim, soil, hist, slope, quakes)
            except Exception as exc:
                box["err"] = str(exc) or exc.__class__.__name__

        def wait():
            nonlocal climate_note
            if not win.winfo_exists():
                return
            if "err" in box:
                climate_note = ("Risk hesaplanamadı: " + box["err"], BAD)
                if state["view"] == "climate":
                    note.configure(text=climate_note[0], fg=climate_note[1])
                return
            if "r" not in box:
                state["phase"] += 1
                draw()
                self.root.after(260, wait)
                return
            state["risks"] = box["r"]
            self.last_risk = (name, box["r"])       # AI asistan bağlamı için
            missing = any(r["duzey"] is None for r in box["r"])
            climate_note = ("En yüksek riskler üstte. Geçmiş kayıtlar ve arazi göstergeleri kullanılır."
                            + ("  Bazı veriler alınamadı (internet ve konum gerekir)." if missing else ""), MUT)
            if state["view"] == "climate":
                note.configure(text=climate_note[0], fg=climate_note[1])
            self._tween(1100, lambda e: (state.update(t=e), draw()), win)

        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, wait)

    def open_rotation(self):
        r = self.current()
        if not r or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        rots = tp.build_rotations(self.results, self.irr)
        win = self._window("Rotasyon planlayıcı")
        tk.Label(win, text="Rotasyon stratejileri", bg=BG, fg=FG,
                 font=self.F(22, True)).pack(anchor="w", padx=26, pady=(22, 2))
        tk.Label(win, text=f"{self.name} · {self.soil['label']} · "
                           f"sulama {'var' if self.irr else 'yok'}",
                 bg=BG, fg=MUT, font=self.F(10)).pack(anchor="w", padx=26, pady=(0, 4))
        tk.Label(win, text="Her strateji en az 3 ekin içerir ve mevcut rotasyonla karşılaştırılır. "
                           "Puan; uygunluk, su, toprak sağlığı, çeşitlilik ve pazar paylarından oluşur.",
                 bg=BG, fg=MUT2, font=self.F(9), wraplength=830,
                 justify="left").pack(anchor="w", padx=26, pady=(0, 12))

        wrap = tk.Frame(win, bg=BG)
        wrap.pack(fill="both", expand=True, padx=26, pady=(0, 20))
        cv = tk.Canvas(wrap, bg=BG, highlightthickness=0, yscrollincrement=30)
        cv.pack(side="left", fill="both", expand=True)
        bar = tk.Scrollbar(wrap, orient="vertical", command=cv.yview, width=10)
        bar.pack(side="right", fill="y")
        cv.configure(yscrollcommand=bar.set)

        anim = {"t": 0.0 if ANIM else 1.0}

        def draw():
            cv.delete("all")
            w = cv.winfo_width() or 820
            y = 6
            for i, rot in enumerate(rots):
                h = 230
                col = tier_color(rot["puan"])
                k = min(1.0, max(0.0, anim["t"] * 1.6 - i * 0.18))     # kart kart belirir
                if k <= 0:
                    y += h + 12
                    continue
                if k < 1:               # henüz belirmekte: sade bir taslak
                    self.rrect(cv, 4, y + 14 * (1 - k), w - 8, y + h + 14 * (1 - k), 14,
                               fill=lerp(BG, CARD, k), outline=lerp(BG, LINE, k))
                    y += h + 12
                    continue
                self.rrect(cv, 4, y, w - 8, y + h, 14, fill=CARD, outline=LINE)
                cv.create_rectangle(4, y + 18, 8, y + h - 18, fill=col, outline="")
                cv.create_text(26, y + 20, text=rot["name"], fill=FG, anchor="w",
                               font=self.F(13, True))
                fill_t = min(1.0, max(0.0, anim["t"] * 1.6 - i * 0.18 - 0.2) / 0.8)
                cv.create_text(w - 26, y + 22, text=f0(rot["puan"] * fill_t), fill=col,
                               anchor="e", font=self.F(20, True))
                cv.create_text(w - 26, y + 44, text="/ 100", fill=MUT2, anchor="e",
                               font=self.F(8))
                cv.create_text(26, y + 44, text=rot["why"], fill=MUT, anchor="w",
                               font=self.F(9), width=int(w - 150))
                x, seq_y = 26, y + 80
                for step in rot["seq"]:
                    if x + self.tw(step, 10) + 60 > w - 30:
                        x, seq_y = 26, seq_y + 34
                    x = self.pill(cv, x, seq_y, step, ACC2, size=10)
                    if step != rot["seq"][-1]:
                        cv.create_text(x - 2, seq_y + 14, text="→", fill=MUT2, font=self.F(10))
                        x += 14
                # faktör barları
                fx = 26
                for key, label in (("fit", "uygunluk"), ("water", "su"), ("soil", "toprak"),
                                   ("diversity", "çeşitlilik"), ("economy", "pazar")):
                    v = rot["faktorler"][key]
                    cv.create_text(fx, y + 158, text=label, fill=MUT2, anchor="w",
                                   font=self.F(10))
                    self.rrect(cv, fx, y + 174, fx + 96, y + 179, 2, fill=LINE, outline="")
                    self.rrect(cv, fx, y + 174, fx + max(4, 96 * v * fill_t), y + 179, 2,
                               fill=tier_color(v * 100), outline="")
                    fx += 112
                if rot["riskler"]:
                    cv.create_text(26, y + 202, text="⚠ " + rot["riskler"][0], fill=GOLD,
                                   anchor="w", font=self.F(10), width=w - 70)
                y += h + 12
            cv.configure(scrollregion=(0, 0, w, y + 8))

        cv.bind("<Configure>", lambda e: draw())
        draw()
        if ANIM:
            win.after_idle(lambda: self._tween(900, lambda e: (anim.update(t=e), draw()), win))

    def open_method_details(self):
        if not self.clim:
            return
        win = self._window("Veri & açıklanabilirlik")
        tk.Label(win, text="Veri kaynakları ve varsayımlar", bg=BG, fg=FG,
                 font=self.F(20, True)).pack(anchor="w", padx=26, pady=(22, 10))
        tabs = tk.Frame(win, bg=BG)
        tabs.pack(fill="x", padx=26, pady=(0, 12))
        reading = tk.Frame(win, bg=BG)
        reading.pack(fill="both", expand=True, padx=26, pady=(0, 20))
        txt = tk.Text(reading, bg=CARD, fg=FG2, relief="flat", wrap="word", font=self.F(10),
                      padx=16, pady=14, insertbackground=ACC, highlightthickness=1,
                      highlightbackground=LINE)
        scroll = tk.Scrollbar(reading, orient="vertical", command=txt.yview)
        scroll.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.configure(yscrollcommand=scroll.set)
        r = self.current()
        lines = [
            f"KONUM   {self.name}",
        ] + ([f"TARLA   {self.field_note()}"] if self.field else []) + [
            f"KAYNAK  {'NASA POWER canlı API' if self.kaynak == 'nasa' else 'Örnek veri (Konya yaklaşımı)'}",
            "",
            "NASA VERİ SETLERİ",
            "  • MODIS MOD13Q1 · ORNL DAAC: seçili konumun güncel 250 m NDVI serisi.",
            "  • SMAP L4 ve GPM IMERG · NASA GIBS: tarla haritasındaki nem ve yağış katmanları.",
            "  • NASA POWER klimatoloji API (MERRA-2, 2001–2025, 25 yıllık aylık ortalama)",
            "    T2M, T2M_MIN, PRECTOTCORR, RH2M, GWETROOT, ALLSKY_SFC_SW_DWN",
            "  • Güneş enerjisi kW·s/m²/gün → kWh/m²/gün (÷3,6) dönüştürülür.",
            "",
            "TOPRAK",
            f"  • {self.soil['label']} — kil %{self.soil['clay']}, kum %{self.soil['sand']}, "
            f"pH {self.soil['ph']}, organik karbon %{self.soil['soc']}",
            f"  • Kaynak: {self.soil.get('source', 'SoilGrids 0-30 cm bölgesel profili')}"
            " (tarla bazlı örnekleme yerine geçmez)",
            "",
            "Ekin parametreleri",
        ]
        crop_lines = [f"{c['name']} · {c['need']} mm · {c['t'][1]}–{c['t'][2]} °C · {c['source']}"
                      for c in tp.CROPS]
        lines += [
            "",
            "PUANLAMA",
            "  • 7 faktör yamuk üyelik fonksiyonuyla 0-1'e çevrilir, ağırlıklı geometrik ortalama",
            "    ile 100'e ölçeklenir: sıcaklık %26, su %20, toprak nemi %12, bağıl nem %8,",
            "    güneş %10, don %16, soğuklama %8.",
            "  • Çok yıllık ürünlerde sıcaklık Nisan–Ekim, don riski kış ayları üzerinden ayrı",
            "    değerlendirilir; ayrıca soğuklama ihtiyacı kontrol edilir.",
            "  • Sulama açıkken su ve toprak nemi faktörleri 0,75 taban alır.",
            "",
            "10 YILLIK SENARYO",
            "  • Değişkenlik: NASA POWER aylık serisinden (2001–2024) gerçek yıllar yeniden",
            "    örneklenir; sıcak-kurak yıl gibi ilişkiler korunur. Seri alınamazsa parametrik",
            "    varsayım kullanılır (yıllık sıcaklık sd 0,7 °C, yağış sd %20).",
            "  • Hafif / orta / güçlü değişim için 10 yıllık model varsayımları:",
            "    ısınma +0,25 / +0,45 / +0,75 °C, yağış −%2 / −%4 / −%7.",
            "    İklim örnekleri senaryolar arasında ortaktır. Sonuçlar model örneklerinin dağılımıdır.",
            "  • Çıktılar: uygunluk eşikleri (%10, %50, %90) ve sezonluk net su açığı.",
            "    Her 1 mm su açığı, bir dekar için 1 m³ net suya karşılık gelir.",
            "",
            "AFET VE EROZYON RİSKİ",
            "  • Eğim: Open-Meteo Elevation API (Copernicus DEM, 90 m), 3×3 nokta, Horn yöntemi.",
            "  • Erozyon ve toprak kayması: eğim + yağışın aşındırma gücü (Fournier indeksi) +",
            "    toprak dokusundan 0-100 GÖSTERGE; olasılık değildir.",
            "  • Kuraklık, aşırı yağış, geç don, aşırı sıcak: NASA POWER geçmiş yıllarında eşiğin",
            "    aşıldığı yılların oranı (aylık ortalamalardan; günlük uç olayları kaçırabilir).",
            "  • Deprem: USGS kataloğunda 100 km içinde 1976'dan beri M5+ sayısından Poisson",
            "    olasılığı. Tarladaki hasarı değil, yakında deprem olma olasılığını gösterir.",
            "  • Resmi afet haritası değildir; AFAD ve il müdürlüğü verileriyle doğrulanmalıdır.",
            "",
            "KUANTUM-ESİNLİ ROTASYON OPTİMİZASYONU (v3.0)",
            "  • Klasik bilgisayarda çalışır; kuantum donanımı kullanılmaz. Yöntem: Quantum-behaved",
            "    PSO (Sun, Feng & Xu 2004) + benzetimli tavlama (Kirkpatrick vd. 1983).",
            "  • Veri harmonizasyonu: NASA POWER aylık klimatoloji ortak aylık ızgaraya alınır;",
            "    kullanıcı SMAP (kök nemi), ECOSTRESS (yüzey sıcaklığı), GPM (yağış) ve GEDI",
            "    (biyokütle) değerleri girerse bu ızgara onlarla kalibre edilir. Girilmezse ilgili",
            "    satır 'uyumlu gösterge' olarak NASA POWER'dan hesaplanır (SMAP ölçümü değildir).",
            "  • ET₀: Hargreaves-Samani (FAO-56 denklem 52, dünya dışı radyasyon denklem 21).",
            "  • Monte Carlo: 240 olası yıl (NASA POWER 2001–2024 gerçek yıllarından); her rotasyon",
            "    80 döngüde test edilir. Puan = ağırlıklı fayda; dayanıklılık = ortalama − λ·sd.",
            "  • Toprak sağlığı: azot dengesi (baklagil +), bitki artığı, aynı familyanın üst üste",
            "    gelmesi (hastalık döngüsü). Erozyon: çıplak ayların aylık yağış aşındırma payı ×",
            "    eğim × toprak dokusu. Ekim-hasat çakışması cezalandırılır.",
            "  • Karbon: örtü bitkisi 0,32 ± 0,08 t C/ha/yıl (Poeplau & Don 2015 meta-analizi);",
            "    baklagil ve artık katkıları varsayımdır. Karbon fiyatını kullanıcı girer.",
            "  • Pazar göstergesi ekin grubuna göre varsayımdır; verim ve gelir hesaplanmaz.",
            "  • 3 yıllık aramada sonuç, tüm kombinasyonların tarandığı 'tam tarama' ile",
            "    doğrulanabilir (pencerede 'Tam tarama ile doğrula').",
            "",
            "TARLA TAKİP PANELİ (v3.1)",
            "  • Uygulama penceresinde açılan panel; tarla kapalı döngü yaşam destek sistemi (CELSS) benzetmesiyle",
            "    ele alınır: su, azot ve karbon girdisi / çıktısı ve toprak örtüsü oranı.",
            "  • Entropi göstergesi (0-100): azot kaybı %25, organik madde tükenmesi %20, erozyon /",
            "    çıplak toprak %20, monokültür / hastalık döngüsü %15, su dengesizliği %20. Fiziksel",
            "    termodinamik entropi değildir; bozulma eğilimini özetler.",
            "  • Kararlılık indeksi = (100 − entropi) × (1 − yıllar arası sapma / 40); model göstergesi.",
            "  • Harita katmanları: termodinamik stres (ısı + su açığı + eğim), azot sızıntısı,",
            "    nem anomalisi (NASA POWER son gözlenen yıl), biyokütle / karbon (GEDI veya toprak).",
            "    NASA GIBS MODIS NDVI ve SMAP L4 döşemeleri yalnızca görseldir, hesapta kullanılmaz.",
            "  • GRACE girilirse su açığı ağırlığı büyür; NDVI girilirse bitki örtüsü stresi gösterilir.",
            "",
            "SAHA MODU (SESLİ KABİN ASİSTANI)",
            "  • Tarla 2×2 parsele bölünür; her parselin eğimi Copernicus DEM'den alınır ve",
            "    optimizasyon parsel eğimiyle tekrarlanır. Öneriler tek dosyalık HTML'e gömülür.",
            "  • Saha modu uygulama sekmesinde açılır. GPS ve ses için cihaz ve tarayıcı izinleri gerekir.",
            "",
            "BİLİNMİYENLER",
            "  • NASA POWER ızgara çözünürlüğü ~0,5° (yaklaşık 50 km); tarla ölçeğinde sapma olur.",
            "  • Haritadan çizilen sınır konumu ve alanı belirler; iklim verisi yine ızgara",
            "    hücresinden gelir, tarla sınırına göre ayrıntılanmaz.",
            "  • T2M_MIN uç don olaylarını değil aylık ortalamayı temsil eder.",
            "  • Verim, gelir ve pazar fiyatı hesaplanmaz. Sonuç ziraat mühendisiyle doğrulanmalıdır.",
            "",
            "AÇIKLAMA",
        ]
        if r:
            ex = tp.explain(r, self.clim, self.soil, self.irr)
            lines.append("  " + ex["gerekce"])
            for k in ex["riskler"]:
                lines.append("  risk: " + k)
            lines.append("  " + ex["bilgi_boslugu"])
        full_text = "\n".join(lines)
        short_text = (f"Konum: {self.name}\n\n"
                      + ("NASA POWER aylık iklim ortalamaları kullanılıyor." if self.kaynak == "nasa"
                         else "Örnek veri kullanılıyor; gerçek tarla ölçümü değildir.")
                      + "\n\nÜrün puanı; sıcaklık, su, toprak nemi, güneş ve don gibi koşullara göre hesaplanır."
                      + "\n\nToprak profili bölgesel bir yaklaşımdır. Tarla ölçümü yerine geçmez."
                      + "\n\nSenaryolar olası değişimleri gösterir; günlük hava tahmini veya gelir garantisi vermez.")
        references = (
            ("NASA Space Apps 2026", "Yarışmanın resmî veri ve kaynak listesi.",
             "https://www.spaceappschallenge.org/2026/challenges/adapting-farms-with-nasa-data/?tab=resources"),
            ("NASA POWER", "İklim ortalamaları, geçmiş aylık seri ve dönem analizi.",
             "https://power.larc.nasa.gov/docs/services/"),
            ("NASA MODIS · ORNL DAAC", "Rotasyonda kullanılan 250 m bitki örtüsü göstergesi (NDVI).",
             "https://modis.ornl.gov/data/modis_webservice.html"),
            ("NASA SMAP L4", "Haritada kök bölgesi toprak nemi.",
             "https://smap.jpl.nasa.gov/"),
            ("NASA GPM IMERG", "Haritada yağış hızı.",
             "https://gpm.nasa.gov/data/imerg"),
            ("ISRIC SoilGrids", "Toprak haritasında organik karbon katmanı.",
             "https://maps.isric.org/generated/soilgrids/soc.html"),
            ("Open-Meteo", "Konum arama ve eğim hesabında kullanılan yükselti verisi.",
             "https://open-meteo.com/en/docs/elevation-api"),
            ("USGS", "Afet ekranında geçmiş deprem kayıtları.",
             "https://earthquake.usgs.gov/fdsnws/event/1/"),
            ("NASA · ISS", "Kaynak kaybı ekranındaki uzayda su geri kazanımı örneği.",
             tarla_kayip.NASA_WATER_URL),
        )
        buttons = {}
        selected = ["Kaynakça"]

        def select_page(page):
            selected[0] = page
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            if page == "Kaynakça":
                for i, (name, description, url) in enumerate(references):
                    tag = f"reference{i}"
                    txt.insert("end", name + " ↗\n", tag)
                    txt.insert("end", description + "\n\n")
                    txt.tag_configure(tag, underline=True, font=self.F(11, True))
                    txt.tag_bind(tag, "<Button-1>", lambda _event, url=url: webbrowser.open(url))
                    txt.tag_bind(tag, "<Enter>", lambda _event: txt.configure(cursor="hand2"))
                    txt.tag_bind(tag, "<Leave>", lambda _event: txt.configure(cursor="xterm"))
            else:
                if page == "Ekin kaynakları":
                    txt.insert("end", "Ekin parametreleri\n\n", "crop_title")
                    txt.tag_configure("crop_title", font=self.F(16, True))
                    txt.insert("end", "\n\n".join(crop_lines))
                else:
                    txt.insert("end", full_text if page == "Hesap yöntemi" else short_text)
            txt.configure(state="disabled")
            txt.yview_moveto(0)
            for label, button in buttons.items():
                button.set_active(label == page)

        for col, page in enumerate(("Özet", "Kaynakça", "Hesap yöntemi", "Ekin kaynakları")):
            button = self.button(tabs, page, lambda page=page: select_page(page), height=40)
            tabs.columnconfigure(col, weight=1, uniform="sources")
            button.grid(row=0, column=col, sticky="ew", padx=(0, 6 if col < 2 else 0))
            buttons[page] = button
        select_page("Kaynakça")
        win._appearance_refresh = lambda: select_page(selected[0])

    # ------------------------------------------------------------ kuantum-esinli optimizasyon
    OPT_GOALS = [("Dengeli", dict(su=50, toprak=50, pazar=50)),
                 ("Su tasarrufu", dict(su=90, toprak=50, pazar=30)),
                 ("Toprak sağlığı", dict(su=50, toprak=90, pazar=30)),
                 ("Daha çok gelir", dict(su=30, toprak=40, pazar=90))]


    def _opt_defaults(self):
        """Pencere kapansa da korunan optimizasyon tercihleri."""
        if getattr(self, "opt_prefs", None) is None:
            self.opt_prefs = dict(su=50, toprak=50, pazar=50, risk=50, dP=0, dT=0.0, L=3,
                                  smap="", eco="", gpm="", gedi="", grace="", ndvi="",
                                  fiyat="", mevcut=None)
        self.opt_prefs.setdefault("hedef", "Dengeli")
        return self.opt_prefs

    def _default_current(self, L):
        rots = tp.build_rotations(self.results, self.irr) if self.results else []
        seq = next((r["seq"] for r in rots if r["name"] == "Mevcut rotasyon"), None)
        seq = [n for n in (seq or []) if n in tarla_optimizer.ANNUALS]
        if len(seq) < 2:
            seq = ["Kışlık buğday", "Kışlık buğday", "Ayçiçeği"]
        while len(seq) < L:
            seq.insert(0, seq[0])
        return seq[:L]

    def _context_extras(self, live, lat, lon, need_slope=True):
        """Geçmiş yıllar ve eğim (önbellekli; arka plan iş parçacığında çağrılır)."""
        hist = slope = None
        if live and lat is not None:
            key = (round(lat, 3), round(lon, 3))
            if key not in HIST_CACHE:
                try:
                    HIST_CACHE[key] = tp.fetch_history(lat, lon)
                except Exception:
                    pass
            hist = HIST_CACHE.get(key)
            if need_slope:
                if key not in SLOPE_CACHE:
                    try:
                        SLOPE_CACHE[key] = tarla_risk.fetch_slope(lat, lon)
                    except Exception:
                        SLOPE_CACHE[key] = None
                slope = SLOPE_CACHE.get(key)
        return hist, slope

    def open_soil_map(self):
        if not self.clim:
            self.set_status("Önce bir şehir veya tarla seçin.", True)
            return
        try:
            if self.map_server is None:
                self.map_server = tarla_harita.MapServer(lambda f: self.q.put(("field", f, False)))
            lat, lon = self.lat, self.lon
            example = lat is None or lon is None
            if example:
                lat, lon = 37.87, 32.48
            data = dict(name=self.name, lat=lat, lon=lon,
                        points=(self.field or {}).get("noktalar", []), example=example)
            # Immutable snapshot: an already-open map keeps the place it was opened for.
            import secrets
            route = "/toprak-" + secrets.token_hex(6)
            page = tarla_toprak.build_page(data).encode("utf-8")
            self.map_server.get_routes[route] = lambda page=page: ("text/html; charset=utf-8", page)
            if self.open_web_window("Toprak verimi ısı haritası", self.map_server.page_url(route)):
                self.set_status("Seçtiğiniz konumun toprak haritası açıldı. Katman internetten yüklenir.")
        except Exception as exc:
            self.set_status("Toprak haritası açılamadı: " + str(exc), True)

    def open_optimizer(self):
        """Rotasyon önerisi penceresi (arka planda QPSO + tavlama çalışır)."""
        if not self.current() or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        old = getattr(self, "opt_win", None)
        try:
            if old is not None and old.winfo_exists():
                old.lift()
                old.focus_force()
                return
        except Exception:
            pass
        clim, irr, soil, name = self.clim, self.irr, self.soil, self.name
        lat, lon, live, field = self.lat, self.lon, self.kaynak == "nasa", self.field
        area_ha = ((field or {}).get("alan_dekar") or 0) / 10.0 or None
        P = self._opt_defaults()
        if not P["mevcut"] or len(P["mevcut"]) != P["L"]:
            P["mevcut"] = self._default_current(P["L"])
        S = {"res": None, "busy": False, "dirty": False, "phase": 0, "selected": 0}

        # ---------------------------------------------------------- pencere
        win = self.opt_win = self._window("Ekim nöbeti önerileri")
        tk.Label(win, text="Ekim nöbeti önerileri", bg=BG, fg=FG,
                 font=self.F(22, True)).pack(anchor="w", padx=24, pady=(18, 0))
        tk.Label(win, text=name + " için hangi ekinleri hangi sırayla ekmeniz daha iyi olur?",
                 bg=BG, fg=MUT, font=self.F(10)).pack(anchor="w", padx=24, pady=(2, 14))

        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        ctl = tk.Frame(body, bg=CARD, width=270, highlightthickness=1, highlightbackground=LINE)
        ctl.pack(side="left", fill="y")
        ctl.pack_propagate(False)
        results = tk.Frame(body, bg=BG)
        results.pack(side="left", fill="both", expand=True, padx=(16, 0))
        cv = tk.Canvas(results, bg=BG, highlightthickness=0, bd=0)
        scroll = tk.Scrollbar(results, orient="vertical", command=cv.yview)
        scroll.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        cv.configure(yscrollcommand=scroll.set)

        # ---------------------------------------------------------- sol: iki soru + buton
        def heading(text, top):
            tk.Label(ctl, text=text, bg=CARD, fg=FG, font=self.F(11, True)).pack(
                anchor="w", padx=16, pady=(top, 8))

        heading("Her yıl için ekin seçin", 16)
        crop_popup = [None]

        def choose_crop(trigger, index):
            if crop_popup[0] is not None and crop_popup[0].winfo_exists():
                crop_popup[0].destroy()
            panel = crop_popup[0] = tk.Toplevel(self.root, bg=CARD)
            panel.title("Ekin seç")
            panel.transient(self.root)
            x = min(trigger.winfo_rootx(), panel.winfo_screenwidth() - 340)
            y = min(trigger.winfo_rooty() + trigger.winfo_height() + 4, panel.winfo_screenheight() - 390)
            panel.geometry(f"320x350+{max(0, x)}+{max(0, y)}")
            if ANIM:
                panel.attributes("-alpha", .87)
                self._tween(160, lambda t: panel.attributes("-alpha", .87 + .13 * t), panel)
            tk.Label(panel, text="Ekin seç", bg=CARD, fg=FG,
                     font=self.F(17, True)).pack(anchor="w", padx=14, pady=10)
            list_frame = tk.Frame(panel, bg=CARD)
            list_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
            scrollbar = tk.Scrollbar(list_frame)
            scrollbar.pack(side="right", fill="y")
            crops = sorted(tarla_optimizer.ANNUALS, key=lambda crop: tarla_dil.tr(crop).casefold())
            choices = tk.Listbox(list_frame, bg=CARD2, fg=FG, font=self.F(11), relief="flat",
                                 selectbackground=ACC2, yscrollcommand=scrollbar.set, exportselection=False)
            choices.pack(fill="both", expand=True)
            scrollbar.configure(command=choices.yview)
            for crop in crops:
                choices.insert("end", tarla_dil.tr(crop))
            current = crops.index(P["mevcut"][index]) if P["mevcut"][index] in crops else 0
            choices.selection_set(current)
            choices.activate(current)
            choices.see(current)
            choices.focus_set()

            def commit(selected_index):
                P["mevcut"][index] = crops[selected_index]
                trigger.set_text(P["mevcut"][index] + " ▾")
                panel.destroy()
                run()

            def keyboard_pick(_event):
                if choices.curselection():
                    commit(choices.curselection()[0])
            choices.bind("<Return>", keyboard_pick)
            def click_pick(event):
                row = choices.nearest(event.y)
                bounds = choices.bbox(row)
                if bounds and bounds[1] <= event.y < bounds[1] + bounds[3]:
                    commit(row)
            choices.bind("<ButtonRelease-1>", click_pick)
            panel.bind("<Escape>", lambda _event: panel.destroy())
            panel.grab_set()

        for i in range(P["L"]):
            row = tk.Frame(ctl, bg=CARD)
            row.pack(fill="x", padx=16, pady=2)
            tk.Label(row, text=f"{i + 1}. yıl", bg=CARD, fg=MUT, width=5, anchor="w",
                     font=self.F(9)).pack(side="left")
            def open_list(index=i, host=row):
                choose_crop(host.crop_button, index)
            row.crop_button = b = self.button(row, P["mevcut"][i] + " ▾", open_list, height=35)
            b.configure(width=130)
            b.pack(side="left", expand=True, fill="x")
            if ANIM:
                win.after(160 + i * 80, lambda b=b: b.set_active(True))
                win.after(610 + i * 80, lambda b=b: b.set_active(False))
        win.bind("<Destroy>", lambda e: crop_popup[0].destroy()
                 if e.widget is win and crop_popup[0] and crop_popup[0].winfo_exists() else None, add="+")

        heading("Neye önem veriyorsunuz?", 20)
        goal_btns = {}

        def set_goal(label):
            P["hedef"] = label
            P.update(dict(self.OPT_GOALS)[label])
            for k, b in goal_btns.items():
                b.set_active(k == label)
            run()
        for label, _w in self.OPT_GOALS:
            b = self.button(ctl, label, lambda l=label: set_goal(l), height=32, radius=10)
            b.pack(fill="x", padx=16, pady=(0, 6))
            goal_btns[label] = b
        win.after(60, lambda: [b.set_active(k == P["hedef"]) for k, b in goal_btns.items()])

        run_btn = self.button(ctl, "Öneri bul", lambda: run(), primary=True, height=42)
        run_btn.pack(side="bottom", fill="x", padx=16, pady=16)

        # ---------------------------------------------------------- hesap
        def run():
            if S["busy"]:
                S["dirty"] = True
                return
            S["busy"] = True
            S["err"] = None
            cv.yview_moveto(0)
            run_btn.set_busy(True)
            run_btn.set_text("Hesaplanıyor…")
            draw()
            args = dict(prio={k: P[k] / 100.0 for k in ("su", "toprak", "pazar", "risk")},
                        dT=P["dT"], dP=P["dP"] / 100.0, L=int(P["L"]), sat=self._prefs_sat(),
                        current=list(P["mevcut"]), area_ha=area_ha)
            box = {}

            def work():
                try:
                    hist, slope = self._context_extras(live, lat, lon)
                    args["sat"], _ = tarla_ikiz.satellite_inputs(args["sat"], field, lat, lon, live)
                    box["r"] = tarla_optimizer.optimize(
                        clim, irr, soil, hist, lat, live=live,
                        slope_pct=(slope or {}).get("egim_yuzde"), **args)
                except Exception as exc:
                    box["err"] = str(exc) or exc.__class__.__name__

            def wait():
                if not win.winfo_exists():
                    return
                if not box:
                    win.after(200, wait)
                    return
                S["busy"] = False
                run_btn.set_busy(False)
                run_btn.set_text("Öneri bul")
                if "err" in box:
                    S["err"] = box["err"]
                else:
                    S["err"] = None
                    S["res"] = box["r"]
                    S["selected"] = 0
                    self.last_opt = (name, irr, box["r"])
                    cv.yview_moveto(0)
                    self._tween(780, lambda e: (S.update(t=e), draw()), win)
                draw()
                if S["dirty"]:
                    S["dirty"] = False
                    run()
            def loading(now):
                if not win.winfo_exists() or not S["busy"]:
                    return False
                S["phase"] = now
                if ANIM:
                    draw()
                return True

            self.ticker.add(("optimizer", win), loading)
            threading.Thread(target=work, daemon=True).start()
            win.after(200, wait)

        # ---------------------------------------------------------- sağ: öneri
        def text(x, y, s, col=FG2, size=10, bold=False, width=None, anchor="nw", tags=()):
            kw = {"width": width} if width else {}
            it = cv.create_text(x, y, text=s, fill=col, font=self.F(size, bold),
                                anchor=anchor, tags=tags, **kw)
            b = cv.bbox(it)
            return b[3] if b else y

        def sequence(x, y, rep):
            start_x = x
            for k, (n, cvr) in enumerate(zip(rep["ekinler"], rep["ortu"])):
                needed = self.tw(n, 10, True) + 56 + (self.tw("+ kışlık örtü", 9) + 28 if cvr else 0)
                if x > start_x and x + needed > cv.winfo_width() - 24:
                    x, y = start_x, y + 36
                x = self.pill(cv, x, y, n, ACC, size=10)
                if cvr:
                    old_items = set(cv.find_all())
                    x = self.chip(cv, x - 4, y + 1, "+ kışlık örtü", ACC, size=9) + 2
                    for item in set(cv.find_all()) - old_items:
                        cv.addtag_withtag("cover_detail", item)
                if k < len(rep["ekinler"]) - 1:
                    cv.create_text(x + 2, y + 13, text="→", fill=MUT2, font=self.F(11))
                    x += 18
            return y + 26

        def show_cover(event):
            cv.delete("cover_tip")
            width = min(300, cv.winfo_width() - 32)
            x = max(16, min(event.x + 12, cv.winfo_width() - width - 18))
            y = cv.canvasy(event.y + 22)
            label = cv.create_text(x + 10, y + 8, anchor="nw", width=width - 20,
                                   fill=FG, font=self.F(10), tags="cover_tip",
                                   text="Kışlık örtü, ana ürünler arasında toprağı kaplayan bitkilerdir. Yağışın toprağı taşımasını azaltmaya yardımcı olur.")
            end = cv.bbox(label)[3]
            if end + 8 > cv.canvasy(cv.winfo_height()):
                dy = -(end - y + 46)
                cv.move(label, 0, dy)
                y, end = y + dy, end + dy
            bg = self.rrect(cv, x, y, x + width, end + 9, 9, fill=CARD2,
                            outline=ACC2, tags="cover_tip")
            cv.tag_lower(bg, label)
        cv.tag_bind("cover_detail", "<Enter>", show_cover)
        cv.tag_bind("cover_detail", "<Leave>", lambda _event: cv.delete("cover_tip"))

        def select_strategy(index):
            S["selected"] = index
            cv.yview_moveto(0)
            draw()

        def draw():
            cv.delete("all")
            w, h = cv.winfo_width(), cv.winfo_height()
            if w < 200:
                return
            res = S["res"]
            if S["busy"] or S.get("err") or res is None:
                cx, cy = w / 2, max(104, h * .37)
                self.rrect(cv, 8, 8, w - 8, max(230, h - 8), 24, fill=CARD, outline=LINE)
                if S.get("err"):
                    cv.create_text(cx, cy, text="Bir hata oldu: " + S["err"], fill=BAD,
                                   font=self.F(11), width=w - 52, justify="center")
                    return
                angle = S["phase"] * 160 % 360 if ANIM else 0
                for r, offset, color in ((44, 0, ACC), (33, 125, WATER), (22, 240, ACC2)):
                    bounds = (cx - r, cy - r, cx + r, cy + r)
                    cv.create_oval(*bounds, outline=LINE2)
                    cv.create_arc(*bounds, start=angle + offset, extent=76, style="arc",
                                  outline=color, width=3)
                cv.create_text(cx, cy + 76, text="Öneri hazırlanıyor…", fill=FG,
                               font=self.F(14, True), width=w - 52, justify="center")
                return
            selected = S["selected"]
            best, cur = res["stratejiler"][selected], res["mevcut"]
            rt = S.get("t", 1.0)

            # ---- öneri kartı
            y0 = 6 + 14 * (1 - rt)
            color = tier_color(best["puan"])
            text(24, y0 + 26, "ÖNERİMİZ" if selected == 0 else "ALTERNATİF", ACC, 10, True, width=w - 165)
            text(24, y0 + 50, "Rotasyon önerisi", FG, 20, True, width=w - 165)
            cx, cy, radius = w - 64, y0 + 62, 40
            bounds = (cx - radius, cy - radius, cx + radius, cy + radius)
            cv.create_oval(*bounds, outline=LINE2, width=6)
            cv.create_arc(*bounds, start=90, extent=-3.6 * best["puan"] * rt,
                          style="arc", outline=color, width=6)
            cv.create_text(cx, cy - 4, text=f0(best["puan"] * rt), fill=color, font=self.F(24, True))
            cv.create_text(cx, cy + 19, text="/ 100", fill=MUT2, font=self.F(9))
            y = sequence(24, y0 + 120, best) + 20
            for label, score, tone in (("Şu anki rotasyon", cur["puan"], WATER),
                                       ("Seçili rotasyon", best["puan"], color)):
                text(24, y, label, FG2, 10, width=w - 120)
                text(w - 24, y, f0(score * rt), tone, 10, True, anchor="ne")
                bar_y = y + 24
                cv.create_rectangle(24, bar_y, w - 24, bar_y + 5, fill=LINE2, outline="")
                cv.create_rectangle(24, bar_y, 24 + (w - 48) * score * rt / 100,
                                    bar_y + 5, fill=tone, outline="")
                y += 43
            fark = best["puan"] - cur["puan"]
            y = text(24, y, f"Şu anki ekim sıranıza göre fark {'+' if fark >= 0 else '−'}{f1(abs(fark))} puan.",
                     FG2, 10, width=w - 48) + 16
            explanation = best["aciklama"]
            neden = explanation["neden"][:3]
            if neden:
                y = text(24, y, "Neden?", ACC, 10, True) + 4
                for reason in neden:
                    y = text(24, y, "• " + reason, FG2, 10, width=w - 48) + 7
                y = text(24, y, "Puanlar uygulamanın hesabıdır. Tarlada ölçülen değerler için toprak analizi gerekir.",
                         MUT, 8, width=w - 60) + 10
            risk = best["aciklama"]["risk"][:2]
            if risk:
                y = text(24, y, "Dikkat", GOLD, 10, True) + 4
                for s_ in risk:
                    y = text(24, y, "• " + s_, MUT, 10, width=w - 60) + 3
                y += 10
            bg = self.rrect(cv, 1, y0, w - 1, y, 16, fill=CARD, outline=lerp(LINE, ACC2, rt))
            cv.tag_lower(bg)

            # ---- diğer seçenekler
            y += 18
            y = text(4, y, "Diğer seçenekler", FG2, 11, True) + 8
            for i, rep in enumerate(res["stratejiler"]):
                if i == selected:
                    continue
                tag = f"strategy_{i}"
                reveal = anim.stagger(rt, i, step=.13, span=.66)
                offset = 14 * (1 - reveal)
                seq = " → ".join(rep["ekinler"])
                end_y = text(20, y + 14 + offset, seq, FG2, 10, width=w - 130, tags=(tag,))
                cv.create_text(w - 20, y + 14 + offset, text=f"{f0(rep['puan'] * reveal)} puan",
                               fill=tier_color(rep["puan"]), anchor="ne", font=self.F(10, True), tags=(tag,))
                card = self.rrect(cv, 1, y + offset, w - 1, end_y + 14, 12, fill=CARD, outline=LINE, tags=(tag,))
                cv.tag_lower(card)
                cv.tag_bind(tag, "<Button-1>", lambda _event, index=i: select_strategy(index))
                cv.tag_bind(tag, "<Enter>", lambda _event: cv.configure(cursor="hand2"))
                cv.tag_bind(tag, "<Leave>", lambda _event: cv.configure(cursor=""))
                y = end_y + 26 - offset

            for note in res["harmonizasyon"]["kalibrasyon"]:
                y = text(4, y + 6, note, MUT, 9, width=w - 12)

            y = text(4, y + 8, "Bu bir rehberdir; son karar sizin. Ziraat mühendisinize danışın.",
                     MUT2, 9, width=w - 16) + 16
            cv.configure(scrollregion=(0, 0, w, max(h, y)), yscrollincrement=28)

        cv.bind("<Configure>", lambda e: draw())
        win._appearance_refresh = draw
        win.after(50, run)



    # ------------------------------------------------------------ tarla seçimi şartı
    def _has_field(self):
        return bool(self.field and len(self.field.get("noktalar") or []) >= 3)

    def _require_field(self, opener, tool, description=None):
        """Parsel bazlı araçlar önce tarla ister. Tarla yoksa seçtirir, gelince aracı açar."""
        if self._has_field():
            return True
        self._after_field = opener
        win = self._window("Önce tarlanı seç")
        tk.Label(win, text="Önce tarlanı seç", bg=BG, fg=FG,
                 font=self.F(19, True)).pack(anchor="w", padx=28, pady=(24, 6))
        tk.Label(win, text=tarla_dil.tr(tool) + " " + tarla_dil.tr(description or
            "tarlanı parsellere bölerek çalışır. Haritada tarlanın köşelerini sırayla işaretle "
            "(en az 3 köşe) ve “Bu tarlayı kullan”a bas. Tarla gelince araç kendiliğinden açılır."),
                 bg=BG, fg=FG2, font=self.F(11), wraplength=500, justify="left").pack(
            anchor="w", padx=28)
        row = tk.Frame(win, bg=BG)
        row.pack(side="bottom", fill="x", padx=28, pady=(0, 24))

        def go():
            win.destroy()
            self.open_map()

        b1 = self.button(row, "Haritada tarlamı seç", go, primary=True, icon="⌖", height=44)
        b1.configure(width=260)
        b1.pack(side="left")

        def cancel():
            self._after_field = None
            win.destroy()

        win.on_close = cancel
        b2 = self.button(row, "Vazgeç", cancel, ghost=True, height=44)
        b2.configure(width=120)
        b2.pack(side="left", padx=(8, 0))
        return False

    # ------------------------------------------------------------ Derin Uzay ikizi
    def open_telegram(self):
        win = self._window("Telegram sohbeti")
        cfg = tarla_ayarlar.load()
        token = tk.StringVar(win, cfg["telegram_token"])
        chat_id = tk.StringVar(win, cfg["telegram_chat_id"])

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=26, pady=(22, 10))
        tk.Button(header, text="Telegram’da aç", bg=CARD2, fg=FG, relief="flat",
                  font=self.F(10), command=lambda: webbrowser.open("https://t.me/tarla_pusulasi_bot")
                  ).pack(side="right")
        tk.Label(header, text="Telegram sohbeti", bg=BG, fg=FG, font=self.F(21, True)).pack(anchor="w")
        self._help_button(header, "Telegram sohbeti").pack(side="right", padx=(0, 10))
        context = tk.Label(win, bg=BG, fg=FG, font=self.F(11, True), justify="left")
        context.pack(anchor="w", padx=26, pady=(12, 0))

        connection = tarla_arayuz.fold(win, "Telegram bağlantısı", BG, FG, self.F(10, True))
        for label, var, mask in (("Bot anahtarı", token, "•"), ("Sohbet ID", chat_id, "")):
            row = tk.Frame(connection, bg=BG)
            row.pack(fill="x", padx=22, pady=3)
            tk.Label(row, text=label, width=16, anchor="w", bg=BG, fg=FG, font=self.F(10)).pack(side="left")
            tk.Entry(row, textvariable=var, show=mask, bg=CARD2, fg=FG, insertbackground=FG,
                     relief="flat", font=self.F(10)).pack(side="left", fill="x", expand=True, ipady=4)

        status = tk.Label(win, text="", bg=BG, fg=MUT, font=self.F(10), anchor="w")
        status.pack(side="bottom", fill="x", padx=26, pady=(6, 16))
        nav = tk.Frame(win, bg=BG)
        nav.pack(fill="x", padx=26, pady=8)
        panel = tk.Frame(win, bg=BG)
        panel.pack(fill="both", expand=True, padx=26)
        pages = {name: tk.Frame(panel, bg=BG) for name in ("Sürgüler", "Hava durumu", "Deprem", "Haşere")}
        buttons = {}

        def show(name):
            for key, page in pages.items():
                if key == name:
                    page.pack(fill="both", expand=True)
                else:
                    page.pack_forget()
                buttons[key].configure(bg=ACC_SOFT if key == name else CARD2)

        for name in pages:
            buttons[name] = tk.Button(nav, text=name, bg=CARD2, fg=FG, relief="flat",
                                      font=self.F(10, True), padx=14, pady=5,
                                      command=lambda key=name: show(key))
            buttons[name].pack(side="left", padx=(0, 8))
        show("Hava durumu")
        controls = tk.Frame(pages["Sürgüler"], bg=BG)
        controls.pack(fill="x")
        tk.Label(pages["Sürgüler"], text="Sürgüyü bırakınca yeni bir sınır aşımı Telegram’a bildirilir.",
                 bg=BG, fg=MUT, font=self.F(9), justify="left").pack(anchor="w")

        def credentials():
            secret, recipient = token.get().strip(), chat_id.get().strip()
            if not re.fullmatch(r"[0-9]+:[A-Za-z0-9_-]{20,}", secret):
                raise ValueError("Telegram bağlantısına geçerli bir bot anahtarı girin.")
            if not re.fullmatch(r"-?[0-9]+", recipient) or not int(recipient):
                raise ValueError("Telegram bağlantısına sayısal bir sohbet ID girin.")
            return secret, recipient

        def save():
            try:
                secret, recipient = credentials()
                tarla_ayarlar.save(telegram_token=secret, telegram_chat_id=recipient)
            except (OSError, ValueError) as exc:
                status.configure(text=str(exc), fg=BAD)
            else:
                status.configure(text="Telegram bağlantısı kaydedildi.", fg=MUT)

        tk.Button(connection, text="Kaydet", command=save, bg=CARD2, fg=FG,
                  relief="flat", font=self.F(10)).pack(anchor="e", padx=22, pady=(5, 0))

        def background(work, done):
            result = queue.Queue()

            def run():
                try:
                    result.put((work(), None))
                except Exception as error:      # her hata arayüze dönsün; "gönderiliyor"da takılmasın
                    result.put((None, error))

            def receive():
                try:
                    answer, error = result.get_nowait()
                except queue.Empty:
                    win.after(90, receive)
                    return
                done(answer, error)

            threading.Thread(target=run, daemon=True).start()
            win.after(90, receive)

        def deliver(body, done=lambda _ok: None):
            try:
                secret, recipient = credentials()
            except ValueError as exc:
                status.configure(text=str(exc), fg=BAD)
                done(False)
                return
            status.configure(text="Telegram’a gönderiliyor…", fg=MUT)

            def receive(error, failure):
                error = error or ("Telegram’a ulaşılamadı." if failure else None)
                status.configure(text=error or "Telegram uyarısı gönderildi.", fg=BAD if error else ACC)
                done(not error)

            background(lambda: self._send_telegram(secret, recipient, body), receive)

        def notify(label, amount, minimum, maximum, zone, done):
            text = tarla_dil.tr
            direction = text("ideal aralığın altına düştü" if zone < 0 else "ideal aralığın üstüne çıktı")
            body = (text("Tarla Pusulası · Deneme uyarısı") + "\n"
                    + f"{field_name} · {text(crop_name)}\n"
                    + f"{text(label)} {direction}.\n"
                    + f"{text('Girilen değer')}  {amount}\n"
                    + f"{text('İdeal aralık')}  {minimum} – {maximum}")
            deliver(body, done)

        def slider(label, unit, start, end, low, high, initial, step):
            card = tk.Frame(controls, bg=CARD, highlightbackground=LINE, highlightthickness=1)
            card.pack(fill="x", pady=(0, 10))
            line = tk.Frame(card, bg=CARD)
            line.pack(fill="x", padx=16, pady=(11, 0))
            tk.Label(line, text=label, bg=CARD, fg=FG, font=self.F(11, True)).pack(side="left")
            value_label = tk.Label(line, bg=CARD, font=self.F(11, True))
            value_label.pack(side="right")
            track = tk.Canvas(card, height=35, bg=CARD, takefocus=True, cursor="hand2",
                              highlightthickness=1, highlightbackground=CARD, highlightcolor=ACC2)
            track.pack(fill="x", padx=14, pady=2)
            detail = tk.Label(card, bg=CARD, fg=MUT, font=self.F(9), anchor="w")
            detail.pack(fill="x", padx=16, pady=(0, 10))

            def show(number):
                return f"{f1(number) if step < 1 else f0(number)} {unit}"

            def zone():
                return -1 if value < low else 1 if value > high else 0

            value = max(start, min(end, initial))
            committed = zone()
            revision = 0

            def position(number):
                return 12 + (number - start) / (end - start) * max(1, track.winfo_width() - 24)

            def draw(_event=None):
                color = BAD if zone() else ACC
                track.delete("all")
                track.create_line(position(start), 17, position(end), 17, fill=LINE2, width=5, capstyle="round")
                track.create_line(position(low), 17, position(high), 17, fill=ACC2, width=5, capstyle="round")
                x = position(value)
                track.create_oval(x - 10, 7, x + 10, 27, fill=CARD2, outline=LINE2)
                track.create_oval(x - 6, 11, x + 6, 23, fill=color, outline="")
                value_label.configure(text=show(value), fg=color)
                mode = ("İdeal aralığın altında" if zone() < 0 else
                        "İdeal aralığın üstünde" if zone() > 0 else "İdeal aralıkta")
                detail.configure(text=tarla_dil.tr(mode) + "  ·  " + tarla_dil.tr("İdeal aralık")
                                      + f"  {show(low)} – {show(high)}")

            def move(number):
                nonlocal value
                value = max(start, min(end, round(number / step) * step))
                draw()

            def mouse(event):
                track.focus_set()
                span = max(1, track.winfo_width() - 24)
                move(start + (event.x - 12) * (end - start) / span)

            def commit():
                nonlocal committed, revision
                current = zone()
                if current == committed:
                    return
                previous, committed = committed, current
                revision += 1
                sent_revision = revision
                if not current:
                    return

                def done(ok):
                    nonlocal committed
                    if not ok and revision == sent_revision:
                        committed = previous

                notify(label, show(value), show(low), show(high), current, done)

            def keyboard(delta):
                move(value + delta * step)
                commit()
                return "break"

            track.bind("<Configure>", draw)
            track.bind("<Button-1>", mouse)
            track.bind("<B1-Motion>", mouse)
            track.bind("<ButtonRelease-1>", lambda event: (mouse(event), commit()))
            track.bind("<Left>", lambda _event: keyboard(-1))
            track.bind("<Right>", lambda _event: keyboard(1))
            track.bind("<Return>", lambda _event: commit())
            draw()
            return draw

        active = None
        field_name = crop_name = ""
        redraw = []
        forecast = None
        quake_run = None

        def card(page, title, source, url):
            host = tk.Frame(pages[page], bg=CARD, highlightbackground=LINE, highlightthickness=1)
            host.pack(fill="x", pady=(0, 10))
            top = tk.Frame(host, bg=CARD)
            top.pack(fill="x", padx=16, pady=(12, 4))
            tk.Label(top, text=title, bg=CARD, fg=FG, font=self.F(12, True)).pack(side="left")
            tk.Button(top, text=source, bg=CARD, fg=WATER, relief="flat", cursor="hand2",
                      command=lambda: webbrowser.open(url)).pack(side="right")
            result = tk.Label(host, bg=CARD, fg=FG2, justify="left", anchor="w", font=self.F(10))
            result.pack(fill="x", padx=16, pady=(4, 8))
            result.bind("<Configure>", lambda event: result.configure(wraplength=max(160, event.width - 8)))
            actions = tk.Frame(host, bg=CARD)
            actions.pack(fill="x", padx=16, pady=(2, 12))
            return result, actions

        def action(row, name, command):
            button = tk.Button(row, text=name, command=command, bg=CARD2, fg=FG,
                               relief="flat", padx=12, pady=5, font=self.F(9, True))
            button.pack(side="left", padx=(0, 7))
            return button

        def demo(text):
            deliver(tarla_dil.tr("Tarla Pusulası · Deneme uyarısı") + "\n"
                    + (field_name or tarla_dil.tr("Tarla")) + "\n" + tarla_dil.tr(text))

        weather_label, weather_actions = card("Hava durumu", "Yarınki hava tahmini",
                                              "Open-Meteo", "https://open-meteo.com/en/docs")
        pest_label, pest_actions = card("Haşere", "Muhtemel haşere baskını", "GBIF + Open-Meteo",
                                        "https://www.gbif.org/occurrence/search")

        def check_pests():
            if not crop_name or self.lat is None or self.lon is None:
                pest_label.configure(text="Ana ekranda önce konumu analiz edip bir ürün seçin.")
                return
            if forecast is None:
                pest_label.configure(text="Haşere kontrolü için yarınki hava tahmini alınıyor…")
                load_weather(scan=True)
                return
            location, crop, lat, lon = active, crop_name, self.lat, self.lon
            day, values = forecast
            temperature = values["temperature_2m_mean"]
            pest_label.configure(text="Bölge geçmişi taranıyor…")

            def display(rows, error):
                if active != location:
                    return
                matches = [tarla_dil.tr(name) for name, count in rows or () if count]
                if matches:
                    summary = tarla_dil.tr("Yarın sıcaklık uygun ve bölgede geçmiş kayıt var") + "\n" + ", ".join(matches)
                    deliver(f"{tarla_dil.tr('Haşere izleme bildirimi')}\n{field_name} · {tarla_dil.tr(crop)}\n"
                            f"{day} · {f1(temperature)} °C\n{summary}\n"
                            + tarla_dil.tr("Kaynak: GBIF geçmiş gözlemleri ve Open-Meteo tahmini. Tarlada kontrol edin."))
                elif error or any(count is None for _, count in (rows or ())):
                    summary = tarla_dil.tr("Bölge kayıtları eksik. Yerel duyurulara bakın.")
                elif not rows:
                    summary = tarla_dil.tr("Yarınki sıcaklıkla eşleşen, sıcaklık verisi olan tür bulunamadı.")
                else:
                    summary = tarla_dil.tr("Eşleşen türler için bölge geçmişinde kayıt bulunamadı.")
                pest_label.configure(text=summary + "\n" + tarla_dil.tr(
                    "GBIF geçmiş gözlemleri gösterir. Baskın doğrulaması için yerel duyurulara ve tarladaki belirtilere bakın."))

            background(lambda: tarla_hasere.scouting_signals(crop, temperature, lat, lon,
                                                             int(day[5:7])), display)

        def load_weather(scan=False):
            nonlocal forecast
            if self.lat is None or self.lon is None:
                weather_label.configure(text="Canlı veriler için ana ekranda bir konum analiz edin.")
                return
            location, lat, lon = active, self.lat, self.lon
            weather_label.configure(text="Hava tahmini alınıyor…")

            def display(answer, error):
                nonlocal forecast
                if location != active:
                    return
                if error:
                    weather_label.configure(text="Open-Meteo tahmini alınamadı. Yeniden deneyin.")
                    if scan:
                        pest_label.configure(text="Haşere kontrolü için yarınki sıcaklık alınamadı.")
                    return
                forecast = answer
                day, values = answer
                rain = values["rain_sum"] + values["showers_sum"]
                weather_label.configure(text=f"{day} · {f1(values['temperature_2m_min'])} – "
                                             f"{f1(values['temperature_2m_max'])} °C\n"
                                             + tarla_dil.tr("Yağış olasılığı") + f" %{f0(values['precipitation_probability_max'])}"
                                             + f" · {tarla_dil.tr('Yağmur')} {f1(rain)} mm"
                                             + f" · {tarla_dil.tr('Rüzgar hamlesi')} {f0(values['wind_gusts_10m_max'])} km/sa")
                if scan:
                    check_pests()

            background(lambda: tarla_risk.tomorrow_weather(lat, lon), display)

        action(weather_actions, "Tahmini yenile", load_weather)
        for button, text in (
            ("Deneme · Yağmur", "Yarın yağmur bekleniyor. Tarlaya çıkmadan önce yağış saatlerini kontrol edin."),
            ("Deneme · Kuvvetli rüzgar", "Yarın kuvvetli rüzgar bekleniyor. Açık alandaki malzemeleri sabitleyin."),
            ("Deneme · Don", "Yarın don riski var. Hassas bitkiler için koruma hazırlığını kontrol edin."),
        ):
            action(weather_actions, button, lambda message=text: demo(message))
        action(pest_actions, "Kontrol et ve bildir", check_pests)
        action(pest_actions, "Deneme · Muhtemel haşere baskını", lambda: demo(
            (f"{tarla_dil.tr(crop_name)} · " if crop_name else "") + tarla_dil.tr(
                "Muhtemel haşere baskını. Yaprak altlarını ve taze zarar izlerini kontrol edin.")))
        action(pest_actions, "Resmî bitki sağlığı duyuruları", lambda: webbrowser.open(
            "https://gd.eppo.int/country/TR/reporting"))

        quake_label, quake_actions = card("Deprem", "Yakındaki depremleri izle", "USGS",
                                          "https://earthquake.usgs.gov/earthquakes/map/")
        threshold = tk.StringVar(win, "4.5")
        tk.Label(quake_actions, text="En düşük büyüklük", bg=CARD, fg=FG).pack(side="left", padx=(0, 6))
        tk.Spinbox(quake_actions, from_=1.0, to=9.9, increment=.5, textvariable=threshold,
                   format="%.1f", width=5).pack(side="left", padx=(0, 10))

        def stop_quakes():
            nonlocal quake_run
            quake_run = None
            watch.configure(text="Takibi başlat")
            quake_label.configure(text="100 km çevre taranır. Takip, bu sekme açık kaldığı sürece çalışır.")

        def toggle_quakes():
            nonlocal quake_run
            if quake_run is not None:
                stop_quakes()
                return
            try:
                minimum = float(threshold.get().replace(",", "."))
                if not 1 <= minimum <= 9.9:
                    raise ValueError
            except ValueError:
                quake_label.configure(text="Büyüklüğü 1,0 ile 9,9 arasında girin.")
                return
            if self.lat is None or self.lon is None:
                quake_label.configure(text="Canlı veriler için ana ekranda bir konum analiz edin.")
                return
            try:
                credentials()
            except ValueError as error:
                status.configure(text=str(error), fg=BAD)
                return
            lat, lon, place, started = self.lat, self.lon, field_name, time.time()
            watch_key = object()
            quake_run = watch_key
            seen = set()
            last_check = started
            watch.configure(text="Takibi durdur")
            quake_label.configure(text="USGS kayıtları kontrol ediliyor…")

            def poll():
                if quake_run is not watch_key:
                    return
                checked_at = time.time()
                since = max(started, last_check - 3600)

                def receive(events, error):
                    nonlocal last_check
                    if quake_run is not watch_key:
                        return
                    if error:
                        quake_label.configure(text="USGS verisi alınamadı. Takip yeniden deneyecek.")
                    else:
                        last_check = checked_at
                        quake_label.configure(text=f"{place} · 100 km · M{f1(minimum)}+ · "
                                                    + tarla_dil.tr("Dakikada bir kontrol ediliyor."))
                        for event_id, magnitude, title, at, url in events:
                            if event_id in seen:
                                continue
                            seen.add(event_id)
                            stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(at / 1000))
                            deliver(f"{tarla_dil.tr('Deprem bildirimi')} · USGS\n{place} · M{f1(magnitude)}\n"
                                    f"{title}\n{stamp}\n{url}",
                                    lambda success, key=event_id: None if success else seen.discard(key))
                    win.after(60000, poll)

                background(lambda: tarla_risk.recent_quakes(lat, lon, minimum, since), receive)

            poll()

        watch = action(quake_actions, "Takibi başlat", toggle_quakes)
        action(quake_actions, "Deneme · Deprem", lambda: demo(
            "Örnek deprem bildirimi. Tarla çevresinde M5,2 büyüklüğünde örnek olay."))
        stop_quakes()

        def refresh(event=None):
            nonlocal active, field_name, crop_name, forecast
            if event is not None and event.widget is not win:
                return
            selected = self.current()
            location_key = (self.lat, self.lon, (self.field or {}).get("kayit_adi") or self.name)
            key = (location_key, id(self.clim), selected["ekin"] if selected else None, self.irr)
            if active == key:
                return
            previous_place = active[0] if active else None
            if quake_run is not None and previous_place != location_key:
                stop_quakes()
            active = key
            forecast = None
            field_name = (self.field or {}).get("kayit_adi") or self.name or "Tarla"
            crop_name = selected["ekin"] if selected else ""
            pest_label.configure(text="Yarınki sıcaklık ve bölge geçmişi eşleşirse Telegram’a izleme bildirimi gider.")
            load_weather()
            for child in controls.winfo_children():
                child.destroy()
            redraw.clear()
            if not selected:
                context.configure(text="Ana ekranda önce konumu analiz edip bir ürün seçin.")
                return
            context.configure(text=f"{field_name} · {tarla_dil.tr(crop_name)}")
            limits = selected["kriter"]
            redraw.append(slider("Sıcaklık", "°C", -30, 55, *limits["t"][1:3],
                                 selected["ortalama_sicaklik"], .1))
            redraw.append(slider("Bağıl nem", "%", 0, 100, *limits["rh"][1:3],
                                 selected["bagil_nem"], 1))

        win.bind("<Map>", refresh, add="+")
        win._appearance_refresh = lambda: [draw() for draw in redraw]
        refresh()

    @staticmethod
    def _send_telegram(token, chat_id, text):
        payload = {"chat_id": int(chat_id), "text": text, "link_preview_options": {"is_disabled": True}}
        request = Request(f"https://api.telegram.org/bot{token}/sendMessage",
                          data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=12) as response:
                answer = json.load(response)
        except HTTPError as exc:
            if exc.code in (401, 404):
                return "Telegram bot anahtarı kabul edilmedi."
            if exc.code in (400, 403):
                return "Telegram’da botu açıp Başlat’a basın ve sohbet ID’yi kontrol edin."
            if exc.code == 429:
                return "Telegram kısa süreli bir sınır uyguladı. Biraz bekleyip yeniden deneyin."
            return "Telegram mesajı kabul etmedi."
        except (OSError, ValueError):
            return "Telegram’a ulaşılamadı. Mesaj görünmüyorsa bağlantıyı kontrol edin."
        return None if isinstance(answer, dict) and answer.get("ok") is True else "Telegram mesajı kabul etmedi."

    def open_resource_loss(self):
        return tarla_kayip.open_window(self)

    def open_twin(self):
        """Deep-Space Planetary Digital Twin: parsel bazlı termodinamik ve besin dengesi."""
        if not self.current() or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        if not self._require_field(self.open_twin, "Derin Uzay ikizi"):
            return
        clim, irr, soil, name = self.clim, self.irr, self.soil, self.name
        lat, lon, live, field = self.lat, self.lon, self.kaynak == "nasa", self.field
        P = self._opt_defaults()
        L = int(P["L"])
        cur = P["mevcut"] if P["mevcut"] and len(P["mevcut"]) == L else self._default_current(L)
        prio = {k: P[k] / 100.0 for k in ("su", "toprak", "pazar", "risk")}
        area = (field.get("alan_dekar") or 0) / 10.0 or None
        win = self._window("Derin Uzay ikizi · termodinamik tarla")

        # ---------------------------------------------------------- başlık
        head = tk.Frame(win, bg=BG)
        head.pack(fill="x", padx=24, pady=(16, 0))
        orbit = tk.Canvas(head, width=54, height=54, bg=BG, highlightthickness=0)
        orbit.pack(side="left")
        tb = tk.Frame(head, bg=BG)
        tb.pack(side="left", padx=12)
        tk.Label(tb, text="DEEP-SPACE PLANETARY DIGITAL TWIN", bg=BG, fg=ACC,
                 font=self.F(9, True)).pack(anchor="w")
        tk.Label(tb, text="Termodinamik ve besin dengeleme ikizi", bg=BG, fg=FG,
                 font=self.F(19, True)).pack(anchor="w")
        sub = tk.Label(tb, text=name + " · " + tarla_dil.tr("kapalı döngü yaşam destek mantığı"),
                       bg=BG, fg=MUT, font=self.F(10))
        sub.pack(anchor="w")
        data_cv = tk.Canvas(win, bg=BG, height=74, highlightthickness=0, bd=0)
        data_cv.pack(fill="x", padx=24, pady=(10, 8))
        foot = tk.Label(win, text="Model göstergeleri; ölçüm değildir. Su tutma ve iletkenlik: Saxton & "
                                  "Rawls (2006). Sızma artışı: Basche & DeLonge (2019) örtü bitkisi "
                                  "meta-analizi (+%35 ort.); kök kanalı etkisi (en çok +%10) varsayımdır. "
                                  "Kök derinliği: FAO-56 Tablo 22. Entropi fiziksel entropi değil, "
                                  "bozulma göstergesidir.",
                        bg=BG, fg=MUT2, font=self.F(9), wraplength=1180, justify="left")
        foot.pack(side="bottom", anchor="w", padx=24, pady=(0, 12))
        body = tk.Frame(win, bg=BG)
        body.pack(fill="both", expand=True, padx=24, pady=(0, 8))
        body.columnconfigure(0, weight=11, uniform="tw")
        body.columnconfigure(1, weight=10, uniform="tw")
        body.rowconfigure(1, weight=1)
        tabs = tk.Canvas(body, bg=BG, height=40, highlightthickness=0, bd=0, cursor="hand2")
        tabs.grid(row=0, column=0, sticky="ew", padx=(0, 10), pady=(0, 8))
        mp = tk.Canvas(body, bg=CARD, highlightthickness=1, highlightbackground=LINE, bd=0,
                       cursor="hand2")
        mp.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        rp = tk.Canvas(body, bg=BG, highlightthickness=0, bd=0, yscrollincrement=28)
        rp.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(10, 0))

        LAYERS = (("azot", "Azot kaybı"), ("entropi", "Entropi"), ("ciplak", "Çıplak toprak"),
                  ("kazanc", "Müdahale kazancı"))
        S = {"data": None, "err": None, "sel": 0, "layer": 0, "t": 1.0, "phase": 0.0,
             "photo": None, "photo_key": None, "hits": [], "tab_hits": []}

        def alive():
            try:
                return bool(win.winfo_exists())
            except Exception:
                return False

        # ---------------------------------------------------------- yörünge animasyonu
        def draw_orbit():
            orbit.delete("all")
            ph = S["phase"]
            orbit.create_oval(7, 7, 47, 47, outline=LINE2, width=2)
            orbit.create_oval(17, 17, 37, 37, fill=ACC_SOFT, outline=ACC2)
            orbit.create_oval(23, 23, 31, 31, fill=ACC, outline="")
            a = ph * 1.6
            x, y = 27 + 20 * math.cos(a), 27 + 20 * math.sin(a)
            orbit.create_oval(x - 4, y - 4, x + 4, y + 4, fill=WATER, outline="")

        def tick():
            if not alive():
                return
            S["phase"] += 0.05
            draw_orbit()
            if S["data"]:
                draw_map(pulse_only=True)
            elif int(S["phase"] * 20) % 8 == 0:
                draw_data()
            if ANIM:
                win.after(50, tick)

        # ---------------------------------------------------------- veri şeridi
        def draw_data():
            data_cv.delete("all")
            w = data_cv.winfo_width()
            d = S["data"]
            if w < 200:
                return
            cards = (d["veri"] if d else []) + ([dict(
                ad="Toprak (SoilGrids)", durum="model",
                deger=f"{f1(d['toprak']['awc_mm'])} mm",
                aciklama=tarla_dil.tr("su tutma 0-30 cm · iletkenlik") + f" {f1(d['toprak']['ksat'])} mm/sa")]
                if d else [])
            if not cards:
                data_cv.create_text(4, 37, anchor="w", fill=MUT, font=self.F(10),
                                    text="NASA verileri alınıyor…" + "." * (int(S["phase"] * 4) % 3))
                return
            gap = 10
            cw = (w - gap * (len(cards) - 1)) / len(cards)
            col = {"canlı": ACC, "girildi": WATER, "vekil": GOLD, "yok": BAD, "model": MUT}
            for i, c in enumerate(cards):
                x = i * (cw + gap)
                self.rrect(data_cv, x + 1, 1, x + cw - 1, 73, 12, fill=CARD, outline=LINE)
                data_cv.create_text(x + 14, 18, text=c["ad"], anchor="w", fill=MUT2,
                                    font=self.F(9, True))
                bw = self.tw(c["durum"], 8, True) + 18
                k = col.get(c["durum"], MUT)
                self.rrect(data_cv, x + cw - bw - 10, 8, x + cw - 10, 28, 10, fill=CARD2,
                           outline=k)
                data_cv.create_text(x + cw - bw / 2 - 10, 18, text=c["durum"], fill=k,
                                    font=self.F(8, True))
                data_cv.create_text(x + 14, 41, text=c["deger"], anchor="w", fill=FG,
                                    font=self.F(13, True))
                data_cv.create_text(x + 14, 60, text=c["aciklama"], anchor="w", fill=MUT,
                                    font=self.F(8), width=cw - 24)

        # ---------------------------------------------------------- katman sekmeleri
        def draw_tabs():
            tabs.delete("all")
            S["tab_hits"] = []
            x = 0
            for i, (_, label) in enumerate(LAYERS):
                tw_ = self.tw(label, 9, True) + 28
                on = i == S["layer"]
                self.rrect(tabs, x + 1, 4, x + tw_, 36, 16, fill=ACC_SOFT if on else CARD2,
                           outline=ACC2 if on else LINE2)
                tabs.create_text(x + tw_ / 2, 20, text=label, fill=ACC if on else FG2,
                                 font=self.F(9, True))
                S["tab_hits"].append((x, x + tw_, i))
                x += tw_ + 8

        def tab_click(e):
            for x0, x1, i in S["tab_hits"]:
                if x0 <= e.x <= x1 and i != S["layer"]:
                    S["layer"] = i
                    draw_tabs()
                    draw_map()
                    return
        tabs.bind("<Configure>", lambda e: draw_tabs())
        tabs.bind("<Button-1>", tab_click)

        # ---------------------------------------------------------- harita
        def layer_value(pt):
            key = LAYERS[S["layer"]][0]
            if key == "azot":
                return pt["mevcut"]["azot_kaybi"] / 100, f"%{f0(pt['mevcut']['azot_kaybi'])}"
            if key == "entropi":
                return pt["mevcut"]["entropi"] / 100, f0(pt["mevcut"]["entropi"])
            if key == "ciplak":
                return pt["mevcut"]["ciplak_ay"] / 12, f"{f0(pt['mevcut']['ciplak_ay'])} ay"
            return 1 - min(1.0, pt["entropi_azalma"] / 60), f"−%{f0(pt['entropi_azalma'])}"

        def bad_color(v):
            v = max(0.0, min(1.0, v))
            return lerp(ACC2, GOLD, v / 0.5) if v < 0.5 else lerp(GOLD, BAD, (v - 0.5) / 0.5)

        def projector(w, h):
            """(enlem, boylam) -> tuval. Tarla görseli varsa görselle hizalı."""
            img = field.get("gorsel")
            pad = 18
            if img is not None:
                ratio = min((w - 2 * pad) / img.w, (h - 2 * pad) / img.h)
                iw, ih = int(img.w * ratio), int(img.h * ratio)
                ox, oy = (w - iw) / 2, (h - ih) / 2
                pts = field["noktalar"]
                n = min(len(pts), len(img.poly))
                lons = [p[1] for p in pts[:n]]
                lats = [p[0] for p in pts[:n]]
                pxs = [q[0] for q in img.poly[:n]]
                pys = [q[1] for q in img.poly[:n]]

                def fit(us, vs):
                    mu, mv = sum(us) / len(us), sum(vs) / len(vs)
                    den = sum((u - mu) ** 2 for u in us) or 1e-12
                    a = sum((u - mu) * (v - mv) for u, v in zip(us, vs)) / den
                    return a, mv - a * mu
                ax, bx = fit(lons, pxs)
                ay, by = fit(lats, pys)
                return (lambda la, lo: (ox + (ax * lo + bx) * ratio, oy + (ay * la + by) * ratio)), \
                    (ox, oy, iw, ih)
            allp = [q for pt in S["data"]["parseller"] for q in pt["poly"]]
            la0 = sum(q[0] for q in allp) / len(allp)
            k = math.cos(math.radians(la0))
            xs = [q[1] * k for q in allp]
            ys = [q[0] for q in allp]
            x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
            sc = min((w - 2 * pad - 20) / ((x1 - x0) or 1e-9), (h - 2 * pad - 20) / ((y1 - y0) or 1e-9))
            ox = (w - sc * (x1 - x0)) / 2
            oy = (h - sc * (y1 - y0)) / 2
            return (lambda la, lo: (ox + (lo * k - x0) * sc, h - (oy + (la - y0) * sc))), None

        def draw_map(pulse_only=False):
            w, h = mp.winfo_width(), mp.winfo_height()
            if w < 120 or h < 120:
                return
            d = S["data"]
            if pulse_only:
                mp.delete("pulse")
            else:
                mp.delete("all")
            if not d:
                if not pulse_only:
                    msg = ("Bir hata oldu: " + S["err"]) if S["err"] else \
                        "Parseller ayrılıyor, NASA verileri ve eğimler alınıyor…"
                    mp.create_text(w / 2, h / 2, text=msg, fill=BAD if S["err"] else MUT,
                                   font=self.F(11), width=w - 60, justify="center")
                return
            P_, box = projector(w, h)
            if not pulse_only:
                if box is not None:
                    ox, oy, iw, ih = box
                    key = (iw, ih)
                    if S["photo_key"] != key:
                        try:
                            png = field["gorsel"].resized(iw, ih).png_original()
                            S["photo"] = tk.PhotoImage(data=tarla_gorsel.b64(png))
                            S["photo_key"] = key
                        except Exception:
                            S["photo"] = None
                    if S["photo"] is not None:
                        mp.create_image(ox, oy, image=S["photo"], anchor="nw")
                else:                       # görsel yoksa habitat ızgarası
                    for gx in range(0, w, 32):
                        mp.create_line(gx, 0, gx, h, fill=LINE)
                    for gy in range(0, h, 32):
                        mp.create_line(0, gy, w, gy, fill=LINE)
                S["hits"] = []
                for i, pt in enumerate(d["parseller"]):
                    pts = [c for q in pt["poly"] for c in P_(q[0], q[1])]
                    v, label = layer_value(pt)
                    col = bad_color(v)
                    kw = dict(fill=col, outline=LINE2 if box is None else "#ffffff", width=1)
                    if box is not None:
                        kw["stipple"] = "gray50"
                    mp.create_polygon(*pts, **kw)
                    cx, cy = P_(pt["lat"], pt["lon"])
                    self.rrect(mp, cx - 34, cy - 22, cx + 34, cy + 22, 10, fill=CARD, outline=col)
                    mp.create_text(cx, cy - 8, text=f"P{i + 1}", fill=FG, font=self.F(10, True))
                    mp.create_text(cx, cy + 9, text=NoTr(label), fill=col, font=self.F(9, True))
                    S["hits"].append((pt["poly"], i))
                if d.get("en_iyi"):
                    mp.create_text(16, h - 16, anchor="sw", fill=FG2, font=self.F(9),
                                   text=tarla_dil.tr("En büyük kazanç:") + " " + tarla_dil.tr(d["en_iyi"]))
                mp.create_text(w - 16, h - 16, anchor="se", fill=MUT, font=self.F(9),
                               text="parsele tıkla")
            pt = d["parseller"][S["sel"]]
            pts = [c for q in pt["poly"] for c in P_(q[0], q[1])]
            glow = 0.5 + 0.5 * math.sin(S["phase"] * 3)
            mp.create_polygon(*pts, fill="", outline=lerp(ACC2, ACC, glow),
                              width=2 + 2 * glow, tags="pulse")

        def in_poly(la, lo, poly):
            inside = False
            j = len(poly) - 1
            for i in range(len(poly)):
                (ya, xa), (yb, xb) = poly[i], poly[j]
                if (ya > la) != (yb > la) and lo < (xb - xa) * (la - ya) / ((yb - ya) or 1e-12) + xa:
                    inside = not inside
                j = i
            return inside

        def map_click(e):
            d = S["data"]
            if not d:
                return
            w, h = mp.winfo_width(), mp.winfo_height()
            P_, _ = projector(w, h)
            for poly, i in S["hits"]:
                cpoly = [P_(q[0], q[1]) for q in poly]
                inside, j = False, len(cpoly) - 1
                for k_ in range(len(cpoly)):
                    (xa, ya), (xb, yb) = cpoly[k_], cpoly[j]
                    if (ya > e.y) != (yb > e.y) and e.x < (xb - xa) * (e.y - ya) / ((yb - ya) or 1e-12) + xa:
                        inside = not inside
                    j = k_
                if inside:
                    select(i)
                    return
        mp.bind("<Configure>", lambda e: draw_map())
        mp.bind("<Button-1>", map_click)

        def select(i):
            if S["data"] is None:
                return
            S["sel"] = i
            draw_map()
            animate_panel()

        # ---------------------------------------------------------- sağ panel
        def draw_panel():
            rp.delete("all")
            w = rp.winfo_width()
            d = S["data"]
            if w < 200 or not d:
                return
            t = S["t"]
            pt = d["parseller"][S["sel"]]
            m, o = pt["mevcut"], pt["oneri"]
            T = tarla_dil.tr
            y = 4
            # -- başlık
            title = T(pt["ad"]) + " · " + T(pt["yon"])
            rp.create_text(4, y + 14, text=NoTr(title), anchor="w", fill=FG, font=self.F(15, True))
            if pt["egim"] is not None:
                self.chip(rp, w - 110, y + 2, T("eğim") + f" %{f1(pt['egim'])}", GOLD if pt["egim"] >= 8 else MUT)
            y += 40
            # -- teşhis paragrafı
            card_top = y
            it = rp.create_text(20, y + 16, text=pt["mesaj"], anchor="nw", fill=FG2,
                                font=self.F(10), width=w - 44)
            b = rp.bbox(it)
            y = (b[3] if b else y + 80) + 16
            bg = self.rrect(rp, 2, card_top, w - 2, y, 14, fill=CARD, outline=ACC2)
            rp.tag_lower(bg)
            rp.create_rectangle(2, card_top + 14, 6, y - 14, fill=ACC, outline="")
            y += 18
            # -- önce / sonra göstergeleri
            rp.create_text(4, y, text="ÖNCE → SONRA", anchor="w", fill=MUT2, font=self.F(9, True))
            rp.create_text(w - 4, y, text="mevcut · müdahale", anchor="e", fill=MUT2, font=self.F(8))
            y += 18
            s0, s1 = m["seyir"][0], o["seyir"][-1]
            k0, k3 = pt["sizma"][0]["ksat"], pt["sizma"][-1]["ksat"]
            rows = [("Entropi göstergesi", m["entropi"], o["entropi"], 100, True, f0),
                    ("Azot kaybı", m["azot_kaybi"], o["azot_kaybi"], 100, True, lambda v: "%" + f0(v)),
                    ("Çıplak toprak (ay/yıl)", m["ciplak_ay"], o["ciplak_ay"], 12, True, f0),
                    ("Sızma kapasitesi (mm/sa)", k0, k3, max(k0, k3) * 1.25, False, f1),
                    ("Su tutma, 0-30 cm (mm)", s0["awc_mm"], s1["awc_mm"],
                     max(s0["awc_mm"], s1["awc_mm"]) * 1.25, False, f1)]
            bx0, bx1 = 200, w - 120
            for label, a, b_, top, low_good, fmt in rows:
                rp.create_text(4, y + 10, text=label, anchor="w", fill=FG2, font=self.F(9))
                for k_, (val, col) in enumerate(((a, MUT2), (b_, None))):
                    yy = y + 4 + k_ * 10
                    self.rrect(rp, bx0, yy, bx1, yy + 6, 3, fill=LINE, outline="")
                    frac = max(0.0, min(1.0, val / (top or 1)))
                    if k_ == 1:
                        better = (b_ < a) if low_good else (b_ > a)
                        col = ACC if better else (MUT if abs(b_ - a) < 1e-9 else GOLD)
                        frac *= t
                    fw = (bx1 - bx0) * frac
                    if fw >= 6:
                        self.rrect(rp, bx0, yy, bx0 + fw, yy + 6, 3, fill=col, outline="")
                rp.create_text(w - 4, y + 10, anchor="e", fill=FG, font=self.F(10, True),
                               text=NoTr(fmt(a) + " → " + fmt(a + (b_ - a) * t)))
                y += 30
            y += 12
            # -- 3 yıllık seyir
            rp.create_text(4, y, text="3 YILLIK SEYİR", anchor="w", fill=MUT2, font=self.F(9, True))
            y += 14
            ch_top, ch_h = y, 130
            self.rrect(rp, 2, ch_top, w - 2, ch_top + ch_h, 12, fill=CARD, outline=LINE)
            L0, R0, T0, B0 = 46, w - 46, ch_top + 22, ch_top + ch_h - 26
            X = lambda yr: L0 + (R0 - L0) * yr / 3
            ent = pt["entropi_seyir"]
            inf = [r["artis"] for r in pt["sizma"]]
            e_max = max(ent) or 1
            i_max = max(1.0, max(inf))
            Ye = lambda v: B0 - (B0 - T0) * v / e_max
            Yi = lambda v: B0 - (B0 - T0) * v / i_max
            for yr in range(4):
                rp.create_line(X(yr), T0, X(yr), B0, fill=LINE)
                rp.create_text(X(yr), B0 + 12, text=f"{YEAR0 + yr}", fill=MUT, font=self.F(8))

            def line(vals, Yf, col):
                pts_ = []
                n = len(vals) - 1
                pos = t * n
                for yr in range(n + 1):
                    if yr <= pos:
                        pts_.append((X(yr), Yf(vals[yr])))
                k_ = int(pos)
                if k_ < n:
                    f_ = pos - k_
                    pts_.append((X(k_ + (f_)), Yf(vals[k_] + (vals[k_ + 1] - vals[k_]) * f_)))
                if len(pts_) >= 2:
                    rp.create_line(*[c for p_ in pts_ for c in p_], fill=col, width=3,
                                   capstyle="round", joinstyle="round")
                for x_, y_ in pts_[:4]:
                    rp.create_oval(x_ - 3, y_ - 3, x_ + 3, y_ + 3, fill=col, outline="")
            line(ent, Ye, GOLD)
            line(inf, Yi, WATER)
            rp.create_text(L0, ch_top + 11, anchor="w", fill=GOLD, font=self.F(8, True),
                           text=T("entropi") + f" {f0(ent[0])} → {f0(ent[-1])}")
            rp.create_text(R0, ch_top + 11, anchor="e", fill=WATER, font=self.F(8, True),
                           text=T("sızma artışı") + f" +%{f0(inf[-1])}")
            y = ch_top + ch_h + 22
            # -- takvim şeridi: hangi ay ne var
            rp.create_text(4, y, text="TOPRAK ÖRTÜSÜ TAKVİMİ", anchor="w", fill=MUT2,
                           font=self.F(9, True))
            y += 16
            for label, rep_ in (("mevcut", m), ("müdahale", o)):
                cal = rep_["takvim"]
                n = len(cal)
                x0_, x1_ = 90, w - 6
                cw_ = (x1_ - x0_) / n
                rp.create_text(4, y + 9, text=label, anchor="w", fill=FG2, font=self.F(9))
                for k_, v in enumerate(cal):
                    if v is None:
                        col = lerp(CARD, BAD, .55)
                    elif v == "C":
                        col = lerp(CARD, ACC, .45)
                    else:
                        col = WATER if tarla_optimizer.TRAITS.get(v, {}).get("n", 0) > 0 else ACC2
                    if k_ / n <= t or label == "mevcut":
                        rp.create_rectangle(x0_ + k_ * cw_ + 1, y, x0_ + (k_ + 1) * cw_ - 1, y + 18,
                                            fill=col, outline="")
                y += 24
            x_ = 90
            for txt, col in (("ekin", ACC2), ("baklagil", WATER), ("kışlık örtü", lerp(CARD, ACC, .45)),
                             ("çıplak", lerp(CARD, BAD, .55))):
                rp.create_rectangle(x_, y + 2, x_ + 12, y + 12, fill=col, outline="")
                rp.create_text(x_ + 16, y + 7, text=txt, anchor="w", fill=MUT, font=self.F(8))
                x_ += 16 + self.tw(txt, 8) + 14
            y += 30
            # -- kök yapısı
            rp.create_text(4, y, text="KÖK YAPISI (FAO-56)", anchor="w", fill=MUT2,
                           font=self.F(9, True))
            y += 14
            col_top, col_h = y, 170
            self.rrect(rp, 2, col_top, w - 2, col_top + col_h, 12, fill=CARD, outline=LINE)
            g0, g1 = col_top + 24, col_top + col_h - 30
            D = 1.8
            Yd = lambda dm: g0 + (g1 - g0) * dm / D
            rp.create_rectangle(10, g0 - 4, w - 10, g0, fill=lerp(CARD, ACC2, .6), outline="")
            for dm in (0.5, 1.0, 1.5):
                rp.create_line(40, Yd(dm), w - 10, Yd(dm), fill=LINE, dash=(2, 4))
                rp.create_text(34, Yd(dm), text=f"{f1(dm)} m", anchor="e", fill=MUT2, font=self.F(8))
            groups = (("mevcut", m["kok"]), ("müdahale", o["kok"]))
            gw = (w - 60) / 2
            for gi, (label, roots) in enumerate(groups):
                gx0 = 50 + gi * gw
                rp.create_text(gx0 + gw / 2 - 10, col_top + 12, text=label, fill=FG2,
                               font=self.F(9, True))
                bw_ = (gw - 30) / max(1, len(roots))
                for k_, r_ in enumerate(roots):
                    cx = gx0 + k_ * bw_ + bw_ / 2
                    deep = r_["ust"] * t
                    col = WATER if tarla_optimizer.TRAITS.get(r_["ekin"], {}).get("n", 0) > 0 else ACC2
                    rp.create_rectangle(cx - 9, g0, cx + 9, Yd(r_["alt"] * t), fill=col, outline="")
                    rp.create_rectangle(cx - 4, Yd(r_["alt"] * t), cx + 4, Yd(deep), fill=lerp(CARD, col, .55),
                                        outline="")
                    for j_ in (-1, 1):          # yan kökler
                        rp.create_line(cx, g0 + (Yd(deep) - g0) * .35, cx + j_ * 12,
                                       g0 + (Yd(deep) - g0) * .55, fill=col, width=2)
                    if r_["ortu"]:
                        rp.create_line(cx + 13, g0, cx + 13, Yd(tarla_ikiz.COVER_ROOT[1] * t),
                                       fill=lerp(CARD, ACC, .6), width=2, dash=(3, 2))
                    short = T(r_["ekin"])
                    if self.tw(short, 8) > bw_ - 4:
                        short = short[:max(3, int(len(short) * (bw_ - 4) / max(1, self.tw(short, 8))))] + "…"
                    rp.create_text(cx, g1 + 14, text=NoTr(short), fill=MUT, font=self.F(8))
            y = col_top + col_h + 16
            rp.create_text(4, y, anchor="nw", fill=MUT2, font=self.F(8), width=w - 8,
                           text="Koyu çubuk: en az etkili kök derinliği · açık: en çok. Kesikli çizgi: "
                                "kışlık örtü bitkisi kökleri. Farklı derinlikteki kökler toprağın "
                                "farklı katmanlarından su ve besin alır, kanal açar.")
            y += 40
            # -- besin döngüsü
            rp.create_text(4, y, text="AZOT DÖNGÜSÜ (göreli)", anchor="w", fill=MUT2,
                           font=self.F(9, True))
            y += 16
            top_n = max(m["n_giris"], m["n_cikis"], o["n_giris"], o["n_cikis"], 0.1)
            for label, rep_ in (("mevcut", m), ("müdahale", o)):
                rp.create_text(4, y + 12, text=label, anchor="w", fill=FG2, font=self.F(9))
                for k_, (val, col, nm) in enumerate(((rep_["n_giris"], WATER, "bağlanan"),
                                                     (rep_["n_cikis"], GOLD, "tüketilen"))):
                    yy = y + 2 + k_ * 12
                    fw = (w - 220) * val / top_n * (t if label == "müdahale" else 1)
                    self.rrect(rp, 90, yy, 90 + max(6, fw), yy + 8, 4, fill=col, outline="")
                    rp.create_text(96 + max(6, fw), yy + 4, anchor="w", fill=MUT, font=self.F(8),
                                   text=nm + " " + f1(val))
                y += 34
            rp.configure(scrollregion=(0, 0, w, y + 10))

        def animate_panel():
            S["aid"] = my = S.get("aid", 0) + 1

            def frame(e):
                if my == S["aid"]:
                    S["t"] = e
                    draw_panel()
            if ANIM:
                self._tween(700, frame, win)
            else:
                frame(1.0)
        rp.bind("<Configure>", lambda e: draw_panel())
        data_cv.bind("<Configure>", lambda e: draw_data())

        # ---------------------------------------------------------- hesap (arka planda)
        box = {}

        def work():
            try:
                hist, _ = self._context_extras(live, lat, lon, need_slope=False)
                sat, ndvi = tarla_ikiz.satellite_inputs(self._prefs_sat(), field, lat, lon, live)
                res = tarla_optimizer.optimize(clim, irr, soil, hist, lat, live=live, L=L,
                                               prio=prio, sat=sat, current=cur, area_ha=area)
                parcels, _ = tarla_optimizer.make_parcels(field, lat, lon)
                slopes, per = {}, {}
                for p in parcels:
                    sl = None
                    if live:
                        k_ = (round(p["lat"], 5), round(p["lon"], 5))
                        if k_ not in PARCEL_SLOPE_CACHE:
                            try:
                                PARCEL_SLOPE_CACHE[k_] = tarla_risk.fetch_slope(p["lat"], p["lon"])["egim_yuzde"]
                            except Exception:
                                PARCEL_SLOPE_CACHE[k_] = None
                        sl = PARCEL_SLOPE_CACHE[k_]
                    slopes[p["ad"]] = sl
                    if sl is not None:
                        per[p["ad"]] = tarla_optimizer.optimize(
                            clim, irr, soil, hist, lat, live=live, L=L, prio=prio, sat=sat,
                            current=cur, slope_pct=sl, table=res["tablo"],
                            particles=16, iters=30, sa_steps=300)
                box["d"] = tarla_ikiz.build(res, per, parcels, slopes, soil, sat, ndvi, hist)
            except Exception as exc:
                log_error("Derin Uzay ikizi")
                box["err"] = str(exc) or exc.__class__.__name__

        def wait():
            if not alive():
                return
            if not box:
                if not ANIM:
                    draw_data()
                self.root.after(150, wait)
                return
            if "err" in box:
                S["err"] = box["err"]
                draw_map()
                return
            d = S["data"] = box["d"]
            self.last_twin = (name, d)
            best = next((i for i, pt in enumerate(d["parseller"]) if pt["ad"] == d["en_iyi"]), 0)
            S["sel"] = best
            sub.configure(text=name + " · " + f"{len(d['parseller'])} " + tarla_dil.tr("parsel")
                          + " · " + tarla_dil.tr("kapalı döngü yaşam destek mantığı"))
            draw_data()
            draw_tabs()
            draw_map()
            animate_panel()

        threading.Thread(target=work, daemon=True).start()
        self.root.after(150, wait)
        draw_orbit()
        if ANIM:
            win.after(50, tick)

    # ------------------------------------------------------------ Mission Control
    def _prefs_sat(self):
        """Optimizasyon penceresinde girilen uydu değerleri (metin) -> sayı sözlüğü."""
        P = self._opt_defaults()
        out = {}
        for k in ("smap", "eco", "gpm", "gedi", "grace", "ndvi"):
            txt = str(P.get(k) or "").strip().replace(",", ".")
            try:
                v = float(txt)
            except ValueError:
                continue
            if not math.isfinite(v):
                continue
            valid = -0.2 <= v <= 1 if k == "ndvi" else v > 0 or k == "grace"
            if valid:
                out[k] = v
        return out

    def open_mission_control(self):
        """Tarayıcıda Mission Control panelini aç (canlı yeniden optimizasyon, harita katmanları)."""
        if not self.current() or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        if not self._require_field(self.open_mission_control, "Tarla Takip Paneli"):
            return
        try:
            if self.map_server is None:
                self.map_server = tarla_harita.MapServer(
                    lambda f: self.q.put(("field", f, False)))
            if getattr(self, "mc", None) is None:
                self.mc = tarla_mc.MissionControl(self.map_server)
            P = self._opt_defaults()
            L = int(P["L"])
            cur = P["mevcut"] if P["mevcut"] and len(P["mevcut"]) == L else self._default_current(L)
            key = (round(self.lat, 3), round(self.lon, 3)) if self.lat is not None else None
            area = ((self.field or {}).get("alan_dekar") or 0) / 10.0 or None
            self.mc.set_state(
                clim=self.clim, irr=self.irr, soil=self.soil, hist=HIST_CACHE.get(key),
                lat=self.lat if self.lat is not None else 37.87,
                lon=self.lon if self.lon is not None else 32.48,
                live=self.kaynak == "nasa", field=self.field, name=self.name,
                sat=self._prefs_sat(), current=cur, area_ha=area,
                prio={k: P[k] / 100.0 for k in ("su", "toprak", "pazar", "risk")})
            opened = self.open_web_window("Tarla Takip Paneli", self.mc.url())
        except Exception as exc:
            self.set_status(f"Tarla Takip Paneli açılamadı: {exc}", True)
            return
        self.set_status("Tarla Takip Paneli sekmesi açıldı." if opened else
                        "Tarla Takip Paneli için build_exe.bat ile uygulamayı yeniden derleyin.", not opened)

    # ------------------------------------------------------------ saha modu
    def open_field_mode(self, res=None):
        """Parsel bazlı sesli öneri sayfası (GPS coğrafi çit + traktör simülasyonu)."""
        if not self.current() or not self.clim:
            self.set_status("Önce konum analizi yapın.", True)
            return
        if not self._require_field(lambda: self.open_field_mode(res), "Saha modu"):
            return
        if getattr(self, "_field_busy", False):
            return
        lo = getattr(self, "last_opt", None)
        if res is None and lo and lo[0] == self.name and lo[1] == self.irr:
            res = lo[2]
        clim, irr, soil, name = self.clim, self.irr, self.soil, self.name
        lat, lon, live, field = self.lat, self.lon, self.kaynak == "nasa", self.field
        P = self._opt_defaults()
        prio = {k: P[k] / 100.0 for k in ("su", "toprak", "pazar", "risk")}
        self._field_busy = True
        manual_sat = self._prefs_sat()
        self.set_status("Saha modu hazırlanıyor: parseller ayrılıyor, eğimler alınıyor…")
        box = {}

        def work():
            try:
                hist, _ = self._context_extras(live, lat, lon, need_slope=False)
                base = res
                if base is None:
                    sat, _ = tarla_ikiz.satellite_inputs(manual_sat, field, lat, lon, live)
                    base = tarla_optimizer.optimize(
                        clim, irr, soil, hist, lat, live=live, L=int(P["L"]),
                        sat=sat,
                        prio=prio, dT=P["dT"], dP=P["dP"] / 100.0,
                        current=P["mevcut"] or self._default_current(int(P["L"])))
                parcels, schematic = tarla_optimizer.make_parcels(field, lat, lon)
                slopes, per = {}, {}
                for p in parcels:
                    sl = None
                    if live:
                        try:
                            sl = tarla_risk.fetch_slope(p["lat"], p["lon"])["egim_yuzde"]
                        except Exception:
                            sl = None
                    slopes[p["ad"]] = sl
                    if sl is not None:      # parsel eğimiyle yeniden (aynı Monte Carlo tablosu)
                        per[p["ad"]] = tarla_optimizer.optimize(
                            clim, irr, soil, hist, lat, live=live, L=base["L"],
                            prio=prio, dT=base["senaryo"]["dT"], dP=base["senaryo"]["dP"],
                            current=base["mevcut"]["ekinler"], slope_pct=sl,
                            table=base["tablo"], particles=20, iters=40, sa_steps=500)
                items = tarla_saha.parcels_from(base, base["harmonizasyon"], parcels, slopes, per)
                try:                        # parsel bazlı ikiz cümlesi de okunsun
                    twin = tarla_ikiz.build(base, per, parcels, slopes, soil)
                    by = {pt["ad"]: pt for pt in twin["parseller"]}
                    for it in items:
                        if it["ad"] in by:
                            it["metin"] = it["metin"].replace(
                                " Son karar sizin;", " " + tarla_saha.twin_sentence(by[it["ad"]])
                                + " Son karar sizin;")
                except Exception:
                    log_error("saha modu ikiz cümlesi")
                html = tarla_saha.build_page(name, items, field["noktalar"])
                if self.map_server is None:
                    self.map_server = tarla_harita.MapServer(
                        lambda f: self.q.put(("field", f, False)))
                data = html.encode("utf-8")
                self.map_server.get_routes["/saha"] = lambda: ("text/html; charset=utf-8", data)
                url = self.map_server.page_url("/saha")
                # sayfadaki "Daha fazla ses: Edge'de aç" düğmesi bu yolu çağırır
                self.map_server.get_routes["/saha-tarayici"] = lambda: (
                    "application/json; charset=utf-8",
                    b'{"ok": true}' if tarla_saha.open_in_browser(url) else b'{"ok": false}')
                try:                        # telefona aktarmak için çevrimdışı kopya
                    path = tarla_saha.write_and_open(html, tarla_ayarlar.app_dir(), open_page=False)
                except OSError:
                    path = None
                box["ok"] = (url, path, sum(1 for v in slopes.values() if v is not None),
                             len(parcels))
            except Exception as exc:
                log_error("saha modu")
                box["err"] = str(exc) or exc.__class__.__name__

        def wait():
            if not box:
                self.root.after(200, wait)
                return
            self._field_busy = False
            if "err" in box:
                self.set_status("Saha modu açılamadı: " + box["err"], True)
                return
            url, path, n_sl, n = box["ok"]
            opened = self.open_web_window("Saha modu · sesli asistan", url)
            self.set_status(
                ("Saha modu sekmesi açıldı." if opened else "Saha modu açılamadı.")
                + f" {n} " + tarla_dil.tr("parsel")
                + (f", {n_sl} " + tarla_dil.tr("parselde gerçek eğim") if n_sl else "")
                + (" " + tarla_dil.tr("Canlı GPS için konum izni verin.") if opened else ""), not opened)
        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, wait)

    # ------------------------------------------------------------ AI asistan
    def ai_context(self):
        """Asistana verilen bağlam: ekrandaki tüm hesap sonuçlarının metin özeti."""
        r = self.current()
        ex = tp.explain(r, self.clim, self.soil, self.irr)
        L = [f"Konum: {self.name}", tarla_kaynak.MODEL_NOTE,
             'Kaynak: iklim = ' + ('NASA POWER aylık ortalamaları' if self.kaynak == 'nasa' else 'proje örnek verisi'),
             'Kaynak: toprak = ' + self.soil.get('source','proje bölgesel varsayımı'),
             'Kaynak: eşikler, su ihtiyaçları, puanlar, senaryolar = proje parametreleri ve model hesabı.',
             'Yöntem bağlantısı: https://www.fao.org/4/X0490E/x0490e0a.htm',
             'Veri bağlantısı: https://power.larc.nasa.gov/docs/services/api/temporal/climatology/']
        if self.field:
            L.append("Tarla: " + self.field_note())
        L += [f"Toprak: {self.soil['label']} (kil %{self.soil['clay']}, kum %{self.soil['sand']}, "
              f"pH {self.soil['ph']})",
              f"Sulama imkânı: {'var' if self.irr else 'yok'}",
              "Veri: " + ("NASA POWER canlı klimatoloji" if self.kaynak == "nasa"
                          else "örnek veri (NASA verisi değil)"),
              f"Yıllık: ortalama {f1(sum(self.clim['T']) / 12)} °C, yağış "
              f"{f0(sum(self.clim['Pm']))} mm",
              "",
              f"SEÇİLİ EKİN: {r['ekin']} — {r['puan']}/100 ({tier_of(r['puan'])}), "
              f"sıralamada {self.results.index(r) + 1}/{len(self.results)}",
              f"  ekim: {r['ekim_ayi'] or 'çok yıllık'}, dönem: {window_label(r)}, "
              f"su ihtiyacı {r['sulama_ihtiyaci_mm']} mm, su açığı {r['sulama_acigi_mm']} mm"]
        for label, sc, val, ideal in factor_rows(r):
            L.append(f"  {label}: {val} ({ideal}) → {f0(min(100, sc * 100))}/100")
        if ex["riskler"]:
            L.append("  riskler: " + "; ".join(ex["riskler"]))
        L += ["", "SIRALAMA (ilk 8):"]
        for i, x in enumerate(self.results[:8], 1):
            f = x["faktorler"]
            low = min(f, key=f.get)
            L.append(f"  {i}. {x['ekin']} {x['puan']} ({x['grup']}, ekim {x['ekim_ayi'] or 'çok yıllık'}"
                     f", su açığı {x['sulama_acigi_mm']} mm, en zayıf: {tp.FACTOR_NAMES[low]} "
                     f"{f0(f[low] * 100)})")
        rots = tp.build_rotations(self.results, self.irr)
        if rots:
            L += ["", "ROTASYON STRATEJİLERİ:"]
            for rot in rots:
                L.append(f"  {rot['name']} ({rot['puan']}/100): {' → '.join(rot['seq'])}"
                         + (f" | risk: {rot['riskler'][0]}" if rot["riskler"] else ""))
        lo = getattr(self, "last_outlook", None)
        if lo and lo[0] == (r["ekin"], self.name, self.irr):
            L += ["", f"10 YILLIK SENARYO ({r['ekin']}, {YEAR0}→{YEAR0 + 10}, olasılık bandı; "
                      "kesin tahmin değil):"]
            for sc in lo[1]["senaryolar"]:
                y0, yn = sc["yillar"][0], sc["yillar"][-1]
                L.append(f"  {sc['ad']}: medyan {y0['p50']}→{yn['p50']} (p10–p90 {yn['p10']}–"
                         f"{yn['p90']}), zayıf yıl olasılığı %{f0(y0['zayif'] * 100)}→"
                         f"%{f0(yn['zayif'] * 100)}, medyan su açığı {y0['su_p50']}→"
                         f"{yn['su_p50']} mm")
        else:
            L += ["", "10 yıllık senaryo: bu ekin için henüz açılmadı (kullanıcı sol panelden "
                      "açabilir)."]
        lo_ = getattr(self, "last_opt", None)
        if lo_ and lo_[0] == self.name and lo_[1] == self.irr:
            L += ["", "KUANTUM-ESİNLİ ROTASYON OPTİMİZASYONU (QPSO + tavlama; puan 0-100, ± "
                      "iklim belirsizliği; karar verici değil):"]
            L += tarla_optimizer.summary_lines(lo_[2])
        else:
            L += ["", "Rotasyon optimizasyonu: henüz çalıştırılmadı (sol panel > Ekim nöbeti önerileri)."]
        lt = getattr(self, "last_twin", None)
        if lt and lt[0] == self.name:
            L += ["", "DERİN UZAY İKİZİ (parsel bazlı model göstergeleri; ölçüm değil):"]
            for pt in lt[1]["parseller"]:
                L.append("  " + pt["mesaj"])
        if self.last_risk and self.last_risk[0] == self.name:
            L += ["", "AFET VE EROZYON RİSKİ (gösterge ve geçmiş sıklık; resmi afet haritası değil):"]
            L += tarla_risk.summary_lines(self.last_risk[1])
        return "\n".join(L)

    def ai_local_answer(self):
        """API anahtarı yokken gösterilen, tamamen hesaptan üretilen özet."""
        r = self.current()
        ex = tp.explain(r, self.clim, self.soil, self.irr)
        low = min(factor_rows(r), key=lambda x: x[1])
        lines = ["**Çevrimdışı özet**", ex["gerekce"],
                 f"- En zayıf faktör: {low[0]} ({low[2]}; {low[3]})"]
        lines.append('Dayanak: ' + ('NASA POWER aylık iklim verisi' if self.kaynak == 'nasa' else 'örnek iklim verisi')
                     + ' + proje ekin eşikleri ve bölgesel toprak varsayımı. Ayrıntı: Kaynaklar ve hesap.')
        lines += ["- Risk: " + k for k in ex["riskler"]]
        lines += [ex["bilgi_boslugu"],
                  "Serbest soru sorabilmek için Araçlar > Özelleştirme bölümünden OpenRouter API anahtarınızı "
                  "ekleyin; o zamana kadar bu özet gösterilir."]
        return "\n".join(lines)

    def _build_chat(self, win):
        """Ana ekrandaki asistanın sohbeti ve giriş alanı."""
        msgs = self.ai_msgs      # {"role": sen|asistan|yerel|hata|ctx, "text": .., ["n": gösterilen]}
        state = {"busy": False, "phase": 0, "copied": None, "placeholder": True}
        hits = []
        PLACEHOLDER = "Bir soru yazın…"

        def alive():
            try:
                return bool(win.winfo_exists())
            except Exception:
                return False

        # ---------------------------------------------------------- üst bölüm
        head = tk.Frame(win, bg=CARD)
        head.pack(fill="x")
        actions = tk.Frame(head, bg=CARD)
        actions.pack(side="right", padx=(2, 4), pady=6)
        title = tk.Label(head, text="Tarla asistanı", bg=CARD, fg=FG,
                         font=self.F(14, True), anchor="w", justify="left")
        title.pack(side="left", fill="x", expand=True, padx=(12, 0), pady=8)
        title.bind("<Configure>", lambda e: title.configure(wraplength=max(40, e.width - 4)))
        self._help_button(actions, "Tarla asistanı").pack(side="right")

        def new_chat():
            if state["busy"]:
                return
            msgs.clear()
            self.ai_ctx_key = None
            render()

        nb = tk.Button(actions, text="Yeni", command=new_chat, relief="flat", bd=0,
                       bg=CARD, fg=ACC, activebackground=ACC_SOFT, activeforeground=FG,
                       font=self.F(9, True), cursor="hand2", padx=6)
        nb.pack(side="left")
        ic = tk.Canvas(win, bg=BG, highlightthickness=0, bd=0, height=62)
        ic.pack(side="bottom", fill="x", padx=8, pady=(3, 9))
        history_panel = tk.Frame(win, bg=BG)
        history_panel.pack(fill="both", expand=True, padx=(6, 4), pady=(4, 4))
        mc = tk.Canvas(history_panel, bg=BG, highlightthickness=0, bd=0, yscrollincrement=24)
        scroll = tk.Scrollbar(history_panel, command=mc.yview, width=10)
        scroll.pack(side="right", fill="y")
        mc.configure(yscrollcommand=scroll.set)
        mc.pack(side="left", fill="both", expand=True)

        inp = tk.Text(ic, bg=CARD2, fg=MUT2, insertbackground=ACC, relief="flat", bd=0,
                      highlightthickness=0, wrap="word", font=self.F(10), height=2,
                      padx=0, pady=0, undo=True)
        inp.insert("1.0", PLACEHOLDER)
        self.chat_input = inp

        # ---------------------------------------------------------- giriş kutusu
        def draw_input(event=None):
            if not alive():
                return
            ic.delete("all")
            w = ic.winfo_width()
            if w < 120:
                return
            self.rrect(ic, 1, 1, w - 1, 61, 13, fill=CARD2,
                       outline=ACC2 if state.get("focus") else LINE2)
            ic.create_window(12, 31, window=inp, anchor="w", width=w - 66, height=44)
            on = not state["busy"]
            self.rrect(ic, w - 46, 12, w - 8, 50, 11, fill=ACC if on else LINE2,
                       outline="", tags="send")
            if on:
                ic.create_line(w - 27, 40, w - 27, 22, fill=ON_ACC, width=2, tags="send")
                ic.create_line(w - 34, 29, w - 27, 22, w - 20, 29, fill=ON_ACC, width=2, tags="send")
            else:
                ic.create_text(w - 27, 31, text="…", fill=MUT, font=self.F(15, True), tags="send")

        def read_input():
            return "" if state["placeholder"] else inp.get("1.0", "end-1c")

        def focus_in(e=None):
            state["focus"] = True
            if state["placeholder"]:
                inp.delete("1.0", "end")
                inp.configure(fg=FG)
                state["placeholder"] = False
            draw_input()

        def focus_out(e=None):
            state["focus"] = False
            if not inp.get("1.0", "end-1c").strip():
                inp.delete("1.0", "end")
                inp.insert("1.0", PLACEHOLDER)
                inp.configure(fg=MUT2)
                state["placeholder"] = True
            draw_input()

        def on_return(e):
            if e is not None and getattr(e, "state", 0) & 0x1:     # Shift+Enter: yeni satır
                return None
            send()
            return "break"

        inp.bind("<FocusIn>", focus_in)
        inp.bind("<FocusOut>", focus_out)
        inp.bind("<Return>", on_return)
        inp.bind("<KP_Enter>", on_return)
        ic.bind("<Configure>", draw_input)
        ic.tag_bind("send", "<Button-1>", lambda e: send())
        ic.bind("<Button-1>", lambda e: inp.focus_set(), add="+")

        # ---------------------------------------------------------- mesaj alanı
        def bubble(blocks, y, w, maxw, left, fill, outline, fg):
            """Metin bloklarını çiz, arkasına balonu yerleştir; (x0, x1, alt) döndür."""
            ix, iy, pad = 12, 10, 7
            x0 = pad + 32
            wrap = maxw - 2 * ix
            items, cy = [], y + iy
            for kind, txt in blocks:
                font = self.F(10, kind == "h")
                if left:
                    ind = 16 if kind == "li" else 0
                    if ind:
                        items.append(mc.create_text(x0 + ix + 2, cy, text="•", anchor="nw",
                                                    fill=ACC, font=self.F(10, True)))
                    it = mc.create_text(x0 + ix + ind, cy, text=txt, anchor="nw",
                                        width=wrap - ind, fill=fg, font=font)
                else:
                    it = mc.create_text(w - pad - ix, cy, text=txt, anchor="ne", width=wrap,
                                        fill=fg, font=font, justify="left")
                items.append(it)
                cy = mc.bbox(it)[3] + (4 if kind == "li" else 8)
            boxes = [mc.bbox(i) for i in items]
            bottom = max(b[3] for b in boxes) + iy
            if left:
                rx0, rx1 = x0, max(max(b[2] for b in boxes) + ix, x0 + 56)
            else:
                rx0, rx1 = min(b[0] for b in boxes) - ix, w - pad
            rect = self.rrect(mc, rx0, y, rx1, bottom, 14, fill=fill, outline=outline)
            mc.tag_lower(rect)
            return rx0, rx1, bottom

        def avatar(y):
            self.rrect(mc, 7, y + 2, 32, y + 27, 8, fill=ACC_SOFT, outline=LINE2)
            mc.create_polygon(19, y + 6, 22, y + 12, 28, y + 15, 22, y + 18,
                              19, y + 24, 16, y + 18, 10, y + 15, 16, y + 12, fill=ACC)

        def action(x, y, label, kind, payload, color=MUT2):
            it = mc.create_text(x, y, text=label, anchor="nw", fill=color, font=self.F(8, True))
            hits.append((mc.bbox(it), kind, payload))
            return mc.bbox(it)[2] + 14

        def render(stick=True):
            if not alive():
                return
            mc.delete("all")
            hits.clear()
            w, h = mc.winfo_width(), mc.winfo_height()
            if w < 160:
                return
            maxw = min(600, w - 48)
            y = 12
            if not msgs and not state["busy"]:
                r = self.current()
                avatar(y)
                empty = "Seçili ürünün su ihtiyacı, riskleri veya ekim zamanı hakkında sorabilirsiniz."
                bot = bubble([("h", r["ekin"]), ("p", empty)] if r else
                             [("p", "Önce konum analizi yapın.")],
                             y, w, maxw, True, CARD, LINE2, FG2)[2]
                mc.configure(scrollregion=(0, 0, w, max(h, bot + 8)))
                return
            last_q = None
            for m in msgs:
                role = m["role"]
                if role == "ctx":
                    item = mc.create_text(w / 2, y, text=m["text"], fill=MUT, font=self.F(8),
                                          width=w - 24, anchor="n", justify="center")
                    y = mc.bbox(item)[3] + 9
                    mc.create_line(12, y, w - 12, y, fill=LINE)
                    y += 9
                elif role == "sen":
                    last_q = m["text"]
                    _, _, bot = bubble([("p", NoTr(m["text"]))], y, w, maxw, False, ACC_SOFT,
                                       ACC2, FG)
                    y = bot + 14
                else:
                    text = m["text"][:m["n"]] if "n" in m else m["text"]
                    avatar(y)
                    err = role == "hata"
                    blocks = md_blocks(text) or [("p", "…")]
                    if role == "asistan":       # model yanıtı zaten seçili dilde: çevirme
                        blocks = [(k_, NoTr(t_)) for k_, t_ in blocks]
                    x0, _, bot = bubble(blocks, y, w, maxw, True,
                                        ERR_BG if err else CARD,
                                        BAD if err else GOLD if role == "yerel" else LINE2,
                                        FG2 if err else FG)
                    y = bot + 6
                    if "n" not in m:
                        x, before = x0 + 4, len(hits)
                        if err and last_q and m is msgs[-1]:
                            x = action(x, y, "↻ Tekrar dene", "retry", last_q, GOLD)
                        if not err:
                            done = state["copied"] is m
                            action(x, y, "✓ Kopyalandı" if done else "Kopyala", "copy", m,
                                   ACC if done else MUT2)
                        if len(hits) > before:      # eylem satırının gerçek yüksekliği kadar in
                            y = hits[-1][0][3]
                    y += 12
            if state["busy"] and not (msgs and "n" in msgs[-1]):
                avatar(y)
                self.rrect(mc, 50, y, 50 + 66, y + 34, 14, fill=CARD, outline=LINE2)
                for i in range(3):
                    on = state["phase"] % 3 == i
                    cx = 50 + 20 + i * 13
                    mc.create_oval(cx - 3.5, y + 13.5, cx + 3.5, y + 20.5,
                                   fill=ACC if on else MUT2, outline="")
                y += 46
            mc.configure(scrollregion=(0, 0, w, max(y + 6, h)))
            if stick:
                mc.yview_moveto(1.0)

        def mc_click(e):
            cx, cy = mc.canvasx(e.x), mc.canvasy(e.y)
            for (x0, y0, x1, y1), kind, payload in hits:
                if x0 - 4 <= cx <= x1 + 4 and y0 - 4 <= cy <= y1 + 4:
                    if kind == "copy":
                        self.root.clipboard_clear()
                        self.root.clipboard_append(payload["text"])
                        state["copied"] = payload
                        render(False)
                        self.root.after(1600, lambda: (state.update(copied=None), render(False)))
                    elif kind == "retry" and not state["busy"]:
                        while msgs and msgs[-1]["role"] in ("hata", "sen"):
                            msgs.pop()
                        send(payload)
                    return

        def mc_move(e):
            cx, cy = mc.canvasx(e.x), mc.canvasy(e.y)
            mc.configure(cursor="hand2" if any(
                b[0] - 4 <= cx <= b[2] + 4 and b[1] - 4 <= cy <= b[3] + 4 for b, _, _ in hits)
                else "")

        mc.bind("<Configure>", lambda e: render())
        mc.bind("<Button-1>", mc_click)
        mc.bind("<Motion>", mc_move)

        # ---------------------------------------------------------- gönder
        def set_busy(on):
            state["busy"] = on
            draw_input()

        def send(text=None):
            q = (text if text is not None else read_input()).strip()
            if not q or state["busy"] or not self.current():
                return
            if text is None:
                inp.delete("1.0", "end")
            r = self.current()
            key = f"{r['ekin']} · {self.name}"
            if self.ai_ctx_key != key:      # ekin/konum değiştiyse sohbette belirt
                msgs.append({"role": "ctx", "text": "bağlam: " + key})
                self.ai_ctx_key = key
            history = [(m["role"], m["text"]) for m in msgs
                       if m["role"] in ("sen", "asistan")][-8:]
            msgs.append({"role": "sen", "text": q})
            context = self.ai_context()
            local = self.ai_local_answer()
            set_busy(True)
            render()
            box = {}

            def work():     # ağ isteği arka planda; sonuç ana iş parçacığında işlenir
                try:
                    box["m"] = {"role": "asistan", "text": ai_asistan.ask(q, context, history)}
                except ai_asistan.NotConfigured:
                    box["m"] = {"role": "yerel", "text": local}
                except Exception as exc:
                    box["m"] = {"role": "hata", "text": str(exc) or exc.__class__.__name__}

            def wait():
                if "m" not in box:
                    state["phase"] += 1
                    render()
                    self.root.after(260, wait)
                    return
                m = box["m"]
                msgs.append(m)
                if m["role"] == "hata" or not alive():
                    set_busy(False)
                    render()
                    return
                set_busy(False)
                render()

            threading.Thread(target=work, daemon=True).start()
            self.root.after(200, wait)

        def refresh_chat():
            if state["placeholder"]:
                inp.delete("1.0", "end")
                inp.insert("1.0", PLACEHOLDER)
            draw_input()
            render(stick=False)

        win._appearance_refresh = refresh_chat
        self._chat_redraw = lambda: render(stick=False)
        render()

    # ------------------------------------------------------------ çizim: karar
    def _tag_after(self, c, mark, tag):
        for i in c.find_all():
            if i > mark:
                c.addtag_withtag(tag, i)

    def _score_ring(self, canvas, x, y, radius, score, color, font, width=4):
        bounds = (x - radius, y - radius, x + radius, y + radius)
        canvas.create_oval(*bounds, outline=LINE2, width=width)
        if score > 0:
            canvas.create_arc(*bounds, start=90, extent=-min(score * 3.6, 359.9),
                              style="arc", outline=color, width=width)
        canvas.create_text(x, y, text=f0(score), fill=color, font=font)

    def draw_verdict(self):
        c = self.cv
        c.delete("all")
        self._spark = self._shine = self._halo_col = None
        self._verdict_rect = (0, 0, 0, 0)
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 60:
            return
        r = self.current()
        highlight = bool(r and r is self.results[0])
        self.rrect(c, 1, 1, w - 1, h - 1, 12, fill=CARD, outline=ACC2 if highlight else LINE)
        if not r:
            c.create_text(16, 24, text="Veri yükleniyor…", fill=MUT, anchor="w", font=self.F(11))
            return

        score = r["puan"]
        color = tier_color(score)
        radius = dpx(28)
        x, y = w - dpx(48), h / 2 - dpx(5)
        for layer in range(3, 0, -1):
            outer = radius + layer * 3
            c.create_oval(x - outer, y - outer, x + outer, y + outer,
                          outline=lerp(CARD, color, .22 / layer), width=2, tags="halo")
        bounds = (x - radius, y - radius, x + radius, y + radius)
        c.create_oval(*bounds, outline=LINE2, width=7)
        extent = min(359.9, score * self.ring_t * 3.6)
        if extent > 0:
            segments = max(1, math.ceil(extent / 10))
            length = extent / segments
            for i in range(segments):
                shade = lerp(lerp(color, "#000000", .35), color, (i + 1) / segments)
                c.create_arc(*bounds, start=90 - i * length,
                             extent=-min(length + .8, extent - i * length),
                             style="arc", width=7, outline=shade)
            angle = math.radians(90 - extent)
            sx, sy = x + radius * math.cos(angle), y - radius * math.sin(angle)
            c.create_oval(sx - 8, sy - 8, sx + 8, sy + 8, outline=lerp(CARD, color, .45),
                          width=2, tags="sparkglow")
            c.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, outline="",
                          fill=lerp(color, FG, .35), tags="spark")
            self._spark = (x, y, radius, angle)
            self._halo_col = color
        c.create_text(x, y, text=f0(score * self.ring_t), fill=color, font=self.F(18, True))
        c.create_text(min(x, w - 6 - self.tw("uyum / 100", 8) / 2), y + radius + dpx(12),
                      text="uyum / 100", fill=MUT, font=self.F(8))
        self._verdict_rect = (x - radius, y - radius, x + radius, y + radius)

        label = "EN UYGUN EKİN" if highlight else "SEÇİLİ EKİN"
        width = max(55, w - dpx(112))
        def line(y, text, font, color):
            item = c.create_text(16, y, text=text, font=font, fill=color, anchor="nw", width=width)
            return c.bbox(item)[3] + 4
        next_y = line(10, label, self.F(9, True), ACC)
        next_y = line(next_y, r["ekin"], self.F(19, True), FG)
        next_y = line(next_y, NoTr(f"{self.name} · {tarla_dil.tr(tier_of(score))}"), self.F(9), MUT)
        when = f"Ekim: {r['ekim_ayi']} · " if r["ekim_ayi"] else "Çok yıllık ürün · "
        summary = when + f"Tahmini sezonluk su açığı: {f0(r['sulama_acigi_mm'])} mm."
        end_y = line(next_y, summary, self.F(9), FG2)
        enough = r["sulama_acigi_mm"] < .15 * r["kriter"]["need"]
        end_y = line(end_y, "Modelde su açığı düşük" if enough else "Su açığı var · nemi kontrol et",
                     self.F(9), ACC if enough else GOLD)
        requested = max(dipx(134), end_y + 6)
        if c.winfo_pixels(c.cget("height")) != requested:
            c.configure(height=requested)

    def cycle_suggestion(self, event):
        if not self.results:
            return
        x0, y0, x1, y1 = getattr(self, "_verdict_rect", (0, 0, 0, 0))
        if not (x0 <= event.x <= x1 and y0 <= event.y <= y1):
            return
        i = next((k for k, r in enumerate(self.results) if r["ekin"] == self.sel), 0)
        self._select(self.results[(i + 1) % len(self.results)]["ekin"])

    def on_verdict_move(self, event):
        x0, y0, x1, y1 = getattr(self, "_verdict_rect", (0, 0, 0, 0))
        self.cv.configure(cursor="hand2" if (x0 <= event.x <= x1 and y0 <= event.y <= y1) else "")

    # ------------------------------------------------------------ çizim: iklim
    def draw_chart(self):
        c = self.cc
        c.delete("all")
        self._cgeo = None
        w, h = c.winfo_width(), c.winfo_height()
        r, d = self.current(), self.clim
        if w < 60 or h < 60:
            return
        self.panel(c, 1, 1, w - 1, h - 1, r=16, fill=CARD, outline=LINE)
        if not r or not d:
            return
        yr, ym = sum(d["Pm"]), sum(d["T"]) / 12
        font = self.F(9)
        line = font.metrics("linespace")
        title_font = self.F(13, True)
        title_y = max(dpx(18), 4 + title_font.metrics("linespace") / 2)
        summary_y = max(dpx(41), title_y + (title_font.metrics("linespace") + line) / 2 + 1)
        c.create_text(15, title_y, text="İKLİM", fill=FG, anchor="w", font=title_font)
        summary = tarla_dil.tr(f"{self.name} · ortalama {f1(ym)} °C · {f0(yr)} mm/yıl"
                               + ("" if self.kaynak == "nasa" else " · örnek veri"))
        c.create_text(15, summary_y, anchor="w", fill=MUT, font=font,
                      text=NoTr(self.fitted_text(summary, font, w - 30)))
        t_lo = int(min(0, min(d["T"])) // 10 * 10)
        t_hi = int(-(-max(d["T"]) // 10) * 10)
        if t_hi <= t_lo:
            t_hi = t_lo + 10
        p_max = max(50, int(-(-max(d["Pm"]) // 25) * 25))
        legend = []
        x, row = 15, 0
        for kind, label, color in (("l", "Sıcaklık", GOLD), ("b", "Yağış", WATER),
                                   ("b", "Yetişme dönemi", BAND)):
            size = self.tw(label, 9) + 30
            if x > 15 and x + size > w:
                x, row = 15, row + 1
            legend.append((x, row, kind, label, color))
            x += size + 8
        legend_top = h - 4 - (row + 1) * (line + 1)
        months_y = legend_top - line / 2 - 2
        L = max(dpx(43), font.measure(f"{t_lo}°") + 12)
        R = max(dpx(70), font.measure(f"{p_max} mm") + 13)
        T = max(dpx(64), summary_y + line + 2)
        B = months_y - line / 2 - 3
        H, cw = B - T, (w - L - R) / 12
        if H <= 0 or cw <= 0:
            return
        yT = lambda v: T + (t_hi - v) / (t_hi - t_lo) * H
        yP = lambda v: B - v / p_max * H
        window = r["aylar"] if r["ekim_ayi"] else list(range(12))
        sw = self.swap_t
        for j, m in enumerate(window):  # yetişme dönemi: aylar sırayla dolar
            e = anim.out_cubic(anim.stagger(sw, j, .05, .45))
            top = B - (B - T) * e
            c.create_rectangle(L + m * cw, top, L + (m + 1) * cw, B,
                               fill=lerp(CARD, BAND, e), outline="")
            c.create_rectangle(L + m * cw, top, L + (m + 1) * cw, top + 3,
                               fill=lerp(CARD, ACC2, e), outline="")
        ticks = ([t_hi] if H < line + 3 else [t_lo, t_hi]) if H < 80 else range(t_lo, t_hi + 1, 10)
        for v in ticks:
            c.create_line(L, yT(v), w - R, yT(v), fill=LINE, dash=(2, 4))
            c.create_text(L - 8, yT(v), text=f"{v}°", fill=GOLD, anchor="e", font=self.F(9))
        c.create_line(L, B, w - R, B, fill=LINE2)
        c.create_text(w - R + 8, yP(p_max), text=f"{p_max} mm", fill=WATER, anchor="w",
                      font=self.F(9))
        tip_m = self._tip["m"] if self._tip else None
        for m, p in enumerate(d["Pm"]):   # yağış çubukları sırayla, hafif taşarak yükselir
            e = anim.out_back(anim.stagger(self.intro_t, m, .045, .5), 1.8)
            top = B - (B - yP(p)) * e
            x0, x1 = L + m * cw + cw * .28, L + m * cw + cw * .72
            colr = lerp(WATER, FG, .3) if m == tip_m else WATER
            if B - top > 8:
                self.rrect(c, x0, top, x1, B + 6, min(5, (x1 - x0) / 2), fill=colr, outline="")
                c.create_rectangle(x0, B - 1, x1, B + 7, fill=CARD, outline="")
            elif B - top > 0:
                c.create_rectangle(x0, top, x1, B, fill=colr, outline="")
        c.create_line(L, B, w - R, B, fill=LINE2)
        # sıcaklık eğrisi: soldan sağa akarak çizilir, ucunda parlak bir nokta
        pts = [(L + (m + .5) * cw, yT(t)) for m, t in enumerate(d["T"])]
        q = anim.clamp(self.intro_t) * 11
        k = int(q)
        path = pts[:k + 1]
        if k < 11:
            f = q - k
            (ax, ay), (bx, by) = pts[k], pts[k + 1]
            path.append((ax + (bx - ax) * f, ay + (by - ay) * f))
        flat = [v for pt in path for v in pt]
        if len(path) >= 2:
            c.create_line(*flat, fill=lerp(CARD, GOLD, .22), width=9, joinstyle="round",
                          capstyle="round", smooth=True)
            c.create_line(*flat, fill=GOLD, width=3, joinstyle="round", capstyle="round",
                          smooth=True)
        for m, (px, py) in enumerate(pts[:k + 1]):
            e = anim.out_back(anim.clamp(q - m + 1), 2.5)
            rr = 3.5 * e
            if rr > .3:
                c.create_oval(px - rr, py - rr, px + rr, py + rr, fill=CARD, outline=GOLD, width=2)
        if k < 11 and path:
            hx, hy = path[-1]
            c.create_oval(hx - 6, hy - 6, hx + 6, hy + 6, fill=lerp(CARD, GOLD, .35), outline="")
            c.create_oval(hx - 3, hy - 3, hx + 3, hy + 3, fill=lerp(GOLD, "#ffffff", .4), outline="")
        step = max(1, math.ceil((max(self.tw(month, 9, True) for month in MON) + 4) / cw))
        for m, n in enumerate(MON):
            if m % step:
                continue
            c.create_text(L + (m + .5) * cw, months_y, text=n,
                          fill=FG if m == tip_m or m in window else MUT2,
                          font=self.F(9, m in window or m == tip_m))
        for x, row, kind, label, colr in legend:
            ly = legend_top + row * (line + 1) + line / 2
            if kind == "l":
                c.create_line(x, ly, x + 16, ly, fill=colr, width=3, capstyle="round")
            else:
                self.rrect(c, x, ly - 5, x + 16, ly + 5, 3, fill=colr, outline="")
            c.create_text(x + 22, ly, text=label, fill=MUT, anchor="w", font=self.F(9))
        self._cgeo = (L, R, T, B, cw, w, yT, yP)
        self.draw_tip()
        self._move_in(c, 1)

    def draw_tip(self):
        """Grafik üzerinde fareyi izleyen kılavuz çizgi + bilgi kartı."""
        c = self.cc
        c.delete("tip")
        tip, geo, d = self._tip, getattr(self, "_cgeo", None), self.clim
        if not tip or tip["m"] is None or not geo or not d:
            return
        L, R, T, B, cw, w, yT, yP = geo
        a = anim.out_cubic(tip.get("a", 1.0))
        x = tip["x"]
        fm = anim.clamp((x - L) / cw - .5, 0, 11)
        i0 = int(fm)
        i1 = min(11, i0 + 1)
        tv = d["T"][i0] + (d["T"][i1] - d["T"][i0]) * (fm - i0)
        ty = yT(tv)
        c.create_line(x, T - 6, x, B, fill=lerp(CARD, MUT2, a), dash=(3, 3), tags="tip")
        c.create_oval(x - 10, ty - 10, x + 10, ty + 10, fill="", outline=lerp(CARD, GOLD, .35 * a),
                      width=2, tags="tip")
        c.create_oval(x - 5, ty - 5, x + 5, ty + 5, fill=CARD, outline=lerp(CARD, GOLD, a),
                      width=2, tags="tip")
        m = tip["m"]
        bw, bh = dpx(168), dpx(78)
        bx = x + 16 if x + 16 + bw < w - 8 else x - 16 - bw
        by = T - 4 + (1 - a) * 8
        self.rrect(c, bx + 2, by + 4, bx + bw + 2, by + bh + 4, 12, fill=lerp(CARD, SHADOW, a),
                   outline="", tags="tip")
        self.rrect(c, bx, by, bx + bw, by + bh, 12, fill=lerp(CARD, CARD2, a),
                   outline=lerp(CARD, LINE2, a), tags="tip")
        c.create_text(bx + 14, by + dpx(16), text=MON[m], fill=lerp(CARD, FG, a), anchor="w",
                      font=self.F(10, True), tags="tip")
        c.create_oval(bx + 14, by + dpx(40) - 4, bx + 22, by + dpx(40) + 4, fill=lerp(CARD, GOLD, a), outline="",
                      tags="tip")
        c.create_text(bx + 30, by + dpx(40), text=f"Sıcaklık  {f1(d['T'][m])} °C",
                      fill=lerp(CARD, FG2, a), anchor="w", font=self.F(9), tags="tip")
        c.create_oval(bx + 14, by + dpx(60) - 4, bx + 22, by + dpx(60) + 4, fill=lerp(CARD, WATER, a), outline="",
                      tags="tip")
        c.create_text(bx + 30, by + dpx(60), text=f"Yağış  {f0(d['Pm'][m])} mm",
                      fill=lerp(CARD, FG2, a), anchor="w", font=self.F(9), tags="tip")

    def on_chart_move(self, event):
        geo = getattr(self, "_cgeo", None)
        if not geo:
            return
        L, R, T, B, cw, w, yT, yP = geo
        m = None
        if L <= event.x < w - R and T - 30 <= event.y <= B + 26:
            m = max(0, min(11, int((event.x - L) / cw)))
        target = L + (m + .5) * cw if m is not None else None
        if m is None:
            if self._tip is not None:
                self._tip = None
                self.draw_chart()
            return
        prev = self._tip
        if prev and prev["m"] == m:
            return
        self._tip = {"m": m, "x": prev["x"] if prev else target, "tx": target,
                     "a": prev["a"] if prev else 0.0}
        self.draw_chart()               # vurgulanan ay çubuğu + etiketi
        if not ANIM:
            self._tip.update(x=target, a=1.0)
            self.draw_tip()
            return

        def step(now):
            tip = self._tip
            if not tip:
                return False
            dx = tip["tx"] - tip["x"]
            tip["x"] += dx * .28
            tip["a"] = min(1.0, tip["a"] + .12)
            done = abs(dx) < .5 and tip["a"] >= 1
            if done:
                tip["x"] = tip["tx"]
            try:
                self.draw_tip()
            except tk.TclError:
                return False
            return not done
        self.ticker.add("tip", step)

    def on_chart_leave(self, event=None):
        if self._tip is not None:
            self._tip = None
            self.draw_chart()

    # ------------------------------------------------------------ çizim: faktör
    def draw_factors(self):
        c = self.cf
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 120:
            return
        r = self.current()
        rows = factor_rows(r) if r else []
        deficit_share = None
        if r:
            if r["ekim_ayi"] is not None:
                rows.append(("Soğuklama", None, "—", "Bu ürün için hesaplanmaz"))
            rows.append(("Sezonluk su açığı", None, f"{f0(r['sulama_acigi_mm'])} mm",
                         "Yağış sonrası karşılanmamış su ihtiyacı"))
            need = r["sulama_ihtiyaci_mm"]
            if need > 0:
                deficit_share = anim.clamp(r["sulama_acigi_mm"] / need)
        cols = 2
        gap, pad = 14, 14
        colw = (w - 2 * pad - gap * (cols - 1)) / cols

        def text_bottom(x, y, text, color, font, **options):
            item = c.create_text(x, y, text=text, fill=color, font=font, **options)
            return c.bbox(item)[3]

        y = text_bottom(pad, 8, "PUANIN BİLEŞENLERİ", FG, self.F(11, True), anchor="nw") + 4
        for start in range(0, len(rows), cols):
            next_y = y
            for offset, (label, score, value, ideal) in enumerate(rows[start:start + cols]):
                x = pad + offset * (colw + gap)
                heading = text_bottom(x, y, label, FG2, self.F(9, True), anchor="nw", width=colw)
                value_y = heading
                rating_bottom = heading
                share = None
                if score is not None:
                    points = min(100, score * 100)
                    color = tier_color(points)
                    progress = anim.out_cubic(anim.stagger(self.ring_t, start + offset, .07, .55))
                    share = points / 100 * progress
                    rating = f"{tier_of(points)} · {f0(points * progress)}"
                elif label == "Sezonluk su açığı" and deficit_share is not None:
                    share = deficit_share
                    color = WATER
                    rating = f"%{f0(share * 100)}" if tarla_dil.lang() == "tr" else f"{f0(share * 100)}%"
                    ideal = "Sezonluk su ihtiyacının karşılanmayan payı"
                if share is not None:
                    rating_bottom = text_bottom(x + colw, heading, rating, color,
                                                self.F(8, True), anchor="ne", width=colw)
                    if self.tw(value, 8) + self.tw(rating, 8, True) + 6 > colw:
                        value_y = rating_bottom
                value_bottom = text_bottom(x, value_y, value, FG, self.F(8), anchor="nw", width=colw)
                detail_y = max(rating_bottom, value_bottom) + 2
                if share is not None:
                    c.create_rectangle(x, detail_y, x + colw, detail_y + 4, fill=LINE2, outline="")
                    if share:
                        c.create_rectangle(x, detail_y, x + colw * share,
                                           detail_y + 4, fill=color, outline="")
                    detail_y += 6
                end = text_bottom(x, detail_y, ideal, MUT, self.F(8), anchor="nw", width=colw)
                next_y = max(next_y, end + 4)
            y = next_y
        height = y + 4
        background = self.rrect(c, 1, 1, w - 1, max(h, height) - 1, 12, fill=CARD, outline=LINE)
        c.tag_lower(background)
        if c.winfo_pixels(c.cget("height")) != height:
            c.configure(height=height)

    # ------------------------------------------------------------ çizim: sıralama
    def draw_rank(self):
        c = self.cr
        c.delete("all")
        w = c.winfo_width()
        if w < 110:
            return
        row_h = max(dipx(70), self.F(11, True).metrics("linespace") + self.F(8).metrics("linespace") + 30)
        viewport = row_h * 4
        if c.winfo_pixels(c.cget("height")) != viewport:
            c.configure(height=viewport)
        self.hits = []
        self._target_sel = self._target_hov = None
        for i, crop in enumerate(self.results):
            y = i * row_h
            row_mark = (c.find_all() or (0,))[-1]
            score = crop["puan"]
            color = tier_color(score)
            selected = crop["ekin"] == self.sel
            bg = ACC_SOFT if selected else CARD3 if i == self.hover else CARD2
            outline = ACC2 if selected else LINE
            cy = y + (row_h - 5) / 2
            self.rrect(c, 4, y + 1, w - 4, y + row_h - 4, 10, fill=bg, outline=outline)
            icon_color = ACC if selected else MUT
            tarla_ekin_simgeleri.draw(c, crop["ekin"], dpx(22), cy, icon_color)
            full_label = tarla_dil.tr(crop["ekin"])
            label = full_label
            max_width = w - dpx(105)
            while len(label) > 3 and self.F(11, True).measure(label + "…") > max_width:
                label = label[:-1]
            if label != full_label:
                label += "…"
            c.create_text(dpx(44), cy - dpx(10), text=NoTr(label), fill=FG, anchor="w", font=self.F(11, True))
            details = " · ".join(filter(None, (crop["grup"], crop["ekim_ayi"])))
            details = self.fitted_text(tarla_dil.tr(details), self.F(8), max_width)
            c.create_text(dpx(44), cy + dpx(11), text=NoTr(details), fill=MUT, anchor="w", font=self.F(8))
            self._score_ring(c, w - dpx(31), cy, dpx(17), score * self.intro_t, color, self.F(10, True))
            if i < 3:
                medal = (GOLD, FG2, lerp(GOLD, BAD, .45))[i]
                c.create_oval(dpx(28), y + 4, dpx(44), y + 4 + dpx(16), fill=bg, outline=medal)
                c.create_text(dpx(36), y + 4 + dpx(8), text=str(i + 1), fill=medal, font=self.F(8, True))
            if self.intro_t < 1 and i < 6:      # yeni analizde satırlar sırayla sağdan kayarak gelir
                e = anim.out_cubic(anim.stagger(self.intro_t, i, .08, .5))
                dx = (1 - e) * dpx(36)
                if dx > .3:
                    for item in c.find_all():
                        if item > row_mark:
                            c.move(item, dx, 0)
            self.hits.append((y, y + row_h, crop["ekin"]))
        c.configure(scrollregion=(0, 0, w, max(viewport, len(self.hits) * row_h)),
                    yscrollincrement=row_h)

    def _row_at(self, event):
        cy = self.cr.canvasy(event.y)
        for i, (a, b, _) in enumerate(self.hits):
            if a <= cy < b:
                return i
        return None

    def on_click(self, event):
        i = self._row_at(event)
        if i is not None:
            self._select(self.hits[i][2])

    def on_move(self, event):
        i = self._row_at(event)
        self.cr.configure(cursor="hand2" if i is not None else "")
        self.set_hover(i)

    def set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.draw_rank()
            self._glide_rank()

def error_log_path():
    return os.path.join(tarla_ayarlar.app_dir(), "hata.log")


def log_error(where=""):
    """Pencereli exe'de hatalar ekrana düşmez: kullanıcı klasöründeki hata.log'a yaz."""
    import traceback
    try:
        os.makedirs(tarla_ayarlar.app_dir(), exist_ok=True)
        with open(error_log_path(), "a", encoding="utf-8") as f:
            f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S] ") + where + "\n")
            f.write(traceback.format_exc())
    except Exception:
        pass


def resource_path(name):
    """Paketlenmiş exe'de (PyInstaller) ve kaynak klasörde dosya yolu."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, name)


def set_app_icon(root):
    """Pencere ve görev çubuğu simgesi. Dosya yoksa sessizce varsayılan kalır."""
    ico, png = resource_path("tarla_pusulasi.ico"), resource_path("tarla_pusulasi.png")
    if os.name == "nt" and os.path.exists(ico):
        try:
            root.iconbitmap(default=ico)        # tüm alt pencereler de bu simgeyi alır
        except Exception:
            pass
    if os.path.exists(png):
        try:
            img = tk.PhotoImage(file=png)
            root.iconphoto(True, img)
            root._app_icon = img                # çöp toplayıcıdan koru
        except Exception:
            pass


def main():
    if "--web-window" in sys.argv:
        i = sys.argv.index("--web-window")
        raise SystemExit(tarla_pencere.run(*sys.argv[i + 1:]))
    try:  # Windows'ta net yazı
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    try:  # görev çubuğunda Python simgesi yerine uygulama simgesi görünsün
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TarlaPusulasi.Masaustu")
    except Exception:
        pass
    if "--graphics-self-test" in sys.argv:
        from verify_revision import verify_graphics
        report = sys.argv[sys.argv.index("--graphics-self-test") + 1]
        raise SystemExit(verify_graphics(sys.modules[__name__], report))
    cfg = tarla_ayarlar.load()          # tema ve dil, pencereler kurulmadan önce
    apply_theme(cfg["tema"], cfg["palet"])
    tarla_dil.set_lang(cfg["dil"])
    ai_asistan.set_language(cfg["dil"])
    tarla_gorunum.install(tk)
    root = tk.Tk()

    def report(exc, val, tb):            # arayüz geri çağrılarındaki hatalar kaybolmasın
        import traceback
        try:
            os.makedirs(tarla_ayarlar.app_dir(), exist_ok=True)
            with open(error_log_path(), "a", encoding="utf-8") as f:
                f.write(time.strftime("\n[%Y-%m-%d %H:%M:%S] arayüz\n"))
                f.write("".join(traceback.format_exception(exc, val, tb)))
        except Exception:
            pass
        traceback.print_exception(exc, val, tb)
    root.report_callback_exception = report
    set_app_icon(root)
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
