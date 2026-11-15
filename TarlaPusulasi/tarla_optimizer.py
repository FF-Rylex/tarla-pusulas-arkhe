#!/usr/bin/env python3
"""Tarla Pusulası — kuantum-esinli rotasyon optimizasyonu (v3.0 · Quantum Bio-Sim).

Klasik bilgisayarda çalışır; kuantum donanımı KULLANMAZ. "Kuantum-esinli" ifadesi
yöntemin adından gelir: Quantum-behaved Particle Swarm Optimization (QPSO, Sun vd.
2004) parçacıkları klasik PSO'daki hız yerine kuantum kuyusundaki olasılık
dağılımından (delta potansiyeli) örnekler. Bulunan en iyi çözümler ardından
benzetimli tavlama (simulated annealing) ile iyileştirilir.

Akış
  1. VERİ HARMONİZASYONU   NASA POWER aylık klimatolojisi + (varsa) kullanıcının
     girdiği SMAP / ECOSTRESS / GPM / GEDI ölçümleri tek bir aylık analiz ızgarasında
     0-1 göstergelere çevrilir -> "ekolojik durum matrisi".
  2. MONTE CARLO           NASA POWER 2001-2024 gerçek yıllarından (yoksa parametrik
     varsayımdan) yüzlerce olası yıl örneklenir; her ekin her olası yılda
     tarla_pusulasi.evaluate ile puanlanır (tablo bir kez hesaplanır).
  3. AMAÇ FONKSİYONU       Bir rotasyonun faydası = verim göstergesi + su + toprak
     sağlığı (azot dengesi, organik madde, hastalık döngüsü) + erozyon azaltma +
     çeşitlilik + pazar. Belirsizliğe karşı dayanıklılık: ortalama − λ·standart sapma.
     ("Enerji" = −fayda; en düşük enerjili durumlar = en iyi rotasyonlar.)
  4. ARAMA                 QPSO (sürü) -> benzetimli tavlama (yerel iyileştirme) ->
     birbirinden farklı en iyi 3 rotasyon. 3 yıllık aramada sonuç, tüm kombinasyonların
     tek tek tarandığı "tam tarama" ile doğrulanabilir (verify_bruteforce).

Yalnızca Python standart kütüphanesini kullanır.
"""
import itertools
import json
import math
import random
import time
from collections import Counter

import tarla_pusulasi as tp

# ------------------------------------------------------------------ ekin özellikleri
# family : botanik familya (aynı familya üst üste gelirse hastalık/zararlı döngüsü sürer)
# n      : azot dengesi (+ bağlar / − tüketir), yaklaşık göreli değer
# res    : bıraktığı bitki artığı / organik madde katkısı (0-1)
# mkt    : pazar değeri göstergesi (kategori bazlı varsayım; çiftçi önceliğiyle ağırlıklanır)
TRAITS = {
    "Kışlık buğday": dict(family="Buğdaygiller", n=-0.5, res=0.70, mkt=0.55),
    "Arpa": dict(family="Buğdaygiller", n=-0.4, res=0.60, mkt=0.50),
    "Mısır": dict(family="Buğdaygiller", n=-1.0, res=0.80, mkt=0.65),
    "Pamuk": dict(family="Ebegümecigiller", n=-0.8, res=0.40, mkt=0.80),
    "Ayçiçeği": dict(family="Papatyagiller", n=-0.6, res=0.50, mkt=0.70),
    "Şeker pancarı": dict(family="Amaranthaceae", n=-0.9, res=0.30, mkt=0.75),
    "Patates": dict(family="Patlıcangiller", n=-0.8, res=0.20, mkt=0.80),
    "Domates": dict(family="Patlıcangiller", n=-0.9, res=0.20, mkt=0.85),
    "Pirinç": dict(family="Buğdaygiller", n=-0.8, res=0.60, mkt=0.70),
    "Nohut": dict(family="Baklagiller", n=0.8, res=0.30, mkt=0.70),
    "Mercimek": dict(family="Baklagiller", n=0.8, res=0.30, mkt=0.70),
    "Karpuz": dict(family="Kabakgiller", n=-0.6, res=0.20, mkt=0.70),
    "Kuru soğan": dict(family="Soğangiller", n=-0.6, res=0.10, mkt=0.70),
    "Biber": dict(family="Patlıcangiller", n=-0.8, res=0.20, mkt=0.85),
    "Hıyar": dict(family="Kabakgiller", n=-0.7, res=0.20, mkt=0.80),
    "Kavun": dict(family="Kabakgiller", n=-0.6, res=0.20, mkt=0.70),
    "Kuru fasulye": dict(family="Baklagiller", n=0.6, res=0.30, mkt=0.75),
    "Yulaf": dict(family="Buğdaygiller", n=-0.4, res=0.60, mkt=0.45),
    "Çavdar": dict(family="Buğdaygiller", n=-0.3, res=0.70, mkt=0.45),
    # v3.6: 40 ekinlik listedeki yeni tek yıllıklar (göreli göstergeler, aynı ölçek)
    "Kanola": dict(family="Turpgiller", n=-0.7, res=0.50, mkt=0.70),
    "Soya": dict(family="Baklagiller", n=0.7, res=0.40, mkt=0.70),
    "Yer fıstığı": dict(family="Baklagiller", n=0.6, res=0.25, mkt=0.80),
    "Tütün": dict(family="Patlıcangiller", n=-0.7, res=0.20, mkt=0.60),
    "Susam": dict(family="Susamgiller", n=-0.4, res=0.30, mkt=0.75),
    "Patlıcan": dict(family="Patlıcangiller", n=-0.8, res=0.20, mkt=0.80),
    "Lahana": dict(family="Turpgiller", n=-0.8, res=0.20, mkt=0.70),
    "Havuç": dict(family="Maydanozgiller", n=-0.5, res=0.10, mkt=0.70),
    "Ispanak": dict(family="Amaranthaceae", n=-0.5, res=0.10, mkt=0.65),
    "Sarımsak": dict(family="Soğangiller", n=-0.5, res=0.10, mkt=0.80),
    # v3.9: 50 ekinlik listedeki yeni tek yıllıklar (göreli göstergeler, aynı ölçek)
    "Kabak": dict(family="Kabakgiller", n=-0.6, res=0.20, mkt=0.75),
    "Marul": dict(family="Papatyagiller", n=-0.5, res=0.05, mkt=0.70),
    "Karnabahar": dict(family="Turpgiller", n=-0.8, res=0.20, mkt=0.70),
    "Bezelye": dict(family="Baklagiller", n=0.7, res=0.30, mkt=0.70),
    "Bakla": dict(family="Baklagiller", n=0.9, res=0.40, mkt=0.60),
    "Sorgum": dict(family="Buğdaygiller", n=-0.7, res=0.80, mkt=0.50),
    "Tritikale": dict(family="Buğdaygiller", n=-0.4, res=0.70, mkt=0.50),
}
ANNUALS = [c["name"] for c in tp.CROPS if c["group"] != "Çok yıllık" and c["name"] in TRAITS]

COVER_NAME = "kışlık örtü bitkisi (fiğ + arpa/çavdar karışımı)"
COVER_SHORT = "örtü"
WINTER = {8, 9, 10, 11, 0, 1, 2}           # Eylül..Mart (0 = Ocak)
COVER_WATER_MM = 40                        # örtü bitkisinin kullandığı su (varsayım)

# Karbon: örtü bitkisi için Poeplau & Don (2015) meta-analizi: 0,32 ± 0,08 t C/ha/yıl.
# Baklagil ve bitki artığı katkıları yaklaşık VARSAYIMDIR (aralık geniş tutuldu).
C_COVER = (0.24, 0.32, 0.40)
C_LEGUME = (0.00, 0.10, 0.20)
C_RESIDUE = 0.15                           # (ortalama artık − 0,5) × bu katsayı
CO2_PER_C = 44.0 / 12.0

# Amaç fonksiyonu temel ağırlıkları (öncelik kaydırıcıları bunları ölçekler)
BASE_W = dict(verim=0.30, su=0.15, toprak=0.20, erozyon=0.12, cesitlilik=0.08, pazar=0.15)
COMP_LABELS = [("verim", "Uygunluk"), ("su", "Su"), ("toprak", "Toprak sağlığı"),
               ("erozyon", "Erozyon azaltma"), ("cesitlilik", "Çeşitlilik"), ("pazar", "Pazar")]

DEFAULT_PRIO = dict(su=0.5, toprak=0.5, pazar=0.5, risk=0.5)


