#!/usr/bin/env python3
"""Tarla Pusulası — haritadan tarla seçimi (v2.4).

Kullanıcının tarayıcısında bir uydu haritası açar; kullanıcı tarlasının
köşelerine tıklayarak sınırı çizer ve "Bu tarlayı kullan" der. Sınır yalnızca
bu bilgisayardaki uygulamaya (127.0.0.1) gönderilir.

Yalnızca Python standart kütüphanesini kullanır (pip gerekmez), API anahtarı
istemez. Harita katmanları:
  • Esri World Imagery (yüksek çözünürlüklü uydu, tarla sınırı çizmek için)
  • OpenStreetMap (sokak haritası)
  • NASA GIBS · MODIS Terra gerçek renk + NDVI (bitki örtüsü) katmanları

Tek başına deneme:  python tarla_harita.py
"""
import hmac
import json
import math
import mimetypes
from pathlib import Path
import secrets
import threading
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import tarla_gorsel
import tarla_gorunum
import tarla_kaynak

MAX_BODY = 3 * 1024 * 1024  # istek gövdesi sınırı (tarla görseli ≈ 1 MB base64)
MAX_POINTS = 200          # bir tarlada en fazla köşe
R_EARTH = 6371008.8       # m


# ---------------------------------------------------------------- geometri
def _project(points):
    """(enlem, boylam) listesini, ortalama noktaya göre metre cinsinden düzleme aç."""
    lat0 = sum(p[0] for p in points) / len(points)
    lon0 = sum(p[1] for p in points) / len(points)
    k = math.cos(math.radians(lat0))
    xy = [(math.radians(lon - lon0) * R_EARTH * k, math.radians(lat - lat0) * R_EARTH)
          for lat, lon in points]
    return xy, lat0, lon0, k


def field_geometry(points):
    """Köşe listesi -> alan (m²) ve ağırlık merkezi (enlem, boylam).

    Yerel düzlem yaklaşımıyla yaklaşık alan verir; kadastro ölçümü değildir.
    1 ya da 2 nokta verilirse alan 0, merkez noktaların ortalamasıdır.
    """
    if not points:
        raise ValueError("Önce haritada konum veya tarla sınırı seçin.")
    xy, lat0, lon0, k = _project(points)
    if len(points) < 3:
        return 0.0, lat0, lon0
    a = cx = cy = 0.0
    for i, (x1, y1) in enumerate(xy):
        x2, y2 = xy[(i + 1) % len(xy)]
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    a *= 0.5
    if abs(a) < 1e-6:                       # köşeler aynı doğru üzerinde
        return 0.0, lat0, lon0
    cx, cy = cx / (6 * a), cy / (6 * a)
    lat = lat0 + math.degrees(cy / R_EARTH)
    lon = lon0 + math.degrees(cx / (R_EARTH * k))
    return abs(a), lat, lon


