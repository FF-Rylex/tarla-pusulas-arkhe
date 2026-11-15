#!/usr/bin/env python3
"""Tarla Pusulası — Mission Control: gezegen ölçeğinde dijital ikiz paneli (v3.1).

Tarlayı, NASA'nın Artemis / Mars görevlerindeki kapalı döngü yaşam destek sistemleri
(CELSS) mantığıyla ele alır: su, azot ve karbon döngüde kalmalı; kayıp ve tükenme
"entropi göstergesi" ile izlenir. Tarayıcıda açılan tek sayfa:

  ÜST BAR   proje + modül adı, UTC saat, veri akışı durumu, kararlılık indeksi, koordinat
  SOL %55   uydu haritası + parseller; katmanlar: termodinamik stres, azot sızıntısı,
            nem anomalisi, biyokütle/karbon; NASA GIBS SMAP kök nemi ve MODIS NDVI
            döşemeleri; kritik parsellerde yanıp sönen uyarı pinleri
  SAĞ %45   rotasyon stratejileri; entropi ibresi; kapalı döngü bilançosu

Bütün sayılar tarla_optimizer'dan hesaplanır; panelde sabit (uydurma) değer yoktur.
Sunucu: tarla_harita.MapServer (yalnızca 127.0.0.1, oturum anahtarlı).
"""
import json
import threading
import time

import tarla_optimizer as to
import tarla_pusulasi as tp
import tarla_risk
import tarla_ikiz
from tarla_toprak import SOIL_LAYER_JS

VERSION = "v3.1"


class MissionControl:
    """Uygulamanın o anki tarla durumunu tutar ve panel isteklerini hesaplar."""

    def __init__(self, server):
        self.server = server
        self.state = None
        self._lock = threading.Lock()
        server.get_routes["/mc"] = self._page
        server.post_routes["/api/mc"] = self._api

    def set_state(self, **kw):
        """kw: clim, irr, soil, hist, lat, lon, live, field, name, sat, prio, current, area_ha"""
        old = self.state or {}
        same = (old.get("lat"), old.get("lon"), old.get("field")) == \
               (kw.get("lat"), kw.get("lon"), kw.get("field"))
        kw["slopes"] = old.get("slopes", {}) if same else {}
        kw["hist_tried"] = old.get("hist_tried", False) if same else False
        kw["satellite"] = old.get("satellite") if same and old.get("sat") == kw.get("sat") else None
        self.state = kw

    def url(self):
        return self.server.page_url("/mc")

    # ---------------------------------------------------------------- uçlar
    def _page(self):
        st = self.state or {}
        field = dict(center=[st.get("lat", 39), st.get("lon", 35)],
                     boundary=(st.get("field") or {}).get("noktalar") or [])
        return "text/html; charset=utf-8", PAGE.replace("__TOKEN__", self.server.token) \
            .replace("__VERSION__", VERSION).replace("__SOIL_LAYER__", SOIL_LAYER_JS) \
            .replace("__FIELD__", json.dumps(field)).encode("utf-8")

    def _api(self, body):
        if not self.state:
            return {"ok": False, "hata": "Önce uygulamada konum analizi yapın."}
        with self._lock:                      # aynı anda tek hesap
            return compute(self.state, body or {})


def _num(body, key, default, lo, hi):
    try:
        v = float(body.get(key, default))
    except (TypeError, ValueError):
        v = default
    return min(hi, max(lo, v))


def compute(st, body):
    t0 = time.perf_counter()
    dP = _num(body, "dP", 0, -60, 30) / 100.0
    risk = _num(body, "risk", 50, 0, 100) / 100.0
    L = 4 if int(_num(body, "L", 3, 3, 4)) == 4 else 3
    prio = dict(st.get("prio") or {})
    prio["risk"] = risk
    # geçmiş seri (bir kez dene)
    if st.get("live") and not st.get("hist") and not st.get("hist_tried"):
        st["hist_tried"] = True
        try:
            st["hist"] = tp.fetch_history(st["lat"], st["lon"])
        except Exception:
            st["hist"] = None
    if st.get("satellite") is None:
        st["satellite"], _ = tarla_ikiz.satellite_inputs(
            st.get("sat"), st.get("field"), st.get("lat"), st.get("lon"), st.get("live"))
    sat = st["satellite"]
    parcels, schematic = to.make_parcels(st.get("field"), st.get("lat"), st.get("lon"))
    slopes = st["slopes"]
    for p in parcels:                         # parsel eğimleri (Copernicus DEM, önbellekli)
        if p["ad"] not in slopes:
            sl = None
            if st.get("live"):
                try:
                    sl = tarla_risk.fetch_slope(p["lat"], p["lon"])["egim_yuzde"]
                except Exception:
                    sl = None
            slopes[p["ad"]] = sl
    known = [v for v in slopes.values() if v is not None]
    field_slope = sum(known) / len(known) if known else None
    cur = list(st.get("current") or [])
    res = to.optimize(st["clim"], st["irr"], st["soil"], st.get("hist"), st.get("lat"),
                      L=L, prio=prio, dP=dP, sat=sat,
                      slope_pct=field_slope, current=cur or None, area_ha=st.get("area_ha"),
                      live=st.get("live", False))
    per = {}
    for p in parcels:
        sl = slopes.get(p["ad"])
        if sl is not None:
            per[p["ad"]] = to.optimize(
                st["clim"], st["irr"], st["soil"], st.get("hist"), st.get("lat"), L=L, prio=prio,
                dP=dP, sat=sat, slope_pct=sl, current=cur or None,
                table=res["tablo"], live=st.get("live", False),
                particles=16, iters=30, sa_steps=300)
    pay = to.mission_payload(res, res["harmonizasyon"], parcels, per, slopes,
                             st.get("hist"), st.get("field"))
    pay.update(ok=True, ad=st.get("name"), lat=st.get("lat"), lon=st.get("lon"),
               canli=bool(st.get("live")), sematik=schematic,
               alan_ha=st.get("area_ha"), hesap_sn=round(time.perf_counter() - t0, 2),
               egim_var=bool(known),
               girdi=dict(dP=round(dP * 100), risk=round(risk * 100), L=L))
    return json.loads(json.dumps(pay, default=lambda o: list(o) if isinstance(o, tuple) else str(o)))