def clamp(x, a=0.0, b=1.0):
    return min(b, max(a, x))


def _c(x, nd=1):
    """Türkçe ondalık: 6.0 -> '6,0'."""
    return f"{x:.{nd}f}".replace(".", ",")


# ================================================================== 1. harmonizasyon
def _ra(lat, month):
    """FAO-56 denklem 21: dünya dışı radyasyon (MJ/m²/gün), ayın ortasındaki gün için."""
    J = int(15 + 30.4 * month)
    phi = math.radians(lat)
    dr = 1 + 0.033 * math.cos(2 * math.pi * J / 365)
    dec = 0.409 * math.sin(2 * math.pi * J / 365 - 1.39)
    ws = math.acos(clamp(-math.tan(phi) * math.tan(dec), -1, 1))
    return (24 * 60 / math.pi) * 0.0820 * dr * (
        ws * math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.sin(ws))


def et0_hargreaves(clim, lat):
    """Aylık referans evapotranspirasyon (mm/ay), Hargreaves-Samani (FAO-56 denklem 52)."""
    out = []
    for m in range(12):
        T, Tmin = clim["T"][m], clim["Tmin"][m]
        Tmax = 2 * T - Tmin                  # günlük ortalama ≈ (Tmax + Tmin) / 2
        ra = _ra(lat, m)
        et = 0.0023 * 0.408 * ra * (T + 17.8) * math.sqrt(max(0.0, Tmax - Tmin))
        out.append(max(0.0, et) * tp.DIM[m])
    return out


def harmonize(clim, lat=None, soil=None, sat=None):
    """Farklı kaynak/çözünürlükteki verileri ortak aylık ızgarada birleştir.

    sat: kullanıcının uydu ürünlerinden okuduğu isteğe bağlı değerler
        smap  : SMAP L4 kök bölgesi toprak nemi, m³/m³ (yetişme dönemi ortalaması)
        grace : GRACE / GRACE-FO karasal su depolama eğilimi, cm/yıl (eksi = azalıyor)
        ndvi  : Landsat / MODIS yetişme dönemi ortalama NDVI (0-1)
        eco   : ECOSTRESS yaz öğle kara yüzeyi sıcaklığı, °C
        gpm   : GPM IMERG yıllık toplam yağış, mm
        gedi  : GEDI L4A yer üstü biyokütle yoğunluğu, Mg/ha
    Dönen: {'iklim': kalibre edilmiş iklim, 'satirlar': [...], 'kalibrasyon': [...],
            'biyokutle': {...}, 'et0': [...]}
    """
    sat = {k: v for k, v in (sat or {}).items() if v is not None}
    water_k = 1.0
    soil = soil or tp.SOIL_DEFAULT
    lat = 39.0 if lat is None else lat
    c = {k: list(v) for k, v in clim.items()}
    notes = []

    # --- GPM: yağış ölçeği (MERRA-2 tabanlı POWER yağışını uydu toplamına oranla)
    if sat.get("gpm"):
        k = clamp(sat["gpm"] / max(1.0, sum(c["Pm"])), 0.5, 1.6)
        c["Pm"] = [v * k for v in c["Pm"]]
        notes.append(f"GPM yıllık yağış {sat['gpm']:.0f} mm → aylık yağış ×{k:.2f}")
    # --- SMAP: hacimsel nem (m³/m³) -> ıslaklık oranı (gözenekliliğe bölünür)
    if sat.get("smap"):
        por = clamp(0.50 - 0.15 * soil["sand"] / 100.0 + 0.05 * soil["clay"] / 100.0, 0.35, 0.55)
        wet = clamp(sat["smap"] / por, 0.02, 1.2)
        grow = [c["GW"][m] for m in tp.GROW_SEASON]
        k = clamp(wet / max(0.02, sum(grow) / len(grow)), 0.5, 1.6)
        c["GW"] = [clamp(v * k, 0, 1.3) for v in c["GW"]]
        notes.append(f"SMAP {sat['smap']:.2f} m³/m³ (gözeneklilik ≈{por:.2f}) → kök nemi ×{k:.2f}")
    # --- ECOSTRESS: yüzey sıcaklığı, hava sıcaklığından beklenenle karşılaştırılır
    if sat.get("eco"):
        summer = [5, 6, 7]
        tmax = sum(2 * c["T"][m] - c["Tmin"][m] for m in summer) / 3
        off = clamp((sat["eco"] - (tmax + 6.0)) * 0.3, -3, 3)
        for m in summer:
            c["T"][m] += off
        notes.append(f"ECOSTRESS yaz LST {sat['eco']:.1f} °C → yaz sıcaklığı {off:+.1f} °C")

    # --- GRACE: uzun vadeli yeraltı/karasal su kaybı -> su açığı cezası büyür
    if sat.get("grace") is not None and "grace" in sat:
        water_k = 1.0 + clamp(-sat["grace"] * 0.08, 0.0, 0.5)
        notes.append(f"GRACE su depolama eğilimi {sat['grace']:+.1f} cm/yıl → su açığı ağırlığı "
                     f"×{water_k:.2f}")
    veg = None
    if sat.get("ndvi") is not None:
        veg = clamp((0.65 - sat["ndvi"]) / 0.45)
        source = sat.get("ndvi_source", "Landsat/MODIS NDVI")
        notes.append(f"{source} · NDVI {sat['ndvi']:.2f} → bitki örtüsü stresi %{veg * 100:.0f}")

    et0 = et0_hargreaves(c, lat)
    ptot = max(1.0, sum(c["Pm"]))
    ero = [p * p / ptot for p in c["Pm"]]             # Fournier benzeri aylık aşındırma payı
    emax = max(ero) or 1.0
    rows = [
        dict(key="nem", ad="Kök bölgesi nem stresi", veri="SMAP-uyumlu",
             kaynak="SMAP (girildi) + NASA POWER GWETROOT" if sat.get("smap")
             else "NASA POWER GWETROOT (MERRA-2) · SMAP girilmedi",
             deger=[clamp(1 - (g - 0.12) / 0.45) for g in c["GW"]]),
        dict(key="isi", ad="Isı stresi", veri="ECOSTRESS-uyumlu",
             kaynak="ECOSTRESS (girildi) + NASA POWER T2M" if sat.get("eco")
             else "NASA POWER T2M / T2M_MIN · ECOSTRESS girilmedi",
             deger=[clamp(((2 * c["T"][m] - c["Tmin"][m]) - 28) / 10) for m in range(12)]),
        dict(key="su", ad="Su dengesi açığı (ET₀ − yağış)", veri="GPM + FAO-56",
             kaynak=("GPM (girildi)" if sat.get("gpm") else "NASA POWER PRECTOTCORR")
             + " + Hargreaves ET₀",
             deger=[clamp((et0[m] - c["Pm"][m]) / 150) for m in range(12)]),
        dict(key="yagis", ad="Aşırı yağış / aşındırma gücü", veri="GPM-uyumlu",
             kaynak="Aylık yağışın Fournier payı",
             deger=[clamp(e / emax) for e in ero]),
        dict(key="don", ad="Don riski", veri="NASA POWER",
             kaynak="NASA POWER T2M_MIN (aylık ortalama gece)",
             deger=[clamp((2 - c["Tmin"][m]) / 8) for m in range(12)]),
    ]
    if sat.get("gedi"):
        agb = sat["gedi"]
        bio = dict(deger=agb, karbon=round(agb * 0.47, 1), kaynak="GEDI L4A (girildi)")
        notes.append(f"GEDI biyokütle {agb:.0f} Mg/ha → üst katman karbon ≈{agb * 0.47:.0f} t C/ha")
    else:
        # GEDI yokken: toprak organik karbonundan 0-30 cm stok (yoğunluk 1,3 g/cm³)
        stok = soil["soc"] / 100 * 1.3 * 0.30 * 10000
        bio = dict(deger=None, karbon=round(stok, 1),
                   kaynak="Proje bölgesel toprak varsayımından 0–30 cm karbon; yoğunluk 1,3 g/cm³ varsayıldı (GEDI girilmedi)")
    return {"iklim": c, "satirlar": rows, "kalibrasyon": notes, "biyokutle": bio,
            "su_katsayi": water_k, "bitki_stresi": veg,
            "et0": [round(v) for v in et0], "erozivite": ero,
            "girilen": sorted(k for k in sat if k != "ndvi_source")}


