#!/usr/bin/env python3
"""Tarla Pusulası — afet ve erozyon riski (v2.8).

Seçilen konum için sade bir risk özeti üretir:
  TOPRAK   erozyon, toprak kayması            -> 0-100 duyarlılık göstergesi
  İKLİM    kuraklık, aşırı yağış, geç don,
           aşırı sıcak                         -> geçmiş yıllardaki görülme sıklığı
  DEPREM   100 km içinde M>=5 deprem           -> 10 yılda en az bir kez olma olasılığı

Veri kaynakları
  • NASA POWER aylık seri (yıllar arası değişkenlik; tarla_pusulasi.fetch_history)
  • Open-Meteo Elevation API (Copernicus DEM, 90 m) -> eğim
  • USGS FDSN deprem kataloğu -> yakın çevredeki geçmiş depremler

DİKKAT: Bunlar resmi afet haritası değildir. Erozyon ve toprak kayması değerleri
olasılık değil, eğim + yağış + toprak dokusundan türetilen göstergedir.
Yalnızca standart kütüphane kullanır.
"""
import json
import math
import random
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import tarla_pusulasi as tp

QUAKE_RADIUS_KM = 100
QUAKE_MIN_MAG = 5.0
QUAKE_START = 1976            # katalog bu tarihten sonra M5+ için dünya genelinde tutarlı
DEM_STEP_M = 90.0             # Copernicus GLO-90 çözünürlüğü
LEVELS = ("Düşük", "Orta", "Yüksek")


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "TarlaPusulasi/2.8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------------------------------------------------------------- veri
def slope_from_grid(z, step=DEM_STEP_M):
    """3×3 yükseklik ızgarası (kuzeyden güneye satırlar) -> eğim (Horn yöntemi)."""
    (a, b, c), (d, e, f), (g, h, i) = z
    dzdx = ((c + 2 * f + i) - (a + 2 * d + g)) / (8 * step)
    dzdy = ((g + 2 * h + i) - (a + 2 * b + c)) / (8 * step)
    rise = math.hypot(dzdx, dzdy)
    flat = [v for row in z for v in row]
    return {"egim_yuzde": round(rise * 100, 1), "egim_derece": round(math.degrees(math.atan(rise)), 1),
            "yukseklik": round(e), "kot_farki": round(max(flat) - min(flat), 1)}


def fetch_slope(lat, lon, step=DEM_STEP_M):
    """Konum çevresindeki 3×3 noktanın yüksekliğinden eğimi hesapla (Open-Meteo / Copernicus DEM)."""
    dlat = step / 111194.9
    dlon = step / (111194.9 * max(0.2, math.cos(math.radians(lat))))
    pts = [(lat + dy * dlat, lon + dx * dlon) for dy in (1, 0, -1) for dx in (-1, 0, 1)]
    url = "https://api.open-meteo.com/v1/elevation?" + urllib.parse.urlencode({
        "latitude": ",".join("%.5f" % p[0] for p in pts),
        "longitude": ",".join("%.5f" % p[1] for p in pts)})
    el = _get(url).get("elevation") or []
    if len(el) != 9 or any(not isinstance(v, (int, float)) or v != v for v in el):
        raise ValueError("Yükseklik verisi eksik.")
    return slope_from_grid([el[0:3], el[3:6], el[6:9]], step)


def fetch_quakes(lat, lon, end_year):
    """USGS kataloğunda yakın çevredeki M>=5 deprem sayısı."""
    url = "https://earthquake.usgs.gov/fdsnws/event/1/count?" + urllib.parse.urlencode({
        "format": "geojson", "latitude": "%.4f" % lat, "longitude": "%.4f" % lon,
        "maxradiuskm": QUAKE_RADIUS_KM, "minmagnitude": QUAKE_MIN_MAG,
        "starttime": "%d-01-01" % QUAKE_START})
    res = _get(url)
    n = res.get("count") if isinstance(res, dict) else res
    if isinstance(n, bool) or not isinstance(n, (int, float)) or n < 0:
        raise ValueError("Deprem sayısı okunamadı.")
    return {"sayi": int(n), "yil": max(1, end_year - QUAKE_START), "yaricap_km": QUAKE_RADIUS_KM,
            "buyukluk": QUAKE_MIN_MAG, "baslangic": QUAKE_START}


def recent_quakes(lat, lon, minimum, since):
    start = datetime.fromtimestamp(since, timezone.utc).isoformat(timespec="seconds")
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query?" + urllib.parse.urlencode({
        "format": "geojson", "latitude": lat, "longitude": lon, "eventtype": "earthquake",
        "maxradiuskm": QUAKE_RADIUS_KM, "minmagnitude": minimum, "starttime": start,
        "orderby": "time-asc",
    })
    features = _get(url, timeout=10)["features"]
    events = []
    for feature in features:
        data = feature["properties"]
        if data["mag"] is not None and data["mag"] >= minimum and data["time"] >= since * 1000:
            events.append((feature["id"], data["mag"], data.get("place") or "USGS", data["time"],
                           data.get("url") or "https://earthquake.usgs.gov/earthquakes/map/"))
    return events


