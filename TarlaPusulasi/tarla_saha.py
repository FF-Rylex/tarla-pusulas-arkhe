#!/usr/bin/env python3
"""Tarla Pusulası — saha modu: canlı GPS haritası + sesli kabin asistanı (v3.4).

v3.4: Leaflet uydu haritası üzerinde gerçek konum (doğruluk dairesi, yön, iz, takip),
tarla dışındayken tarlaya uzaklık ve yön, ses kuyruğu (duyurular birbirini kesmez),
Türkçe ses seçimi, cümle cümle vurgulama, duyuru zili, sesli komutlar (destekleyen
tarayıcıda). Sayfa uygulamanın yerel sunucusundan (127.0.0.1) açılır: tarayıcılar bu
adreste konum iznine izin verir.


Optimizasyon sonuçlarından parsel bazlı sesli öneriler üretir ve bunları tek
dosyalık bir HTML sayfasına gömer (internet ve kurulum gerekmez):
  • Coğrafi çit (geofencing): telefonun GPS konumu parsel sınırına girince o
    parselin önerisi otomatik olarak sesli okunur (tarayıcının Web Speech API'si, tr-TR).
  • Traktör simülasyonu: GPS olmadan, sanal traktör tarlayı şerit şerit dolaşır;
    jüri sunumu ve deneme için. Rota seçilen tarlanın biçimine göre kurulur: şeritler
    en uzun kenara paraleldir ve yalnızca sınırın içinde kalan aralıkta gidilir.
Gerçek GPS için tarayıcılar güvenli bağlantı ister: dosyayı HTTPS üzerinden (ör.
GitHub Pages) ya da bilgisayarda doğrudan açın. Simülasyon her durumda çalışır.
"""
import json
import os
import shutil
import subprocess
import time
import webbrowser

import tarla_optimizer as to