# ================================================================== 2. Monte Carlo tablosu
class Table:
    """Her ekin × her olası yıl için uygunluk ve su açığı (bir kez hesaplanır)."""

    def __init__(self, clim, sulama=False, soil=None, history=None, dT=0.0, dP=0.0,
                 draws=240, seed=11, crops=None):
        rnd = random.Random(seed)
        pool = (history or {}).get("yillar") or []
        self.method = "gecmis" if pool else "parametrik"
        self.crops = list(crops or ANNUALS)
        self.n = len(self.crops)
        self.D = draws
        dGW = 0.3 * dP
        anoms = []
        for _ in range(draws):
            if pool:
                a = rnd.choice(pool)
                j = rnd.gauss(0, 0.2)
                anoms.append({"T": [v + j for v in a["T"]], "Tmin": [v + j for v in a["Tmin"]],
                              "P": a["P"], "GW": a["GW"], "RH": a["RH"], "SW": a["SW"]})
            else:
                anoms.append(tp._synthetic_anomaly(rnd))
        climates = [tp._apply(clim, an, dT, dP, dGW, 1) for an in anoms]
        self.S, self.W = [], []
        for name in self.crops:
            crop = tp.BY_NAME[name]
            s_row, w_row = [], []
            for cc in climates:
                r = tp.evaluate(crop, cc, sulama, soil)
                s_row.append(r["puan"])
                w_row.append(r["sulama_acigi_mm"])
            self.S.append(s_row)
            self.W.append(w_row)
        base = tp.rank(_shift(clim, dT, dP, dGW), sulama, soil)
        by = {r["ekin"]: r for r in base}
        # takvim: iklim ortalamasında en iyi ekim ayı ve süre
        self.sow = [by[n]["aylar"][0] for n in self.crops]
        self.dur = [tp.BY_NAME[n]["months"] for n in self.crops]
        self.mean = [by[n]["puan"] for n in self.crops]


def _shift(clim, dT, dP, dGW):
    return {"T": [v + dT for v in clim["T"]], "Tmin": [v + dT for v in clim["Tmin"]],
            "Pm": [max(0.0, v * (1 + dP)) for v in clim["Pm"]],
            "GW": [clamp(v + dGW, 0, 1.3) for v in clim["GW"]],
            "RH": list(clim["RH"]), "SW": list(clim["SW"])}


# ================================================================== 3. amaç fonksiyonu
def canonical(g):
    """Rotasyon döngüseldir: (A,B,C) ile (B,C,A) aynı plandır. En küçük dönüşümü seç."""
    L = len(g) // 2
    pairs = list(zip(g[:L], g[L:]))
    best = min(tuple(pairs[i:] + pairs[:i]) for i in range(L))
    return tuple(p[0] for p in best) + tuple(p[1] for p in best)