def tomorrow_weather(lat, lon):
    fields = ("temperature_2m_min", "temperature_2m_max", "temperature_2m_mean",
              "precipitation_probability_max", "rain_sum", "showers_sum", "wind_gusts_10m_max")
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode({
        "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 2,
        "daily": ",".join(fields),
    })
    daily = _get(url, timeout=10)["daily"]
    values = {key: daily[key][1] for key in fields}
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values.values()):
        raise ValueError("Yarın için hava verisi eksik.")
    return daily["time"][1], values


# ---------------------------------------------------------------- yardımcı
def level_of(score, lo=25, hi=50):
    return 0 if score < lo else 1 if score < hi else 2


def _clamp01(x):
    return min(1.0, max(0.0, x))


def fournier(climate):
    """Değiştirilmiş Fournier indeksi: Σ(aylık yağış²) / yıllık yağış. Yağışın aşındırma gücü."""
    total = sum(climate["Pm"])
    return sum(p * p for p in climate["Pm"]) / total if total > 0 else 0.0


def _years(climate, history, dT=0.0, dP=0.0, dGW=0.0, y=0, n_synth=400, seed=7):
    """Olası yıllar: geçmiş yılların sapmaları (varsa) ya da parametrik örnekler."""
    pool = (history or {}).get("yillar") or []
    if not pool:
        rnd = random.Random(seed)
        pool = [tp._synthetic_anomaly(rnd) for _ in range(n_synth)]
    return [tp._apply(climate, an, dT, dP, dGW, y) for an in pool]


# Her iklim olayı: (anahtar, ad, ölçüt açıklaması, yıl -> bool)
def _climate_events(climate):
    normal = sum(climate["Pm"])
    return [
        ("kuraklik", "Kuraklık", "yıllık yağışın normalin %75'inin altında kaldığı yıllar",
         lambda c: sum(c["Pm"]) < 0.75 * normal),
        ("asiri_yagis", "Aşırı yağış / sel", "bir ayda normalin 2 katından ve 100 mm'den fazla yağış",
         lambda c: any(c["Pm"][m] > 100 and c["Pm"][m] > 2 * climate["Pm"][m] for m in range(12))),
        ("gec_don", "Geç don", "Nisan gece sıcaklığı ortalamasının 3 °C'nin altına indiği yıllar",
         lambda c: c["Tmin"][3] < 3.0),
        ("asiri_sicak", "Aşırı sıcak", "en sıcak ayın ortalamasının 27 °C'yi geçtiği yıllar",
         lambda c: max(c["T"]) >= 27.0),
    ]


