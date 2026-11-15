#!/usr/bin/env python3
"""Tarla Pusulası — Deep-Space Planetary Digital Twin (termodinamik ve besin dengeleme ikizi).

NASA'nın uzay habitatlarındaki kapalı döngü yaşam destek (CELSS) mantığı tarlaya
uygulanır: su, azot ve karbon döngüde kalmalı; kaçaklar "entropi göstergesi" ile izlenir.
Her parsel için:

  • mevcut rotasyonun azot kaybı, entropi göstergesi, çıplak toprak ayları, kök derinliği
  • DERİN KÖKLÜ BAKLAGİL müdahalesi (nohut + uygun yıllarda kışlık örtü) ile aynı sayılar
  • sızma (infiltrasyon) kapasitesi ve su tutma kapasitesinin 3 yıllık seyri

Veri
  MODIS NDVI  : ORNL DAAC MODIS Web Service, MOD13Q1 250 m (anahtarsız, canlı)
  GEDI        : kullanıcı girerse (Mg/ha); yoksa SoilGrids toprak karbonu vekil
  GRACE       : kullanıcı girerse (cm/yıl); yoksa NASA POWER kök bölgesi nemi eğilimi vekil
  Toprak      : SoilGrids bölgesel profil (kum, kil, organik karbon)
  İklim/eğim  : NASA POWER (optimizer) + Copernicus DEM (parsel eğimi)

Yöntem ve varsayımlar (ekranda da yazılır)
  Su tutma (AWC) ve doygun iletkenlik : Saxton & Rawls (2006) pedotransfer denklemleri
  Organik madde değişimi              : rotasyonun karbon girdisi (optimizer.carbon) / 0-30 cm toprak kütlesi
  Sızma artışı                        : Basche & DeLonge (2019) meta-analizi — örtü bitkisi ort. +%35;
                                        model bunu kazanılan örtülü ay sayısıyla orantılar. Derin kök
                                        kanalları için en çok +%10 ek etki VARSAYIMDIR.
  Kök derinliği                       : FAO-56 Tablo 22 (en çok etkili kök derinliği aralıkları)
  Entropi                              : fiziksel entropi değil; bozulma/kayıp eğilimi göstergesi (0-100)

Yalnızca standart kütüphane kullanır.
"""
import datetime as _dt
import json
import math
import urllib.parse
import urllib.request
from functools import lru_cache

import tarla_optimizer as to
import tarla_pusulasi as tp

DEEP_LEGUME = "Nohut"
YEARS = 3
SOIL_MASS_T_HA = 3900.0           # 0-30 cm, hacim ağırlığı 1,3 g/cm³
LAYER_MM = 300.0
COVER_INFIL = 0.35                # Basche & DeLonge 2019: örtü bitkisi sızma artışı (ortalama)
ROOT_INFIL_MAX = 0.10             # varsayım: derin kök kanalları
RAMP = (0.0, 0.40, 0.75, 1.0)     # etkinin yıllara yayılışı (varsayım)

# FAO-56 Tablo 22: en çok etkili kök derinliği (m), (alt, üst)
ROOT_DEPTH = {
    "Kışlık buğday": (1.5, 1.8), "Arpa": (1.0, 1.5), "Mısır": (1.0, 1.7), "Pamuk": (1.0, 1.7),
    "Ayçiçeği": (0.8, 1.5), "Şeker pancarı": (0.7, 1.2), "Patates": (0.4, 0.6),
    "Domates": (0.7, 1.5), "Pirinç": (0.5, 1.0), "Nohut": (0.6, 1.0), "Mercimek": (0.6, 0.8),
    "Karpuz": (0.8, 1.5), "Kuru soğan": (0.3, 0.6), "Biber": (0.5, 1.0), "Hıyar": (0.7, 1.2),
    "Kavun": (0.8, 1.5), "Kuru fasulye": (0.6, 0.9), "Yulaf": (1.0, 1.5), "Çavdar": (1.0, 1.5),
    "Kanola": (1.0, 1.5), "Soya": (0.6, 1.3), "Yer fıstığı": (0.5, 1.0), "Tütün": (0.5, 1.0),
    "Susam": (1.0, 1.5), "Patlıcan": (0.7, 1.2), "Lahana": (0.5, 0.8), "Havuç": (0.5, 1.0),
    "Ispanak": (0.3, 0.5), "Sarımsak": (0.3, 0.5),
    "Kabak": (0.6, 1.0), "Marul": (0.3, 0.5), "Karnabahar": (0.4, 0.7), "Bezelye": (0.6, 1.0),
    "Bakla": (0.5, 0.7), "Sorgum": (1.0, 2.0), "Tritikale": (1.0, 1.5),
}
COVER_ROOT = (0.6, 1.0)           # fiğ + tahıl karışımı (yaklaşık)