class Problem:
    def __init__(self, table, L=3, prio=None, erosivity=None, slope_pct=None, soil=None,
                 sulama=False, runs=80, water_k=1.0):
        self.t = table
        self.water_k = water_k
        self.L = L
        self.sulama = sulama
        self.runs = min(runs, table.D // L)
        p = dict(DEFAULT_PRIO, **(prio or {}))
        w = dict(BASE_W)
        w["su"] *= 0.4 + 1.2 * p["su"]
        w["toprak"] *= 0.4 + 1.2 * p["toprak"]
        w["erozyon"] *= 0.4 + 1.2 * p["toprak"]
        w["pazar"] *= 0.4 + 1.2 * p["pazar"]
        tot = sum(w.values())
        self.w = {k: v / tot for k, v in w.items()}
        self.lam = 2.0 * p["risk"]
        ero = erosivity or [1 / 12.0] * 12
        s = sum(ero) or 1.0
        self.ero = [e / s for e in ero]
        soil = soil or tp.SOIL_DEFAULT
        silt = max(0, 100 - soil["clay"] - soil["sand"])
        self.k_soil = 0.8 + 0.4 * silt / 60.0
        if isinstance(slope_pct, dict):
            slope_pct = slope_pct.get("egim_yuzde")
        if slope_pct is not None:
            slope_pct = float(slope_pct)
            if not math.isfinite(slope_pct) or slope_pct < 0:
                raise ValueError("Eğim yüzdesi sıfır veya pozitif bir sayı olmalıdır.")
        self.k_slope = 0.6 + clamp((2.0 if slope_pct is None else slope_pct) / 10.0, 0, 1.6)
        self.slope_pct = slope_pct
        self.cache = {}
        self.evals = 0
        self.space = table.n ** L * 2 ** L

    # -------- takvim: ekim/hasat çakışması ve boş (çıplak) aylar
    def calendar(self, crops, covers):
        L, t = self.L, self.t
        span = 12 * L
        occ = [None] * span                         # her ay: ekin indeksi / 'C' örtü / None
        conflicts = 0
        starts = [12 * k + t.sow[c] for k, c in enumerate(crops)]
        ends = [s + t.dur[c] for s, c in zip(starts, crops)]
        for k in range(L):
            nxt = starts[(k + 1) % L] + (span if k == L - 1 else 0)
            if nxt < ends[k]:
                conflicts += 1
            for m in range(starts[k], ends[k]):
                if occ[m % span] is None:
                    occ[m % span] = crops[k]
        cover_ok = []
        for k in range(L):
            nxt = starts[(k + 1) % L] + (span if k == L - 1 else 0)
            gap = [m % span for m in range(ends[k], nxt) if occ[m % span] is None]
            ok = len(gap) >= 4 and sum(1 for m in gap if m % 12 in WINTER) >= 3
            cover_ok.append(ok)
            if ok and covers[k]:
                for m in gap:
                    if m % 12 in WINTER:
                        occ[m] = "C"
        return occ, conflicts, cover_ok

    def components(self, g):
        """Deterministik bileşenler (toprak, erozyon, çeşitlilik, pazar) + takvim."""
        L = self.L
        crops, covers = list(g[:L]), list(g[L:])
        names = [self.t.crops[c] for c in crops]
        occ, conflicts, cover_ok = self.calendar(crops, covers)
        covers = [1 if (cv and ok) else 0 for cv, ok in zip(covers, cover_ok)]
        tr = [TRAITS[n] for n in names]
        nb = sum(x["n"] for x in tr) + 0.4 * sum(covers)
        soil_n = clamp(0.5 + 0.5 * nb / L)
        om = clamp(sum(x["res"] for x in tr) / L + 0.25 * sum(covers) / L)
        fam_rep = sum(1 for k in range(L) if tr[k]["family"] == tr[(k + 1) % L]["family"])
        same = sum(1 for k in range(L) if names[k] == names[(k + 1) % L])
        pest = clamp(1 - 0.50 * fam_rep / L - 0.45 * same / L)
        toprak = 0.40 * soil_n + 0.30 * om + 0.30 * pest
        bare = [m for m, v in enumerate(occ) if v is None]
        ero_idx = sum(self.ero[m % 12] for m in bare) / L
        erozyon = clamp(1 - ero_idx * self.k_slope * self.k_soil)
        fams = len({x["family"] for x in tr})
        cesit = clamp((fams - 1) / max(1, L - 1))
        pazar = sum(x["mkt"] for x in tr) / L
        return dict(crops=crops, covers=covers, names=names, occ=occ, conflicts=conflicts,
                    cover_ok=cover_ok, toprak=toprak, erozyon=erozyon, cesitlilik=cesit,
                    pazar=pazar, soil_n=soil_n, om=om, pest=pest, bare=len(bare) / L,
                    ero_idx=ero_idx, fam_rep=fam_rep, same=same)

    def utilities(self, g, comp=None):
        comp = comp or self.components(g)
        t, L, w = self.t, self.L, self.w
        crops, covers = comp["crops"], comp["covers"]
        fixed = (w["toprak"] * comp["toprak"] + w["erozyon"] * comp["erozyon"]
                 + w["cesitlilik"] * comp["cesitlilik"] + w["pazar"] * comp["pazar"])
        penalty = 0.78 ** comp["conflicts"] * 0.85 ** comp["same"] * 0.93 ** comp["fam_rep"]
        cover_mm = COVER_WATER_MM * sum(covers) / L if not self.sulama else 0.0
        us, suit, weak, first = [], [], 0, []
        for r in range(self.runs):
            s_sum = d_sum = 0.0
            for k in range(L):
                d = (r * L + k) % t.D
                s = t.S[crops[k]][d]
                suit.append(s)
                s_sum += s
                d_sum += t.W[crops[k]][d]
                if s < 45:
                    weak += 1
                if k == 0:
                    first.append(s)
            verim = s_sum / L / 100.0
            su = clamp(1 - (d_sum / L * self.water_k + cover_mm) / 600.0)
            u = (w["verim"] * verim + w["su"] * su + fixed) * penalty
            us.append(u * 100)
        return us, suit, weak / (self.runs * L), first

    def fitness(self, g):
        g = canonical(g)
        hit = self.cache.get(g)
        if hit is not None:
            return hit
        self.evals += 1
        us = self.utilities(g)[0]
        m = sum(us) / len(us)
        sd = math.sqrt(sum((u - m) ** 2 for u in us) / max(1, len(us) - 1))
        f = m - self.lam * sd
        self.cache[g] = f
        return f

    def report(self, g):
        """Bir rotasyonun tüm sayıları (arayüz ve sesli asistan bunu kullanır)."""
        g = canonical(g)
        comp = self.components(g)
        us, suit, weak, first = self.utilities(g, comp)
        n = len(us)
        m = sum(us) / n
        sd = math.sqrt(sum((u - m) ** 2 for u in us) / max(1, n - 1))
        su = sorted(us)
        sm = sorted(suit)
        ns = len(sm)
        mean_def = sum(self.t.W[c][(r * self.L + k) % self.t.D] for r in range(self.runs)
                       for k, c in enumerate(comp["crops"])) / (self.runs * self.L)
        verim = sum(suit) / ns / 100
        return dict(genom=g, ekinler=comp["names"], ortu=comp["covers"], ortu_uygun=comp["cover_ok"],
                    puan=round(m, 1), sd=round(sd, 1), p10=round(su[int(.1 * n)], 1),
                    p90=round(su[min(n - 1, int(.9 * n))], 1), fitness=round(m - self.lam * sd, 2),
                    uygunluk=round(sum(suit) / ns, 1), uygunluk_p10=round(sm[int(.1 * ns)], 1),
                    uygunluk_p90=round(sm[min(ns - 1, int(.9 * ns))], 1),
                    zayif_yil=round(weak, 3), ilk_yil=round(sum(first) / len(first), 1),
                    su_acigi=round(mean_def), cakisma=comp["conflicts"],
                    bilesen=dict(verim=round(verim, 3),
                                 su=round(clamp(1 - mean_def * self.water_k / 600.0), 3),
                                 toprak=round(comp["toprak"], 3), erozyon=round(comp["erozyon"], 3),
                                 cesitlilik=round(comp["cesitlilik"], 3), pazar=round(comp["pazar"], 3)),
                    azot=round(comp["soil_n"], 2), organik=round(comp["om"], 2),
                    hastalik=round(comp["pest"], 2), ciplak_ay=round(comp["bare"], 1),
                    ero_idx=round(comp["ero_idx"], 3),
                    n_baglanan=round(sum(max(0, TRAITS[n]["n"]) for n in comp["names"])
                                     + 0.4 * sum(comp["covers"]), 2),
                    n_tuketilen=round(sum(max(0, -TRAITS[n]["n"]) for n in comp["names"]), 2),
                    takvim=[(self.t.crops[v] if isinstance(v, int) else v) for v in comp["occ"]],
                    ekim=[tp.MONTHS[self.t.sow[c]] for c in comp["crops"]])

    def neighbors_random(self, g, rnd):
        L = self.L
        g = list(g)
        mv = rnd.random()
        if mv < 0.55:
            g[rnd.randrange(L)] = rnd.randrange(self.t.n)
        elif mv < 0.80:
            k = rnd.randrange(L)
            g[L + k] = 1 - g[L + k]
        else:
            i, j = rnd.sample(range(L), 2)
            g[i], g[j] = g[j], g[i]
            g[L + i], g[L + j] = g[L + j], g[L + i]
        return tuple(g)


# ================================================================== 4. arama
def decode(x, n, L):
    return tuple(int((v % 1.0) * n) % n for v in x[:L]) + tuple(1 if (v % 1.0) >= 0.5 else 0
                                                             for v in x[L:])


def qpso(prob, particles=30, iters=70, seed=5, log=None):
    """Quantum-behaved PSO (Sun, Feng & Xu 2004), ayrık genoma eşlenmiş sürekli uzayda.

    x_i ← p_i ± β·|mbest − x_i|·ln(1/u),  p_i = φ·pbest_i + (1−φ)·gbest
    β (daralma-genişleme katsayısı) 1,0 → 0,5 doğrusal azalır.
    """
    rnd = random.Random(seed)
    n, L = prob.t.n, prob.L
    D = 2 * L
    # başlangıç: yarısı rastgele, yarısı tek tek iyi ekinlerden (sıcak başlangıç)
    good = sorted(range(n), key=lambda i: -prob.t.mean[i])[:max(3, n // 3)]
    X = []
    for i in range(particles):
        if i % 2:
            X.append([(rnd.choice(good) + rnd.random()) / n for _ in range(L)]
                     + [rnd.random() for _ in range(L)])
        else:
            X.append([rnd.random() for _ in range(D)])
    P = [list(x) for x in X]
    Pf = [prob.fitness(decode(x, n, L)) for x in X]
    gi = max(range(particles), key=lambda i: Pf[i])
    G, Gf = list(P[gi]), Pf[gi]
    curve = [Gf]
    for it in range(iters):
        beta = 1.0 - 0.5 * it / max(1, iters - 1)
        mbest = [sum(P[i][d] for i in range(particles)) / particles for d in range(D)]
        for i in range(particles):
            for d in range(D):
                phi = rnd.random()
                p = phi * P[i][d] + (1 - phi) * G[d]
                u = max(1e-12, rnd.random())
                step = beta * abs(mbest[d] - X[i][d]) * math.log(1 / u)
                X[i][d] = p + step if rnd.random() < 0.5 else p - step
            f = prob.fitness(decode(X[i], n, L))
            if f > Pf[i]:
                P[i], Pf[i] = list(X[i]), f
                if f > Gf:
                    G, Gf = list(X[i]), f
        curve.append(Gf)
        if log:
            log(("qpso", it, Gf))
    return decode(G, n, L), Gf, curve


def anneal(prob, start, steps=900, T0=3.0, cool=0.993, seed=9):
    """Benzetimli tavlama: Metropolis kabulü, geometrik soğuma."""
    rnd = random.Random(seed)
    cur, cf = start, prob.fitness(start)
    best, bf = cur, cf
    T = T0
    curve = []
    for _ in range(steps):
        nb = prob.neighbors_random(cur, rnd)
        nf = prob.fitness(nb)
        if nf >= cf or rnd.random() < math.exp((nf - cf) / max(1e-6, T)):
            cur, cf = nb, nf
            if cf > bf:
                best, bf = cur, cf
        T *= cool
        curve.append(bf)
    return best, bf, curve


def overlap(a, b, L):
    """İki rotasyonun ortak ekin sayısı (çoklu küme kesişimi)."""
    ca, cb = list(a[:L]), list(b[:L])
    n = 0
    for x in ca:
        if x in cb:
            cb.remove(x)
            n += 1
    return n


def ground_states(prob, first, k=3, seed=21, steps=700):
    """Birbirinden belirgin farklı k "temel durum" (en iyi rotasyon).

    1. durum arama sonucudur. Sonrakiler için tavlama, seçilmiş durumlarla en fazla
    L−2 ortak ekin taşıyacak şekilde ceza eklenmiş fayda üzerinde yeniden çalışır
    (niş / tabu yaklaşımı). Böylece "aynı rotasyonun sırası değişmiş hali" gelmez.
    """
    L = prob.L
    chosen = [canonical(first)]
    rnd = random.Random(seed)
    limit = max(1, L - 2)
    for i in range(1, k):
        def pen(g):
            over = max(overlap(g, c, L) for c in chosen)
            return prob.fitness(g) - 25.0 * max(0, over - limit)
        cand = sorted(prob.cache.items(), key=lambda x: -x[1])
        start = next((g for g, _ in cand if max(overlap(g, c, L) for c in chosen) <= limit), None)
        if start is None:
            start = tuple(rnd.randrange(prob.t.n) for _ in range(L)) + (1,) * L
        cur, cf = start, pen(start)
        best, bf = cur, cf
        T = 3.0
        for _ in range(steps):
            nb = prob.neighbors_random(cur, rnd)
            nf = pen(nb)
            if nf >= cf or rnd.random() < math.exp((nf - cf) / max(1e-6, T)):
                cur, cf = nb, nf
                if cf > bf:
                    best, bf = cur, cf
            T *= 0.993
        g = canonical(best)
        if g in chosen:
            break
        chosen.append(g)
    return chosen


def tags_for(rep, all_reps):
    t = []
    if any(TRAITS[n]["n"] > 0 for n in rep["ekinler"]):
        t.append("Azot bağlayan")
    if any(rep["ortu"]):
        t.append("Örtü bitkili")
    if rep["su_acigi"] <= min(r["su_acigi"] for r in all_reps):
        t.append("Su tasarruflu")
    if rep["uygunluk"] >= max(r["uygunluk"] for r in all_reps):
        t.append("Verim odaklı")
    if rep["bilesen"]["erozyon"] >= max(r["bilesen"]["erozyon"] for r in all_reps):
        t.append("Erozyona dayanıklı")
    return t or ["Dengeli"]


def carbon(rep, L, area_ha=None, price=None):
    """Toprakta tutulan karbon tahmini (t C/ha/yıl) → t CO₂e; aralıklı."""
    cov = sum(rep["ortu"]) / L
    leg = sum(1 for n in rep["ekinler"] if TRAITS[n]["n"] > 0) / L
    res = sum(TRAITS[n]["res"] for n in rep["ekinler"]) / L
    lo = cov * C_COVER[0] + leg * C_LEGUME[0] + C_RESIDUE * (res - 0.5)
    mid = cov * C_COVER[1] + leg * C_LEGUME[1] + C_RESIDUE * (res - 0.5)
    hi = cov * C_COVER[2] + leg * C_LEGUME[2] + C_RESIDUE * (res - 0.5)
    out = dict(c_ha=(round(lo, 3), round(mid, 3), round(hi, 3)),
               co2_ha=tuple(round(v * CO2_PER_C, 2) for v in (lo, mid, hi)))
    if area_ha:
        out["co2_tarla"] = tuple(round(v * CO2_PER_C * area_ha, 1) for v in (lo, mid, hi))
        if price:
            out["deger"] = tuple(round(v * CO2_PER_C * area_ha * price) for v in (lo, mid, hi))
    return out


def explain_strategy(rep, cur, prob, harm=None, live=True):
    """Neden önerildi / kanıt / riskler / bilgi boşlukları (sade Türkçe)."""
    why, risk, gaps = [], [], []
    sources = []
    climate_source = "NASA POWER · iklim modeli" if live else "Örnek iklim · model"
    b, bc = rep["bilesen"], cur["bilesen"]
    before, after = cur["ekinler"], rep["ekinler"]
    added = Counter(after) - Counter(before)
    replacement = next(((old, new) for old, new in zip(before, after)
                        if TRAITS[old]["n"] <= 0 < TRAITS[new]["n"] and added[new]), None)
    if rep["azot"] > cur["azot"] and replacement:
        old, new = replacement
        why.append(f"Azot desteği. Bu sırada {old} yerine {new} ekiliyor. "
                   "Baklagiller köklerindeki bakterilerle havadaki azotu bağlar. Bitki artıkları "
                   "ayrıştıkça azotun bir kısmı sonraki ürüne kalabilir. "
                   f"Modelde azot dengesi {cur['azot'] * 100:.0f} → {rep['azot'] * 100:.0f}/100.")
        sources.append("Ekin özellikleri · ekim nöbeti modeli · USDA NRCS")
    elif rep["azot"] > cur["azot"]:
        why.append(f"Azot dengesi. Modelde bu sıranın azot puanı "
                   f"{cur['azot'] * 100:.0f} → {rep['azot'] * 100:.0f}/100. Hesap, her ürünün "
                   "azot katkısını veya tüketimini ve araya eklenen örtüyü birlikte değerlendirir.")
        sources.append("Ekin özellikleri · ekim nöbeti modeli")
    if rep["ciplak_ay"] < cur["ciplak_ay"] or b["erozyon"] > bc["erozyon"] + 0.02:
        cover_crops = list(dict.fromkeys(crop for crop, cover in zip(after, rep["ortu"]) if cover))
        if cover_crops:
            cover_context = ", ".join(cover_crops)
            protection = (f"Hasattan sonra kışlık örtü ekleniyor ({cover_context}). "
                          "Örtü, yağmurun toprağı taşıma riskini azaltmaya yardımcı olur.")
        else:
            protection = ("Yeni ekim takvimi, yağışlı aylarda toprağı daha çok örter."
                          if b["erozyon"] > bc["erozyon"] + 0.02
                          else "Yeni ekim takvimi tarlanın yıl içinde daha uzun süre örtülü kalmasını sağlar.")
        why.append(f"Toprağı koruma. {protection} Yılda açık kalan süre "
                   f"{_c(cur['ciplak_ay'])} → {_c(rep['ciplak_ay'])} ay. "
                   f"Toprağı koruma puanı {bc['erozyon'] * 100:.0f} → {b['erozyon'] * 100:.0f}/100.")
        terrain = "Copernicus DEM" if prob.slope_pct is not None else "düz arazi varsayımı"
        rain = climate_source.split(" · ")[0]
        if "gpm" in (harm or {}).get("girilen", ()):
            rain += " + GPM"
        sources.append(f"Ekim takvimi · {rain} · {terrain}")
    if b["toprak"] > bc["toprak"] + 0.02:
        why.append(f"Toprak sağlığı puanı {bc['toprak'] * 100:.0f} → {b['toprak'] * 100:.0f}/100. "
                   "Bu puan azot dengesini, tarlada kalan bitki artıklarını ve benzer ürünlerin "
                   "arka arkaya ekilip ekilmediğini birlikte değerlendirir.")
        sources.append("Ekin özellikleri · ekim nöbeti modeli")
    if rep["su_acigi"] < cur["su_acigi"] - 10:
        why.append(f"Sezon su açığı ortalama {cur['su_acigi']} → {rep['su_acigi']} mm. "
                   "Hesap, ekinlerin su ihtiyacını ve yetişme dönemindeki yağışı karşılaştırır.")
        sources.append(climate_source + " · ekin su ihtiyacı")
    if rep["hastalik"] > cur["hastalik"] + 0.02:
        why.append("Ürün tekrarı azalıyor. Benzer ürünler arka arkaya ekildiğinde aynı "
                   "zararlılar veya hastalıklar sonraki üründe de görülebilir.")
        sources.append("Ekin grupları · ekim nöbeti modeli")
    if rep["uygunluk"] > cur["uygunluk"] + 1:
        why.append(f"İklim uygunluğu ortalama {cur['uygunluk']:.0f} → {rep['uygunluk']:.0f}/100. "
                   "Ekinlerin yetişme koşulları bölgenin iklimiyle karşılaştırılır.")
        sources.append(climate_source + " · ekin eşikleri")
    if not why:
        why.append("Hesap, ekin uygunluğu, su açığı, toprak sağlığı ve çeşitliliği seçili hedefe göre tartar.")
        sources.append("Rotasyon modeli · seçili hedef")
    ev = [f"{n}: {prob.t.mean[prob.t.crops.index(n)]:.0f}/100 iklim uygunluğu, ekim {m}"
          for n, m in zip(rep["ekinler"], rep["ekim"])]
    if rep["zayif_yil"] > 0.25:
        risk.append(f"Olası yılların %{rep['zayif_yil'] * 100:.0f}'inde en az bir ekin zayıf kalıyor.")
    if rep["cakisma"]:
        risk.append("Ekim-hasat takvimi sıkışık: bir ekin hasat edilmeden diğerinin ekim zamanı "
                    "geliyor; erkenci çeşit veya ekim kaydırma gerekir.")
    if rep["su_acigi"] > 200 and not prob.sulama:
        risk.append(f"Sulamasız tarlada ≈{rep['su_acigi']} mm su açığı.")
    if any(rep["ortu"]):
        risk.append("Kışlık örtü de su kullanır. Model örtü başına yaklaşık 40 mm kabul eder. "
                    "Kurak yıllarda örtüyü ne zaman kaldıracağınızı toprak nemine göre belirleyin.")
    if rep["ilk_yil"] < cur["ilk_yil"] - 5:
        risk.append(f"Geçiş yılı: ilk ekinin uygunluğu {cur['ilk_yil']:.0f} → {rep['ilk_yil']:.0f}.")
    gaps.append("İklim verisi ~50 km'lik NASA POWER hücresinden; tarla içi farklar yansımaz.")
    if harm and "grace" not in harm.get("girilen", []):
        gaps.append("Yeraltı suyu eğilimi (GRACE) girilmedi; uzun vadeli kuraklık eksik olabilir.")
    if harm and "smap" not in harm.get("girilen", []):
        gaps.append("Toprak nemi model verisi (GWETROOT); SMAP ölçümü girilirse güven artar.")
    if prob.slope_pct is None:
        gaps.append("Eğim bilinmiyor; erozyon düz arazi varsayımıyla hesaplandı.")
    gaps.append("Pazar göstergesi ekin grubuna göre varsayımdır; yerel fiyat ve alıcı bilgisi gerekir.")
    if any(TRAITS[n]["n"] > 0 for n in rep["ekinler"]):
        gaps.append("Baklagillerde aşılama (rhizobium) ve tohum bulunabilirliği yerelde doğrulanmalı.")
    return dict(neden=why, neden_kaynak=sources, kanit=ev, risk=risk, bosluk=gaps)


def confidence(live, history_ok, harm):
    n = len((harm or {}).get("girilen", []))
    if not live:
        return "Düşük", "Örnek veri kullanılıyor (NASA canlı verisi değil)."
    if history_ok and n >= 2:
        return "Yüksek", f"NASA POWER canlı + 2001–2024 gerçek yıllar + {n} uydu ölçümü."
    if history_ok:
        return "Orta", "NASA POWER canlı + 2001–2024 gerçek yıllar; uydu ölçümü girilmedi."
    return "Orta-düşük", "NASA POWER canlı; geçmiş seri alınamadı, değişkenlik varsayımdan."


def optimize(clim, sulama=False, soil=None, history=None, lat=None, L=3, prio=None,
             dT=0.0, dP=0.0, sat=None, slope_pct=None, current=None, area_ha=None,
             price=None, live=True, seed=5, particles=30, iters=70, sa_steps=900,
             table=None, log=None):
    """Tüm akış: harmonizasyon → Monte Carlo → QPSO → tavlama → en iyi 3 + mevcut."""
    t0 = time.perf_counter()
    # senaryo (ya … olursa?) iklime baştan uygulanır: matris, su bilançosu ve Monte Carlo
    # aynı kaydırılmış iklimi görür
    harm = harmonize(_shift(clim, dT, dP, 0.3 * dP) if (dT or dP) else clim, lat, soil, sat)
    if table is None:
        table = Table(harm["iklim"], sulama, soil, history, 0.0, 0.0)
    t_tab = time.perf_counter() - t0
    prob = Problem(table, L, prio, harm["erozivite"], slope_pct, soil, sulama,
                   water_k=harm["su_katsayi"])
    g_q, f_q, curve_q = qpso(prob, particles, iters, seed, log)
    g_a, f_a, curve_a = anneal(prob, g_q, sa_steps, seed=seed + 4)
    best = ground_states(prob, g_a, 3, seed=seed + 16)
    reps = [prob.report(g) for g in best]
    # mevcut rotasyon
    if current:
        cur_names = [n for n in current if n in table.crops][:L]
        while len(cur_names) < L:
            cur_names.append(cur_names[-1] if cur_names else table.crops[0])
    else:
        cur_names = (["Kışlık buğday"] * (L - 1) + ["Ayçiçeği"])
    cg = tuple(table.crops.index(n) for n in cur_names) + (0,) * L
    cur = prob.report(cg)
    cur["ekinler_girilen"] = cur_names
    for r in reps:
        r["etiket"] = tags_for(r, reps + [cur])
        r["aciklama"] = explain_strategy(r, cur, prob, harm, live=live)
        r["karbon"] = carbon(r, L, area_ha, price)
        r["fark"] = round(r["puan"] - cur["puan"], 1)
    cur["karbon"] = carbon(cur, L, area_ha, price)
    cur["etiket"] = ["Mevcut"]
    for r in reps:
        r["karbon_ek"] = tuple(round(a - b, 2) for a, b in zip(r["karbon"]["co2_ha"],
                                                               cur["karbon"]["co2_ha"]))
    conf = confidence(live, bool((history or {}).get("yillar")), harm)
    return dict(stratejiler=reps, mevcut=cur, harmonizasyon=harm, L=L,
                arama=dict(uzay=prob.space, degerlendirme=prob.evals,
                           oran=round(prob.evals / prob.space * 100, 2),
                           sure=round(time.perf_counter() - t0, 2), tablo_sure=round(t_tab, 2),
                           qpso=curve_q, tavlama=curve_a, qpso_en_iyi=round(f_q, 2),
                           tavlama_en_iyi=round(f_a, 2), parcacik=particles, iterasyon=iters,
                           mc_yil=table.D, mc_kosu=prob.runs, yontem=table.method),
                agirlik={k: round(v, 3) for k, v in prob.w.items()}, lam=round(prob.lam, 2),
                guven=conf, senaryo=dict(dT=dT, dP=dP), problem=prob, tablo=table)


def verify_bruteforce(prob, progress=None):
    """Tüm kombinasyonları tek tek tara (yalnızca küçük arama uzayında anlamlı)."""
    t0 = time.perf_counter()
    n, L = prob.t.n, prob.L
    best, bf, count = None, -1e9, 0
    done = set()
    total = n ** L
    for i, crops in enumerate(itertools.product(range(n), repeat=L)):
        for cov in itertools.product((0, 1), repeat=L):
            g = canonical(crops + cov)
            if g in done:
                continue
            done.add(g)
            count += 1
            f = prob.fitness(g)
            if f > bf:
                best, bf = g, f
        if progress and i % 200 == 0:
            progress(i / total)
    return dict(en_iyi=best, fitness=round(bf, 2), sayi=count,
                sure=round(time.perf_counter() - t0, 1))


# ================================================================== 5. parseller
def _clip(poly, xmin, xmax, ymin, ymax):
    """Sutherland–Hodgman: çokgeni dikdörtgenle kırp. Noktalar (x, y)."""
    def inside(p, e):
        x, y = p
        return (x >= xmin, x <= xmax, y >= ymin, y <= ymax)[e]

    def inter(a, b, e):
        (x1, y1), (x2, y2) = a, b
        if e < 2:
            xe = xmin if e == 0 else xmax
            t = (xe - x1) / ((x2 - x1) or 1e-12)
            return (xe, y1 + t * (y2 - y1))
        ye = ymin if e == 2 else ymax
        t = (ye - y1) / ((y2 - y1) or 1e-12)
        return (x1 + t * (x2 - x1), ye)

    out = list(poly)
    for e in range(4):
        if not out:
            break
        inp, out = out, []
        for i, cur in enumerate(inp):
            prev = inp[i - 1]
            if inside(cur, e):
                if not inside(prev, e):
                    out.append(inter(prev, cur, e))
                out.append(cur)
            elif inside(prev, e):
                out.append(inter(prev, cur, e))
    return out


def _area(poly):
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1]
                   for i in range(len(poly)))) / 2