# ---------------------------------------------------------------- değerlendirme
def assess(climate, soil, history=None, slope=None, quakes=None, years=10):
    """Tüm riskleri hesapla. Dönen liste arayüzde sırayla gösterilir.

    Her öğe: {anahtar, grup, ad, duzey (0-2), oran (0-1, çubuk), deger (büyük yazı),
              aciklama, kaynak, [gelecek]}
    """
    out = []
    mfi = fournier(climate)
    f_rain = _clamp01((mfi - 30) / 130.0)                 # 30 çok düşük … 160 çok yüksek
    silt = max(0, 100 - soil["clay"] - soil["sand"])
    f_soil = _clamp01(0.7 * silt / 60.0 + 0.3 * (1 - _clamp01(soil["soc"] / 3.0)))
    wettest = max(climate["Pm"])

    # --- erozyon (su erozyonu): eğim baskın, yağış ve toprak dokusu çarpan
    if slope:
        f_slope = _clamp01(slope["egim_yuzde"] / 20.0) ** 0.8
        ero = 100 * f_slope * (0.35 + 0.40 * f_rain + 0.25 * f_soil)
        out.append({"anahtar": "erozyon", "grup": "Toprak", "ad": "Erozyon (su)",
                    "duzey": level_of(ero), "oran": ero / 100, "deger": f"{ero:.0f} / 100",
                    "aciklama": f"Eğim %{slope['egim_yuzde']:.1f}".replace(".", ",")
                                + f" · yağışın aşındırma gücü {('düşük', 'orta', 'yüksek')[level_of(f_rain * 100, 33, 66)]}"
                                + f" · toprak {('dayanıklı', 'orta', 'hassas')[level_of(f_soil * 100, 40, 60)]}",
                    "kaynak": "Copernicus DEM 90 m + NASA POWER yağış + toprak profili · gösterge"})
        # --- toprak kayması: eğim olmadan olmaz; ıslak ay ve kil payı artırır
        f_s = _clamp01((slope["egim_derece"] - 3) / 22.0)
        f_w = _clamp01((wettest - 40) / 160.0)
        f_c = _clamp01((soil["clay"] - 20) / 30.0)
        land = 100 * f_s * (0.50 + 0.35 * f_w + 0.15 * f_c)
        out.append({"anahtar": "heyelan", "grup": "Toprak", "ad": "Toprak kayması (heyelan)",
                    "duzey": level_of(land), "oran": land / 100, "deger": f"{land:.0f} / 100",
                    "aciklama": f"Eğim {slope['egim_derece']:.1f}°".replace(".", ",")
                                + f" · en yağışlı ay {wettest:.0f} mm · kil %{soil['clay']}"
                                + (" · düz arazide beklenmez" if slope["egim_derece"] < 3 else ""),
                    "kaynak": "Copernicus DEM 90 m + NASA POWER yağış + toprak profili · gösterge"})
    else:
        for key, name in (("erozyon", "Erozyon (su)"), ("heyelan", "Toprak kayması (heyelan)")):
            out.append({"anahtar": key, "grup": "Toprak", "ad": name, "duzey": None, "oran": 0.0,
                        "deger": "veri yok",
                        "aciklama": "Eğim verisi alınamadı (internet ya da konum gerekli); "
                                    "eğim olmadan bu risk hesaplanmaz.",
                        "kaynak": "Copernicus DEM 90 m"})

    # --- iklim olayları: görülme sıklığı (bugün ve orta senaryoda 10. yıl)
    today = _years(climate, history)
    _, dT, dP, dGW = tp.SCENARIOS[1]
    future = _years(climate, history, dT, dP, dGW, years)
    basis = (f"NASA POWER {history['baslangic']}–{history['bitis']} ({len(history['yillar'])} yıl)"
             if history and history.get("yillar") else "parametrik değişkenlik (geçmiş seri yok)")
    for key, name, rule, test in _climate_events(climate):
        p = sum(1 for c in today if test(c)) / len(today)
        pf = sum(1 for c in future if test(c)) / len(future)
        n10 = int(round(p * 10))
        out.append({"anahtar": key, "grup": "İklim", "ad": name,
                    "duzey": 0 if p < 0.10 else 1 if p < 0.30 else 2, "oran": p,
                    "deger": ("10 yılda ~%d yıl" % n10) if n10 else "10 yılda 1'den az",
                    "olasilik": round(p, 3), "gelecek": round(pf, 3),
                    "aciklama": rule[0].upper() + rule[1:],
                    "kaynak": basis + " · sıklık"})

    # --- deprem: Poisson, yıllık oran = katalogdaki sayı / yıl
    if quakes:
        rate = quakes["sayi"] / float(quakes["yil"])
        p10 = 1 - math.exp(-rate * years)
        out.append({"anahtar": "deprem", "grup": "Deprem",
                    "ad": f"Yakında M{quakes['buyukluk']:.0f}+ deprem",
                    "duzey": 0 if p10 < 0.10 else 1 if p10 < 0.40 else 2, "oran": p10,
                    "deger": f"%{p10 * 100:.0f}", "olasilik": round(p10, 3),
                    "aciklama": f"{years} yılda en az bir kez olma olasılığı · {quakes['yaricap_km']} km "
                                f"içinde {quakes['baslangic']}'dan beri {quakes['sayi']} kayıt",
                    "kaynak": "USGS deprem kataloğu · geçmiş sıklıktan olasılık"})
    else:
        out.append({"anahtar": "deprem", "grup": "Deprem", "ad": "Yakında M5+ deprem",
                    "duzey": None, "oran": 0.0, "deger": "veri yok",
                    "aciklama": "Deprem kataloğuna ulaşılamadı (internet ya da konum gerekli).",
                    "kaynak": "USGS deprem kataloğu"})
    return out


def headline(risks):
    """En yüksek riskin tek cümlelik özeti."""
    known = [r for r in risks if r["duzey"] is not None]
    if not known:
        return "Risk verisi alınamadı."
    top = max(known, key=lambda r: (r["duzey"], r["oran"]))
    if top["duzey"] == 0:
        return "Bu konumda öne çıkan bir risk görünmüyor; tüm göstergeler düşük."
    highs = [r["ad"] for r in known if r["duzey"] == top["duzey"]]
    return f"Öne çıkan risk: {', '.join(highs[:3])} ({LEVELS[top['duzey']].lower()})."


def summary_lines(risks):
    """AI asistan bağlamı için kısa metin satırları."""
    out = []
    for r in risks:
        lvl = "veri yok" if r["duzey"] is None else LEVELS[r["duzey"]]
        extra = ""
        if "gelecek" in r:
            extra = f"; bugün %{r['olasilik'] * 100:.0f}/yıl, 10 yıl sonra (orta senaryo) %{r['gelecek'] * 100:.0f}/yıl"
        out.append(f"  {r['ad']}: {lvl} — {r['deger']}{extra} ({r['aciklama']})")
    return out