def _clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def root_mid(name):
    lo, hi = ROOT_DEPTH.get(name, (0.6, 1.0))
    return (lo + hi) / 2


# ------------------------------------------------------------------ toprak fiziği
def saxton_rawls(sand, clay, om):
    """Saxton & Rawls (2006). sand, clay: %; om: organik madde %.

    Dönen: θ33 (tarla kapasitesi), θ1500 (solma noktası), AWC (hacimsel), Ksat (mm/sa).
    """
    S, C, OM = sand / 100.0, clay / 100.0, max(0.0, min(8.0, om))
    t1500t = (-0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM
              + 0.068 * S * C + 0.031)
    t1500 = t1500t + (0.14 * t1500t - 0.02)
    t33t = (-0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM
            + 0.452 * S * C + 0.299)
    t33 = t33t + (1.283 * t33t ** 2 - 0.374 * t33t - 0.015)
    ts33t = (0.278 * S + 0.034 * C + 0.022 * OM - 0.018 * S * OM - 0.027 * C * OM
             - 0.584 * S * C + 0.078)
    ts33 = ts33t + (0.636 * ts33t - 0.107)
    ts = t33 + ts33 - 0.097 * S + 0.043
    B = (math.log(1500) - math.log(33)) / (math.log(t33) - math.log(t1500))
    lam = 1.0 / B
    ksat = 1930.0 * max(1e-6, ts - t33) ** (3 - lam)
    return dict(t33=t33, t1500=t1500, awc=t33 - t1500, ksat=ksat, ts=ts)


# ------------------------------------------------------------------ NASA verileri
def _modis_date(d):
    return "A%d%03d" % (d.year, d.timetuple().tm_yday)


def fetch_ndvi(lat, lon, days=160, timeout=12):
    """MODIS MOD13Q1 NDVI (250 m, 16 günlük) — ORNL DAAC Web Service, anahtarsız.

    Tek isteğe en çok 10 tarih sığar; son ~160 gün istenir.
    Dönen: {son, tarih, ortalama, en_yuksek, seri[(tarih, ndvi)], kaynak}
    """
    end = _dt.date.today()
    start = end - _dt.timedelta(days=days)
    return _fetch_ndvi(round(lat, 5), round(lon, 5), start, end, timeout)


@lru_cache(maxsize=128)
def _fetch_ndvi(lat, lon, start, end, timeout):
    base = "https://modis.ornl.gov/rst/api/v1/MOD13Q1/"
    coords = {"latitude": lat, "longitude": lon}
    dates = tp.http_json(base + "dates?" + urllib.parse.urlencode(coords), timeout, 1)
    available = sorted(row["modis_date"] for row in dates["dates"]
                       if _modis_date(start) <= row["modis_date"] <= _modis_date(end))[-10:]
    if not available:
        raise ValueError("Bu dönem için MODIS görüntüsü bulunamadı.")
    query = dict(coords, startDate=available[0], endDate=available[-1],
                 kmAboveBelow=0, kmLeftRight=0)
    data = tp.http_json(base + "subset?" + urllib.parse.urlencode(query), timeout, 1)
    return parse_ndvi(data)


def satellite_inputs(manual, field, lat, lon, live):
    """Elle girilen NDVI değerini korur, aksi halde MODIS konum serisini kullanır."""
    sat = dict(manual or {})
    ndvi = None
    if live and "ndvi" not in sat:
        if field:
            lat, lon = field["lat"], field["lon"]
        try:
            ndvi = fetch_ndvi(lat, lon)
        except (OSError, KeyError, TypeError, ValueError):
            return sat, None
        sat["ndvi"] = ndvi["ortalama"]
        sat["ndvi_source"] = ndvi["kaynak"]
    return sat, ndvi