PAGE = r"""<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#080b0a">
<title>Saha modu · Tarla Pusulası</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--bg:#080b0a;--card:#101614;--card2:#161d1a;--line:#24302a;--fg:#f2f6f3;--fg2:#cdd8d1;
  --mut:#8b9c92;--acc:#7cf0a8;--acc2:#37a06b;--gold:#e8c07d;--bad:#ee8874;--water:#6fb8e8}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:var(--bg);color:var(--fg);
  font:16px/1.5 "Segoe UI",system-ui,-apple-system,Roboto,sans-serif}
#app{display:grid;grid-template-columns:minmax(0,1fr) 400px;height:100%}
#mapwrap{position:relative;min-height:320px}
#map{position:absolute;inset:0;background:#0b100e}
#hud{position:absolute;top:12px;left:12px;right:12px;display:flex;gap:8px;flex-wrap:wrap;z-index:500;pointer-events:none}
.chip{pointer-events:auto;background:rgba(16,22,20,.88);backdrop-filter:blur(6px);border:1px solid var(--line);
  color:var(--fg2);border-radius:999px;padding:6px 12px;font-size:14px;font-weight:600;white-space:nowrap}
.chip.on{color:var(--acc);border-color:var(--acc2)} .chip.warn{color:var(--gold)} .chip.bad{color:var(--bad)}
#recenter{position:absolute;right:14px;bottom:24px;z-index:500;width:54px;height:54px;border-radius:50%;
  border:1px solid var(--line);background:rgba(16,22,20,.92);color:var(--acc);font-size:24px;cursor:pointer;
  display:grid;place-items:center;transition:transform .15s,opacity .2s}
#recenter.hide{opacity:0;pointer-events:none;transform:scale(.8)}
aside{background:var(--card);border-left:1px solid var(--line);overflow-y:auto;padding:18px 18px 28px}
h1{font-size:20px;margin:0}
.sub{color:var(--mut);font-size:14px;margin:2px 0 14px}
.now{border:1px solid var(--line);border-radius:18px;padding:16px;background:var(--card2);position:relative;overflow:hidden}
.now.enter{animation:flash .9s ease}
@keyframes flash{0%{box-shadow:0 0 0 0 rgba(124,240,168,.55)}100%{box-shadow:0 0 0 18px rgba(124,240,168,0)}}
.now .eyebrow{font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--mut)}
.now h2{margin:4px 0 8px;font-size:22px}
#nowText span{transition:background-color .2s,color .2s;border-radius:6px;padding:0 2px}
#nowText span.reading{background:rgba(124,240,168,.16);color:var(--fg)}
#nowText{color:var(--fg2);font-size:16px;margin:0}
.wave{display:flex;gap:3px;align-items:center;height:22px;position:absolute;top:16px;right:16px;opacity:0;transition:opacity .2s}
.wave.on{opacity:1}
.wave i{display:block;width:4px;height:6px;border-radius:2px;background:var(--acc);animation:wv .9s ease-in-out infinite}
.wave i:nth-child(2){animation-delay:.12s}.wave i:nth-child(3){animation-delay:.24s}.wave i:nth-child(4){animation-delay:.36s}.wave i:nth-child(5){animation-delay:.48s}
@keyframes wv{0%,100%{height:5px}50%{height:20px}}
.seq{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.seq span{background:#16241d;color:var(--acc);border-radius:999px;padding:4px 10px;font-size:14px;font-weight:700}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}
button{font:inherit;font-weight:700;border-radius:14px;border:1px solid var(--line);background:var(--card2);
  color:var(--fg);padding:12px 14px;min-height:50px;cursor:pointer;transition:background-color .18s,border-color .18s,transform .12s}
button:hover{border-color:var(--acc2)} button:active{transform:scale(.97)}
button.primary{background:var(--acc);color:#06130c;border-color:var(--acc)}
button.live{background:#16241d;color:var(--acc);border-color:var(--acc2)}
button[hidden]{display:none}
.section{margin-top:18px}
.label{font-size:12px;font-weight:700;letter-spacing:.08em;color:var(--mut);margin-bottom:6px}
select,input[type=range]{width:100%;accent-color:var(--acc)}
select{background:var(--card2);color:var(--fg);border:1px solid var(--line);border-radius:10px;padding:8px}
.row{display:flex;gap:10px;align-items:center}
.row label{flex:1;color:var(--fg2);font-size:14px}
.log{color:var(--mut);font-size:14px;max-height:200px;overflow:auto}
.log div{padding:4px 0;border-bottom:1px solid #141b18}
.note{color:var(--mut);font-size:13px}
.banner{border:1px solid var(--gold);color:var(--gold);border-radius:12px;padding:10px 12px;font-size:14px;margin-bottom:12px}
#heard{color:var(--water);font-size:14px;min-height:20px;margin-top:6px}
button.sm{min-height:42px;padding:8px 14px;font-size:14px}
.voices{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px}
.me{position:relative;width:22px;height:22px}
.me .dot{position:absolute;inset:4px;border-radius:50%;background:#4aa3ff;border:3px solid #fff;box-shadow:0 0 0 2px rgba(0,0,0,.25)}
.me .pulse{position:absolute;inset:-10px;border-radius:50%;background:rgba(74,163,255,.35);animation:pl 1.8s ease-out infinite}
@keyframes pl{0%{transform:scale(.3);opacity:.9}100%{transform:scale(1.4);opacity:0}}
.me .cone{position:absolute;left:50%;top:50%;width:0;height:0;border-left:11px solid transparent;border-right:11px solid transparent;
  border-bottom:26px solid rgba(74,163,255,.55);transform-origin:50% 100%;margin-left:-11px;margin-top:-34px;display:none}
.tractor .dot{background:var(--gold)} .tractor .pulse{background:rgba(232,192,125,.35)}
.plabel{background:rgba(8,11,10,.82);color:#f2f6f3;border:1px solid #37a06b;border-radius:10px;padding:2px 8px;font-weight:700;font-size:13px;white-space:nowrap}
.leaflet-tooltip.plabel:before{display:none}
/* ---------------- animasyonlar (v3.7) — hareketi azalt ayarında kapanır */
@keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
aside>*{animation:fadeUp .45s cubic-bezier(.2,.8,.2,1) both}
aside>*:nth-child(2){animation-delay:.04s}aside>*:nth-child(3){animation-delay:.08s}aside>*:nth-child(4){animation-delay:.12s}
aside>*:nth-child(5){animation-delay:.16s}aside>*:nth-child(6){animation-delay:.2s}aside>*:nth-child(7){animation-delay:.24s}
aside>*:nth-child(8){animation-delay:.28s}aside>*:nth-child(9){animation-delay:.32s}aside>*:nth-child(10){animation-delay:.36s}
#hud .chip{animation:fadeUp .4s ease both}
.chip{transition:color .25s,border-color .25s,background-color .25s}
.chip.pop{animation:pop .38s cubic-bezier(.3,1.6,.5,1)}
@keyframes pop{0%{transform:scale(1)}40%{transform:scale(1.12)}100%{transform:scale(1)}}
button{position:relative;overflow:hidden}
button:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 6px 18px rgba(0,0,0,.25)}
button:active:not(:disabled){transform:translateY(0) scale(.97)}
.ripple{position:absolute;border-radius:50%;background:currentColor;opacity:.28;transform:scale(0);pointer-events:none;animation:rip .6s ease-out forwards}
@keyframes rip{to{transform:scale(1);opacity:0}}
button.listening{animation:mic 1.2s ease-out infinite}
@keyframes mic{0%{box-shadow:0 0 0 0 rgba(124,240,168,.55)}100%{box-shadow:0 0 0 16px rgba(124,240,168,0)}}
#nowText.swap,#nowTitle.swap,#nowEyebrow.swap{animation:swap .5s cubic-bezier(.2,.8,.2,1)}
@keyframes swap{from{opacity:0;transform:translateX(14px)}to{opacity:1;transform:none}}
.seq span{animation:fadeUp .35s ease both}
.seq span:nth-child(2){animation-delay:.08s}.seq span:nth-child(3){animation-delay:.16s}.seq span:nth-child(4){animation-delay:.24s}
.prog{height:4px;border-radius:2px;background:var(--line);margin-top:12px;overflow:hidden;opacity:0;transition:opacity .3s}
.prog.on{opacity:1}
.prog i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--acc2),var(--acc));border-radius:2px;transition:width .25s linear}
.log div{animation:slideIn .35s ease both}
@keyframes slideIn{from{opacity:0;transform:translateX(-10px);background:rgba(124,240,168,.12)}to{opacity:1;transform:none;background:transparent}}
.voices{position:relative}
#toneBtns{background:var(--card2);border:1px solid var(--line);border-radius:14px;padding:4px;gap:4px;display:flex}
#toneBtns button{flex:1;background:transparent;border-color:transparent;z-index:1;transition:color .25s}
#toneBtns button.live{background:transparent;color:#06130c;border-color:transparent}
#toneBtns .slider{position:absolute;top:4px;bottom:4px;border-radius:10px;background:var(--acc);transition:left .3s cubic-bezier(.3,1.3,.5,1),width .3s;z-index:0}
#voiceBtns button{transition:background-color .25s,border-color .25s,color .25s,transform .12s}
.eq{display:none;gap:2px;align-items:flex-end;height:12px;margin-left:6px;vertical-align:middle}
.eq i{display:block;width:3px;height:4px;border-radius:1px;background:currentColor;animation:wv .8s ease-in-out infinite}
.eq i:nth-child(2){animation-delay:.15s}.eq i:nth-child(3){animation-delay:.3s}
body.speaking button.live .eq{display:inline-flex}
.route-flow{animation:flow 1.1s linear infinite}
@keyframes flow{to{stroke-dashoffset:-22}}
.ping{width:18px;height:18px;border-radius:50%;border:3px solid var(--acc);animation:ping 1.2s ease-out forwards}
.ping.parcel{border-color:#fff}
@keyframes ping{0%{transform:scale(.4);opacity:1}100%{transform:scale(5);opacity:0}}
.me .cone{transition:transform .35s ease}
.now .wave.on~h2{color:var(--fg)}
@media(max-width:860px){#app{grid-template-columns:1fr;grid-template-rows:55vh auto}aside{border-left:0;border-top:1px solid var(--line)}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
</style>
</head>
<body>
<div id="app">
  <div id="mapwrap">
    <div id="map" aria-label="Tarla haritası ve canlı konum"></div>
    <div id="hud">
      <span class="chip" id="gpsChip">GPS kapalı</span>
      <span class="chip" id="spdChip" hidden></span>
      <span class="chip" id="parcelChip">Parsel: —</span>
      <span class="chip" id="distChip" hidden></span>
    </div>
    <button id="recenter" class="hide" title="Konumuma dön" aria-label="Konumuma dön">◎</button>
  </div>
  <aside>
    <div id="banner"></div>
    <h1>Saha modu · sesli asistan</h1>
    <div class="sub" id="sub"></div>
    <div class="now" id="now">
      <div class="wave" id="wave"><i></i><i></i><i></i><i></i><i></i></div>
      <div class="eyebrow" id="nowEyebrow">ŞU AN</div>
      <h2 id="nowTitle">Tarlaya girilmedi</h2>
      <p id="nowText">Gerçek GPS'i açın ya da simülasyonu başlatın. Bir parsele girdiğinizde öneri otomatik okunur.</p>
      <div class="seq" id="nowSeq"></div>
      <div class="prog" id="prog"><i id="progBar"></i></div>
    </div>
    <div class="grid2">
      <button class="primary" id="gpsBtn">⌖ Canlı GPS</button>
      <button id="simBtn">▶ Simülasyon</button>
      <button id="resetBtn">⟲ Baştan başlat</button>
      <button id="repeatBtn">↻ Tekrar oku</button>
      <button id="muteBtn">🔇 Sessiz</button>
      <button id="micBtn" hidden>🎤 Sesli komut</button>
      <button id="whereBtn">📍 Neredeyim?</button>
    </div>
    <div id="heard"></div>
    <div class="section">
      <div class="label">SES</div>
      <select id="voiceSel" aria-label="Ses"></select>
      <div class="row" style="margin-top:10px"><label for="rate">Konuşma hızı</label><input type="range" id="rate" min="0.8" max="1.3" step="0.05" value="1"></div>
      <div class="row"><label for="chime">Duyuru öncesi zil</label><input type="checkbox" id="chime" checked></div>
      <div class="row"><label for="speed">Simülasyon hızı</label><input type="range" id="speed" min="1" max="10" value="4"></div>
    </div>
    <div class="section"><div class="label">DUYURULAR</div><div class="log" id="log"></div></div>
    <div class="section">
      <div class="label">SESİ DEĞİŞTİR</div>
      <div class="voices" id="voiceBtns"></div>
      <div class="voices" id="toneBtns">
        <button class="sm" data-p="0">Kalın · ağır</button>
        <button class="sm" data-p="1">Normal</button>
        <button class="sm" data-p="2">İnce · hızlı</button>
      </div>
      <button class="sm" id="moreVoices" hidden>🌐 Daha fazla ses: Edge'de aç</button>
      <div class="note" id="voiceNote"></div>
    </div>
    <p class="note" id="disc"></p>
  </aside>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
"use strict";
const DATA = __DATA__;
const $ = id => document.getElementById(id);
const tr1 = v => v.toLocaleString(document.documentElement.lang, {maximumFractionDigits: 1});
$("sub").textContent = DATA.tarla + " · " + DATA.parseller.length + " parsel · " + DATA.tarih;
$("disc").textContent = DATA.uyari;
const store = {get(k, d) { try { const v = localStorage.getItem("saha." + k); return v === null ? d : v; } catch (e) { return d; } },
               set(k, v) { try { localStorage.setItem("saha." + k, v); } catch (e) {} }};

function logLine(t) {
  const d = document.createElement("div");
  d.textContent = new Date().toLocaleTimeString(document.documentElement.lang, {hour: "2-digit", minute: "2-digit", second: "2-digit"}) + " · " + t;
  $("log").prepend(d);
  while ($("log").children.length > 60) $("log").lastChild.remove();
}
function banner(t) { $("banner").innerHTML = t ? '<div class="banner"></div>' : ""; if (t) $("banner").firstChild.textContent = t; }
if (!window.isSecureContext) banner("Gerçek GPS için sayfa https:// veya uygulamanın açtığı yerel adresten açılmalı. Simülasyon yine çalışır.");

// ------------------------------------------------------------------ geometri
const R = 6371008.8, rad = Math.PI / 180;
function dist(a, b) {                      // [lat, lon] metre
  const dLa = (b[0] - a[0]) * rad, dLo = (b[1] - a[1]) * rad;
  const h = Math.sin(dLa / 2) ** 2 + Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLo / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
function bearing(a, b) {
  const y = Math.sin((b[1] - a[1]) * rad) * Math.cos(b[0] * rad);
  const x = Math.cos(a[0] * rad) * Math.sin(b[0] * rad) - Math.sin(a[0] * rad) * Math.cos(b[0] * rad) * Math.cos((b[1] - a[1]) * rad);
  return (Math.atan2(y, x) / rad + 360) % 360;
}
const DIRS = ["kuzey", "kuzeydoğu", "doğu", "güneydoğu", "güney", "güneybatı", "batı", "kuzeybatı"];
const dirName = b => DIRS[Math.round(b / 45) % 8];
function inPoly(la, lo, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [ya, xa] = poly[i], [yb, xb] = poly[j];
    if (((ya > la) !== (yb > la)) && (lo < (xb - xa) * (la - ya) / (yb - ya) + xa)) inside = !inside;
  }
  return inside;
}
function nearestOnField(p) {               // sınırdaki en yakın nokta (yerel düzlemde)
  const k = Math.cos(p[0] * rad), ring = DATA.sinir;
  let best = null, bd = Infinity;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    const ax = a[1] * k, ay = a[0], bx = b[1] * k, by = b[0], px = p[1] * k, py = p[0];
    const dx = bx - ax, dy = by - ay, L2 = dx * dx + dy * dy || 1e-18;
    const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / L2));
    const q = [ay + t * dy, (ax + t * dx) / k], d = dist(p, q);
    if (d < bd) { bd = d; best = q; }
  }
  return [best, bd];
}
const fmtDist = m => m < 1000 ? Math.round(m / 10) * 10 + " metre" : tr1(m / 1000) + " kilometre";
const fmtDistShort = m => m < 1000 ? Math.round(m) + " m" : tr1(m / 1000) + " km";

// ------------------------------------------------------------------ ses
const synth = "speechSynthesis" in window ? window.speechSynthesis : null;
let muted = store.get("muted", "0") === "1", voices = [], queue = [], speaking = false, lastText = "", gen = 0;
// Ton: Windows sesleri küçük perde farklarını duyurmaz; bu yüzden uç değerler (0 ve 2) kullanılır
// ve hız da tona eşlik eder (kalın = ağır, ince = hızlı). Böylece tek ses olsa da fark duyulur.
const TONE_RATE = {0: .85, 1: 1, 2: 1.15};
let pitch = +store.get("pitch", "1");
if (!(pitch in TONE_RATE)) pitch = 1;
function rankVoice(v) {
  let s = 0;
  if (/natural|neural|online|premium|enhanced|google/i.test(v.name)) s += 10;
  if (v.lang.toLowerCase().startsWith(document.documentElement.lang)) s += 100;
  if (v.localService === false) s += 2;
  return s;
}
function loadVoices() {
  if (!synth) return;
  voices = synth.getVoices().filter(v => v.lang.toLowerCase().startsWith(document.documentElement.lang)).sort((a, b) => rankVoice(b) - rankVoice(a));
  const sel = $("voiceSel"), saved = store.get("voice:" + document.documentElement.lang, store.get("voice", ""));
  sel.innerHTML = "";
  if (!voices.length) { const o = document.createElement("option"); o.textContent = "Seçili dilde ses bulunamadı (varsayılan ses)"; sel.appendChild(o); paintVoiceBtns(); return; }
  voices.forEach((v, i) => { const o = document.createElement("option"); o.value = v.name;
    o.textContent = v.name.replace(/Microsoft |Google /, "") + (i === 0 ? " · önerilen" : ""); if (v.name === saved) o.selected = true; sel.appendChild(o); });
  paintVoiceBtns();
}
// Sayfanın altındaki ses düğmeleri: seçili dildeki ilk 4 ses + her seste çalışan 3 ton
const shortVoice = v => v.name.replace(/Microsoft |Google /, "").replace(/\s+-\s+.*$/, "").replace(/ Online \(Natural\)/i, " (doğal)");
function paintVoiceBtns() {
  const box = $("voiceBtns"), cur = $("voiceSel").value;
  box.innerHTML = "";
  voices.slice(0, 4).forEach(v => {
    const b = document.createElement("button");
    b.className = "sm" + (v.name === cur ? " live" : ""); b.textContent = "🗣 " + shortVoice(v);
    const eq = document.createElement("span"); eq.className = "eq"; eq.innerHTML = "<i></i><i></i><i></i>"; b.appendChild(eq);
    b.onclick = () => { $("voiceSel").value = v.name; store.set("voice:" + document.documentElement.lang, v.name); voiceChanged(); };
    box.appendChild(b);
  });
  document.querySelectorAll("#toneBtns button").forEach(b => { b.className = "sm" + (+b.dataset.p === pitch ? " live" : ""); });
  moveSlider();
  // Uygulama penceresi yalnızca Windows'a kurulu sesleri görür (Türkçe için çoğunlukla tek ses).
  // Edge tarayıcısında çevrimiçi doğal sesler de (ör. Emel, Ahmet) listelenir.
  const few = voices.length < 2 && location.protocol.startsWith("http");
  $("moreVoices").hidden = !few;
  $("voiceNote").textContent = !voices.length
    ? "Bu dilde yüklü ses yok. Windows: Ayarlar > Saat ve dil > Konuşma > Ses ekle; ya da Edge penceresinde çevrimiçi sesleri kullanın."
    : few ? "Bu pencerede tek ses var. Edge penceresinde çevrimiçi doğal sesler de gelir (internet gerekir)." : "";
}
$("moreVoices").onclick = () => {
  $("voiceNote").textContent = "Edge açılıyor…";
  fetch("/saha-tarayici" + location.search).then(r => r.json()).then(j => {
    $("voiceNote").textContent = j.ok ? "Sayfa tarayıcıda açıldı. Sesi oradan seçin; bu pencereyi kapatabilirsiniz." : "Tarayıcı açılamadı. Edge'i açıp bu adresi yapıştırın: " + location.href;
    if (j.ok) { stopSim(true); hush(); }
  }).catch(() => { $("voiceNote").textContent = "Tarayıcı açılamadı. Edge'i açıp bu adresi yapıştırın: " + location.href; });
};
function moveSlider() {                      // ton seçicide yeşil gösterge seçilene kayar
  const box = $("toneBtns"), on = box.querySelector("button.live");
  let sl = box.querySelector(".slider");
  if (!sl) { sl = document.createElement("div"); sl.className = "slider"; box.prepend(sl); }
  if (on) { sl.style.left = on.offsetLeft + "px"; sl.style.width = on.offsetWidth + "px"; }
}
window.addEventListener("resize", moveSlider);
function voiceChanged() {                   // okuma sürüyorsa aynı metni yeni sesle baştan oku
  paintVoiceBtns();
  if (muted || !synth) return;
  if (speaking && lastText) say(lastText, {oncelik: true, vurgu: true});
  else say("Bu ses seçildi.", {oncelik: true});
}
document.querySelectorAll("#toneBtns button").forEach(b => { b.onclick = () => { pitch = +b.dataset.p; store.set("pitch", String(pitch)); voiceChanged(); }; });
if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; }
let langSeen = null;
window.addEventListener('tarla-appearance', () => {
  if (!synth) return;
  queue = []; gen++; synth.cancel(); speaking = false; loadVoices();
  const L = document.documentElement.lang;
  if (langSeen && langSeen !== L && !muted) say("Bu ses seçildi.", {oncelik: true});   // yeni dilin sesiyle kısa onay
  langSeen = L;
});
$("voiceSel").onchange = e => { store.set("voice:" + document.documentElement.lang, e.target.value); voiceChanged(); };
$("rate").value = store.get("rate", "1"); $("rate").oninput = e => store.set("rate", e.target.value);
$("chime").checked = store.get("chime", "1") === "1"; $("chime").onchange = e => store.set("chime", e.target.checked ? "1" : "0");

let actx = null;
function chime() {
  if (!$("chime").checked || muted) return Promise.resolve();
  try {
    actx = actx || new (window.AudioContext || window.webkitAudioContext)();
    const t = actx.currentTime;
    [[880, 0], [1320, .14]].forEach(([f, d]) => {
      const o = actx.createOscillator(), g = actx.createGain();
      o.frequency.value = f; o.type = "sine"; g.gain.setValueAtTime(0, t + d);
      g.gain.linearRampToValueAtTime(.18, t + d + .02); g.gain.exponentialRampToValueAtTime(.001, t + d + .35);
      o.connect(g); g.connect(actx.destination); o.start(t + d); o.stop(t + d + .4);
    });
  } catch (e) {}
  return new Promise(r => setTimeout(r, 420));
}
const sentences = t => (t.match(/[^.!?]+[.!?]*/g) || [t]).map(s => s.trim()).filter(Boolean);
function renderText(t) {
  const p = $("nowText"); p.innerHTML = "";
  sentences(t).forEach((s, i) => { const sp = document.createElement("span"); sp.textContent = s + " "; sp.dataset.i = i; p.appendChild(sp); });
}
function setReading(i) { document.querySelectorAll("#nowText span").forEach(s => s.classList.toggle("reading", +s.dataset.i === i)); }
function waveOn(on) { $("wave").classList.toggle("on", on); document.body.classList.toggle("speaking", on); }
const REDUCED = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
function pop(id) { const e = $(id); if (!e || REDUCED) return; e.classList.remove("pop"); void e.offsetWidth; e.classList.add("pop"); }
function swap(...ids) { if (REDUCED) return; ids.forEach(id => { const e = $(id); e.classList.remove("swap"); void e.offsetWidth; e.classList.add("swap"); }); }
function ping(pos, cls) {                    // haritada genişleyen halka
  if (!map || !window.L || REDUCED || !pos) return;
  const m = L.marker(pos, {icon: L.divIcon({className: "", html: '<div class="ping ' + (cls || "") + '"></div>', iconSize: [18, 18], iconAnchor: [9, 9]}),
                           interactive: false, keyboard: false}).addTo(map);
  setTimeout(() => map.removeLayer(m), 1300);
}
function glowParcel(i) {                     // girilen parsel kısa süre parlayıp yerine oturur
  const l = layers[i];
  if (!l || !l.setStyle || REDUCED) return;
  const t0 = performance.now();
  (function step(now) {
    const k = Math.min(1, (now - t0) / 900), e = 1 - Math.pow(1 - k, 3);
    l.setStyle({fillOpacity: .62 - .24 * e, weight: 7 - 3 * e});
    if (k < 1) requestAnimationFrame(step);
  })(t0);
}
document.addEventListener("pointerdown", ev => {     // düğmelerde dokunma dalgası
  const b = ev.target.closest && ev.target.closest("button");
  if (!b || b.disabled || REDUCED) return;
  const r = b.getBoundingClientRect(), d = Math.max(r.width, r.height) * 2.2, sp = document.createElement("span");
  sp.className = "ripple"; sp.style.width = sp.style.height = d + "px";
  sp.style.left = (ev.clientX - r.left - d / 2) + "px"; sp.style.top = (ev.clientY - r.top - d / 2) + "px";
  b.appendChild(sp); setTimeout(() => sp.remove(), 650);
});
// say(metin, {oncelik, vurgu}): öncelikli duyuru kuyruğu boşaltır; vurgu=true ise kartta cümle cümle işaretlenir
async function say(text, opt = {}) {
  lastText = opt.vurgu ? text : lastText;
  if (muted || !synth) return;
  if (opt.oncelik) { queue = []; gen++; synth.cancel(); speaking = false; }
  queue.push({text, vurgu: !!opt.vurgu, zil: !!opt.zil});
  if (!speaking) pump();
}
async function pump() {
  if (!queue.length) { speaking = false; waveOn(false); setReading(-1); return; }
  speaking = true;
  const my = gen;                     // araya öncelikli duyuru girerse bu döngü susar
  const job = queue.shift();
  if (job.zil) await chime();
  const parts = sentences(job.text);
  waveOn(true);
  for (let i = 0; i < parts.length; i++) {
    if (muted || my !== gen) return;
    if (job.vurgu) setReading(i);
    await new Promise(res => {
      const u = new SpeechSynthesisUtterance(window.TarlaUI ? window.TarlaUI.translate(parts[i]).replace(/\s*→\s*/g, ", ") : parts[i]);
      u.lang = ({tr:"tr-TR",en:"en-US",de:"de-DE"})[document.documentElement.lang] || "tr-TR"; u.rate = Math.max(.5, Math.min(2, +$("rate").value * TONE_RATE[pitch])); u.pitch = pitch;
      const name = $("voiceSel").value, v = voices.find(x => x.name === name) || voices[0];
      if (v) u.voice = v;
      u.onend = u.onerror = () => res();
      synth.speak(u);
      setTimeout(res, 20000);         // takılan konuşma motoruna karşı güvenlik
    });
    if (my !== gen) return;           // öncelikli bir duyuru araya girdi
  }
  if (my === gen) pump();
}
function hush() {                           // konuşmayı ANINDA kes, sıradaki duyuruları sil
  gen++; queue = []; speaking = false;
  if (synth) synth.cancel();
  waveOn(false); setReading(-1);
}
function setMuted(m) {
  muted = m; store.set("muted", m ? "1" : "0");
  if (m && synth) { gen++; synth.cancel(); queue = []; speaking = false; waveOn(false); setReading(-1); }
  $("muteBtn").textContent = m ? "🔊 Sesi aç" : "🔇 Sessiz";
}
setMuted(muted);
if (!synth) { $("muteBtn").disabled = true; $("muteBtn").textContent = "Ses desteklenmiyor"; }

// ------------------------------------------------------------------ harita
let map = null, meMarker = null, accCircle = null, trail = null, layers = [], follow = true;
const sinirLL = DATA.sinir;
const meIcon = cls => window.L ? L.divIcon({className: "", html: '<div class="me ' + cls + '"><div class="pulse"></div><div class="cone"></div><div class="dot"></div></div>', iconSize: [22, 22], iconAnchor: [11, 11]}) : null;
if (window.L) {
  map = L.map("map", {zoomControl: true, attributionControl: true});
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    {maxZoom: 20, maxNativeZoom: 19, attribution: "Uydu: Esri, Maxar"}).addTo(map);
  L.polygon(sinirLL, {color: "#ffffff", weight: 2, dashArray: "6 6", fill: false}).addTo(map);
  DATA.parseller.forEach((p, i) => {
    const poly = L.polygon(p.poly, {color: "#37a06b", weight: 2, fillColor: "#7cf0a8", fillOpacity: .12}).addTo(map);
    poly.bindTooltip(p.ad, {permanent: true, direction: "center", className: "plabel"});
    poly.on("click", () => { show(p, false); say(p.metin, {oncelik: true, vurgu: true, zil: true}); });
    layers.push(poly);
  });
  trail = L.polyline([], {color: "#e8c07d", weight: 3, opacity: .75}).addTo(map);
  map.fitBounds(L.latLngBounds(sinirLL), {padding: [40, 40]});
  map.on("dragstart", () => { follow = false; $("recenter").classList.remove("hide"); });
} else {
  $("map").innerHTML = '<div style="padding:24px;color:#8b9c92">Harita yüklenemedi (internet gerekli). Konum ve sesli öneriler yine çalışır.</div>';
}
$("recenter").onclick = () => { follow = true; $("recenter").classList.add("hide"); if (lastPos && map) map.setView(lastPos, Math.max(map.getZoom(), 17)); };

// ------------------------------------------------------------------ parsel / konum
let current = null, candidate = null, candCount = 0, lastPos = null, lastFixT = 0, lastHeading = null;
let lastGuide = {t: 0, d: null}, mode = null;
function show(p, enter = true) {
  layers.forEach((l, i) => l.setStyle && l.setStyle({fillOpacity: DATA.parseller[i] === p ? .38 : .12,
    weight: DATA.parseller[i] === p ? 4 : 2, color: DATA.parseller[i] === p ? "#7cf0a8" : "#37a06b"}));
  if (!p) {
    $("parcelChip").textContent = "Parsel: dışarıda"; $("nowEyebrow").textContent = "TARLA DIŞI";
    $("nowTitle").textContent = "Tarla sınırının dışındasınız"; $("nowSeq").innerHTML = "";
    swap("nowEyebrow", "nowTitle"); pop("parcelChip");
    return;
  }
  if ($("parcelChip").textContent !== p.ad) pop("parcelChip");
  $("parcelChip").textContent = p.ad; $("parcelChip").className = "chip on";
  $("nowEyebrow").textContent = "ŞU AN · " + p.yon.toUpperCase() + (p.egim == null ? "" : " · EĞİM %" + tr1(p.egim));
  $("nowTitle").textContent = p.ad;
  renderText(p.metin);
  $("nowSeq").innerHTML = ""; p.rotasyon.forEach(s => { const e = document.createElement("span"); e.textContent = s; $("nowSeq").appendChild(e); });
  if (enter) {
    $("now").classList.remove("enter"); void $("now").offsetWidth; $("now").classList.add("enter");
    swap("nowEyebrow", "nowTitle", "nowText");
    glowParcel(DATA.parseller.indexOf(p));
    ping(lastPos, "parcel");
  }
}
function guide(pos, force) {
  const [q, d] = nearestOnField(pos);
  const dir = dirName(bearing(pos, q));
  if ($("distChip").hidden) pop("distChip");
  $("distChip").hidden = false; $("distChip").textContent = "Tarlaya " + fmtDistShort(d) + " · " + dir;
  const now = Date.now(), moved = lastGuide.d == null || Math.abs(d - lastGuide.d) > Math.max(30, lastGuide.d * .25);
  if (force || (now - lastGuide.t > 90000 && moved)) {
    say("Tarlaya " + fmtDist(d) + ", " + dir + " yönünde.", {});
    lastGuide = {t: now, d};
  }
}
function update(la, lo, acc, heading, speed) {
  const pos = [la, lo];
  if (lastPos && heading == null) {      // yön verilmezse hareketten hesapla
    if (dist(lastPos, pos) > Math.max(3, (acc || 0) * .5)) heading = bearing(lastPos, pos);
  }
  if (heading != null && !isNaN(heading)) lastHeading = heading;
  lastPos = pos; lastFixT = Date.now();
  if (map) {
    if (!meMarker) {
      meMarker = L.marker(pos, {icon: meIcon(mode === "sim" ? "tractor" : ""), zIndexOffset: 1000, keyboard: false}).addTo(map);
      if (acc) accCircle = L.circle(pos, {radius: acc, color: "#4aa3ff", weight: 1, fillOpacity: .08}).addTo(map);
      map.setView(pos, Math.max(map.getZoom(), 17));
    } else {
      meMarker.setLatLng(pos);
      if (accCircle && acc) { accCircle.setLatLng(pos); accCircle.setRadius(acc); }
    }
    const el = meMarker.getElement && meMarker.getElement();
    const cone = el && el.querySelector(".cone");
    if (cone && lastHeading != null) { cone.style.display = "block"; cone.style.transform = "rotate(" + lastHeading + "deg)"; }
    trail.addLatLng(pos);
    const ll = trail.getLatLngs(); if (ll.length > 600) trail.setLatLngs(ll.slice(-600));
    if (follow) map.panTo(pos, {animate: true, duration: .5});
  }
  if (speed != null && !isNaN(speed)) { $("spdChip").hidden = false; $("spdChip").textContent = tr1(speed * 3.6) + " km/sa"; }
  // parsel tespiti: aynı parselde 2 ardışık konum = giriş (GPS zıplamasına karşı)
  let p = DATA.parseller.find(q => inPoly(la, lo, q.poly)) || null;
  if (!p && DATA.parseller.length && inPoly(la, lo, sinirLL))   // tarla içinde ama parsel dışı dilim: en yakın parsel
    p = DATA.parseller.reduce((best, q) => dist(pos, [q.lat, q.lon]) < dist(pos, [best.lat, best.lon]) ? q : best);
  const key = p ? p.ad : "_out";
  // ±40 m'den kötü konum (Wi-Fi/baz istasyonu tahmini) parsel değiştirmez; işaretçi yine hareket eder
  if (acc != null && acc > 40) { if (!p && current === null) guide(pos, false); return; }
  if (key === candidate) candCount++; else { candidate = key; candCount = 1; }
  if (candCount >= 2 && current !== key) {
    const was = current; current = key; show(p);
    if (p) { say(p.metin, {oncelik: true, vurgu: true, zil: true}); logLine(p.ad + " girişi · öneri okundu"); }
    else if (was) { say("Tarla sınırından çıktınız.", {oncelik: true}); logLine("Tarla dışına çıkıldı"); }
  }
  if (!p) guide(pos, current === null && candCount === 2 && mode === "gps"); else $("distChip").hidden = true;
}

// ------------------------------------------------------------------ canlı GPS
let gpsId = null, wakeLock = null;
const GPS_ERR = {1: "Konum izni verilmedi. Tarayıcının adres çubuğundaki konum simgesinden izin verin; Windows'ta Ayarlar > Gizlilik > Konum açık olmalı.",
                 2: "Konum bulunamadı. Açık havaya çıkın ya da Wi-Fi'yi açık tutun.", 3: "Konum zaman aşımına uğradı; tekrar deneniyor."};
function stopGps() {
  if (gpsId !== null) navigator.geolocation.clearWatch(gpsId);
  gpsId = null; mode = null;
  $("gpsBtn").textContent = "⌖ Canlı GPS"; $("gpsBtn").className = "primary";
  $("gpsChip").textContent = "GPS kapalı"; $("gpsChip").className = "chip";
  if (wakeLock) { wakeLock.release().catch(() => {}); wakeLock = null; }
}
function startGps() {
  if (gpsId !== null) { stopGps(); logLine("GPS durduruldu"); return; }
  if (simTimer) simulate();
  if (!("geolocation" in navigator)) { logLine("Bu tarayıcı konum desteklemiyor."); return; }
  mode = "gps"; follow = true; $("recenter").classList.add("hide");
  $("gpsChip").textContent = "GPS bekleniyor…"; $("gpsChip").className = "chip warn";
  $("gpsBtn").textContent = "■ GPS'i durdur"; $("gpsBtn").className = "live";
  if (meMarker && map) { map.removeLayer(meMarker); meMarker = null; }
  if (accCircle && map) { map.removeLayer(accCircle); accCircle = null; }
  current = null; candidate = null; candCount = 0; trail && trail.setLatLngs([]);
  lastPos = null; lastHeading = null; lastFixT = 0; lastGuide = {t: 0, d: null};
  gpsId = navigator.geolocation.watchPosition(pos => {
    const c = pos.coords;
    $("gpsChip").textContent = "Canlı · ±" + Math.round(c.accuracy) + " m";
    $("gpsChip").className = c.accuracy <= 30 ? "chip on" : "chip warn";
    update(c.latitude, c.longitude, c.accuracy, c.heading, c.speed);
  }, err => {
    $("gpsChip").textContent = "GPS hatası"; $("gpsChip").className = "chip bad";
    logLine("GPS: " + (GPS_ERR[err.code] || err.message));
    if (err.code === 1) { banner(GPS_ERR[1]); stopGps(); }
  }, {enableHighAccuracy: true, maximumAge: 0, timeout: 15000});
  keepAwake();
  if (!muted) say("Canlı konum açıldı.", {});
}
setInterval(() => {                         // 20 sn konum gelmezse uyar
  if (mode === "gps" && lastFixT && Date.now() - lastFixT > 20000) { $("gpsChip").textContent = "Sinyal zayıf…"; $("gpsChip").className = "chip warn"; }
}, 5000);

// ------------------------------------------------------------------ simülasyon (gerçek koordinatlarda)
let simTimer = null, simRoute = null;
// Rota seçilen tarlanın biçimine göre kurulur: şeritler tarlanın en uzun kenarına paraleldir,
// her şerit yalnızca tarla sınırının İÇİNDE kalan aralıkta gidilir (sınırdan birkaç metre içeride).
// Traktör tarlaya tek bir kısa yaklaşma parçasıyla girer; sonrasında tarlanın içinde kalır.
function simPath(ring) {
  const n = ring.length;
  const laC = ring.reduce((s, p) => s + p[0], 0) / n, loC = ring.reduce((s, p) => s + p[1], 0) / n;
  const kx = R * rad * Math.cos(laC * rad), ky = R * rad;
  const P = ring.map(p => [(p[1] - loC) * kx, (p[0] - laC) * ky]);      // yerel düzlem, metre
  let ang = 0, longest = 0;
  for (let i = 0; i < n; i++) {
    const a = P[i], b = P[(i + 1) % n], L_ = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (L_ > longest) { longest = L_; ang = Math.atan2(b[1] - a[1], b[0] - a[0]); }
  }
  const c = Math.cos(-ang), s = Math.sin(-ang);
  const Q = P.map(([x, y]) => [x * c - y * s, x * s + y * c]);          // en uzun kenar yatay
  const back = ([x, y]) => [laC + (-x * s + y * c) / ky, loC + (x * c + y * s) / kx];
  const ys = Q.map(q => q[1]), y0 = Math.min(...ys), y1 = Math.max(...ys), H = y1 - y0;
  const lanes = Math.max(4, Math.min(12, Math.round(H / 20)));
  const runs = [];                            // tarla içinde kalan şerit parçaları
  for (let i = 0; i < lanes; i++) {
    const y = y1 - H * (i + .5) / lanes, xs = [];
    for (let j = 0; j < n; j++) {             // şerit çizgisinin tarla sınırını kestiği yerler
      const a = Q[j], b = Q[(j + 1) % n];
      if ((a[1] > y) !== (b[1] > y)) xs.push(a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]));
    }
    xs.sort((u, v) => u - v);
    for (let j = 0; j + 1 < xs.length; j += 2) {
      const w = xs[j + 1] - xs[j], m = Math.min(3, w * .1);             // sınırdan içeri pay
      if (w >= 4) runs.push([[xs[j] + m, y], [xs[j + 1] - m, y]]);
    }
  }
  if (!runs.length) return null;
  // Sıra: her seferinde en yakın ucu olan parçaya geç. Düz tarlada bildik gidiş-dönüş çıkar;
  // L ya da U biçimli tarlada önce bir kol bitirilir, boşluğun üstünden defalarca geçilmez.
  const pts = [];
  let cur = runs.shift();
  pts.push(cur[0], cur[1]);
  while (runs.length) {
    const p = pts[pts.length - 1];
    let bi = 0, bd = Infinity, flip = false;
    runs.forEach((r, i) => {
      const d0 = Math.hypot(r[0][0] - p[0], r[0][1] - p[1]), d1 = Math.hypot(r[1][0] - p[0], r[1][1] - p[1]);
      if (d0 < bd) { bd = d0; bi = i; flip = false; }
      if (d1 < bd) { bd = d1; bi = i; flip = true; }
    });
    cur = runs.splice(bi, 1)[0];
    if (flip) pts.push(cur[1], cur[0]); else pts.push(cur[0], cur[1]);
  }
  const A = pts[0], B = pts[1], L_ = Math.hypot(A[0] - B[0], A[1] - B[1]) || 1, e = Math.max(8, Math.min(20, L_ * .08));
  pts.unshift([A[0] + (A[0] - B[0]) / L_ * e, A[1] + (A[1] - B[1]) / L_ * e]);   // tarlaya giriş
  return pts.map(back);
}
function insideShare(path, ring) {            // yolun tarla içinde kalan payı (0-1)
  let inside = 0, total = 0;
  for (let i = 0; i + 1 < path.length; i++) {
    const a = path[i], b = path[i + 1], k = Math.max(1, Math.round(dist(a, b) / 2));
    for (let j = 0; j < k; j++) {
      const t = (j + .5) / k;
      total++; if (inPoly(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, ring)) inside++;
    }
  }
  return total ? inside / total : 0;
}
function resetCard() {                      // kartı ve parselleri ilk hâline döndür
  layers.forEach(l => l.setStyle && l.setStyle({fillOpacity: .12, weight: 2, color: "#37a06b"}));
  $("parcelChip").textContent = "Parsel: —"; $("parcelChip").className = "chip";
  $("distChip").hidden = true; $("spdChip").hidden = true;
  $("nowEyebrow").textContent = "ŞU AN"; $("nowTitle").textContent = "Tarlaya girilmedi";
  $("nowText").textContent = "Simülasyon başladı. Bir parsele girildiğinde öneri otomatik okunur.";
  $("nowSeq").innerHTML = "";
}
function stopSim(silence) {                 // silence=true: okuma da anında kesilir
  if (!simTimer) return;
  clearInterval(simTimer); simTimer = null; mode = null;
  if (silence) hush();
  $("simBtn").textContent = "▶ Simülasyon"; $("simBtn").className = "";
  if (simRoute && map) { map.removeLayer(simRoute); simRoute = null; }
  setTimeout(() => { if (!simTimer) $("prog").classList.remove("on"); }, 900);
  $("gpsChip").textContent = "GPS kapalı"; $("gpsChip").className = "chip";
}
function startSim() {                       // her çağrıda en baştan: rota, iz, kart ve okuma sıfırlanır
  stopSim(true);
  if (gpsId !== null) stopGps();
  hush();
  mode = "sim"; follow = true; $("recenter").classList.add("hide");
  if (meMarker && map) { map.removeLayer(meMarker); meMarker = null; }
  if (accCircle && map) { map.removeLayer(accCircle); accCircle = null; }
  let path = simPath(sinirLL);
  if (!path) {                                // sınır çok dar ya da bozuksa: tarlanın ortasından geç
    const las = sinirLL.map(p => p[0]), los = sinirLL.map(p => p[1]);
    const la = (Math.min(...las) + Math.max(...las)) / 2;
    path = [[la, Math.min(...los)], [la, Math.max(...los)]];
  }
  if (map) simRoute = L.polyline(path, {color: "#e8c07d", weight: 2, opacity: .65, dashArray: "4 7", interactive: false,
                                        className: "route-flow"}).addTo(map);
  const segLen = []; let total = 0;
  for (let i = 0; i + 1 < path.length; i++) { segLen.push(total); total += dist(path[i], path[i + 1]); }
  $("prog").classList.add("on"); $("progBar").style.width = "0%";
  logLine("Rota tarlaya göre kuruldu · yolun %" + Math.round(insideShare(path, sinirLL) * 100) + "'i tarla içinde");
  let seg = 0, t = 0; current = null; candidate = null; candCount = 0; trail && trail.setLatLngs([]);
  lastPos = null; lastHeading = null; lastText = ""; lastGuide = {t: 0, d: null};
  resetCard();
  $("gpsChip").textContent = "Simülasyon"; $("gpsChip").className = "chip warn";
  $("simBtn").textContent = "■ Simülasyonu durdur"; $("simBtn").className = "live";
  say("Simülasyon başladı. Parsellere girdikçe öneriler okunacak.", {});
  simTimer = setInterval(() => {
    const talking = speaking && !muted;
    const out = lastPos && seg > 0 && !inPoly(lastPos[0], lastPos[1], sinirLL);   // içbükey tarlada kısa geçiş
    const mps = +$("speed").value * 4 * (talking ? .15 : 1) * (out ? 3 : 1);      // m/sn; dışarıda hızlan
    const a = path[seg], b = path[seg + 1], L_ = dist(a, b) || 1;
    t += mps * .1 / L_;
    if (t >= 1) { t = 0; seg++; if (seg >= path.length - 1) { $("progBar").style.width = "100%"; stopSim(false); logLine("Simülasyon bitti"); return; } }
    const la = a[0] + (b[0] - a[0]) * t, lo = a[1] + (b[1] - a[1]) * t;
    $("progBar").style.width = (total ? (segLen[seg] + L_ * t) / total * 100 : 0).toFixed(1) + "%";
    update(la, lo, null, bearing(a, b), mps);
  }, 100);
}
function simulate() {                       // Simülasyon düğmesi: çalışıyorsa durdur, değilse başlat
  if (simTimer) { stopSim(true); logLine("Simülasyon durduruldu"); } else startSim();
}

// ------------------------------------------------------------------ düğmeler ve sesli komut
function whereAmI() {
  ping(lastPos);
  if (!lastPos) { say("Konum henüz yok. Canlı GPS'i açın.", {oncelik: true}); return; }
  const p = DATA.parseller.find(q => inPoly(lastPos[0], lastPos[1], q.poly));
  if (p) say(p.ad + ", " + p.yon + " bölümündesiniz.", {oncelik: true});
  else { const [q, d] = nearestOnField(lastPos); say("Tarlanın dışındasınız. Tarlaya " + fmtDist(d) + ", " + dirName(bearing(lastPos, q)) + " yönünde.", {oncelik: true}); }
}
$("gpsBtn").onclick = startGps;
$("simBtn").onclick = simulate;
$("resetBtn").onclick = () => { startSim(); logLine("Simülasyon baştan başlatıldı"); };
$("repeatBtn").onclick = () => say(lastText || "Henüz bir parsele girilmedi.", {oncelik: true, vurgu: !!lastText});
$("muteBtn").onclick = () => setMuted(!muted);
$("whereBtn").onclick = whereAmI;
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (SR) {
  $("micBtn").hidden = false;
  const rec = new SR(); rec.lang = document.documentElement.lang; rec.interimResults = false; rec.maxAlternatives = 3;
  let listening = false;
  rec.onresult = e => {
    const said = Array.from(e.results[0]).map(r => r.transcript.toLocaleLowerCase(document.documentElement.lang)).join(" | ");
    $("heard").textContent = "Duyulan: “" + e.results[0][0].transcript + "”";
    if (/tekrar|repeat|again|wieder/.test(said)) $("repeatBtn").click();
    else if (/nerede|konum|where|location|wo bin|standort/.test(said)) whereAmI();
    else if (/sus|sessiz|\b(mute|silent|stumm)\b/.test(said)) setMuted(true);
    else if (/sesi aç|konuş|unmute|speak|sprechen/.test(said)) { setMuted(false); say("Ses açık.", {}); }
    else if (/simülasyon|simulation/.test(said)) simulate();
    else if (/gps|canlı|live/.test(said)) startGps();
    else say("Anlayamadım. Tekrar, neredeyim, sessiz ya da simülasyon diyebilirsiniz.", {oncelik: true});
  };
  rec.onend = () => { listening = false; $("micBtn").className = ""; $("micBtn").textContent = "🎤 Sesli komut"; };
  rec.onerror = e => { $("heard").textContent = "Mikrofon: " + e.error; };
  $("micBtn").onclick = () => {
    if (listening) { rec.stop(); return; }
    try { synth && synth.cancel(); rec.lang = document.documentElement.lang; rec.start(); listening = true; $("micBtn").className = "live listening"; $("micBtn").textContent = "● Dinleniyor…"; $("heard").textContent = "Komut: tekrar · neredeyim · sessiz · simülasyon"; }
    catch (e) { $("heard").textContent = "Mikrofon başlatılamadı."; }
  };
}
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && mode === "gps" && "wakeLock" in navigator && !wakeLock)
    keepAwake();
});
function keepAwake() {
  if (!("wakeLock" in navigator) || wakeLock) return;
  navigator.wakeLock.request("screen").then(w => { wakeLock = w; w.addEventListener("release", () => { wakeLock = null; }); }).catch(() => {});
}
window.__saha = {update, inPoly, nearestOnField, startSim, stopSim, hush, state: () => ({current, mode, queue: queue.length, speaking, lastPos})};
</script>
</body>
</html>
"""