def parcel_grid(width_m, height_m):
    """Tarla büyüklüğüne ve biçimine göre parsel ızgarası (nx, ny).

    Hedef parsel sayısı alanla artar (2-9); ızgara tarlanın uzun kenarı boyunca açılır.
    """
    area_ha = max(0.0, width_m * height_m) / 10000.0
    n = 2 if area_ha < 3 else 4 if area_ha < 12 else 6 if area_ha < 40 else 9
    aspect = (width_m / height_m) if height_m > 0 else 1.0
    best = None
    for nx in (1, 2, 3):                  # en çok 3×3: parsel adları (kuzeybatı…) tekil kalır
        for ny in (1, 2, 3):
            if nx * ny < 2:
                continue
            score = 2.0 * abs(nx * ny - n) + abs(math.log((nx / ny) / max(1e-6, aspect)))
            if best is None or score < best[0]:
                best = (score, nx, ny)
    return best[1], best[2]


def _direction(fx, fy):
    """fx: batı(0)→doğu(1), fy: güney(0)→kuzey(1) -> 'kuzeybatı', 'merkez' ..."""
    ns = "kuzey" if fy > 0.62 else "güney" if fy < 0.38 else ""
    ew = "doğu" if fx > 0.62 else "batı" if fx < 0.38 else ""
    return (ns + ew) or "merkez"