def parse_ndvi(data):
    rows = (data or {}).get("subset") or []
    try:
        scale = float(data.get("scale") or 0.0001)
    except (TypeError, ValueError):
        scale = 0.0001
    if scale <= 0 or scale > 1:
        scale = 0.0001
    quality = {row.get("modis_date"): row.get("data") or []
               for row in rows if str(row.get("band", "")).lower().endswith("pixel_reliability")}
    seri = []
    for row in rows:
        if not str(row.get("band", "")).lower().endswith("_ndvi"):
            continue
        flags = quality.get(row.get("modis_date"))
        vals = [v for i, v in enumerate(row.get("data") or [])
                if isinstance(v, (int, float)) and -2000 <= v <= 10000
                and (flags is None or (i < len(flags) and flags[i] == 0))]
        if not vals:
            continue
        v = sum(vals) / len(vals) * scale
        if -0.2 <= v <= 1.0:
            seri.append((str(row.get("calendar_date") or row.get("modis_date") or ""), round(v, 3)))
    if not seri:
        raise ValueError("NDVI verisi boş döndü.")
    seri.sort()
    vals = [v for _, v in seri]
    return dict(son=vals[-1], tarih=seri[-1][0], ortalama=round(sum(vals) / len(vals), 3),
                en_yuksek=max(vals), seri=seri, kaynak="MODIS MOD13Q1 250 m · ORNL DAAC")


def water_trend(history):
    """GRACE yokken vekil: NASA POWER kök bölgesi nemi (yetişme dönemi) eğilimi, 10 yıllık."""
    yl = (history or {}).get("yillar") or []
    if len(yl) < 8:
        return None
    grow = tp.GROW_SEASON
    xs = [y["yil"] for y in yl]
    ys = [sum(y["GW"][m] for m in grow) / len(grow) for y in yl]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs) or 1.0
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return round(slope * 10 * 100, 2)     # ıslaklık puanı / 10 yıl


def data_status(sat, ndvi, history, soil):
    """Ekrandaki üç NASA veri satırı: ölçülen / girilen / vekil."""
    out = []
    if ndvi:
        out.append(dict(ad="MODIS NDVI", durum="canlı", deger=f"{ndvi['son']:.2f}",
                        aciklama=f"son 16 günlük ({ndvi['tarih']}) · dönem ort. {ndvi['ortalama']:.2f}"))
    elif sat.get("ndvi"):
        out.append(dict(ad="Landsat/MODIS NDVI", durum="girildi", deger=f"{sat['ndvi']:.2f}",
                        aciklama="kullanıcı girdisi"))
    else:
        out.append(dict(ad="MODIS NDVI", durum="yok", deger="—",
                        aciklama="alınamadı (internet gerekli)"))
    if sat.get("gedi"):
        out.append(dict(ad="GEDI biyokütle", durum="girildi", deger=f"{sat['gedi']:.0f} Mg/ha",
                        aciklama=f"üst katman karbon ≈{sat['gedi'] * 0.47:.0f} t C/ha"))
    else:
        stok = soil["soc"] / 100 * SOIL_MASS_T_HA
        out.append(dict(ad="GEDI biyokütle", durum="vekil", deger=f"{stok:.0f} t C/ha",
                        aciklama="girilmedi → SoilGrids 0-30 cm toprak karbonu"))
    if sat.get("grace") is not None and "grace" in sat:
        out.append(dict(ad="GRACE su rezervi", durum="girildi", deger=f"{sat['grace']:+.1f} cm/yıl",
                        aciklama="karasal su depolama eğilimi"))
    else:
        tr = water_trend(history)
        out.append(dict(ad="GRACE su rezervi", durum="vekil",
                        deger="—" if tr is None else f"{tr:+.1f} puan/10 yıl",
                        aciklama="girilmedi → NASA POWER kök bölgesi nemi eğilimi"
                        if tr is not None else "girilmedi; geçmiş seri de yok"))
    return out


# ------------------------------------------------------------------ müdahale
def _genome(prob, names, covers):
    idx = tuple(prob.t.crops.index(n) for n in names)
    return idx + tuple(1 if c else 0 for c in covers)