def build_page(name, parcels, boundary=None):
    """parcels: [{ad, yon, poly, lat, lon, egim, metin, rotasyon[]}]; boundary: [[lat, lon]...]"""
    if not boundary:                       # sınır yoksa parsellerin dış kutusu
        las = [q[0] for p in parcels for q in p["poly"]]
        los = [q[1] for p in parcels for q in p["poly"]]
        if not las:
            raise ValueError("Saha modu için önce haritada tarla sınırı çizin.")
        boundary = [[max(las), min(los)], [max(las), max(los)], [min(las), max(los)],
                    [min(las), min(los)]]
    data = {
        "sinir": [[float(a), float(b)] for a, b in boundary],
        "tarla": name,
        "tarih": time.strftime("%d.%m.%Y %H:%M"),
        "parseller": parcels,
        "uyari": ("Bu asistan karar verici değildir; NASA verilerini analiz eden bir rehberdir. "
                  "Öneriler aylık iklim ortalamaları ve yaklaşık toprak profiline dayanır. "
                  "Son karar her zaman çiftçinin yerel tecrübesine aittir; ziraat mühendisinize "
                  "danışın. Sürüş sırasında ekrana bakmayın, sesli duyuruları dinleyin."),
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return PAGE.replace("__DATA__", blob)


def parcels_from(res, harm, parcel_list, slopes, per_parcel=None):
    """Optimizasyon sonucundan sayfaya gömülecek parsel kayıtlarını üret.

    per_parcel: {ad: optimize() sonucu} — parsel bazlı (eğime göre) çalıştırma varsa.
    """
    out = []
    for p in parcel_list:
        r = (per_parcel or {}).get(p["ad"], res)
        sl = slopes.get(p["ad"])
        best = r["stratejiler"][0]
        rot = [n + (" + örtü" if c else "") for n, c in zip(best["ekinler"], best["ortu"])]
        out.append(dict(ad=p["ad"], yon=p["yon"], poly=p["poly"], lat=p["lat"], lon=p["lon"],
                        egim=None if sl is None else round(sl, 1),
                        metin=to.parcel_advice(p, r, harm, sl), rotasyon=rot))
    return out


def twin_sentence(pt):
    """Derin Uzay ikizinden parsel için kısa sesli cümle."""
    m = pt["mevcut"]
    s = f"Bu parselde azot kaybı göstergesi yüzde {m['azot_kaybi']:.0f}."
    if pt["entropi_azalma"] >= 5:
        s += (f" Derin köklü baklagil ve kışlık örtüyle entropi yüzde {pt['entropi_azalma']:.0f} "
              f"azalır, sızma üç yılda yüzde {pt['sizma_artis']:.0f} artar.")
    return s


def edge_path():
    """Windows'ta msedge.exe yolu; bulunamazsa None."""
    if os.name != "nt":
        return None
    for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(var)
        if base:
            exe = os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe")
            if os.path.isfile(exe):
                return exe
    return shutil.which("msedge")


def open_app_window(url, width=1200, height=820):
    """Saha sayfasını Edge'in UYGULAMA KİPİNDE aç: adres çubuğu ve sekme olmayan ayrı pencere.

    Uygulamanın kendi web penceresi (WebView2) yalnızca Windows'a kurulu sesleri görür;
    Türkçe için çoğunlukla tek ses vardır. Edge penceresinde çevrimiçi doğal sesler de
    listelenir. Edge yoksa ya da başlatılamazsa False döner (çağıran eski pencereye düşer).
    """
    exe = edge_path()
    if not exe:
        return False
    try:
        subprocess.Popen([exe, "--app=" + url, "--window-size=%d,%d" % (width, height)],
                         close_fds=True)
        return True
    except OSError:
        return False


def open_in_browser(url):
    """Saha sayfasını Edge'de aç (önce uygulama kipi, olmazsa olağan tarayıcı penceresi)."""
    if open_app_window(url):
        return True
    try:
        if os.name == "nt":
            os.startfile("microsoft-edge:" + url)
            return True
    except OSError:
        pass
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def write_and_open(html, folder, filename="saha_modu.html", open_page=True):
    path = os.path.join(folder, filename)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(html)
    try:
        if open_page:
            webbrowser.open("file:///" + os.path.abspath(path).replace("\\", "/").lstrip("/"))
    except Exception:
        pass
    return path