def make_parcels(field=None, lat=None, lon=None, nx=None, ny=None):
    """Tarla poligonunu parsellere böl. Tarla yoksa merkezde 600 m'lik kare varsayılır.

    nx/ny verilmezse parsel sayısı tarlanın alanına ve en-boy oranına göre seçilir
    (parcel_grid). Dönen: ([{ad, poly [[lat, lon]...], lat, lon, pay, yon}], şematik_mi)
    """
    if field and len(field.get("noktalar") or []) >= 3:
        pts = [(p[1], p[0]) for p in field["noktalar"]]           # (x=lon, y=lat)
        schematic = False
    else:
        la = lat if lat is not None else (field or {}).get("lat", 39.0)
        lo = lon if lon is not None else (field or {}).get("lon", 32.0)
        d_la = 300 / 111195.0
        d_lo = 300 / (111195.0 * max(0.2, math.cos(math.radians(la))))
        pts = [(lo - d_lo, la + d_la), (lo + d_lo, la + d_la), (lo + d_lo, la - d_la),
               (lo - d_lo, la - d_la)]
        schematic = True
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if nx is None or ny is None:
        k = math.cos(math.radians((y0 + y1) / 2))
        gx, gy = parcel_grid((x1 - x0) * 111195.0 * k, (y1 - y0) * 111195.0)
        nx, ny = nx or gx, ny or gy
    total = _area(pts) or 1e-12
    out = []
    for j in range(ny):                       # kuzeyden güneye
        for i in range(nx):                   # batıdan doğuya
            cx0 = x0 + (x1 - x0) * i / nx
            cx1 = x0 + (x1 - x0) * (i + 1) / nx
            cy1 = y1 - (y1 - y0) * j / ny
            cy0 = y1 - (y1 - y0) * (j + 1) / ny
            poly = _clip(pts, cx0, cx1, cy0, cy1)
            if len(poly) < 3:
                continue
            a = _area(poly)
            if a / total < 0.04:
                continue
            cx = sum(p[0] for p in poly) / len(poly)
            cy = sum(p[1] for p in poly) / len(poly)
            fx = (cx - x0) / ((x1 - x0) or 1e-12)
            fy = (cy - y0) / ((y1 - y0) or 1e-12)
            out.append(dict(poly=[[round(p[1], 6), round(p[0], 6)] for p in poly],
                            lat=round(cy, 6), lon=round(cx, 6), pay=round(a / total, 3),
                            yon=_direction(fx, fy)))
    for k, p in enumerate(out, 1):
        p["ad"] = f"Parsel {k}"
    return out, schematic