def intervention(prob, cur):
    """Mevcut rotasyonun bir yılına derin köklü baklagil koy; uygun yıllara kışlık örtü ekle.

    En düşük entropiyi veren yıl seçilir; uygunluk puanı 6'dan fazla düşmesin.
    """
    if DEEP_LEGUME not in prob.t.crops:
        return None, None
    L = prob.L
    names = list(cur["ekinler"])
    best, best_k, loose = None, None, None
    for k in range(L):
        trial = names[:k] + [DEEP_LEGUME] + names[k + 1:]
        for cover_all in (True, False):
            g = _genome(prob, trial, [cover_all] * L)
            rep = prob.report(g)
            S = to.entropy(rep)["S"]
            if loose is None or S < loose[0]:
                loose = (S, rep, k)
            if rep["puan"] < cur["puan"] - 6:
                continue
            if best is None or S < best[0] - 1e-9:
                best, best_k = (S, rep), k
    if best is None:                  # puan şartı sağlanamadı: en düşük entropiyi yine göster
        return loose[1], loose[2]
    return best[1], best_k


def _covered_months(rep):
    return 12.0 - rep["ciplak_ay"]


def _deep_share(rep, L):
    return sum(1 for n in rep["ekinler"] if root_mid(n) >= 1.0) / L


def soil_track(soil, rep, L):
    """Rotasyonun 0..YEARS yıl boyunca organik madde, su tutma ve doygun iletkenlik seyri."""
    c_ha = to.carbon(rep, L)["c_ha"][1]           # t C/ha/yıl (orta tahmin)
    om0 = soil["soc"] * 1.72
    out = []
    for y in range(YEARS + 1):
        soc = soil["soc"] + c_ha * y / SOIL_MASS_T_HA * 100
        sr = saxton_rawls(soil["sand"], soil["clay"], soc * 1.72)
        out.append(dict(yil=y, om=round(soc * 1.72, 3), awc_mm=round(sr["awc"] * LAYER_MM, 2),
                        ksat=round(sr["ksat"], 2)))
    return out, c_ha, om0


def parcel_twin(parcel, prob, cur, soil, slope=None):
    """Bir parselin ikizi: mevcut / müdahale karşılaştırması ve 3 yıllık seyir."""
    L = prob.L
    new, k = intervention(prob, cur)
    if new is None:     # nohut bu bölgede aday değilse müdahale kurulamaz (entropy(None) çökmesin)
        raise ValueError(f"{DEEP_LEGUME} bu konum için aday ekinler arasında değil; "
                         "derin köklü baklagil müdahalesi hesaplanamadı.")
    e0, e1 = to.entropy(cur), to.entropy(new)
    tr0, c0, om0 = soil_track(soil, cur, L)
    tr1, c1, _ = soil_track(soil, new, L)
    d_cov = max(0.0, _covered_months(new) - _covered_months(cur))
    d_deep = max(0.0, _deep_share(new, L) - _deep_share(cur, L))
    gain = COVER_INFIL * min(1.0, d_cov / 5.0) + ROOT_INFIL_MAX * min(1.0, d_deep * 2)
    base_k = tr0[0]["ksat"]
    infil = [dict(yil=y, ksat=round(base_k * (1 + gain * RAMP[y]), 2),
                  artis=round(gain * RAMP[y] * 100, 1)) for y in range(YEARS + 1)]
    S0, S1 = e0["S"], e1["S"]
    ent_drop = round((S0 - S1) / S0 * 100, 1) if S0 > 0 else 0.0
    ent_curve = [round(S0 + (S1 - S0) * RAMP[y], 1) for y in range(YEARS + 1)]

    def roots(rep):
        out = []
        for n, cv in zip(rep["ekinler"], rep["ortu"]):
            lo, hi = ROOT_DEPTH.get(n, (0.6, 1.0))
            out.append(dict(ekin=n, alt=lo, ust=hi, ortu=bool(cv)))
        return out

    def side(rep, ent, track, c_ha):
        return dict(ekinler=rep["ekinler"], ortu=rep["ortu"], puan=rep["puan"],
                    entropi=ent["S"], parcalar=ent["parcalar"], azot_kaybi=ent["parcalar"]["azot"],
                    ciplak_ay=rep["ciplak_ay"], n_giris=rep["n_baglanan"],
                    n_cikis=rep["n_tuketilen"], karbon=round(c_ha, 3),
                    takvim=rep["takvim"], kok=roots(rep), seyir=track,
                    kok_cesitlilik=round(_spread([root_mid(n) for n in rep["ekinler"]]), 2))

    awc0, awc3 = tr0[0]["awc_mm"], tr1[-1]["awc_mm"]
    return dict(
        ad=parcel["ad"], yon=parcel["yon"], poly=parcel["poly"], lat=parcel["lat"],
        lon=parcel["lon"], egim=None if slope is None else round(slope, 1),
        yerine=cur["ekinler"][k],
        mevcut=side(cur, e0, tr0, c0), oneri=side(new, e1, tr1, c1),
        entropi_azalma=ent_drop, entropi_seyir=ent_curve, sizma=infil,
        sizma_artis=round(gain * 100, 1), awc_degisim=round(awc3 - awc0, 2),
        ciplak_azalma=round(cur["ciplak_ay"] - new["ciplak_ay"], 1),
        puan_degisim=round(new["puan"] - cur["puan"], 1))