PAGE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tarla Takip Paneli</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root { --bg:#05080a; --panel:#0a1014; --panel2:#0e161b; --line:#18242b; --line2:#22323b;
          --fg:#e8f1f2; --fg2:#b9c8cc; --mut:#6f858c; --acc:#5cf2c4; --acc2:#1f9e7c;
          --cyan:#5cc8f2; --gold:#f2c35c; --bad:#f2706a; --mono: "Cascadia Mono", "Consolas",
          "JetBrains Mono", "SFMono-Regular", monospace; }
  * { box-sizing: border-box; }
  html, body { height:100%; margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.45 "Segoe UI", system-ui, -apple-system, Roboto, sans-serif; }
  .mono { font-family: var(--mono); letter-spacing:.02em; }
  header { height:58px; display:flex; align-items:center; gap:18px; padding:0 18px;
    border-bottom:1px solid var(--line); background:linear-gradient(#0a1116,#070b0e); }
  .logo { display:flex; align-items:center; gap:10px; }
  .logo svg { width:26px; height:26px; }
  .brand { font-family:var(--mono); font-weight:700; font-size:14px; letter-spacing:.08em; }
  .brand small { color:var(--mut); font-weight:500; letter-spacing:.06em; }
  .tele { margin-left:auto; display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }
  .t { border:1px solid var(--line2); border-radius:8px; padding:5px 10px; font-family:var(--mono);
    font-size:12px; color:var(--fg2); white-space:nowrap; background:#0a1217; }
  .t b { color:var(--fg); font-weight:600; }
  .dot { display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:6px;
    background:var(--acc); box-shadow:0 0 8px var(--acc); vertical-align:1px; }
  .dot.off { background:var(--gold); box-shadow:0 0 8px var(--gold); }
  .dot.busy { animation: blink .7s infinite alternate; background:var(--cyan); box-shadow:0 0 8px var(--cyan); }
  @keyframes blink { to { opacity:.25; } }
  main { display:grid; grid-template-columns: 55fr 45fr; gap:14px; padding:14px;
    height: calc(100% - 58px); }
  .col { min-height:0; display:flex; flex-direction:column; gap:12px; }
  .right { overflow:auto; padding-right:4px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:14px 16px; }
  .ttl { font-family:var(--mono); font-size:11px; letter-spacing:.12em; color:var(--mut);
    text-transform:uppercase; margin:0 0 10px; display:flex; justify-content:space-between; gap:8px; }
  .ttl span:last-child { color:var(--mut); letter-spacing:.04em; text-transform:none; }
  #mapWrap { position:relative; flex:1; min-height:360px; border-radius:14px; overflow:hidden;
    border:1px solid var(--line); }
  #map { position:absolute; inset:0; background:#060a0c; }
  .leaflet-container { font:inherit; background:#060a0c; }
  .ovl { position:absolute; z-index:500; }
  .layers { top:12px; left:12px; display:flex; flex-wrap:wrap; gap:6px; max-width:calc(100% - 24px); }
  .seg { border:1px solid var(--line2); background:rgba(6,11,14,.86); color:var(--fg2);
    border-radius:9px; padding:7px 11px; font:600 12px var(--mono); cursor:pointer;
    backdrop-filter: blur(6px); }
  .seg.on { color:#04130e; background:var(--acc); border-color:var(--acc); }
  .seg.tile.on { background:var(--cyan); border-color:var(--cyan); }
  .legend { bottom:12px; left:12px; background:rgba(6,11,14,.88); border:1px solid var(--line2);
    border-radius:10px; padding:9px 12px; font:12px var(--mono); color:var(--fg2); max-width:340px;
    backdrop-filter: blur(6px); }
  .ramp { height:8px; border-radius:4px; margin:6px 0 4px; }
  #soilLegend { max-width:min(320px,calc(100% - 72px)); }
  .soil-key { display:flex; align-items:flex-start; gap:10px; margin-top:6px; }
  #soilScale { display:block; background:#fff; border-radius:4px; }
  #soilScale[hidden] { display:none; }
  .soil-scale { max-height:160px; overflow:auto; flex-shrink:0; }
  #soilLegend label { display:block; margin:6px 0; }
  #soilOpacity { display:block; width:100%; accent-color:var(--acc); }
  #soilStatus { margin-top:6px; }
  .note { color:var(--mut); font-size:12px; }
  .pin { width:18px; height:18px; border-radius:50%; background:var(--bad);
    box-shadow:0 0 0 0 rgba(242,112,106,.7); animation:pulse 1.6s infinite; border:2px solid #fff3; }
  @keyframes pulse { 70% { box-shadow:0 0 0 16px rgba(242,112,106,0); } 100% { box-shadow:0 0 0 0 rgba(242,112,106,0);} }
  .lbl { background:rgba(6,11,14,.85) !important; color:var(--fg) !important; border:1px solid var(--line2) !important;
    border-radius:8px !important; font:600 12px var(--mono) !important; box-shadow:none !important; padding:3px 7px !important; }
  .lbl:before { display:none; }
  .strip { display:grid; grid-template-columns:repeat(12,1fr); gap:3px; }
  .strip div { height:16px; border-radius:3px; }
  .months { display:grid; grid-template-columns:repeat(12,1fr); gap:3px; font:10px var(--mono); color:var(--mut); text-align:center; margin-top:3px; }
  .row { display:flex; align-items:center; gap:10px; }
  .tabs { display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }
  .tab { border:1px solid var(--line2); background:var(--panel2); color:var(--fg2); border-radius:10px;
    padding:8px 8px; cursor:pointer; text-align:left; font:12px var(--mono); }
  .tab b { display:block; font-size:18px; color:var(--fg); }
  .tab.on { border-color:var(--acc); box-shadow: inset 0 0 0 1px var(--acc); }
  .gaugeWrap { display:grid; grid-template-columns: 230px 1fr; gap:14px; align-items:center; }
  .bar { height:7px; border-radius:4px; background:var(--line2); overflow:hidden; }
  .bar i { display:block; height:100%; border-radius:4px; transition: width .6s ease; }
  .kv { display:grid; grid-template-columns: 1fr auto; gap:4px 10px; font-size:12px; align-items:center; }
  .kv .k { color:var(--fg2); }
  .kv .v { font:600 12px var(--mono); color:var(--fg); }
  .seq { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0; }
  .seq span { border:1px solid var(--line2); border-radius:999px; padding:3px 10px; font:600 12px var(--mono); color:var(--acc); }
  .seq span.c { color:var(--cyan); }
  ul { margin:6px 0 0; padding-left:18px; color:var(--fg2); font-size:13px; }
  li { margin:3px 0; }
  .disc { color:var(--gold); font-size:12px; }
  .err { color:var(--bad); }
  button.seg { text-align:center; }

html, body { overflow-y:auto; scroll-behavior:smooth; }
body { font-size:16px; line-height:1.6; }
button, input, select { font-size:15px; }
button { min-height:44px; white-space:normal; line-height:1.45; }
p, label, .note, .sub, .ttl, .kv, .t { overflow-wrap:anywhere; }
details.tarla-detail { border:1px solid var(--line,#24302a); border-radius:14px; margin:12px 0; padding:12px 16px; }
details.tarla-detail summary { cursor:pointer; color:var(--fg,#f2f6f3); font-size:15px; font-weight:600; padding:6px 0; }
details.tarla-detail[open] summary { margin-bottom:12px; }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after {animation:none!important;transition:none!important;scroll-behavior:auto!important;} }

  header { flex-wrap:wrap; gap:16px; padding:20px 24px; height:auto; }
  header .brand { font-size:20px; white-space:normal; }
  .tele { flex-wrap:wrap; gap:12px; }
  main { max-width:1500px; margin:0 auto; height:auto; min-height:0; padding:24px; gap:24px; }
  .col { overflow:visible; min-width:0; gap:18px; }
  .card { padding:22px; border-radius:18px; }
  #mapWrap { min-height:460px; }
  .ttl { font-size:15px; flex-wrap:wrap; gap:10px; line-height:1.5; }
  .kv { font-size:14px; row-gap:10px; }
  .note,ul,.disc { font-size:14px; }
  .tabs { grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
  .tab { font-size:14px; min-height:64px; }
  .layer-bar{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:2px}
  .layer-bar .seg{min-height:36px;padding:6px 10px;max-width:100%;overflow-wrap:anywhere}
  .legend{max-height:42%;overflow:auto;max-width:min(280px,calc(100% - 70px))}
  .lbl{max-width: min(180px,35vw);white-space:normal;overflow-wrap:anywhere;text-align:center}
  .tab[aria-pressed="true"]{background:var(--panel2);border-color:var(--acc)}
  .tab b{font-variant-numeric:tabular-nums}
  .panel-change{animation:panel-change .22s ease-out}
  @keyframes panel-change{from{opacity:.65;transform:translateY(3px)}to{opacity:1;transform:none}}
  .kv{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
  .kv .v{text-align:right;overflow-wrap:anywhere}
  .tele .t{white-space:normal}
  header .logo svg{flex:none}
  .gaugeWrap { grid-template-columns:1fr; }
  .gaugeWrap svg { max-width:230px; margin:auto; }
  .legend { max-width:280px; font-size:13px; }
  @media(max-width:900px){main{display:flex;flex-direction:column;padding:14px}#mapWrap{flex:none;height:420px}}
  @media(max-width:550px){header{padding:14px} .card{padding:14px} #mapWrap{height:360px;min-height:0}}
  

/* giriş ve etkileşim animasyonları (hareketi azalt ayarında kapanır) */
@keyframes tpUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes tpFade{from{opacity:0}to{opacity:1}}
.card{animation:tpUp .42s cubic-bezier(.2,.8,.2,1) both}
.card:nth-child(2){animation-delay:0.04s}
.card:nth-child(3){animation-delay:0.08s}
.card:nth-child(4){animation-delay:0.12s}
.card:nth-child(5){animation-delay:0.16s}
.card:nth-child(6){animation-delay:0.20s}
.card:nth-child(7){animation-delay:0.24s}
.card:nth-child(8){animation-delay:0.28s}
.card:nth-child(9){animation-delay:0.32s}
.card:nth-child(10){animation-delay:0.36s}
#map{animation:tpFade .5s ease both}
button{transition:background-color .18s,border-color .18s,color .18s,box-shadow .18s,transform .12s}
button:hover:not(:disabled){box-shadow:0 0 0 3px rgba(124,240,168,.12)}
button:active:not(:disabled){transform:scale(.97)}
</style>
</head>
<body>
<header>
  <div class="logo">
    <svg viewBox="0 0 32 32" fill="none" stroke="#5cf2c4" stroke-width="2" aria-hidden="true">
      <rect x="3" y="3" width="26" height="26" rx="7"/>
      <path d="M9 23 23 9M10 17l7-7M15 23l8-8"/></svg>
    <div class="brand">Tarla Takip Paneli</div>
  </div>
  <div class="tele">
    <div class="t" id="tStream"><span class="dot off"></span>VERİ AKIŞI <b>—</b></div>
    <div class="t" title="Model göstergesi: 100 − entropi, yıllar arası oynaklıkla düzeltilmiş">KARARLILIK <b id="tStab">—</b></div>
    <div class="t">PARSEL <b id="tCoord">—</b></div>
    <div class="t" id="tCalc">HESAP <b>—</b></div>
  </div>
</header>
<main>
  <section class="col">
    <div class="layer-bar" id="layerBtns" aria-label="Harita katmanları"></div>
    <div id="mapWrap">
      <div id="map"></div>
      <div class="ovl legend" id="legend"></div>
      <div class="ovl legend" id="soilLegend" hidden>
        <b>Organik karbon · 0–5 cm</b>
        <div class="soil-key">
          <div class="soil-scale"><img id="soilScale" alt="Organik karbon renk ölçeği (dg/kg)" hidden></div>
          <div>
            <div class="note">SoilGrids · yaklaşık 250 m çözünürlük. Küçük bir tarlada tek renk görünmesi normaldir.</div>
            <div class="note">Birim: dg/kg. 10 dg/kg = 1 g/kg.</div>
            <div class="note" id="soilStatus" role="status"></div>
            <label for="soilOpacity">Katman görünürlüğü</label>
            <input id="soilOpacity" type="range" min="0" max="100" value="75">
            <button type="button" class="seg" id="soilRetry">Katmanı yeniden yükle</button>
          </div>
        </div>
      </div>
    </div>
    <div class="card">
      <div class="ttl"><span>Aylık durum</span><span id="monthNote"></span></div>
      <div class="row" style="gap:12px">
        <div style="width:150px" class="note">Su dengesi açığı</div><div style="flex:1" class="strip" id="sSu"></div></div>
      <div class="row" style="gap:12px;margin-top:4px">
        <div style="width:150px" class="note">Kök nemi stresi</div><div style="flex:1" class="strip" id="sNem"></div></div>
      <div class="row" style="gap:12px;margin-top:4px">
        <div style="width:150px" class="note">Isı stresi</div><div style="flex:1" class="strip" id="sIsi"></div></div>
      <div class="row" style="gap:12px"><div style="width:150px"></div><div style="flex:1" class="months" data-no-tr>
        <span>O</span><span>Ş</span><span>M</span><span>N</span><span>M</span><span>H</span><span>T</span><span>A</span><span>E</span><span>E</span><span>K</span><span>A</span></div></div>
    </div>
  </section>

  <section class="col right">
    <div class="card">
      <div class="ttl"><span>Toprağın zorlanma puanı</span><span id="entNote"></span></div>
      <div class="gaugeWrap">
        <svg id="gauge" viewBox="0 0 230 170"></svg>
        <div>
          <div id="entHead" style="font-size:15px;color:var(--fg)"></div>
          <div class="kv" id="entParts" style="margin-top:10px"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="ttl"><span>Ekim planları</span></div>
      <div class="tabs" id="tabs"></div>
      <div id="stratBody"></div>
    </div>

    <div class="card">
      <div class="ttl"><span>Veri kaynakları ve sınırlar</span></div>
      <div id="data" class="note"></div>
      <p class="disc">Sonuçlar model tahminidir. Karar vermeden önce tarladaki koşulları kontrol edin.</p>
    </div>
  </section>
</main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";
__SOIL_LAYER__
const TOKEN = "__TOKEN__";
const FIELD = __FIELD__;
const $ = id => document.getElementById(id);
const tr = (n, d = 0) => (n == null ? "—" : Number(n).toLocaleString(document.documentElement.lang, {minimumFractionDigits: d, maximumFractionDigits: d}));
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
let D = null, sel = 1, layer = "termo";

// ---------------------------------------------------------------- saat

// ---------------------------------------------------------------- harita
let map = null, parcelLayer = null, pinLayer = null, soilLayer = null;
function monthLetters() {                 // ay baş harfleri seçili dile göre
  const L = {en: "JFMAMJJASOND", de: "JFMAMJJASOND"}[document.documentElement.lang] || "OŞMNMHTAEEKA";
  document.querySelectorAll(".months span").forEach((s, i) => { s.textContent = L[i]; });
}
window.addEventListener("tarla-appearance", monthLetters);
monthLetters();
if (window.L) {
  map = L.map("map", {zoomControl: false, attributionControl: true}).setView(FIELD.center || [39, 35], 6);
  L.control.zoom({position: "bottomright"}).addTo(map);
  map.createPane("soilPane").style.zIndex = 250;
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {maxZoom: 19, attribution: "Uydu: Esri, Maxar"}).addTo(map);
  L.control.scale({imperial: false}).addTo(map);
  parcelLayer = L.layerGroup().addTo(map);
  pinLayer = L.layerGroup().addTo(map);
}

const LAYERS = {
  termo: {ad: "Isı ve su baskısı", unit: "/100", lo: 0, hi: 100, ramp: ["#12352b", "#f2c35c", "#f2706a"],
    get: p => p.katman.termo, not: "Isı, su açığı ve eğim birlikte değerlendirilir."},
  azot: {ad: "Azot kaybı göstergesi", unit: "/100", lo: 0, hi: 100, ramp: ["#12352b", "#f2c35c", "#f2706a"],
    get: p => p.katman.azot[sel] ?? p.katman.azot[0], not: "Azot dengesi ve açık kalan toprak, tahmini kayıp riskini belirler."},
  nem: {ad: "Nem değişimi", unit: " puan", lo: -8, hi: 8, ramp: ["#f2706a", "#22323b", "#5cc8f2"],
    get: p => p.katman.nem, not: "NASA POWER GWETROOT: son gözlenen yılın yetişme dönemi sapması (×100); dik parsel biraz kuru varsayılır."},
  gedi: {ad: "Karbon tahmini", unit: " t C/ha", lo: 0, hi: 80, ramp: ["#12352b", "#1f9e7c", "#5cf2c4"],
    get: p => p.katman.gedi, not: "GEDI değeri girilmişse kullanıcı girdisinden karbon hesabı; yoksa projenin bölgesel toprak varsayımından hesap. Tarla ölçümü değildir; tüm parsellerde aynıdır."},
  soil: {ad: "Toprak karbon haritası"},
};

function selectLayer(key) {
  if (key === layer) return;
  layer = key;
  if (layer === "soil") {
    soilLayer ??= createSoilLayer(text => { $("soilStatus").textContent = text; }, $("soilScale"), "soilPane");
    soilLayer.addTo(map);
  } else if (soilLayer) {
    soilLayer.remove();
  }
  buildButtons();
  drawMap(!D);
}
$("soilOpacity").oninput = e => soilLayer?.setOpacity(Number(e.target.value) / 100);
$("soilRetry").onclick = () => soilLayer?.redraw();

function buildButtons() {
  const host = $("layerBtns"); host.innerHTML = "";
  for (const [k, value] of Object.entries(LAYERS)) {
    const b = document.createElement("button");
    b.className = "seg" + (k === layer ? " on" : ""); b.textContent = value.ad;
    b.setAttribute("aria-pressed", String(k === layer));
    b.disabled = k === "soil" && !map;
    b.onclick = () => selectLayer(k);
    host.appendChild(b);
  }

}
function mix(a, b, t) { const p = s => [1, 3, 5].map(i => parseInt(s.slice(i, i + 2), 16));
  const x = p(a), y = p(b); return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join(""); }
function rampColor(r, t) { t = Math.max(0, Math.min(1, t)); return t < .5 ? mix(r[0], r[1], t * 2) : mix(r[1], r[2], (t - .5) * 2); }

function drawLegend() {
  $("legend").hidden = layer === "soil";
  $("soilLegend").hidden = layer !== "soil";
  if (layer === "soil") return;
  const Ly = LAYERS[layer];
  $("legend").innerHTML = "<b>" + Ly.ad + "</b>" +
    '<div class="ramp" style="background:linear-gradient(90deg,' + Ly.ramp.join(",") + ')"></div>' +
    '<div style="display:flex;justify-content:space-between"><span>' + Ly.lo + '</span><span>' + Ly.hi + Ly.unit + '</span></div>' +
    '<div class="note" style="margin-top:6px">' + esc(Ly.not) + "</div>" +
    (D && D.sematik ? '<div class="note" style="margin-top:4px;color:#f2c35c">Tarla çizilmedi: 600 m örnek kare.</div>' : "") +
    (window.L ? "" : '<div class="note err" style="margin-top:4px">Harita kütüphanesi yüklenemedi (internet gerekir); paneller çalışmaya devam eder.</div>');
}

function drawMap(fit) {
  drawLegend();
  if (!map) return;
  parcelLayer.clearLayers(); pinLayer.clearLayers();
  if (layer === "soil") {
    if (FIELD.boundary.length >= 3) {
      const outline = L.polygon(FIELD.boundary, {color: "#5cf2c4", weight: 3, fill: false}).addTo(parcelLayer);
      if (fit) map.fitBounds(outline.getBounds().pad(0.25));
    } else if (fit) {
      map.setView(FIELD.center, 10);
    }
    return;
  }
  if (!D) return;
  const Ly = LAYERS[layer]; const all = [];
  for (const p of D.parseller) {
    const v = Ly.get(p); const t = (v - Ly.lo) / (Ly.hi - Ly.lo);
    const col = v == null ? '#6f858c' : rampColor(Ly.ramp, t);
    const pg = L.polygon(p.poly, {color: "#5cf2c4", weight: 1.5, fillColor: col, fillOpacity: .55}).addTo(parcelLayer);
    pg.bindTooltip(p.ad + " · " + tr(v, layer === "nem" ? 1 : 0) + Ly.unit, {sticky:true, className: "lbl"});
    pg.bindPopup("<b>" + esc(p.ad) + "</b> · " + esc(p.yon) + "<br>Eğim: " + (p.egim == null ? "bilinmiyor" : "%" + tr(p.egim, 1)) +
      "<br>Isı ve su baskısı: " + p.katman.termo + "/100<br>Azot kaybı göstergesi: " + (p.katman.azot[sel] ?? p.katman.azot[0]) +
      "/100<br>Nem değişimi: " + tr(p.katman.nem, 1) + (p.uyari.length ? "<br><b style='color:#f2706a'>⚠ " + esc(p.uyari.join(" · ")) + "</b>" : ""));
    all.push(...p.poly);
    if (p.uyari.length) {
      const icon = L.divIcon({className: "", html: '<div class="pin"></div>', iconSize: [18, 18], iconAnchor: [9, 9]});
      L.marker([p.lat, p.lon], {icon}).addTo(pinLayer).bindTooltip("⚠ " + p.uyari.join(" · "), {direction: "top", offset: [0, -10]});
    }
  }
  if (fit && all.length) map.fitBounds(L.latLngBounds(all).pad(0.25));
}

// ---------------------------------------------------------------- entropi ibresi
function gauge(S, Scur) {
  const g = $("gauge"); const cx = 115, cy = 118, R = 92, a0 = -210, a1 = 30;
  const ang = v => (a0 + (a1 - a0) * v / 100) * Math.PI / 180;
  const pt = (v, r) => [cx + r * Math.cos(ang(v)), cy + r * Math.sin(ang(v))];
  let h = "";
  for (let i = 0; i < 50; i++) {
    const v0 = i * 2, v1 = v0 + 1.6; const [x0, y0] = pt(v0, R), [x1, y1] = pt(v1, R);
    const c = rampColor(["#5cf2c4", "#f2c35c", "#f2706a"], v0 / 100);
    h += `<path d="M${x0} ${y0} A${R} ${R} 0 0 1 ${x1} ${y1}" stroke="${c}" stroke-width="10" fill="none" opacity="${v0 <= S ? 1 : .18}"/>`;
  }
  for (const v of [0, 25, 50, 75, 100]) { const [x, y] = pt(v, R - 18);
    h += `<text x="${x}" y="${y}" fill="#6f858c" font-size="10" font-family="Consolas,monospace" text-anchor="middle" dominant-baseline="central">${v}</text>`; }
  if (Scur != null) { const [x0, y0] = pt(Scur, R - 8), [x1, y1] = pt(Scur, R + 9);
    h += `<line x1="${x0}" y1="${y0}" x2="${x1}" y2="${y1}" stroke="#e8f1f2" stroke-width="2" stroke-dasharray="2 2"/>`; }
  const [nx, ny] = pt(S, R - 26);
  h += `<line x1="${cx}" y1="${cy}" x2="${nx}" y2="${ny}" stroke="#e8f1f2" stroke-width="3" stroke-linecap="round"/>` +
       `<circle cx="${cx}" cy="${cy}" r="6" fill="#e8f1f2"/>` +
       `<text x="${cx}" y="${cy + 30}" fill="#e8f1f2" font-size="26" font-weight="700" font-family="Consolas,monospace" text-anchor="middle">${tr(S, 1)}</text>` +
       `<text x="${cx}" y="${cy + 47}" fill="#6f858c" font-size="10" font-family="Consolas,monospace" text-anchor="middle" letter-spacing="2">TOPRAK PUANI</text>`;
  g.innerHTML = h;
}

// ---------------------------------------------------------------- sağ panel
function drawRight() {
  const s = D.strateji[sel], cur = D.strateji[0];
  $("tStab").textContent = tr(s.kararlilik, 1) + '/100';
  gauge(s.entropi.S, sel ? cur.entropi.S : null);
  $("entNote").textContent = sel ? "kesikli çizgi: mevcut rotasyon" : "";
  $("entHead").innerHTML = sel && s.azalma != null
    ? (s.azalma >= 0
      ? `Bu ekim sırası zorlanma puanını <b style="color:#5cf2c4">%${tr(s.azalma, 0)}</b> azaltıyor (${tr(cur.entropi.S, 1)} → ${tr(s.entropi.S, 1)}).`
      : `Bu ekim sırası zorlanma puanını <b style="color:#f2706a">%${tr(-s.azalma, 0)}</b> artırıyor.`)
    : `Seçili planda azot kaybı göstergesi <b style="color:#f2c35c">${tr(s.entropi.parcalar.azot, 0)}/100</b>; zorlanma puanı ${tr(s.entropi.S, 1)}/100. Bunlar proje modeli puanlarıdır.`;
  $("entParts").innerHTML = Object.entries(s.entropi.parcalar).map(([k, v]) => {
    const c = rampColor(["#5cf2c4", "#f2c35c", "#f2706a"], v / 100);
    return `<span class="k">${esc(D.etiketler[k])} <span class="note">· ağırlık %${Math.round(D.agirlik[k] * 100)}</span></span><span class="v">${tr(v, 0)}</span>` +
      `<div class="bar" style="grid-column:1 / span 2"><i style="width:${v}%;background:${c}"></i></div>`; }).join("");
  $("tabs").innerHTML = D.strateji.map((x, i) =>
    `<button class="tab${i === sel ? " on" : ""}" aria-pressed="${i === sel}" data-i="${i}">${i ? 'Plan ' + i : 'Mevcut plan'}<b>${tr(x.puan, 0)} / 100</b></button>`).join("");
  document.querySelectorAll(".tab").forEach(b => b.onclick = () => { sel = +b.dataset.i; drawRight(); drawMap(false);
    for (const id of ["stratBody"]) {
      const section = $(id); section.classList.remove("panel-change");
      requestAnimationFrame(() => section.classList.add("panel-change"));
    }
  });
  const seq = s.ekinler.map((n, i) => `<span>${i + 1}. ${esc(n)}</span>` + (s.ortu[i] ? '<span class="c">+ örtü bitkisi</span>' : "")).join("");
  $("stratBody").innerHTML =
    `<div class="seq">${seq}</div>` +
    `<div class="kv"><span class="k">Puan (aralık)</span><span class="v">${tr(s.puan, 1)} ± ${tr(s.sd, 1)} · ${tr(s.p10, 0)}–${tr(s.p90, 0)}</span>` +
    `<span class="k">Zayıf yıl olasılığı</span><span class="v">%${tr(s.zayif_yil * 100, 0)}</span>` +
    `<span class="k">Sezon su açığı</span><span class="v">${tr(s.su_acigi)} mm</span>` +
    `<span class="k">Çıplak toprak</span><span class="v">yılda ${tr(s.ciplak_ay, 1)} ay</span>` +
    `<span class="k">Karbon (toprakta tutulan)</span><span class="v">${tr(s.karbon[1], 2)} t CO₂e/ha/yıl (${tr(s.karbon[0], 1)}–${tr(s.karbon[2], 1)})</span></div>` +
    (s.neden.length ? "<ul>" + s.neden.map((x,i) => `<li>${esc(x)}<div class="note">Dayanak: ${esc((s.neden_kaynak||[])[i] || 'Proje rotasyon modeli; varsayımlar kaynak ekranında.')}</div></li>`).join("") + "</ul>" : "") +
    (s.risk.length ? '<ul style="color:#f2c35c">' + s.risk.map(x => `<li>${esc(x)}</li>`).join("") + "</ul>" : "");

}

function strip(id, vals, ramp) { $(id).innerHTML = vals.map(v => `<div title="${tr(v * 100)}/100" style="background:${rampColor(ramp, v)}"></div>`).join(""); }

function render(fit) {
  const a = D.arama;
  $("tStream").innerHTML = `<span class="dot${D.canli ? "" : " off"}"></span>VERİ AKIŞI <b>${D.canli ? "NASA POWER · İKLİM" : "ÖRNEK VERİ"}</b>`;
  $("tCoord").textContent = (D.lat == null ? "—" : tr(D.lat, 4) + "°K " + tr(D.lon, 4) + "°D");
  $("tCalc").innerHTML = `HESAP <b>${tr(D.hesap_sn, 1)} sn</b>`;
  $("monthNote").textContent = D.nem_yili ? "nem karşılaştırma yılı: " + D.nem_yili : "Geçmiş nem verisi yok → nem değişimi hesaplanmadı.";
  strip("sSu", D.aylik.su, ["#12352b", "#f2c35c", "#f2706a"]);
  strip("sNem", D.aylik.nem, ["#12352b", "#f2c35c", "#f2706a"]);
  strip("sIsi", D.aylik.isi, ["#12352b", "#f2c35c", "#f2706a"]);
  $("data").innerHTML = [
    "Konum: " + esc(D.ad || "—") + (D.alan_ha ? " · " + tr(D.alan_ha, 2) + " ha" : ""),
    "İklim: " + (D.canli ? "NASA POWER aylık iklim verisi (tarla sensörü değil)" : "ÖRNEK İKLİM · tarlaya ait ölçüm değil") + " · değişkenlik: " + (a.yontem === "gecmis" ? "geçmiş yıl serileri" : "proje varsayımı"),
    "Eğim: Copernicus DEM 90 m " + (D.egim_var ? "(parsel bazlı)" : "(alınamadı — düz arazi varsayıldı)"),
    "Uydu altlığı · Esri ve Maxar",
    "Toprak ısı haritası · ISRIC SoilGrids",
    "Veri güveni: " + esc(D.guven[0]) + " — " + esc(D.guven[1]),
    ...(D.kalibrasyon.length ? D.kalibrasyon.map(k => "Kalibrasyon: " + esc(k)) :
      ["Uydu ölçümü (SMAP, ECOSTRESS, GPM, GEDI, GRACE, NDVI) girilmedi; uygulamadaki optimizasyon penceresinden girilebilir."]),
    ...((D.strateji[sel].bosluk || []).map(b => "Bilgi boşluğu: " + esc(b))),
  ].map(x => "<div>• " + x + "</div>").join("");
  drawRight(); drawMap(fit);
}

// ---------------------------------------------------------------- hesap
function setBusy(b) {
  $("tCalc").innerHTML = b ? '<span class="dot busy"></span>HESAPLANIYOR' : `HESAP <b>${D ? tr(D.hesap_sn, 1) + " sn" : "—"}</b>`;
}
async function run(fit) {
  setBusy(true);
  try {
    const r = await fetch("/api/mc?t=" + TOKEN, {method: "POST", headers: {"Content-Type": "application/json"},
      body: "{}"});
    const j = await r.json();
    if (!j.ok) throw new Error(j.hata || "Hesap yapılamadı");
    D = j; if (sel >= D.strateji.length) sel = 1; setBusy(false); render(fit);
  } catch (e) {
    setBusy(false);
    $("tCalc").innerHTML = '<span class="err">HATA: ' + esc(e.message) + "</span>";
  }
}
buildButtons(); drawLegend();
window.addEventListener("tarla-appearance", () => {
  if (D) render(false);
});
run(true);
</script>
<script>
function tarlaFold(node,title){
 if(!node)return;
 const d=document.createElement('details');d.className='tarla-detail';
 const s=document.createElement('summary');s.textContent=title;
 node.parentNode.insertBefore(d,node);d.appendChild(s);d.appendChild(node);
 d.addEventListener('toggle',()=>window.dispatchEvent(new Event('resize')));
}

  document.addEventListener('DOMContentLoaded',()=>{
   for(const [id,title] of [['gauge','Toprağın zorlanma puanı'],['data','Veri kaynakları ve sınırlar'],['sSu','Aylık durum']])
     tarlaFold(document.getElementById(id)?.closest('.card'),title);
   tarlaFold(document.querySelector('.tele'),'Veri akışı ve konum ayrıntıları');
   const right=document.querySelector('.right');
   const strategies=document.getElementById('tabs')?.closest('.card');
   if(right&&strategies)right.prepend(strategies);
  });
  </script>
</body>
</html>
"""