def _join(names):
    return ", ".join(names[:-1]) + " ve " + names[-1] if len(names) > 1 else names[0]


def parcel_advice(parcel, res, harm, slope=None):
    """Sesli asistanın okuyacağı kısa metin (parsel bazlı)."""
    best = res["stratejiler"][0]
    rows = {r["key"]: r for r in harm["satirlar"]}
    nem = rows["nem"]["deger"]
    m_nem = max(range(12), key=lambda m: nem[m])
    isi = rows["isi"]["deger"]
    m_isi = max(range(12), key=lambda m: isi[m])
    parts = [f"{parcel['ad']}, {parcel['yon']} bölümüne girdiniz."]
    if slope is not None:
        lvl = "yüksek" if slope >= 8 else "orta" if slope >= 3 else "düşük"
        parts.append(f"Eğim yüzde {slope:.0f}".replace(".", ",") + f", erozyon riski {lvl}.")
    if nem[m_nem] >= 0.6:
        parts.append(f"Toprak nemi {tp.MONTHS[m_nem]} ayında kritik eşiğe iniyor.")
    if isi[m_isi] >= 0.5:
        parts.append(f"{tp.MONTHS[m_isi]} ayında ısı stresi yüksek.")
    parts.append("Önerilen rotasyon: " + _join(best["ekinler"]) + ".")
    nc = sum(best["ortu"])
    if nc == len(best["ortu"]):
        parts.append("Her hasattan sonra kışlık örtü bitkisi ekin; toprak kışın çıplak kalmasın.")
    elif nc:
        after = [n for n, cv in zip(best["ekinler"], best["ortu"]) if cv]
        parts.append(_join(after) + " hasadından sonra kışlık örtü bitkisi ekin.")
    parts.append(f"Uygunluk {best['puan']:.0f}, artı eksi {best['sd']:.0f} puan.")
    if best["aciklama"]["neden"]:
        parts.append(best["aciklama"]["neden"][0])
    parts.append("Son karar sizin; yerel ziraat mühendisinize danışın.")
    return " ".join(parts)


def summary_lines(res):
    """AI asistan bağlamı için kısa metin satırları."""
    a = res["arama"]
    L = [f"  Yöntem: QPSO + benzetimli tavlama (klasik bilgisayar), {a['uzay']:,} kombinasyonun "
         f"{a['degerlendirme']:,}'i değerlendirildi; Monte Carlo {a['mc_yil']} olası yıl "
         f"({'NASA POWER gerçek yıllar' if a['yontem'] == 'gecmis' else 'parametrik'}).",
         f"  Senaryo: yağış {res['senaryo']['dP'] * 100:+.0f}%, sıcaklık {res['senaryo']['dT']:+.1f} °C; "
         f"güven: {res['guven'][0]} ({res['guven'][1]})"]
    cur = res["mevcut"]
    L.append(f"  Mevcut: {' → '.join(cur['ekinler'])} — {cur['puan']} ± {cur['sd']}")
    for i, r in enumerate(res["stratejiler"], 1):
        seq = " → ".join(n + (" (+örtü)" if c else "") for n, c in zip(r["ekinler"], r["ortu"]))
        co2 = r["karbon"]["co2_ha"][1]
        L.append(f"  {i}. [{', '.join(r['etiket'])}] {seq} — {r['puan']} ± {r['sd']} "
                 f"(mevcuda göre {r['fark']:+.1f}); su açığı {r['su_acigi']} mm; zayıf yıl "
                 f"%{r['zayif_yil'] * 100:.0f}; karbon ≈{co2} t CO2e/ha/yıl")
        if r["aciklama"]["neden"]:
            L.append("     neden: " + r["aciklama"]["neden"][0])
    return L


# ================================================================== 6. entropi · kapalı döngü
# Tarla, kapalı döngü yaşam destek sistemi gibi ele alınır: su, azot ve karbon döngüde kalmalı.
# "Entropi" burada fiziksel termodinamik entropi DEĞİL; toprağın düzensizlik/bozulma
# eğilimini özetleyen 0-100 bir göstergedir (yüksek = kayıp ve tükenme fazla).
ENTROPY_W = dict(azot=0.25, organik=0.20, erozyon=0.20, biyolojik=0.15, su=0.20)
ENTROPY_LABELS = dict(azot="Azot kaybı", organik="Organik madde tükenmesi",
                      erozyon="Erozyon / çıplak toprak", biyolojik="Monokültür / hastalık döngüsü",
                      su="Su dengesizliği")


def entropy(rep):
    """Bir rotasyon raporundan entropi göstergesi ve bileşenleri (0-100)."""
    b = rep["bilesen"]
    parts = {
        "azot": clamp(0.7 * (1 - rep["azot"]) + 0.3 * clamp(rep["ero_idx"] * 1.5)),
        "organik": 1 - rep["organik"],
        "erozyon": 1 - b["erozyon"],
        "biyolojik": clamp(0.6 * (1 - rep["hastalik"]) + 0.4 * (1 - b["cesitlilik"])),
        "su": 1 - b["su"],
    }
    S = 100 * sum(ENTROPY_W[k] * v for k, v in parts.items())
    return {"S": round(S, 1), "parcalar": {k: round(v * 100, 1) for k, v in parts.items()}}


def stability(rep, ent):
    """Ekosistem kararlılık indeksi (model): düşük entropi + düşük yıllar arası oynaklık."""
    return round(clamp((100 - ent["S"]) / 100 * (1 - rep["sd"] / 40.0)) * 100, 1)