def _spread(xs):
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def message(pt, L):
    """Çiftçiye okunacak tek paragraf (sayıların hepsi modelden)."""
    m, o = pt["mevcut"], pt["oneri"]
    rot = " → ".join(m["ekinler"])
    parts = [f"{pt['ad']} ({pt['yon']}): mevcut rotasyonda ({rot}) azot kaybı göstergesi "
             f"%{m['azot_kaybi']:.0f}, toprak yılda {m['ciplak_ay']:.0f} ay çıplak kalıyor."]
    add = f"Rotasyondaki bir {pt['yerine']} yılı yerine derin köklü baklagil ({DEEP_LEGUME.lower()})"
    if any(o["ortu"]):
        add += " ve hasat sonrası kışlık örtü"
    if pt["entropi_azalma"] > 0:
        parts.append(f"{add} eklenirse entropi göstergesi %{pt['entropi_azalma']:.0f} azalır, "
                     f"azot kaybı %{m['azot_kaybi']:.0f} → %{o['azot_kaybi']:.0f}"
                     + (f", çıplak ay {m['ciplak_ay']:.0f} → {o['ciplak_ay']:.0f}" if
                        pt["ciplak_azalma"] >= 0.5 else "") + ".")
    else:
        parts.append(f"{add} bu parselde entropiyi belirgin düşürmüyor; mevcut düzen dengeli.")
    if pt["sizma_artis"] >= 1:
        parts.append(f"Suyun toprağa sızma kapasitesi {YEARS} yılda yaklaşık %{pt['sizma_artis']:.0f} "
                     "artar (örtü ve kök kanalları).")
    awc = f"{pt['awc_degisim']:+.2f}".replace(".", ",")
    parts.append(f"Su tutma kapasitesi yavaş değişir: {YEARS} yılda {awc} mm (0-30 cm).")
    if pt["puan_degisim"] < -1:
        parts.append(f"Uygunluk puanı {abs(pt['puan_degisim']):.0f} puan düşer; denge karşılığı.")
    return " ".join(parts)


def build(res, per_parcel, parcels, slopes, soil, sat=None, ndvi=None, history=None):
    """İkiz paneli için tüm veri."""
    sat = sat or {}
    L = res["L"]
    out = []
    for p in parcels:
        r = (per_parcel or {}).get(p["ad"], res)
        prob = r["problem"]
        cur = prob.report(r["mevcut"]["genom"])
        pt = parcel_twin(p, prob, cur, soil, slopes.get(p["ad"]))
        pt["mesaj"] = message(pt, L)
        out.append(pt)
    best = max(out, key=lambda x: (x["entropi_azalma"], x["sizma_artis"])) if out else None
    sr = saxton_rawls(soil["sand"], soil["clay"], soil["soc"] * 1.72)
    harm = res["harmonizasyon"]
    c = harm["iklim"]
    return dict(
        parseller=out, en_iyi=best["ad"] if best else None, L=L,
        toprak=dict(etiket=soil["label"], kum=soil["sand"], kil=soil["clay"], soc=soil["soc"],
                    awc_mm=round(sr["awc"] * LAYER_MM, 1), ksat=round(sr["ksat"], 1)),
        veri=data_status(sat, ndvi, history, soil),
        dongu=dict(yagis=round(sum(c["Pm"])), et0=round(sum(harm["et0"]))),
        ndvi=ndvi)
