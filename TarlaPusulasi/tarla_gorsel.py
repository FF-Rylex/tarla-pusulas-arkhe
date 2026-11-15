#!/usr/bin/env python3
"""Tarla Pusulası — tarla görseli ve temsili "gelecek görünümü" (v2.7).

Haritadan alınan uydu görüntüsünü (ham RGB) tutar ve tarla sınırının içini
simülasyondaki uygunluk puanına göre renklendirir:
  düşük puan  -> kuru, kahverengi/saman tonları
  yüksek puan -> canlı yeşil

ÖNEMLİ: Bu bir uydu tahmini ya da üretilmiş fotoğraf DEĞİLDİR. Görüntünün
dokusu (parlaklık) korunur, yalnızca renk simülasyon sonucuna göre atanır.

Yalnızca standart kütüphane kullanır (PIL gerekmez); çıktı PNG baytlarıdır
ve tkinter.PhotoImage(data=base64...) ile gösterilebilir.
"""
import base64
import math
import struct
import zlib

MAX_SIDE = 800

# uygunluk (0-1) -> tarla rengi (R, G, B)
RAMP = [(0.00, (126, 94, 64)),     # kuru toprak
        (0.45, (182, 154, 86)),    # sararmış / zayıf örtü
        (0.75, (112, 152, 62)),    # sağlıklı
        (1.00, (56, 126, 46))]     # çok canlı


def ramp(v):
    """0-1 uygunluk -> (R, G, B). Aradaki değerler doğrusal geçişle bulunur."""
    v = min(1.0, max(0.0, float(v)))
    for (a, ca), (b, cb) in zip(RAMP, RAMP[1:]):
        if v <= b:
            t = (v - a) / (b - a)
            return tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))
    return RAMP[-1][1]


def png_bytes(w, h, rgb):
    """Ham RGB (w*h*3 bayt) -> PNG dosya baytları."""
    stride = w * 3
    raw = b"".join(b"\x00" + bytes(rgb[y * stride:(y + 1) * stride]) for y in range(h))

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 1)) + chunk(b"IEND", b""))


class FieldImage:
    """Tarla çevresinin uydu görüntüsü + görüntü pikselleri cinsinden tarla sınırı."""

    def __init__(self, w, h, rgb, poly):
        w, h = int(w), int(h)
        if not (16 <= w <= MAX_SIDE and 16 <= h <= MAX_SIDE):
            raise ValueError("Görsel boyutu geçersiz.")
        if len(rgb) != w * h * 3:
            raise ValueError("Görsel verisi boyutla uyuşmuyor.")
        poly = [(float(x), float(y)) for x, y in poly]
        if len(poly) < 3 or not all(math.isfinite(v) and abs(v) < 1e5 for p in poly for v in p):
            raise ValueError("Tarla sınırı geçersiz.")
        self.w, self.h, self.poly = w, h, poly
        rgb = bytes(rgb)
        self.planes = (rgb[0::3], rgb[1::3], rgb[2::3])
        self._lum = self._spans = None

    @classmethod
    def from_payload(cls, obj):
        """Tarayıcıdan gelen {'w','h','rgb'(base64),'poly'} sözlüğünü doğrulayıp oluştur."""
        if not isinstance(obj, dict):
            raise ValueError("Görsel biçimi geçersiz.")
        try:
            rgb = base64.b64decode(obj.get("rgb") or "", validate=True)
        except Exception:
            raise ValueError("Görsel verisi çözülemedi.")
        return cls(obj.get("w"), obj.get("h"), rgb, obj.get("poly") or [])

    # -- türetilmiş veriler
    def resized(self, tw, th):
        """En yakın komşu yöntemiyle (tw × th) boyutuna ölçekle."""
        tw, th = int(tw), int(th)
        if (tw, th) == (self.w, self.h):
            return self
        xs = [min(self.w - 1, int(x * self.w / tw)) for x in range(tw)]
        ys = [min(self.h - 1, int(y * self.h / th)) for y in range(th)]
        planes = []
        for p in self.planes:
            rows = []
            for y in ys:
                row = p[y * self.w:(y + 1) * self.w]
                rows.append(bytes(map(row.__getitem__, xs)))
            planes.append(b"".join(rows))
        out = FieldImage.__new__(FieldImage)
        out.w, out.h = tw, th
        out.poly = [(x * tw / self.w, y * th / self.h) for x, y in self.poly]
        out.planes = tuple(planes)
        out._lum = out._spans = None
        return out

    def lum(self):
        """Parlaklık düzlemi (doku); bir kez hesaplanır."""
        if self._lum is None:
            r, g, b = self.planes
            self._lum = bytes((77 * x + 150 * y + 29 * z) >> 8 for x, y, z in zip(r, g, b))
        return self._lum

    def spans(self):
        """Satır satır tarla içi aralıkları: [(y, x0, x1), ...] (tarama çizgisi dolgusu)."""
        if self._spans is None:
            out, n = [], len(self.poly)
            y_lo = max(0, int(math.floor(min(p[1] for p in self.poly))))
            y_hi = min(self.h - 1, int(math.ceil(max(p[1] for p in self.poly))))
            for y in range(y_lo, y_hi + 1):
                yc, xs = y + 0.5, []
                for i in range(n):
                    (x1, y1), (x2, y2) = self.poly[i], self.poly[(i + 1) % n]
                    if (y1 <= yc < y2) or (y2 <= yc < y1):
                        xs.append(x1 + (yc - y1) * (x2 - x1) / (y2 - y1))
                xs.sort()
                for a, b in zip(xs[0::2], xs[1::2]):
                    x0, x1 = max(0, int(math.ceil(a - 0.5))), min(self.w, int(math.floor(b - 0.5)) + 1)
                    if x1 > x0:
                        out.append((y, x0, x1))
            self._spans = out
        return self._spans

    def coverage(self):
        """Tarlanın görüntüde kapladığı pay (0-1)."""
        return sum(b - a for _, a, b in self.spans()) / float(self.w * self.h)

    def _interleave(self, planes):
        out = bytearray(self.w * self.h * 3)
        out[0::3], out[1::3], out[2::3] = planes
        return out

    # -- çıktılar
    def png_original(self):
        return png_bytes(self.w, self.h, self._interleave(self.planes))

    def png_simulated(self, vigor, dim=0.70):
        """Tarla içi: parlaklık dokusu × uygunluk rengi. Tarla dışı: karartılmış özgün görüntü."""
        tint = ramp(vigor)
        dim_lut = bytes(int(i * dim) for i in range(256))
        lum, w, planes = self.lum(), self.w, []
        for c in range(3):
            lut = bytes(min(255, int(tint[c] * (0.42 + 1.05 * i / 255.0))) for i in range(256))
            inside = lum.translate(lut)
            out = bytearray(self.planes[c].translate(dim_lut))
            for y, x0, x1 in self.spans():
                o = y * w
                out[o + x0:o + x1] = inside[o + x0:o + x1]
            planes.append(bytes(out))
        return png_bytes(self.w, self.h, self._interleave(planes))


def b64(png):
    """tkinter.PhotoImage(data=...) için base64."""
    return base64.b64encode(png)