def closed_loop(rep, harm, L):
    """Kapalı döngü bilançosu: girdi / çıktı (yıllık, göreli)."""
    c = harm["iklim"]
    P = sum(c["Pm"])
    et0 = sum(harm["et0"])
    cover_frac = clamp(1 - rep["ciplak_ay"] / 12.0)
    kb = rep["karbon"]["c_ha"][1]
    water = ('Yağış, havanın oluşturduğu tahmini su kaybını karşılamıyor → kurak dönemde su açığı oluşabilir. '
             'Bu fark doğrudan sulama miktarı değildir; ürün ve toprak nemiyle birlikte değerlendirin.'
             if P < et0 else
             'Yıllık yağış tahmini su kaybını karşılıyor → yıllık açık görünmüyor. Yağışın mevsimi nedeniyle yazın yine sulama gerekebilir.')
    nd = rep['n_baglanan'] - rep['n_tuketilen']
    nitrogen = ('Baklagil ve örtü katkısı modelde tüketimden fazla → sonraki ürünün azot ihtiyacına destek olabilir. '
                if nd > 0 else 'Ürünlerin azot tüketimi modelde katkıdan fazla → besin desteği ihtiyacını toprak analiziyle kontrol edin. '
                if nd < 0 else 'Modelde azot katkısı ve tüketimi eşit → net değişim görünmüyor. ')
    nitrogen += 'Bu göreli puan kg gübre değildir; gübre azaltma miktarını söylemez.'
    carbon_note = ('Örtü, baklagil ve bitki artığı varsayımları modelde karbon artışı veriyor → organik yapının güçlenmesine katkı olabilir. '
                   if kb > 0 else 'Modelde bitki artığı katkısı yeterli görünmüyor → organik madde kaybı riski var. '
                   if kb < 0 else 'Modelde net karbon değişimi sıfır → artış veya azalış öngörülmüyor. ')
    carbon_note += 'Bu bir tahmindir; toprak ölçümü değildir. Giren ve çıkan sütunları net değişimin yönünü gösterir.'
    return {
        "su": dict(giris=round(P), cikis=round(et0), birim="mm/yıl",
                   denge=round(P - et0), not_=water,
                   kaynak='İklim girdisi + FAO-56 Hargreaves hesabı; referans yüzey, ürüne özgü tüketim değil.'),
        "azot": dict(giris=rep["n_baglanan"], cikis=rep["n_tuketilen"], birim="göreli birim / tüm plan",
                     denge=round(rep["n_baglanan"] - rep["n_tuketilen"], 2),
                     not_=nitrogen, kaynak='Proje varsayımı: ürün ve örtü azot katsayıları; saha ölçümü yok.'),
        "karbon": dict(giris=round(max(0.0, kb), 2), cikis=round(max(0.0, -kb), 2),
                       birim="t C/ha/yıl", denge=round(kb, 2),
                       not_=carbon_note, kaynak='Poeplau & Don (2015) örtü katsayısı + proje baklagil/artık varsayımları.'),
        "ortu": dict(oran=round(cover_frac * 100), birim="%",
                     not_=(f"Takvime göre yılın %{round(cover_frac * 100)} bölümünde toprak örtülü → "
                           'örtü suyun toprağa girmesine ve erozyonun azalmasına yardımcı olabilir. '
                           'Bu oran uyduyla ölçülmedi; erozyonun tamamen önlendiği anlamına gelmez.'),
                     kaynak='Seçili ekim takvimi: (12 − çıplak ay) / 12. Genel dayanak: USDA NRCS örtü bitkileri.'),
    }


def mission_payload(res, harm, parcels, per_parcel, slopes, history=None, field=None):
    """Mission Control paneli için tek JSON."""
    L = res["L"]
    reps = [res["mevcut"]] + res["stratejiler"]
    rows = {r["key"]: r for r in harm["satirlar"]}
    grow = tp.GROW_SEASON
    heat = max(rows["isi"]["deger"])
    wdef = sum(rows["su"]["deger"][m] for m in grow) / len(grow)
    # Nem anomalisi: NASA POWER geçmiş serisinin son yılı (yetişme dönemi) — gerçek gözlem
    anom, anom_year = None, None
    yl = (history or {}).get("yillar") or []
    if yl:
        last = yl[-1]
        anom = sum(last["GW"][m] for m in grow) / len(grow)
        anom_year = last["yil"]
    bio = harm["biyokutle"]
    strategies = []
    cur_S = None
    for i, r in enumerate(reps):
        ent = entropy(r)
        if i == 0:
            cur_S = ent["S"]
        strategies.append(dict(
            ad="Mevcut rotasyon" if i == 0 else f"Strateji {i}", etiket=r["etiket"],
            ekinler=r["ekinler"], ortu=r["ortu"], ekim=r["ekim"], puan=r["puan"], sd=r["sd"],
            p10=r["p10"], p90=r["p90"], entropi=ent, kararlilik=stability(r, ent),
            azalma=None if i == 0 or not cur_S else round((cur_S - ent["S"]) / cur_S * 100, 1),
            su_acigi=r["su_acigi"], zayif_yil=r["zayif_yil"], ciplak_ay=r["ciplak_ay"],
            karbon=r["karbon"]["co2_ha"], dongu=closed_loop(r, harm, L),
            neden=(r.get("aciklama") or {}).get("neden", [])[:3],
            neden_kaynak=(r.get("aciklama") or {}).get("neden_kaynak", [])[:3],
            risk=(r.get("aciklama") or {}).get("risk", [])[:2],
            bosluk=(r.get("aciklama") or {}).get("bosluk", [])[:3]))
    out_parcels = []
    for p in parcels:
        pr = (per_parcel or {}).get(p["ad"], res)
        sl = slopes.get(p["ad"])
        slope_f = clamp((sl or 0) / 15.0)
        termo = clamp(0.40 * heat + 0.40 * wdef + 0.20 * slope_f)
        nem = None if anom is None else anom - 0.004 * (sl or 0)
        preps = [pr["mevcut"]] + pr["stratejiler"]
        azot = [entropy(x)["parcalar"]["azot"] for x in preps]
        while len(azot) < len(reps):
            azot.append(azot[-1])
        warn = []
        if termo >= 0.55:
            warn.append("termodinamik stres yüksek")
        if sl is not None and sl >= 8:
            warn.append(f"eğim %{sl:.0f}: erozyon")
        if nem is not None and nem <= -0.03:
            warn.append("nem anomalisi negatif")
        out_parcels.append(dict(
            ad=p["ad"], yon=p["yon"], poly=p["poly"], lat=p["lat"], lon=p["lon"],
            egim=None if sl is None else round(sl, 1),
            katman=dict(termo=round(termo * 100), azot=[round(a) for a in azot],
                        nem=None if nem is None else round(nem * 100, 1), gedi=bio["karbon"]),
            uyari=warn))
    a = res["arama"]
    return dict(
        strateji=strategies, parseller=out_parcels,
        nem_yili=anom_year, biyokutle=bio, kalibrasyon=harm["kalibrasyon"],
        bitki_stresi=harm.get("bitki_stresi"), su_katsayi=harm.get("su_katsayi"),
        aylik=dict(su=[round(v, 2) for v in rows["su"]["deger"]],
                   isi=[round(v, 2) for v in rows["isi"]["deger"]],
                   nem=[round(v, 2) for v in rows["nem"]["deger"]]),
        arama=dict(uzay=a["uzay"], degerlendirme=a["degerlendirme"], sure=a["sure"],
                   oran=a["oran"], mc=a["mc_kosu"], yontem=a["yontem"]),
        guven=res["guven"], senaryo=res["senaryo"], L=L,
        agirlik=ENTROPY_W, etiketler=ENTROPY_LABELS)


# ================================================================== komut satırı
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Kuantum-esinli rotasyon optimizasyonu")
    ap.add_argument("--yil", type=int, default=3)
    ap.add_argument("--kuraklik", type=float, default=0.0, help="yağış değişimi, ör. -0.3")
    ap.add_argument("--isinma", type=float, default=0.0, help="°C")
    ap.add_argument("--dogrula", action="store_true", help="tam tarama ile doğrula (yalnızca 3 yıl)")
    a = ap.parse_args()
    soil = tp.soil_for("Konya")
    res = optimize(tp.DEMO, soil=soil, lat=37.87, L=a.yil, dT=a.isinma, dP=a.kuraklik, live=False)
    s = res["arama"]
    print(f"Arama uzayı {s['uzay']:,} · değerlendirilen {s['degerlendirme']:,} "
          f"(%{s['oran']}) · {s['sure']} sn")
    cur = res["mevcut"]
    print(f"\nMevcut  {' → '.join(cur['ekinler']):<50} {cur['puan']:5.1f} ± {cur['sd']}")
    for r in res["stratejiler"]:
        seq = " → ".join(n + ("+örtü" if c else "") for n, c in zip(r["ekinler"], r["ortu"]))
        print(f"{'/'.join(r['etiket']):<30} {seq:<50} {r['puan']:5.1f} ± {r['sd']} "
              f"(fitness {r['fitness']})")
    if a.dogrula and a.yil == 3:
        v = verify_bruteforce(res["problem"])
        print(f"\nTam tarama: {v['sayi']:,} benzersiz rotasyon, {v['sure']} sn, en iyi fitness "
              f"{v['fitness']} · QPSO+SA: {res['stratejiler'][0]['fitness']}")


if __name__ == "__main__":
    main()