def clean_points(raw):
    """Tarayıcıdan gelen veriyi doğrula; geçersizse ValueError."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= MAX_POINTS:
        raise ValueError("Köşe sayısı 1 ile %d arasında olmalı." % MAX_POINTS)
    out = []
    for p in raw:
        if (not isinstance(p, (list, tuple)) or len(p) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in p)):
            raise ValueError("Köşe biçimi [enlem, boylam] olmalı.")
        lat, lon = float(p[0]), float(p[1])
        if not (math.isfinite(lat) and math.isfinite(lon)
                and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Koordinat aralık dışında.")
        out.append((round(lat, 6), round(lon, 6)))
    return out


def describe_field(points, image=None):
    """Doğrulanmış köşelerden uygulamanın kullanacağı tarla kaydını üret.

    image: tarayıcının gönderdiği uydu görseli ({'w','h','rgb','poly'}); geçerliyse
    kayda 'gorsel' (tarla_gorsel.FieldImage) olarak eklenir, geçersizse yok sayılır.
    """
    pts = clean_points(points)
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()  # kapalı GeoJSON halkasını da kabul et
    if len(set(pts)) != len(pts):
        raise ValueError("Aynı köşe birden fazla seçilmiş. Yinelenen köşeyi kaldırın.")
    if len(pts) == 2:
        raise ValueError("Konum için tek nokta, tarla sınırı için en az üç köşe seçin.")
    if any(abs(p[0]) >= 85.051129 for p in pts):
        raise ValueError("Bu harita kutup bölgelerini desteklemiyor.")
    if len(pts) >= 3:
        xy, *_ = _project(pts)
        def cross(a, b, c):
            return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
        def on_segment(a, b, p):
            return (abs(cross(a, b, p)) < 1e-7 and
                    min(a[0], b[0])-1e-7 <= p[0] <= max(a[0], b[0])+1e-7 and
                    min(a[1], b[1])-1e-7 <= p[1] <= max(a[1], b[1])+1e-7)
        for i, a in enumerate(xy):
            b = xy[(i+1) % len(xy)]
            for j in range(i+1, len(xy)):
                if j == i+1 or (i == 0 and j == len(xy)-1):
                    continue
                c, d = xy[j], xy[(j+1) % len(xy)]
                if (cross(a,b,c)*cross(a,b,d) < 0 and cross(c,d,a)*cross(c,d,b) < 0
                        or any((on_segment(a,b,c), on_segment(a,b,d),
                                on_segment(c,d,a), on_segment(c,d,b)))):
                    raise ValueError("Tarla sınırı kendi üzerinden geçiyor. Köşeleri çevre boyunca sırayla seçin.")
    area, lat, lon = field_geometry(pts)
    if len(pts) >= 3 and area < 1:
        raise ValueError("Tarla alanı oluşmadı. Aynı çizgi üzerinde olmayan en az üç köşe seçin.")
    field = {"lat": round(lat, 5), "lon": round(lon, 5),
             "alan_m2": round(area, 1), "alan_dekar": round(area / 1000.0, 2),
             "kose": len(pts), "noktalar": [list(p) for p in pts], "gorsel": None}
    if image and len(pts) >= 3:
        try:
            field["gorsel"] = tarla_gorsel.FieldImage.from_payload(image)
        except (ValueError, TypeError):
            pass
    return field


def area_label(field):
    """'42,5 dekar (4,25 ha)' gibi okunur alan metni; alan yoksa boş."""
    da = (field or {}).get("alan_dekar") or 0
    if da <= 0:
        return ""
    txt = ("%.1f" % da if da < 100 else "%.0f" % da).replace(".", ",")
    return "%s dekar (%s ha)" % (txt, ("%.2f" % (da / 10)).replace(".", ","))


# ---------------------------------------------------------------- yer adı
def reverse_name(lat, lon, timeout=6):
    """Koordinat -> 'İlçe, İl' (OpenStreetMap Nominatim). Olmazsa None döner."""
    url = "https://nominatim.openstreetmap.org/reverse?" + urllib.parse.urlencode(
        {"format": "jsonv2", "lat": "%.5f" % lat, "lon": "%.5f" % lon,
         "zoom": 10, "accept-language": "tr"})
    req = urllib.request.Request(url, headers={
        "User-Agent": "TarlaPusulasi/2.4 (NASA Space Apps; masaustu uygulama)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            adr = json.load(r).get("address") or {}
    except Exception:
        return None
    ilce = next((adr[k] for k in ("town", "city_district", "county", "municipality",
                                  "city", "village") if adr.get(k)), None)
    il = next((adr[k] for k in ("province", "state", "region") if adr.get(k)), None)
    parts = [p for p in (ilce, il) if p]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    return ", ".join(parts) or None


# ---------------------------------------------------------------- sunucu
class MapServer:
    """Tek kullanıcılık, yalnızca 127.0.0.1'e bağlı küçük harita sunucusu.

    on_field(field) geri çağrısı SUNUCU İŞ PARÇACIĞINDAN çağrılır; arayüz
    tarafında bir kuyruğa bırakılmalıdır (tkinter iş parçacığı güvenli değil).
    """

    def __init__(self, on_field):
        self.on_field = on_field
        self.on_save = None
        self.token = secrets.token_urlsafe(18)
        self.state = {"center": [39.0, 35.2], "zoom": 6, "points": []}
        self._lock = threading.Lock()
        self._httpd = None
        # ek sayfalar / uçlar (ör. Mission Control): yol -> işlev
        self.get_routes = {}      # yol -> f() -> (içerik türü, bayt)
        self.post_routes = {}     # yol -> f(json gövde) -> sözlük

    # -- yaşam döngüsü
    def start(self):
        if self._httpd:
            return
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._httpd.daemon_threads = True
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

    @property
    def port(self):
        return self._httpd.server_address[1]

    @property
    def url(self):
        return "http://127.0.0.1:%d/?t=%s" % (self.port, self.token)

    def page_url(self, path):
        self.start()
        return "http://127.0.0.1:%d%s?t=%s" % (self.port, path, self.token)

    def prepare(self, center=None, points=None, zoom=None, name=""):
        """Haritayı tarayıcıda aç. center=(enlem, boylam), points=mevcut sınır."""
        self.start()
        with self._lock:
            self.state["points"] = [list(p) for p in points] if points else []
            self.state["name"] = name
            self.state["can_save"] = self.on_save is not None
            if center:
                self.state["center"] = [float(center[0]), float(center[1])]
                self.state["zoom"] = zoom or (16 if points else 12)
        return self.url

    def open(self, center=None, points=None, zoom=None):
        return webbrowser.open(self.prepare(center, points, zoom))

    # -- istek işleyici
    def _handler(self):
        srv = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "TarlaPusulasi"
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):          # konsolu kirletme
                pass

            def _send(self, code, body, ctype="application/json; charset=utf-8"):
                data = body if isinstance(body, bytes) else json.dumps(
                    body, ensure_ascii=False).encode("utf-8")
                if "text/html" in ctype:
                    page = tarla_gorunum.decorate_html(data.decode("utf-8"), "/ui?t=" + srv.token)
                    data = page.encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
                self.end_headers()
                self.wfile.write(data)

            def _allowed(self):
                """Yalnızca bu oturumun anahtarıyla ve yerel adresten gelen istekler."""
                host = (self.headers.get("Host") or "").lower()
                port = self.server.server_address[1]
                if host not in ("127.0.0.1:%d" % port, "localhost:%d" % port):
                    return False
                parsed = urllib.parse.urlsplit(self.path)
                if parsed.path.startswith('/assets/'):
                    parts = parsed.path.split('/')
                    return len(parts) >= 4 and hmac.compare_digest(parts[2], srv.token)
                q = urllib.parse.parse_qs(parsed.query)
                return hmac.compare_digest((q.get("t") or [""])[0], srv.token)

            def do_GET(self):
                path = urllib.parse.urlsplit(self.path).path
                if not self._allowed():
                    return self._send(403, {"ok": False, "hata": "Yetkisiz istek."})
                if path.startswith('/assets/'):
                    name = '/'.join(path.split('/')[3:])
                    allowed = {'leaflet.js', 'leaflet.css', 'images/layers.png',
                               'images/layers-2x.png', 'images/marker-icon.png',
                               'images/marker-icon-2x.png', 'images/marker-shadow.png'}
                    if name not in allowed:
                        return self._send(404, {"ok": False})
                    root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
                    try:
                        data = (root / 'assets' / 'leaflet' / name).read_bytes()
                    except OSError:
                        return self._send(404, {"ok": False, "hata": "Harita dosyası eksik. Uygulamayı yeniden derleyin."})
                    return self._send(200, data, mimetypes.guess_type(name)[0] or 'application/octet-stream')
                if path == "/ui":
                    return self._send(200, tarla_gorunum.state())
                if path == '/kaynaklar':
                    return self._send(200, tarla_kaynak.page().encode('utf-8'), 'text/html; charset=utf-8')
                if path == "/":
                    return self._send(200, PAGE.replace("__TOKEN__", srv.token).encode("utf-8"),
                                      "text/html; charset=utf-8")
                if path == "/durum":
                    with srv._lock:
                        return self._send(200, dict(srv.state))
                if path in srv.get_routes:
                    try:
                        ctype, body = srv.get_routes[path]()
                    except Exception as exc:
                        return self._send(500, {"ok": False, "hata": str(exc)})
                    return self._send(200, body, ctype)
                self._send(404, {"ok": False, "hata": "Bulunamadı."})

            def do_POST(self):
                path = urllib.parse.urlsplit(self.path).path
                if not self._allowed():
                    return self._send(403, {"ok": False, "hata": "Yetkisiz istek."})
                if path in srv.post_routes:
                    try:
                        n = int(self.headers.get("Content-Length") or 0)
                        body = json.loads(self.rfile.read(n)) if 0 < n <= 65536 else {}
                        return self._send(200, srv.post_routes[path](body))
                    except Exception as exc:
                        return self._send(500, {"ok": False, "hata": str(exc) or
                                                exc.__class__.__name__})
                if path != "/tarla":
                    return self._send(404, {"ok": False, "hata": "Bulunamadı."})
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    n = -1
                if not 0 < n <= MAX_BODY:
                    return self._send(413, {"ok": False, "hata": "İstek çok büyük ya da boş."})
                try:
                    body = json.loads(self.rfile.read(n))
                    field = describe_field(body.get("points"), body.get("image"))
                    saving = body.get("kaydet") is True
                    if saving:
                        if field["kose"] < 3:
                            raise ValueError("Kaydetmek için en az 3 köşe işaretle.")
                    ad = body.get("ad")
                    if isinstance(ad, str):
                        field["kayit_adi"] = " ".join(ad.split())[:60]
                except (ValueError, AttributeError, UnicodeDecodeError) as exc:
                    return self._send(400, {"ok": False, "hata": str(exc) or "Geçersiz veri."})
                try:
                    if saving:
                        if srv.on_save is None:
                            return self._send(503, {"ok": False, "hata": "Tarla kaydı kullanılamıyor."})
                        field = srv.on_save(field)
                    else:
                        srv.on_field(field)
                except ValueError as exc:
                    return self._send(400, {"ok": False, "hata": str(exc)})
                except Exception as exc:
                    return self._send(500, {"ok": False, "hata": str(exc)})
                with srv._lock:
                    srv.state["points"] = field["noktalar"]
                    srv.state["center"] = [field["lat"], field["lon"]]
                    srv.state["zoom"] = 16
                    srv.state["name"] = field.get("kayit_adi", "")
                public = {k: v for k, v in field.items() if k != "gorsel"}
                self._send(200, {"ok": True, "tarla": public, "alan": area_label(field),
                                 "gorsel": field.get("gorsel") is not None})

        return Handler


# ---------------------------------------------------------------- sayfa
PAGE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tarla Pusulası · Tarlamı seç</title>
<style>
  :root { --bg:#080b0a; --side:#0c100e; --card:#161d1a; --line:#2a3630; --fg:#f2f6f3;
          --mut:#8b9c92; --acc:#7cf0a8; --acc2:#37a06b; --gold:#e8c07d; --bad:#ee8874; }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; background: var(--bg); color: var(--fg);
               font: 14px/1.45 "Segoe UI", Inter, system-ui, sans-serif; }
  #wrap { display: flex; height: 100%; }
  #side { width: 330px; flex: none; background: var(--side); border-right: 1px solid var(--line);
          padding: 22px 20px; display: flex; flex-direction: column; gap: 14px; overflow-y: auto; }
  #map { flex: 1; min-width: 0; background: #10161a; cursor: crosshair; }
  h1 { font-size: 19px; margin: 0; text-wrap: balance; }
  .sub { color: var(--mut); font-size: 12px; margin: 2px 0 0; }
  .label { color: var(--mut); font-size: 11px; font-weight: 700; letter-spacing: .08em; }
  ol { margin: 0; padding-left: 18px; color: #cdd8d1; font-size: 13px; }
  ol li { margin-bottom: 4px; }
  .row { display: flex; gap: 8px; }
  input[type=text] { flex: 1; min-width: 0; background: var(--card); color: var(--fg);
          border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; font: inherit; }
  input[type=text]:focus-visible, button:focus-visible { outline: 2px solid var(--acc2); outline-offset: 1px; }
  button { font: inherit; font-weight: 600; color: #cdd8d1; background: var(--card);
           border: 1px solid var(--line); border-radius: 12px; padding: 10px 12px; cursor: pointer; }
  button:hover:not(:disabled) { background: #1c2521; color: var(--fg); }
  button:disabled { opacity: .45; cursor: default; }
  button.primary { background: var(--acc); color: #06130c; border-color: transparent;
                   padding: 13px 12px; font-size: 15px; }
  button.primary:hover:not(:disabled) { background: #8bf5b4; color: #06130c; }
  .stat { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
  .stat b { display: block; font-size: 24px; color: var(--acc); font-variant-numeric: tabular-nums; }
  .stat span { color: var(--mut); font-size: 12px; }
  #msg { font-size: 13px; min-height: 20px; color: var(--mut); }
  #msg.ok { color: var(--acc); } #msg.err { color: var(--bad); }
  .foot { margin-top: auto; color: #63746a; font-size: 11px; }
  .vtx { width: 14px; height: 14px; border-radius: 50%; background: var(--acc);
         border: 2px solid #06130c; box-shadow: 0 0 0 2px rgba(124,240,168,.35); }
  .leaflet-container { font: inherit; }
  #manual {padding:24px;max-width:620px}
  #manual textarea {box-sizing:border-box;width:100%;min-height:130px;font:inherit}
  @media (max-width: 760px) {
    #wrap { flex-direction: column-reverse; }
    #side { width: auto; max-height: 48%; border-right: 0; border-top: 1px solid var(--line); }
  }

html, body { overflow-y:auto; scroll-behavior:smooth; }
body { font-size:16px; line-height:1.6; }
button, input, select { font-size:15px; }
button { min-height:44px; white-space:normal; line-height:1.45; }
p, label, .note, .sub, .ttl, .kv, .t { overflow-wrap:anywhere; }
details.tarla-detail { border:1px solid var(--line,#24302a); border-radius:14px; margin:12px 0; padding:12px 16px; }
details.tarla-detail summary { cursor:pointer; color:var(--fg,#f2f6f3); font-size:15px; font-weight:600; padding:6px 0; }
details.tarla-detail[open] summary { margin-bottom:12px; }
@media(prefers-reduced-motion:reduce) { *,*::before,*::after {animation:none!important;transition:none!important;scroll-behavior:auto!important;} }
html,body{overflow:hidden}
#wrap{height:100%;min-height:0;overflow:hidden}
#side{width:clamp(265px,32vw,360px);min-height:0;gap:12px;padding:18px 20px;
      overflow-y:auto;overscroll-behavior:contain}
#side .sub,#side .label,#side ol,#side .foot{font-size:14px}
#side .row{flex-wrap:wrap}
#side>*{flex-shrink:0}
#map{height:100%;min-height:0;position:relative}
@media(max-width:700px){
  #wrap{flex-direction:column-reverse}
  #side{width:100%;max-height:48%}
  #map{height:auto}
}

/* giriş ve etkileşim animasyonları (hareketi azalt ayarında kapanır) */
@keyframes tpUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes tpFade{from{opacity:0}to{opacity:1}}
#side>*{animation:tpUp .42s cubic-bezier(.2,.8,.2,1) both}
#side>*:nth-child(2){animation-delay:0.04s}
#side>*:nth-child(3){animation-delay:0.08s}
#side>*:nth-child(4){animation-delay:0.12s}
#side>*:nth-child(5){animation-delay:0.16s}
#side>*:nth-child(6){animation-delay:0.20s}
#side>*:nth-child(7){animation-delay:0.24s}
#side>*:nth-child(8){animation-delay:0.28s}
#side>*:nth-child(9){animation-delay:0.32s}
#side>*:nth-child(10){animation-delay:0.36s}
#map{animation:tpFade .5s ease both}
button{transition:background-color .18s,border-color .18s,color .18s,box-shadow .18s,transform .12s}
button:hover:not(:disabled){box-shadow:0 0 0 3px rgba(124,240,168,.12)}
button:active:not(:disabled){transform:scale(.97)}
</style>
<style>
.measure-track{height:4px;margin-top:10px;background:#24302a;border-radius:4px;overflow:hidden}
.measure-track i{display:block;width:0;height:100%;background:#7cf0a8;transition:width .25s ease-out}
@keyframes measure-pop{from{opacity:.55;transform:translateY(3px)}to{opacity:1;transform:none}}
.measure-pop{animation:measure-pop .28s ease-out}
.vtx{animation:measure-pop .22s ease-out}
.archive-controls{display:grid;gap:8px}
.save-box{display:grid;gap:8px;margin-top:-6px}
.save-box[hidden]{display:none}
.save-box input{width:100%}
button.outline{background:transparent;color:var(--acc);border:2px solid var(--acc2)}
button.outline:hover:not(:disabled){background:rgba(124,240,168,.10);color:var(--acc)}
.archive-controls input{width:100%}
</style>
</head>
<body>
<div id="wrap">
  <aside id="side">
    <div>
      <h1>Tarlanı haritada işaretle</h1>
      <p class="sub">Tarla Pusulası · NASA Space Apps</p>
    </div>
    <div>
      <div class="label">YER ARA</div>
      <form class="row" id="search" style="margin-top:8px">
        <input type="text" id="q" placeholder="Köy, ilçe ya da 37.87, 32.48" autocomplete="off"
               aria-label="Yer ara">
        <button type="submit">Git</button>
      </form>
      <button id="locate" style="width:100%;margin-top:8px">Bulunduğum yere git</button>
    </div>
    <ol>
      <li>Haritayı tarlana yaklaştır.</li>
      <li>Tarlanın <b>dış sınırındaki noktaları istediğin sırada işaretle</b>. Alan otomatik hesaplanır.</li>
      <li>Köşeyi sürükleyerek düzelt, çift tıklayarak sil.</li>
    </ol>
    <div class="stat" aria-live="polite">
      <b id="area">—</b>
      <span id="areaSub">Alan için en az 3 köşe işaretle</span>
      <span id="perimeter">Çevre —</span>
      <div class="measure-track" aria-hidden="true"><i id="measureTrack"></i></div>
    </div>
    <div class="row">
      <button id="undo" style="flex:1" disabled>Son köşeyi geri al</button>
      <button id="clear" style="flex:1" disabled>Temizle</button>
    </div>
    <button id="send" class="primary" disabled>Bu tarlayı kullan</button>
    <div class="save-box" id="saveBox" hidden>
      <input type="text" id="fieldName" maxlength="60" autocomplete="off"
             placeholder="Tarla adı (örn. Pınarbaşı tarlası)" aria-label="Tarla adı">
      <button id="save" class="outline" disabled>Bu tarlayı kaydet</button>
    </div>
    <div id="msg" role="status"></div>
    <details>
      <summary>Geçmiş uydu görüntüsü</summary>
      <div class="archive-controls">
        <label for="imageDate">Görüntü tarihi</label>
        <input type="date" id="imageDate" min="2000-02-24">
        <button id="archive">MODIS görüntüsünü aç</button>
        <p>NASA Terra MODIS · 250 m. Bulut veya kapsama boşluğu görülebilir.</p>
      </div>
    </details>
    <div class="foot">
      Çizdiğin sınır yalnızca bu bilgisayardaki Tarla Pusulası'na gönderilir.<br>
      Katmanlar (sağ üst): Esri uydu · OpenStreetMap · NASA GIBS (MODIS, SMAP L4, GPM IMERG).
    </div>
  </aside>
  <div id="map" role="application" aria-label="Tarla haritası">
    <section id="manual" hidden>
      <h2>Koordinatla tarla seç</h2>
      <p>Her satıra bir köşe yazın. Örnek: 37.87, 32.48. Tarla sınırı için en az üç köşe girin.</p>
      <textarea id="coordinates" aria-label="Tarla koordinatları" spellcheck="false"></textarea>
    </section>
  </div>
</div>
<script>
"use strict";
(async () => {
async function loadMapLibrary(base) {
  if (window.L) return true;
  return new Promise(resolve => {
    const script = document.createElement("script");
    script.src = base + "/leaflet.js";
    const timer = setTimeout(() => { script.remove(); resolve(false); }, 4500);
    script.onload = () => {
      clearTimeout(timer);
      if (window.L) {
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = base + "/leaflet.css";
        document.head.append(css);
      }
      resolve(Boolean(window.L));
    };
    script.onerror = () => { clearTimeout(timer); resolve(false); };
    document.head.append(script);
  });
}
await loadMapLibrary("https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist")
  || await loadMapLibrary("https://unpkg.com/leaflet@1.9.4/dist");
const TOKEN = "__TOKEN__";
const $ = id => document.getElementById(id);
const msg = (t, cls) => { $("msg").textContent = t; $("msg").className = cls || ""; };
const tr = (n, d) => n.toLocaleString(document.documentElement.lang, {minimumFractionDigits: d, maximumFractionDigits: d});

if (!window.L) {
  $("manual").hidden = false;
  msg("Harita yüklenemedi. Koordinatla devam edebilir veya bağlantıyı kontrol edip yenileyebilirsiniz.", "err");
  for (const id of ["q", "locate", "archive"]) $(id).disabled = true;
  $("search").onsubmit = e => e.preventDefault();
  const coordinates = $("coordinates");
  const parsed = () => coordinates.value.trim().split(/\r?\n/).filter(line => line.trim()).map(
    line => line.split(",").map(value => value.trim() ? Number(value) : NaN));
  const valid = points => points.length > 0 && points.length !== 2 && points.length <= 200 &&
    points.every(p => p.length === 2 && Number.isFinite(p[0]) && Number.isFinite(p[1]) &&
      Math.abs(p[0]) <= 90 && Math.abs(p[1]) <= 180);
  const sync = () => {
    const points = parsed();
    $("send").disabled = !valid(points);
    $("save").disabled = !valid(points) || points.length < 3;
  };
  coordinates.oninput = sync;
  const send = async save => {
    const points = parsed();
    if (!valid(points) || (save && points.length < 3)) return;
    $("send").disabled = $("save").disabled = true;
    try {
      const response = await fetch("/tarla?t=" + encodeURIComponent(TOKEN), {
        method:"POST", headers:{"Content-Type":"application/json"},
        body:JSON.stringify({points, ad:$("fieldName").value.trim(), kaydet:save})
      });
      const result = await response.json();
      if (!result.ok) throw new Error(result.hata || "Tarla gönderilemedi.");
      msg(save ? "Tarla kaydedildi." : "Tarla uygulamaya gönderildi.", "ok");
    } catch (error) {
      msg(error.message, "err");
    } finally {
      sync();
    }
  };
  $("send").onclick = () => send(false);
  $("save").onclick = () => send(true);
  fetch("/durum?t=" + encodeURIComponent(TOKEN)).then(r => r.json()).then(state => {
    $("saveBox").hidden = !state.can_save;
    $("fieldName").value = state.name || "";
    if (!coordinates.value && state.points.length) coordinates.value = state.points.map(p => p.join(", ")).join("\n");
    sync();
  }).catch(() => {});
} else {

const map = L.map("map", {doubleClickZoom: false}).setView([39.0, 35.2], 6);
const gunStr = n => new Date(Date.now() - n * 864e5).toISOString().slice(0, 10);
const GIBS = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/";
const uydu = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  {maxZoom: 19, attribution: "Uydu: Esri, Maxar, Earthstar Geographics"}).addTo(map);
const sokak = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",
  {maxZoom: 19, attribution: "&copy; OpenStreetMap katkıcıları"});
let baseTilesFailed = 0;
uydu.on("tileerror", () => {
  if (++baseTilesFailed >= 3 && map.hasLayer(uydu)) {
    map.removeLayer(uydu);
    sokak.addTo(map);
    msg("Uydu görüntüsü alınamadı. OpenStreetMap açıldı.", "err");
  }
});
sokak.on("tileerror", () => {
  msg("Harita görüntüsü alınamadı. İnternet bağlantınızı kontrol edin.", "err");
});
const modis = L.tileLayer(
  GIBS + "MODIS_Terra_CorrectedReflectance_TrueColor/default/" + gunStr(2) +
  "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
  {maxNativeZoom: 9, maxZoom: 19, attribution: "NASA GIBS · MODIS Terra (" + gunStr(2) + ")"});
const imageDate = $("imageDate");
imageDate.max = gunStr(2);
imageDate.value = gunStr(2);
function showArchive() {
  if (!imageDate.value || !imageDate.checkValidity()) {
    imageDate.reportValidity();
    return;
  }
  const day = imageDate.value;
  msg("NASA MODIS · " + day);
  modis.options.attribution = "NASA GIBS · MODIS Terra · " + day;
  if (map.hasLayer(modis)) map.removeLayer(modis);
  modis.setUrl(GIBS + "MODIS_Terra_CorrectedReflectance_TrueColor/default/" + day +
    "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg");
  for (const base of [uydu, sokak]) map.removeLayer(base);
  modis.addTo(map);
}
$("archive").onclick = showArchive;
const ndvi = L.tileLayer(
  GIBS + "MODIS_Terra_NDVI_8Day/default/" + gunStr(16) +
  "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png",
  {maxNativeZoom: 9, maxZoom: 19, opacity: .65, attribution: "NASA GIBS · MODIS NDVI (8 günlük)"});
const smap = L.tileLayer(
  GIBS + "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture/default/" + gunStr(5) +
  "/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png",
  {maxNativeZoom: 6, maxZoom: 19, opacity: .62, attribution: "NASA GIBS · SMAP L4 · " + gunStr(5)});
const imerg = L.tileLayer(
  GIBS + "IMERG_Precipitation_Rate/default/" + gunStr(3) +
  "/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png",
  {maxNativeZoom: 6, maxZoom: 19, opacity: .66, attribution: "NASA GIBS · GPM IMERG · " + gunStr(3)});
L.control.layers(
  {"Uydu (yüksek çözünürlük)": uydu, "Sokak haritası": sokak, "NASA MODIS (güncel, 250 m)": modis},
  {"NASA NDVI · bitki örtüsü (250 m)": ndvi,
   "SMAP · kök bölgesi nemi": smap, "GPM IMERG · yağış hızı": imerg}, {collapsed: true}).addTo(map);
for (const layer of [modis, ndvi, smap, imerg]) {
  layer.on("tileerror", () => msg("NASA katmanında bazı görüntüler yüklenemedi."));
}
L.control.scale({imperial: false}).addTo(map);

// ---- çizim
const markers = [];
const poly = L.polygon([], {color: "#7cf0a8", weight: 3, fillColor: "#7cf0a8", fillOpacity: .18}).addTo(map);
const icon = L.divIcon({className: "", html: '<div class="vtx"></div>', iconSize: [14, 14], iconAnchor: [7, 7]});

function alanM2(pts) {            // Python tarafındaki hesapla aynı (yerel düzlem)
  if (pts.length < 3) return 0;
  const R = 6371008.8, rad = Math.PI / 180;
  const lat0 = pts.reduce((s, p) => s + p[0], 0) / pts.length;
  const lon0 = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  const k = Math.cos(lat0 * rad);
  const xy = pts.map(p => [(p[1] - lon0) * rad * R * k, (p[0] - lat0) * rad * R]);
  let a = 0;
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i], [x2, y2] = xy[(i + 1) % xy.length];
    a += x1 * y2 - x2 * y1;
  }
  return Math.abs(a) / 2;
}
// Noktalar çapraz veya karışık sırada işaretlense bile dışbükey dış sınırı bul.
// İçeride işaretlenen noktalar korunur ancak alanın dış sınırını değiştirmez.
// İçbükey parsellerde gerçek girintileri temsil etmek için çevre boyunca köşe seçimi gerekir.
function disSinir(pts) {
  if (pts.length < 3) return pts.slice();
  const sorted = pts.map(p => [p[1], p[0]]).sort((a,b) => a[0]-b[0] || a[1]-b[1]);
  const unique = sorted.filter((p,i) => !i || p[0] !== sorted[i-1][0] || p[1] !== sorted[i-1][1]);
  const turn = (a,b,c) => (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
  const lower=[], upper=[];
  for (const pt of unique) {
    while (lower.length >= 2 && turn(lower[lower.length-2], lower[lower.length-1], pt) <= 0) lower.pop();
    lower.push(pt);
  }
  for (const pt of unique.slice().reverse()) {
    while (upper.length >= 2 && turn(upper[upper.length-2], upper[upper.length-1], pt) <= 0) upper.pop();
    upper.push(pt);
  }
  const hull = lower.slice(0,-1).concat(upper.slice(0,-1));
  return hull.map(p => [p[1],p[0]]);
}
const hamNoktalar = () => markers.map(m => { const p = m.getLatLng(); return [p.lat, p.lng]; });
const noktalar = () => disSinir(hamNoktalar());

let fieldRequestPending = false;
function yenile(animate = false) {
  const pts = noktalar();
  const totalPoints = markers.length;
  poly.setLatLngs(pts);
  const a = alanM2(pts), da = a / 1000;
  const perimeter = pts.reduce((total, point, i) => {
    const next = i + 1 < pts.length ? pts[i + 1] : pts.length > 2 ? pts[0] : null;
    return next ? total + map.distance(point, next) : total;
  }, 0);
  $("perimeter").textContent = pts.length > 2 ? "Çevre " + tr(perimeter, 0) + " m" :
    pts.length === 2 ? "Kenar " + tr(perimeter, 0) + " m" : "Çevre —";
  $("measureTrack").style.width = (Math.min(pts.length, 3) / 3 * 100) + "%";
  if (animate === true) {
    const stat = $("area").parentElement;
    stat.classList.remove("measure-pop");
    void stat.offsetWidth;
    stat.classList.add("measure-pop");
  }
  if (a > 0) {
    $("area").textContent = tr(da, da < 100 ? 1 : 0) + " dekar";
    $("areaSub").textContent = tr(da / 10, 2) + " hektar · " + totalPoints + " nokta · otomatik dış sınır";
  } else {
    $("area").textContent = "—";
    $("areaSub").textContent = pts.length
      ? totalPoints + " nokta · alan için en az 3 farklı nokta gerek"
      : "Alan için en az 3 köşe işaretle";
  }
  $("undo").disabled = $("clear").disabled = !pts.length;
  $("send").disabled = fieldRequestPending || !pts.length || pts.length === 2 || (pts.length > 2 && a < 1);
  $("save").disabled = fieldRequestPending || pts.length < 3 || a < 1;
}

function ekle(latlng) {
  if (markers.length >= 200) { msg("En fazla 200 nokta eklenebilir.", "err"); return; }
  const m = L.marker(latlng, {icon, draggable: true, keyboard: false}).addTo(map);
  m.on("drag", yenile);
  m.on("dragend", () => yenile(true));
  m.on("dblclick", e => { L.DomEvent.stop(e); map.removeLayer(m); markers.splice(markers.indexOf(m), 1); yenile(true); });
  m.on("click", e => L.DomEvent.stop(e));
  markers.push(m);
  yenile(true);
}
function temizle() { markers.forEach(m => map.removeLayer(m)); markers.length = 0; yenile(true); }
window.addEventListener("tarla-appearance", () => yenile());

map.on("click", e => { msg(""); ekle(e.latlng); });
$("undo").onclick = () => { const m = markers.pop(); if (m) map.removeLayer(m); yenile(true); };
$("clear").onclick = temizle;

// ---- arama ve konum
$("search").onsubmit = async e => {
  e.preventDefault();
  const q = $("q").value.trim();
  if (!q) return;
  const c = q.match(/^(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)$/);
  if (c) {
    const lat=+c[1].replace(',', '.'), lon=+c[2].replace(',', '.');
    if(Math.abs(lat)>85.051128 || Math.abs(lon)>180){msg('Koordinat aralık dışında. Enlem ve boylamı kontrol edin.','err');return;}
    map.setView([lat,lon],16); return;
  }
  msg("Aranıyor…");
  try {
    const params = new URLSearchParams({count: 1, language: document.documentElement.lang, format: "json", name: q});
    const r = await fetch("https://geocoding-api.open-meteo.com/v1/search?" + params);
    const hit = ((await r.json()).results || [])[0];
    if (!hit) { msg("“" + q + "” bulunamadı. Başka bir yazımla dene.", "err"); return; }
    map.setView([hit.latitude, hit.longitude], 14);
    msg(hit.name + (hit.admin1 ? ", " + hit.admin1 : ""));
  } catch (err) { msg("Arama yapılamadı. İnternet bağlantını kontrol et.", "err"); }
};
$("locate").onclick = () => {
  if (!navigator.geolocation) { msg("Tarayıcı konum paylaşımını desteklemiyor.", "err"); return; }
  msg("Konum alınıyor…");
  navigator.geolocation.getCurrentPosition(
    p => { map.setView([p.coords.latitude, p.coords.longitude], 16); msg("Bulunduğun yer gösteriliyor."); },
    () => msg("Konum alınamadı. Tarayıcıda konum iznini kontrol et.", "err"),
    {enableHighAccuracy: true, timeout: 10000});
};

// ---- tarlanın uydu görseli (10 yıllık senaryodaki "Tarla görünümü" için)
const UYDU = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/";
function karoYukle(g, z, tx, ty, dx, dy) {
  return new Promise((res, rej) => {
    const im = new Image();
    im.crossOrigin = "anonymous";
    im.onload = () => { g.drawImage(im, dx, dy); res(); };
    im.onerror = () => rej(new Error("karo yok"));
    im.src = UYDU + z + "/" + ty + "/" + tx + "?blankTile=false";   // veri yoksa 404 dönsün
  });
}
async function goruntuAl(pts, z) {
  const W = 560, H = 420, b = L.latLngBounds(pts);
  for (; z > 4; z--) {                       // tarla, çerçevenin ~%75'ine sığsın
    const nw = map.project(b.getNorthWest(), z), se = map.project(b.getSouthEast(), z);
    if ((se.x - nw.x) * 1.35 <= W && (se.y - nw.y) * 1.35 <= H) break;
  }
  const c = map.project(b.getCenter(), z);
  const x0 = Math.round(c.x - W / 2), y0 = Math.round(c.y - H / 2);
  const cv = document.createElement("canvas");
  cv.width = W; cv.height = H;
  const g = cv.getContext("2d", {willReadFrequently: true});
  const isler = [];
  for (let tx = Math.floor(x0 / 256); tx <= Math.floor((x0 + W - 1) / 256); tx++)
    for (let ty = Math.floor(y0 / 256); ty <= Math.floor((y0 + H - 1) / 256); ty++)
      isler.push(karoYukle(g, z, tx, ty, tx * 256 - x0, ty * 256 - y0));
  await Promise.all(isler);
  const d = g.getImageData(0, 0, W, H).data, rgb = new Uint8Array(W * H * 3);
  for (let i = 0, j = 0; i < d.length; i += 4) { rgb[j++] = d[i]; rgb[j++] = d[i + 1]; rgb[j++] = d[i + 2]; }
  let s = "";
  for (let i = 0; i < rgb.length; i += 0x8000) s += String.fromCharCode.apply(null, rgb.subarray(i, i + 0x8000));
  return {w: W, h: H, zoom: z, rgb: btoa(s),
          poly: pts.map(p => { const q = map.project(L.latLng(p[0], p[1]), z); return [q.x - x0, q.y - y0]; })};
}
async function tarlaGorseli(pts) {
  if (pts.length < 3) return null;
  for (const z of [18, 17, 16]) {            // yüksek yakınlıkta görüntü yoksa bir kademe uzaklaş
    try {
      return await Promise.race([goruntuAl(pts, z),
        new Promise((_, rej) => setTimeout(() => rej(new Error("zaman aşımı")), 12000))]);
    } catch (err) { /* sıradaki yakınlığı dene */ }
  }
  return null;
}

// ---- gönder
$("send").onclick = async () => {
  const pts = noktalar();
  if (fieldRequestPending || !pts.length) return;
  const ad = $("fieldName").value;
  fieldRequestPending = true;
  $("save").disabled = $("send").disabled = true;
  msg(pts.length > 2 ? "Tarlanın uydu görseli hazırlanıyor…" : "Gönderiliyor…");
  try {
    // Görsel isteği yavaşsa tarla seçimini 36 saniye bloke etme.
    const image = await Promise.race([tarlaGorseli(pts),new Promise(resolve=>setTimeout(()=>resolve(null),2500))]);
    msg("Gönderiliyor…");
    const r = await fetch("/tarla?t=" + encodeURIComponent(TOKEN), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({points: pts, image, ad})});
    const j = await r.json();
    if (!j.ok) throw new Error(j.hata || "Gönderilemedi.");
    msg("Tarla gönderildi" + (j.alan ? " · " + j.alan : "") +
        (pts.length > 2 ? (j.gorsel ? " · uydu görseli alındı" : " · uydu görseli alınamadı") : "") +
        ". Tarla Pusulası penceresine dönebilirsin.", "ok");
  } catch (err) {
    msg((err && err.message && !/fetch/i.test(err.message) ? err.message + " " : "") +
        "Uygulama açık mı? Kapandıysa haritayı uygulamadan yeniden aç.", "err");
  } finally {
    fieldRequestPending = false;
    yenile();
  }
};

// ---- kaydet (Tarlalarım'a ekler; analiz başlatmaz)
$("save").onclick = async () => {
  if (fieldRequestPending) return;
  const pts = noktalar();
  if (pts.length < 3) { msg("Kaydetmek için en az 3 köşe işaretle.", "err"); return; }
  const ad = $("fieldName").value.trim();
  fieldRequestPending = true;
  $("save").disabled = $("send").disabled = true;
  msg("Kaydediliyor…");
  try {
    const r = await fetch("/tarla?t=" + encodeURIComponent(TOKEN), {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({points: pts, kaydet: true, ad})});
    const j = await r.json();
    if (!j.ok) throw new Error(j.hata || "Kaydedilemedi.");
    $("fieldName").value = j.tarla.kayit_adi;
    msg("“" + j.tarla.kayit_adi + "” Tarlalarım'a kaydedildi" + (j.alan ? " · " + j.alan : "") + ".", "ok");
  } catch (err) {
    msg((err && err.message && !/fetch/i.test(err.message) ? err.message + " " : "") +
        "Uygulama açık mı? Kapandıysa haritayı uygulamadan yeniden aç.", "err");
  } finally {
    fieldRequestPending = false;
    yenile();
  }
};
$("fieldName").addEventListener("keydown", e => { if (e.key === "Enter") $("save").click(); });

// ---- başlangıç durumu (uygulamadaki konum ve varsa önceki sınır)
fetch("/durum?t=" + encodeURIComponent(TOKEN)).then(r => r.json()).then(s => {
  $("saveBox").hidden = !s.can_save;
  $("fieldName").value = s.name || "";
  if (s.center) map.setView(s.center, s.zoom || 12);
  (s.points || []).forEach(p => ekle(L.latLng(p[0], p[1])));
  if (markers.length > 2) map.fitBounds(poly.getBounds(), {padding: [60, 60], maxZoom: 18});
  const archiveDate = new URLSearchParams(location.search).get("date");
  if (archiveDate) {
    imageDate.value = archiveDate;
    showArchive();
    imageDate.closest("details").open = true;
  }
}).catch(() => {});
}
})();
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
   tarlaFold(document.querySelector('#side .foot'),'Harita katmanları ve gizlilik');
  });</script>
</body>
</html>
"""


if __name__ == "__main__":
    import time

    def _show(field):
        print("Tarla alındı:", json.dumps(field, ensure_ascii=False))

    s = MapServer(_show)
    s.open(center=(37.87, 32.48))
    print("Harita:", s.url, "\nÇıkmak için Ctrl+C")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        s.stop()
