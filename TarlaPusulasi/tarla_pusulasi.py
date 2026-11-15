#!/usr/bin/env python3
"""Tarla Pusulası — hesap motoru (v2).

NASA POWER klimatolojisi + toprak profili -> ekin uygunluğu, rotasyon
stratejileri ve belirsizlikli 10 yıllık iklim senaryosu.

Yalnızca Python standart kütüphanesini kullanır (pip gerekmez).

Kullanım:
  python tarla_pusulasi.py Konya
  python tarla_pusulasi.py "37.87, 32.48" --sulama
  python tarla_pusulasi.py Adana --top 5 --json
  python tarla_pusulasi.py Konya --demo
"""
import argparse
import calendar
import json
import math
import random
import re
import sys
import time
import urllib.parse
import urllib.request

# ------------------------------------------------------------------ sabitler
MONTHS = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
          "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
DIM = [31, 28.25, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

# NASA POWER ALLSKY_SFC_SW_DWN bu uçta kW·s/m²/gün döner, kWh/m²/gün değil.
KWH_PER_UNIT = 1.0 / 3.6

# Ekin parametreleri.
#   t     : dönem ort. sıcaklık [donma, ideal alt, ideal üst, üst sınır] °C
#   need  : sezon su ihtiyacı mm
#   soil  : kök bölgesi nemi [min, ideal alt, ideal üst, max] (0-1)
#   rh    : bağıl nem % [min, ideal alt, ideal üst, max]
#   sun   : en az kWh/m²/gün
#   frost : tolere edilen en soğuk gece ortalaması °C
#   sow   : ekim başlangıç ayları (0 = Ocak)
#   group : Tahıl / Endüstri / Baklagil / Sebze / Çok yıllık
#   nfix  : 1.0 azot bağlar, 0 bağlamaz
#   chill : çok yıllıklarda gereken soğuklama (kış sıcaklık ekseni toplamı)
FAO = "FAO-56 (Allen vd. 1998) ekin su ihtiyacı + çiftçi uygulaması"
TAGEM = "FAO + TAGEM baklagil yetiştirme kılavuzu"
TARIM = "FAO-56 + Tarım ve Orman Bakanlığı ekim takvimi"

CROPS = [
    dict(name="Kışlık buğday", group="Tahıl", months=8, sow=[8, 9, 10], t=[-2, 5, 15, 22],
         need=380, soil=[.10, .25, .65, .90], rh=[25, 40, 75, 95], sun=3.0, frost=-16,
         nfix=0.0, source=FAO),
    dict(name="Arpa", group="Tahıl", months=7, sow=[8, 9, 10], t=[0, 6, 17, 25],
         need=300, soil=[.08, .20, .60, .90], rh=[20, 35, 75, 95], sun=3.0, frost=-14,
         nfix=0.0, source=FAO),
    dict(name="Mısır", group="Tahıl", months=5, sow=[2, 3, 4, 5], t=[12, 18, 26, 34],
         need=550, soil=[.20, .40, .75, .95], rh=[30, 45, 80, 95], sun=4.5, frost=6,
         nfix=0.0, source=FAO),
    dict(name="Pamuk", group="Endüstri", months=6, sow=[3, 4], t=[15, 21, 30, 36],
         need=700, soil=[.12, .25, .60, .85], rh=[25, 40, 70, 90], sun=5.0, frost=9,
         nfix=0.0, source=FAO),
    dict(name="Ayçiçeği", group="Endüstri", months=5, sow=[2, 3, 4], t=[11, 17, 26, 34],
         need=450, soil=[.10, .25, .60, .85], rh=[25, 40, 70, 90], sun=5.0, frost=3,
         nfix=0.0, source=FAO),
    dict(name="Şeker pancarı", group="Endüstri", months=7, sow=[1, 2, 3], t=[8, 15, 24, 32],
         need=650, soil=[.20, .40, .75, .95], rh=[30, 45, 80, 95], sun=4.0, frost=-2,
         nfix=0.0, source=FAO),
    dict(name="Patates", group="Sebze", months=4, sow=[1, 2, 3, 6], t=[5, 11, 20, 27],
         need=400, soil=[.20, .40, .70, .90], rh=[40, 55, 85, 95], sun=3.5, frost=2,
         nfix=0.0, source=FAO),
    dict(name="Domates", group="Sebze", months=5, sow=[1, 2, 3, 4], t=[12, 18, 27, 34],
         need=500, soil=[.20, .40, .70, .90], rh=[35, 50, 75, 92], sun=4.5, frost=8,
         nfix=0.0, source=FAO),
    dict(name="Pirinç", group="Tahıl", months=5, sow=[3, 4], t=[16, 22, 30, 36],
         need=1000, soil=[.40, .60, .95, 1.30], rh=[45, 60, 90, 100], sun=4.0, frost=10,
         nfix=0.0, source=FAO),
    dict(name="Nohut", group="Baklagil", months=5, sow=[1, 2, 3, 10, 11], t=[5, 12, 24, 32],
         need=300, soil=[.08, .20, .55, .85], rh=[20, 35, 70, 90], sun=4.0, frost=0,
         nfix=1.0, source=TAGEM),
    dict(name="Mercimek", group="Baklagil", months=6, sow=[1, 2, 9, 10, 11], t=[2, 8, 20, 28],
         need=280, soil=[.08, .20, .55, .85], rh=[20, 35, 70, 90], sun=3.5, frost=-4,
         nfix=1.0, source=TAGEM),
    dict(name="Zeytin", group="Çok yıllık", months=12, sow=[0], t=[8, 14, 21, 30],
         need=500, soil=[.08, .20, .55, .85], rh=[30, 45, 75, 92], sun=4.5, frost=-1,
         nfix=0.0, source="FAO + Zeytincilik Araştırma Enstitüsü", chill=150),
    dict(name="Üzüm (bağ)", group="Çok yıllık", months=12, sow=[0], t=[8, 12, 22, 30],
         need=450, soil=[.08, .20, .55, .85], rh=[25, 40, 70, 90], sun=4.5, frost=-8,
         nfix=0.0, source="FAO + Bağcılık Araştırma Enstitüsü", chill=100),
    dict(name="Fındık", group="Çok yıllık", months=12, sow=[0], t=[8, 12, 18, 25],
         need=900, soil=[.25, .40, .80, .95], rh=[55, 65, 88, 98], sun=3.5, frost=-6,
         nfix=0.0, source="FAO + Fındık Araştırma Enstitüsü", chill=300),
    dict(name="Narenciye", group="Çok yıllık", months=12, sow=[0], t=[12, 16, 25, 32],
         need=900, soil=[.20, .35, .70, .90], rh=[45, 55, 85, 95], sun=4.5, frost=3,
         nfix=0.0, source="FAO + Turunçgiller Araştırma Enstitüsü", chill=40),
    dict(name="Karpuz", group="Sebze", months=4, sow=[3, 4], t=[14, 20, 30, 36],
         need=450, soil=[.15, .30, .65, .85], rh=[30, 45, 70, 88], sun=5.0, frost=8,
         nfix=0.0, source=TARIM),
    dict(name="Elma", group="Çok yıllık", months=12, sow=[0], t=[7, 13, 20, 27],
         need=700, soil=[.20, .35, .70, .90], rh=[40, 50, 80, 95], sun=4.0, frost=-12,
         nfix=0.0, source="FAO + Meyvecilik Araştırma Enstitüsü", chill=350),
    dict(name="Kuru soğan", group="Sebze", months=6, sow=[1, 2, 8, 9], t=[4, 12, 22, 30],
         need=450, soil=[.20, .35, .70, .90], rh=[35, 50, 75, 90], sun=4.0, frost=-4,
         nfix=0.0, source=TARIM),
    dict(name="Biber", group="Sebze", months=5, sow=[3, 4], t=[13, 19, 27, 34],
         need=550, soil=[.20, .40, .70, .90], rh=[40, 50, 75, 90], sun=4.5, frost=9,
         nfix=0.0, source=TARIM),
    dict(name="Hıyar", group="Sebze", months=4, sow=[3, 4, 5], t=[14, 19, 28, 34],
         need=400, soil=[.25, .45, .75, .92], rh=[45, 60, 85, 95], sun=4.0, frost=9,
         nfix=0.0, source=TARIM),
    dict(name="Kavun", group="Sebze", months=4, sow=[3, 4], t=[14, 20, 30, 36],
         need=400, soil=[.12, .28, .60, .85], rh=[25, 40, 65, 85], sun=5.0, frost=8,
         nfix=0.0, source=TARIM),
    dict(name="Çay", group="Çok yıllık", months=12, sow=[0], t=[12, 17, 24, 30],
         need=1300, soil=[.35, .50, .85, 1.00], rh=[65, 75, 92, 100], sun=3.0, frost=2,
         nfix=0.0, source="FAO + Çay Araştırma Enstitüsü", chill=0),
    dict(name="Kuru fasulye", group="Baklagil", months=4, sow=[3, 4, 5], t=[12, 17, 25, 32],
         need=400, soil=[.20, .38, .70, .90], rh=[40, 50, 75, 90], sun=4.5, frost=6,
         nfix=1.0, source=TAGEM),
    dict(name="Yulaf", group="Tahıl", months=7, sow=[1, 2, 8, 9, 10], t=[1, 7, 18, 25],
         need=350, soil=[.12, .28, .68, .92], rh=[30, 45, 80, 95], sun=3.0, frost=-10,
         nfix=0.0, source=FAO),
    dict(name="Çavdar", group="Tahıl", months=8, sow=[8, 9, 10], t=[-4, 2, 11, 19],
         need=400, soil=[.10, .25, .60, .85], rh=[25, 40, 70, 92], sun=3.0, frost=-22,
         nfix=0.0, source=FAO),
    # ---- v2.6: liste 40 ekine tamamlandı (hepsi farklı)
    dict(name="Mandalina", group="Çok yıllık", months=12, sow=[0], t=[11, 15, 24, 31],
         need=850, soil=[.20, .35, .70, .90], rh=[45, 55, 85, 95], sun=4.5, frost=1,
         nfix=0.0, source="FAO + Turunçgiller Araştırma Enstitüsü", chill=30),
    dict(name="Kanola", group="Endüstri", months=9, sow=[8, 9], t=[-2, 5, 16, 24],
         need=450, soil=[.12, .28, .65, .90], rh=[30, 45, 80, 95], sun=3.0, frost=-12,
         nfix=0.0, source=FAO),
    dict(name="Soya", group="Baklagil", months=5, sow=[4, 5], t=[14, 20, 28, 34],
         need=500, soil=[.20, .38, .72, .92], rh=[40, 50, 80, 92], sun=4.5, frost=8,
         nfix=1.0, source=TAGEM),
    dict(name="Yer fıstığı", group="Baklagil", months=5, sow=[3, 4], t=[16, 22, 30, 36],
         need=550, soil=[.15, .30, .65, .88], rh=[35, 50, 80, 92], sun=5.0, frost=10,
         nfix=1.0, source=TAGEM),
    dict(name="Tütün", group="Endüstri", months=4, sow=[3, 4], t=[14, 20, 28, 34],
         need=450, soil=[.12, .28, .62, .85], rh=[35, 50, 75, 90], sun=4.5, frost=8,
         nfix=0.0, source=FAO),
    dict(name="Susam", group="Endüstri", months=4, sow=[4, 5], t=[18, 24, 32, 38],
         need=400, soil=[.08, .20, .55, .80], rh=[25, 40, 70, 88], sun=5.5, frost=12,
         nfix=0.0, source=FAO),
    dict(name="Patlıcan", group="Sebze", months=5, sow=[3, 4], t=[15, 21, 29, 35],
         need=550, soil=[.20, .40, .72, .90], rh=[40, 50, 75, 90], sun=4.5, frost=10,
         nfix=0.0, source=TARIM),
    dict(name="Lahana", group="Sebze", months=4, sow=[1, 2, 6, 7], t=[2, 10, 20, 27],
         need=400, soil=[.25, .40, .75, .92], rh=[45, 60, 88, 98], sun=3.0, frost=-6,
         nfix=0.0, source=TARIM),
    dict(name="Havuç", group="Sebze", months=4, sow=[2, 3, 6, 7], t=[5, 12, 22, 28],
         need=400, soil=[.20, .35, .70, .90], rh=[40, 55, 80, 95], sun=3.5, frost=-2,
         nfix=0.0, source=TARIM),
    dict(name="Ispanak", group="Sebze", months=3, sow=[1, 2, 8, 9], t=[0, 7, 18, 25],
         need=250, soil=[.20, .38, .72, .92], rh=[45, 60, 88, 98], sun=2.5, frost=-8,
         nfix=0.0, source=TARIM),
    dict(name="Sarımsak", group="Sebze", months=8, sow=[9, 10], t=[-2, 6, 18, 26],
         need=400, soil=[.15, .30, .65, .88], rh=[30, 45, 75, 92], sun=3.5, frost=-10,
         nfix=0.0, source=TARIM),
    dict(name="Kiraz", group="Çok yıllık", months=12, sow=[0], t=[7, 13, 21, 28],
         need=650, soil=[.20, .35, .70, .90], rh=[35, 45, 75, 92], sun=4.0, frost=-14,
         nfix=0.0, source="FAO + Meyvecilik Araştırma Enstitüsü", chill=250),
    dict(name="Kayısı", group="Çok yıllık", months=12, sow=[0], t=[8, 14, 24, 32],
         need=600, soil=[.12, .28, .62, .85], rh=[20, 35, 65, 88], sun=4.5, frost=-12,
         nfix=0.0, source="FAO + Kayısı Araştırma Enstitüsü", chill=150),
    dict(name="Antep fıstığı", group="Çok yıllık", months=12, sow=[0], t=[10, 18, 30, 38],
         need=450, soil=[.05, .15, .50, .80], rh=[15, 25, 55, 80], sun=5.5, frost=-10,
         nfix=0.0, source="FAO + Antepfıstığı Araştırma Enstitüsü", chill=30),
    dict(name="İncir", group="Çok yıllık", months=12, sow=[0], t=[10, 17, 28, 35],
         need=500, soil=[.08, .20, .55, .85], rh=[25, 40, 70, 90], sun=5.0, frost=-6,
         nfix=0.0, source="FAO + İncir Araştırma Enstitüsü", chill=20),
    # ---- v3.9: liste 50 ekine tamamlandı (hepsi farklı)
    dict(name="Kabak", group="Sebze", months=4, sow=[3, 4], t=[12, 18, 27, 33],
         need=450, soil=[.20, .38, .72, .92], rh=[40, 50, 80, 92], sun=4.0, frost=8,
         nfix=0.0, source=TARIM),
    dict(name="Marul", group="Sebze", months=3, sow=[1, 2, 7, 8], t=[2, 10, 20, 26],
         need=250, soil=[.25, .40, .75, .95], rh=[45, 60, 88, 98], sun=2.5, frost=-4,
         nfix=0.0, source=TARIM),
    dict(name="Karnabahar", group="Sebze", months=4, sow=[6, 7], t=[3, 10, 20, 26],
         need=400, soil=[.25, .40, .75, .92], rh=[45, 60, 88, 98], sun=3.0, frost=-4,
         nfix=0.0, source=TARIM),
    dict(name="Bezelye", group="Baklagil", months=4, sow=[1, 2, 10], t=[2, 8, 20, 26],
         need=350, soil=[.20, .35, .70, .90], rh=[40, 55, 85, 95], sun=3.0, frost=-6,
         nfix=1.0, source=TAGEM),
    dict(name="Bakla", group="Baklagil", months=7, sow=[9, 10, 11], t=[0, 6, 18, 26],
         need=400, soil=[.25, .40, .75, .92], rh=[45, 55, 85, 95], sun=3.0, frost=-8,
         nfix=1.0, source=TAGEM),
    dict(name="Sorgum", group="Tahıl", months=4, sow=[4, 5], t=[15, 22, 32, 40],
         need=450, soil=[.08, .20, .60, .85], rh=[20, 35, 70, 90], sun=5.0, frost=10,
         nfix=0.0, source=FAO),
    dict(name="Tritikale", group="Tahıl", months=8, sow=[9, 10], t=[-3, 4, 16, 24],
         need=400, soil=[.10, .25, .62, .88], rh=[25, 40, 75, 92], sun=3.0, frost=-18,
         nfix=0.0, source=FAO),
    dict(name="Ceviz", group="Çok yıllık", months=12, sow=[0], t=[6, 12, 24, 32],
         need=700, soil=[.20, .35, .70, .90], rh=[30, 45, 75, 92], sun=4.0, frost=-18,
         nfix=0.0, source="FAO + Meyvecilik Araştırma Enstitüsü", chill=300),
    dict(name="Badem", group="Çok yıllık", months=12, sow=[0], t=[8, 15, 26, 35],
         need=550, soil=[.08, .20, .55, .82], rh=[20, 35, 65, 88], sun=5.0, frost=-10,
         nfix=0.0, source="FAO + Meyvecilik Araştırma Enstitüsü", chill=100),
    dict(name="Nar", group="Çok yıllık", months=12, sow=[0], t=[10, 18, 30, 38],
         need=650, soil=[.12, .28, .65, .88], rh=[25, 40, 75, 92], sun=5.5, frost=-8,
         nfix=0.0, source="FAO + Batı Akdeniz Tarımsal Araştırma Enstitüsü", chill=40),
]
# Eski etiketler tam bir yayın/sayfa atfı içermiyordu. Sayıları değiştirmeden
# gerçek kökenini belirt: doğrulanmayı bekleyen proje parametreleri.
for _crop in CROPS:
    _crop['source'] = 'Proje ekin parametreleri (varsayım; saha doğrulaması yok). Genel su yöntemi: FAO-56.'
BY_NAME = {c["name"]: c for c in CROPS}

# Ana puanlama ağırlıkları (toplam 1.0)
WEIGHTS = dict(t=.26, w=.20, soil=.12, rh=.08, sun=.10, frost=.16, chill=.08)

# Çok yıllıklarda vejetasyon dönemi (Nisan..Ekim)
GROW_SEASON = list(range(3, 10))

# Rotasyon değerlendirme ağırlıkları
ROT_WEIGHTS = dict(fit=.50, water=.18, soil=.14, diversity=.10, economy=.08)

# İklim projeksiyon senaryoları: (ad, yıllık ısınma °C, yıllık yağış değişimi,
# yıllık kök nemi değişimi)
SCENARIOS = [
    ("Düşük değişim (proje varsayımı)", 0.025, -0.002, -0.001),
    ("Orta değişim (proje varsayımı)", 0.045, -0.004, -0.003),
    ("Yüksek değişim (proje varsayımı)", 0.075, -0.007, -0.005),
]

DEMO = {  # internet yokken denemek için yaklaşık Konya iklimi
    "T":    [-0.3, 1.2, 5.5, 10.5, 15.5, 19.8, 23.3, 22.5, 18.0, 12.0, 5.5, 1.5],
    "Tmin": [-5.8, -4.3, -0.5, 4.0, 8.5, 12.3, 15.8, 15.0, 10.5, 6.0, 0.5, -4.0],
    "Pm":   [33, 25, 30, 40, 45, 30, 8, 6, 12, 28, 30, 38],
    "RH":   [75, 70, 62, 57, 55, 48, 41, 41, 46, 57, 68, 76],
    "SW":   [1.7, 2.6, 3.8, 5.0, 6.2, 7.1, 7.2, 6.5, 5.2, 3.4, 2.1, 1.5],
    "GW":   [.45, .50, .50, .45, .40, .30, .20, .18, .20, .28, .38, .45],
}

# Türkiye için bölgesel toprak profili (SoilGrids 0-30 cm tabanlı yaklaşım)
SOIL_ZONES = {
    "konya": dict(clay=34, sand=38, ph=7.8, soc=1.1, label="Kireçli, killi-tınlı step toprağı"),
    "adana": dict(clay=30, sand=34, ph=7.4, soc=1.6, label="Alüvyal, tınlı akarsu toprağı"),
    "samsun": dict(clay=38, sand=24, ph=6.1, soc=2.4, label="Asidik, killi Karadeniz toprağı"),
    "izmir": dict(clay=26, sand=44, ph=7.1, soc=1.3, label="Tınlı, taşlı Ege toprağı"),
    "şanlıurfa": dict(clay=40, sand=30, ph=7.9, soc=0.9, label="Kırmızımsı, kireçli GAP toprağı"),
    "sanliurfa": dict(clay=40, sand=30, ph=7.9, soc=0.9, label="Kırmızımsı, kireçli GAP toprağı"),
    "erzurum": dict(clay=32, sand=36, ph=6.8, soc=1.7, label="Volkanik, tınlı yayla toprağı"),
    "trabzon": dict(clay=36, sand=26, ph=5.9, soc=2.6, label="Asidik, killi Doğu Karadeniz toprağı"),
    "bursa": dict(clay=30, sand=36, ph=6.9, soc=1.8, label="Tınlı, Marmara geçiş toprağı"),
    "antalya": dict(clay=28, sand=40, ph=7.6, soc=1.5, label="Kırmızımsı Akdeniz, tınlı toprak"),
    "rize": dict(clay=34, sand=28, ph=5.5, soc=2.9, label="Asidik, killi Doğu Karadeniz toprağı"),
    "i̇stanbul": dict(clay=31, sand=35, ph=6.9, soc=1.6, label="Tınlı, Marmara geçiş toprağı"),
    "ankara": dict(clay=35, sand=36, ph=7.7, soc=1.2, label="Kireçli, killi-tınlı step toprağı"),
    "gaziantep": dict(clay=38, sand=32, ph=7.8, soc=1.0, label="Kırmızımsı, kireçli Güneydoğu toprağı"),
    "kayseri": dict(clay=34, sand=38, ph=7.6, soc=1.1, label="Volkanik-kireçli, tınlı İç Anadolu toprağı"),
    "mersin": dict(clay=30, sand=38, ph=7.5, soc=1.4, label="Kırmızımsı Akdeniz, tınlı toprak"),
    "diyarbakır": dict(clay=40, sand=30, ph=7.7, soc=1.0, label="Kırmızımsı, killi Güneydoğu toprağı"),
}
SOIL_DEFAULT = dict(clay=33, sand=34, ph=7.2, soc=1.4, label="Tınlı, ortalama Anadolu toprağı")


# ------------------------------------------------------------------ yardımcı
def clamp(x, a, b):
    return min(b, max(a, x))


def trap(x, a, b, c, d):
    if x <= a or x >= d:
        return 0.0
    if x < b:
        return (x - a) / (b - a)
    return 1.0 if x <= c else (d - x) / (d - c)


def peak(x, a, b, c, d):
    """Yamuk üyelik + ideal aralığın ortasına yakınlık payı."""
    return trap(x, a, b, c, d) * (0.85 + 0.15 * (1 - clamp(abs(x - (b + c) / 2) / ((d - a) / 2), 0, 1)))


def weighted_geo(parts, weights):
    total = sum(weights[k] for k in weights)
    return math.exp(sum(weights[k] * math.log(max(parts[k], .02)) for k in weights) / total)


# ---------------------------------------------------------------- veri
def http_json(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r:
                return json.load(r)
        except Exception as exc:  # ağ dalgalanmalarına iki kez daha şans ver
            last = exc
            if i < tries - 1:
                time.sleep(1.5 * (i + 1))
    raise last


def geocode(query):
    """'enlem, boylam' ya da yer adı -> (ad, enlem, boylam)."""
    m = re.match(r"^\s*(-?\d+(?:[.,]\d+)?)\s*[,; ]\s*(-?\d+(?:[.,]\d+)?)\s*$", query)
    if m:
        lat, lon = (float(g.replace(",", ".")) for g in m.groups())
        return f"{lat:.3f}, {lon:.3f}", lat, lon
    url = "https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode(
        {"name": query, "count": 1, "language": "tr", "format": "json"})
    res = (http_json(url).get("results") or [None])[0]
    if not res:
        raise SystemExit(f"'{query}' bulunamadı. Başka yazımla ya da 'enlem, boylam' ile deneyin.")
    ad = res["name"] + (", " + res["admin1"] if res.get("admin1") else "")
    return ad, res["latitude"], res["longitude"]


def fetch_nasa(lat, lon):
    """NASA POWER klimatoloji verisi -> aylık 12'şer değerlik listeler."""
    params = "T2M,T2M_MIN,PRECTOTCORR,RH2M,GWETROOT,ALLSKY_SFC_SW_DWN"
    url = ("https://power.larc.nasa.gov/api/temporal/climatology/point?"
           f"parameters={params}&community=AG&longitude={lon}&latitude={lat}&format=JSON")
    par = http_json(url, timeout=60)["properties"]["parameter"]

    def get(name):
        vals = [par[name][k] for k in KEYS]
        if any(v is None or v < -900 for v in vals):
            raise ValueError(f"NASA POWER eksik veri döndürdü: {name}")
        return vals

    return {"T": get("T2M"), "Tmin": get("T2M_MIN"),
            "Pm": [v * d for v, d in zip(get("PRECTOTCORR"), DIM)],  # mm/gün -> mm/ay
            "RH": get("RH2M"), "GW": get("GWETROOT"),
            "SW": [v * KWH_PER_UNIT for v in get("ALLSKY_SFC_SW_DWN")]}


def soil_for(name):
    low = (name or "").replace("İ", "i").replace("I", "ı").lower()
    for key, prof in SOIL_ZONES.items():
        if key.replace("i̇", "i") in low.replace("i̇", "i") or key in low:
            return dict(prof, source="Proje bölgesel toprak profili (varsayım; tarla ölçümü değil)")
    return dict(SOIL_DEFAULT, source="Proje varsayılan toprak profili (varsayım; tarla ölçümü değil)")


# Bölgesel profillerin temsil ettiği il merkezleri (enlem, boylam)
SOIL_ZONE_COORDS = {
    "konya": (37.87, 32.48), "adana": (37.00, 35.32), "samsun": (41.29, 36.33),
    "izmir": (38.42, 27.14), "şanlıurfa": (37.16, 38.79), "erzurum": (39.90, 41.27),
    "trabzon": (41.00, 39.72), "bursa": (40.19, 29.06), "antalya": (36.89, 30.71),
    "rize": (41.02, 40.52), "i̇stanbul": (41.01, 28.98), "ankara": (39.93, 32.86),
    "gaziantep": (37.07, 37.38), "kayseri": (38.72, 35.49), "mersin": (36.81, 34.64),
    "diyarbakır": (37.91, 40.24),
}


def soil_near(lat, lon, max_km=150):
    """Koordinata en yakın bölgesel toprak profili (haritadan seçilen tarla için).

    max_km içinde profil yoksa varsayılan Anadolu profili döner.
    """
    best, best_d = None, None
    for key, (la, lo) in SOIL_ZONE_COORDS.items():
        dx = math.radians(lon - lo) * math.cos(math.radians((lat + la) / 2))
        dy = math.radians(lat - la)
        d = 6371.0 * math.hypot(dx, dy)
        if best_d is None or d < best_d:
            best, best_d = key, d
    if best is None or best_d > max_km:
        return dict(SOIL_DEFAULT, source="Proje varsayılan toprak profili (varsayım; tarla ölçümü değil)")
    return dict(SOIL_ZONES[best],
                source=f"Proje bölgesel toprak varsayımı (en yakın profil ≈{best_d:.0f} km; tarla ölçümü değil)")


def soil_penalty(crop, soil):
    """Toprak dokusundan gelen çarpan (0.6 - 1.0)."""
    clay, sand, ph = soil["clay"], soil["sand"], soil["ph"]
    f = 1.0
    if crop["group"] == "Çok yıllık" and crop["name"] in ("Zeytin", "Üzüm (bağ)"):
        f *= 0.90 if clay > 38 else 1.0
    if crop["name"] == "Pirinç":
        f *= 1.0 if clay >= 30 else 0.85
    if crop["name"] in ("Patates", "Şeker pancarı"):
        f *= 1.0 if sand >= 30 else 0.88
    if crop["name"] == "Fındık":
        f *= 1.0 if ph <= 6.8 else 0.80
    if crop["name"] == "Çay":                       # çay asidik toprak ister
        f *= 1.0 if ph <= 6.0 else 0.70
    if crop["name"] in ("Patates", "Kuru soğan", "Karpuz", "Kavun", "Havuç", "Sarımsak"):
        f *= 1.0 if clay <= 38 else 0.92            # ağır killi toprakta yumru/kök gelişimi zorlaşır
    if crop["name"] == "Yer fıstığı":               # kabuklar toprak içinde gelişir: kumlu toprak
        f *= 1.0 if sand >= 35 else 0.85
    if crop["name"] in ("Narenciye", "Mandalina"):  # çok kireçli toprakta demir eksikliği
        f *= 1.0 if ph <= 8.0 else 0.90
    if crop["name"] in ("Antep fıstığı", "İncir", "Kayısı", "Kiraz", "Badem", "Ceviz", "Nar"):
        f *= 0.92 if clay > 40 else 1.0             # ağır, su tutan killi toprak kökü boğar
    if crop["name"] in ("Mısır", "Ayçiçeği", "Kışlık buğday", "Arpa", "Nohut", "Mercimek",
                        "Yulaf", "Çavdar", "Kuru fasulye", "Soya", "Kanola", "Susam",
                        "Sorgum", "Tritikale", "Bezelye", "Bakla"):
        f *= 1.0 if 6.0 <= ph <= 8.2 else 0.9
    return clamp(f, 0.6, 1.0)


def chill_units(climate):
    """Soğuklama göstergesi: vejetasyon dışı ayların 4 °C altı sıcaklık toplamı."""
    months = [m for m in range(12) if m not in GROW_SEASON]
    return sum(max(0.0, 4.0 - climate["T"][m]) for m in months) * 30


def aridity_index(climate):
    """Kuraklık göstergesi: kış yağışı / kış sıcaklığı (yükseldikçe nemli)."""
    w = [9, 10, 11, 0, 1, 2]
    p = sum(climate["Pm"][m] for m in w) / 6
    t = sum(climate["T"][m] for m in w) / 6
    return p / max(1.0, t)


# ---------------------------------------------------------------- puanlama
def evaluate(crop, c, sulama, soil=None):
    """Tek ekin için en iyi ekim penceresini bul ve puanla."""
    best = None
    ch = chill_units(c)
    for s in crop["sow"]:
        if crop["months"] == 12:
            T = sum(c["T"][i] for i in GROW_SEASON) / len(GROW_SEASON)
            GW = sum(c["GW"][i] for i in GROW_SEASON) / len(GROW_SEASON)
            RH = sum(c["RH"][i] for i in GROW_SEASON) / len(GROW_SEASON)
            SW = sum(c["SW"][i] for i in GROW_SEASON) / len(GROW_SEASON)
            P = sum(c["Pm"])
            tmin = min(c["Tmin"][i] for i in GROW_SEASON)
            win_min = min(c["Tmin"][m] for m in range(12) if m not in GROW_SEASON)
            idx = list(range(12))
        else:
            idx = [(s + k) % 12 for k in range(crop["months"])]
            T = sum(c["T"][i] for i in idx) / len(idx)
            GW = sum(c["GW"][i] for i in idx) / len(idx)
            RH = sum(c["RH"][i] for i in idx) / len(idx)
            SW = sum(c["SW"][i] for i in idx) / len(idx)
            P = sum(c["Pm"][i] for i in idx)
            tmin = min(c["Tmin"][i] for i in idx)
            win_min = tmin
        r = P / crop["need"]

        sT = peak(T, *crop["t"])
        sW = peak(r, .2, .75, 2, 4)
        if sulama and r < .75:
            sW = max(sW, .75)
        sS = peak(GW, *crop["soil"])
        if sulama and GW < crop["soil"][1]:
            sS = max(sS, .75)
        sR = peak(RH, *crop["rh"])
        sU = clamp((SW - crop["sun"] * .6) / (crop["sun"] * .4), 0, 1)
        sF = 1.0 if tmin >= crop["frost"] else clamp(1 - (crop["frost"] - tmin) / 6, 0, 1)
        if crop["months"] == 12:
            sF = min(sF, 1.0 if win_min >= crop["frost"] - 4
                     else clamp(1 - (crop["frost"] - 4 - win_min) / 10, 0, 1))
            need_ch = crop.get("chill", 0)
            sC = 1.0 if not need_ch else clamp(ch / need_ch, 0, 1)
        else:
            sC = 1.0

        parts = dict(t=sT, w=sW, soil=sS, rh=sR, sun=sU, frost=sF, chill=sC)
        score = weighted_geo(parts, WEIGHTS) * 100
        if soil:
            score *= soil_penalty(crop, soil)
        if best is None or score > best["puan"] + 1e-9:
            best = {
                "ekin": crop["name"], "grup": crop["group"], "puan": round(score, 1),
                "ekim_ayi": None if crop["months"] == 12 else MONTHS[s],
                "sure_ay": crop["months"], "aylar": idx,
                "kriter": {k: crop[k] for k in ("t", "need", "soil", "rh", "sun", "frost")},
                "kaynak": crop["source"], "nfix": crop["nfix"],
                "sulama_ihtiyaci_mm": crop["need"],
                "ortalama_gunes": round(SW, 1),
                "sulama_acigi_mm": round(max(0.0, crop["need"] - P)),
                "ortalama_sicaklik": round(T, 1), "toplam_yagis_mm": round(P),
                "kok_bolgesi_nemi": round(GW, 2), "bagil_nem": round(RH),
                "en_soguk_gece": round(tmin, 1),
                "kis_en_soguk": round(win_min, 1),
                "soguklama": round(ch),
                "faktorler": {"sicaklik": round(sT, 2), "su": round(sW, 2),
                              "toprak_nemi": round(sS, 2), "nem": round(sR, 2),
                              "gunes": round(sU, 2), "don": round(sF, 2),
                              "soguklama": round(sC, 2)},
            }
    return best


def rank(c, sulama=False, soil=None):
    out = [evaluate(cr, c, sulama, soil) for cr in CROPS]
    return sorted([o for o in out if o], key=lambda r: -r["puan"])


def tier(score):
    return "Uygun" if score >= 75 else "Orta" if score >= 45 else "Zayıf"


# ---------------------------------------------------------------- rotasyon
def rotation_score(seq, results):
    by = {r["ekin"]: r for r in results}
    items = [by[n] for n in seq if n in by]
    if not items:
        return None
    fit = sum(i["puan"] for i in items) / len(items)
    water = 1.0 - clamp(sum(i["sulama_acigi_mm"] for i in items) / (len(items) * 450), 0, 1)
    nfix = sum(BY_NAME[i["ekin"]]["nfix"] for i in items) / len(items)
    has_grain = any(BY_NAME[i["ekin"]]["group"] == "Tahıl" for i in items)
    soil_health = clamp(0.45 + 0.45 * nfix + (0.10 if has_grain else 0), 0, 1)
    groups = len({i["grup"] for i in items})
    diversity = clamp((groups - 1) / 2.5, 0, 1)
    money = [i["puan"] for i in items if i["grup"] in ("Endüstri", "Sebze")]
    economy = clamp((sum(money) / len(money) if money else 0) / 100, 0, 1)
    parts = dict(fit=fit / 100, water=water, soil=soil_health, diversity=diversity, economy=economy)
    score = weighted_geo(parts, ROT_WEIGHTS) * 100
    return {"puan": round(score, 1),
            "faktorler": {k: round(v, 2) for k, v in parts.items()},
            "ekinler": items}


def build_rotations(results, sulama):
    """En iyi ekinlerden 4 strateji üret (biri mevcut rotasyon)."""
    # Rotasyon yıldan yıla değişen ekinlerle kurulur; bağ, bahçe gibi çok yıllıklar girmez.
    results = [r for r in results if r["grup"] != "Çok yıllık"]
    if not results:
        return []
    top = [r["ekin"] for r in results[:8]]
    tahil = [r["ekin"] for r in results if r["grup"] == "Tahıl"][:2]
    baklagil = [r["ekin"] for r in results if r["grup"] == "Baklagil"][:2]
    endustri = [r["ekin"] for r in results if r["grup"] in ("Endüstri", "Sebze")][:2]

    def safe(*names):
        out = []
        for n in names:
            if n and n in top and n not in out:
                out.append(n)
        while len(out) < 3 and top:
            for n in top:
                if n not in out:
                    out.append(n)
                    break
        return out[:3]

    adaylar = [
        ("Mevcut rotasyon",
         "Bugün tarlada uyguladığınız sıra: iki tahıl + bir endüstri bitkisi.",
         safe(tahil[0] if tahil else None, tahil[1] if len(tahil) > 1 else None,
              endustri[0] if endustri else None)),
        ("Azot bağlayan rotasyon",
         "Baklagil araya girer, toprağa biyolojik azot kazandırır; gübre ihtiyacı düşer.",
         safe(baklagil[0] if baklagil else None, tahil[0] if tahil else None,
              endustri[0] if endustri else None)),
        ("Su tasarruflu rotasyon",
         "Sezon su açığı en düşük üç ekin; sulama kısıtı olan tarlalar için.",
         safe(*[r["ekin"] for r in sorted(results, key=lambda r: r["sulama_acigi_mm"])[:3]])),
        ("Toprak sağlığı odaklı rotasyon",
         "Baklagil + tahıl + endüstri dönüşü; organik madde ve hastalık döngüsünü kırar.",
         safe(baklagil[-1] if baklagil else None, tahil[-1] if tahil else None,
              endustri[-1] if endustri else None)),
    ]
    out, seen = [], set()
    for name, why, seq in adaylar:
        key = tuple(seq)
        if not seq or key in seen:
            continue
        seen.add(key)
        ev = rotation_score(seq, results)
        if not ev:
            continue
        risks = []
        for it in ev["ekinler"]:
            if it["sulama_acigi_mm"] > 200 and not sulama:
                risks.append(f"{it['ekin']}: {it['sulama_acigi_mm']} mm su açığı")
            if it["faktorler"]["don"] < .6:
                risks.append(f"{it['ekin']}: don riski (en soğuk gece {it['en_soguk_gece']} °C)")
        out.append(dict(name=name, why=why, seq=seq, puan=ev["puan"],
                        faktorler=ev["faktorler"], riskler=risks[:3],
                        kanit=[f"{i['ekin']} uygunluğu {i['puan']}/100 ({tier(i['puan'])})"
                               for i in ev["ekinler"]]))
    return sorted(out, key=lambda r: -r["puan"])


# ---------------------------------------------------------------- senaryo
def simulate_scenarios(crop_name, climate, sulama=False, soil=None, years=10, runs=300, seed=42):
    """İklim projeksiyonu + rastgelelik ile 10 yıllık belirsizlik bandı."""
    crop = BY_NAME.get(crop_name)
    if crop is None:
        raise ValueError("Seçilen ekin bulunamadı: " + str(crop_name))
    rnd = random.Random(seed)

    def sd(v):
        m = sum(v) / len(v)
        return math.sqrt(sum((x - m) ** 2 for x in v) / max(1, len(v) - 1))

    sdT = max(0.8, sd(climate["T"]))
    sdP = max(0.10, sd(climate["Pm"]) / max(1.0, sum(climate["Pm"]) / 12))
    sdGW = max(0.02, sd(climate["GW"]))

    out = []
    for sname, dT, dP, dGW in SCENARIOS:
        yearly = []
        for y in range(1, years + 1):
            pts = []
            for _ in range(runs):
                cc = {k: list(v) for k, v in climate.items()}
                for i in range(12):
                    cc["T"][i] += dT * y + rnd.gauss(0, sdT * 0.55)
                    cc["Tmin"][i] += dT * y + rnd.gauss(0, sdT * 0.75)
                    cc["Pm"][i] = max(0.0, cc["Pm"][i] * (1 + dP * y) * (1 + rnd.gauss(0, sdP * 0.6)))
                    cc["GW"][i] = clamp(cc["GW"][i] + dGW * y + rnd.gauss(0, sdGW * 0.5), 0, 1.3)
                r = evaluate(crop, cc, sulama, soil)
                if r:
                    pts.append(r["puan"])
            pts.sort()
            pick = lambda q: pts[min(len(pts) - 1, int(q * len(pts)))]
            yearly.append({"yil": y, "p10": round(pick(.10), 1), "p50": round(pick(.50), 1),
                           "p90": round(pick(.90), 1)})
        out.append({"ad": sname, "yillar": yearly})
    return out


# ---------------------------------------------------------------- 10 yıllık görünüm (v2.5)
# Geçmiş yıllar arası değişkenlik için NASA POWER aylık seri penceresi
HIST_START, HIST_END = 2001, 2024
HIST_NAMES = {"T": "T2M", "Tmin": "T2M_MIN", "P": "PRECTOTCORR", "RH": "RH2M",
              "GW": "GWETROOT", "SW": "ALLSKY_SFC_SW_DWN"}


def history_anomalies(par, start=HIST_START, end=HIST_END):
    """NASA POWER aylık serisi ('YYYYMM' anahtarlı) -> yıl yıl sapma kümeleri.

    Her yıl için 12 aylık sapma tutulur; böylece "sıcak ve kurak yıl" gibi
    değişkenler arası ve aylar arası ilişkiler korunur. Sıcaklıkta doğrusal
    eğilim çıkarılır (ısınma, değişkenlik olarak iki kez sayılmasın).
      T, Tmin, RH, GW : fark (yıl - ortalama)
      P, SW           : oran (yıl / ortalama)
    """
    rows = []
    for y in range(start, end + 1):
        row = {}
        for k, name in HIST_NAMES.items():
            vals = [(par.get(name) or {}).get(f"{y}{m:02d}") for m in range(1, 13)]
            if any(v is None or v < -900 for v in vals):
                row = None
                break
            row[k] = vals
        if row:
            rows.append((y, row))
    n = len(rows)
    if n < 10:
        raise ValueError("Geçmiş seride yeterli tam yıl yok (%d)." % n)
    mean = {k: [sum(r[k][m] for _, r in rows) / n for m in range(12)] for k in HIST_NAMES}
    ys = [y for y, _ in rows]
    ym = sum(ys) / n
    den = sum((y - ym) ** 2 for y in ys)

    def slope(k):
        ann = [sum(r[k]) / 12 for _, r in rows]
        am = sum(ann) / n
        return sum((y - ym) * (a - am) for y, a in zip(ys, ann)) / den if den else 0.0

    sl = {"T": slope("T"), "Tmin": slope("Tmin")}
    out = []
    for y, r in rows:
        a = {"yil": y}
        for k in ("T", "Tmin"):
            a[k] = [r[k][m] - mean[k][m] - sl[k] * (y - ym) for m in range(12)]
        for k in ("RH", "GW"):
            a[k] = [r[k][m] - mean[k][m] for m in range(12)]
        a["P"] = [clamp(r["P"][m] / mean["P"][m], 0, 4) if mean["P"][m] > 0.1 else 1.0
                  for m in range(12)]
        a["SW"] = [clamp(r["SW"][m] / mean["SW"][m], .5, 1.5) if mean["SW"][m] > 0 else 1.0
                   for m in range(12)]
        out.append(a)
    observations = [
        {"yil": y, "sicaklik": sum(r["T"]) / 12,
         "yagis": sum(p * days for p, days in zip(
             r["P"], [calendar.monthrange(y, m)[1] for m in range(1, 13)]))}
        for y, r in rows
    ]
    return {"yillar": out, "gozlemler": observations, "baslangic": ys[0], "bitis": ys[-1],
            "egilim_T": round(sl["T"] * 10, 2)}      # gözlenen ısınma, °C / 10 yıl


def fetch_history(lat, lon, start=HIST_START, end=HIST_END):
    """NASA POWER aylık zaman serisi -> history_anomalies çıktısı."""
    url = ("https://power.larc.nasa.gov/api/temporal/monthly/point?"
           f"parameters={','.join(HIST_NAMES.values())}&community=AG"
           f"&longitude={lon}&latitude={lat}&start={start}&end={end}&format=JSON")
    par = http_json(url, timeout=60, tries=2)["properties"]["parameter"]
    return history_anomalies(par, start, end)


def _synthetic_anomaly(rnd):
    """Geçmiş seri yokken kullanılan varsayılan yıl sapması (parametrik).

    Varsayım: yıllık sıcaklık sapması sd 0,7 °C, yıllık yağış sd %20, sıcak
    yıllar hafifçe kurak (korelasyon -0,3); üzerine aylık bağımsız oynaklık.
    """
    zt = rnd.gauss(0, 1)
    zp = -0.3 * zt + math.sqrt(1 - 0.09) * rnd.gauss(0, 1)
    T = [0.7 * zt + rnd.gauss(0, 1.0) for _ in range(12)]
    return {"T": T, "Tmin": [t + rnd.gauss(0, 0.5) for t in T],
            "P": [max(0.0, (1 + 0.20 * zp) * (1 + rnd.gauss(0, 0.45))) for _ in range(12)],
            "GW": [0.04 * zp + rnd.gauss(0, 0.02) for _ in range(12)],
            "RH": [3.0 * zp + rnd.gauss(0, 3.0) for _ in range(12)],
            "SW": [clamp(1 - 0.03 * zp + rnd.gauss(0, 0.04), .5, 1.5) for _ in range(12)]}


def _apply(climate, an, dT, dP, dGW, y):
    """Klimatoloji + (senaryo eğilimi × yıl) + o yılın sapması -> bir olası yıl."""
    return {
        "T": [climate["T"][m] + dT * y + an["T"][m] for m in range(12)],
        "Tmin": [climate["Tmin"][m] + dT * y + an["Tmin"][m] for m in range(12)],
        "Pm": [max(0.0, climate["Pm"][m] * (1 + dP * y) * an["P"][m]) for m in range(12)],
        "GW": [clamp(climate["GW"][m] + dGW * y + an["GW"][m], 0, 1.3) for m in range(12)],
        "RH": [clamp(climate["RH"][m] + an["RH"][m], 5, 100) for m in range(12)],
        "SW": [climate["SW"][m] * an["SW"][m] for m in range(12)],
    }


def _pct(sorted_vals, q):
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def simulate_outlook(crop_name, climate, sulama=False, soil=None, history=None,
                     years=10, runs=300, crop_runs=150, seed=42, include_crops=True):
    """Kapsamlı 10 yıllık görünüm.

    Seçili ekin için her senaryoda yıl yıl: uygunluk bandı (p10/p50/p90),
    Uygun/Orta/Zayıf yıl payları, sezon su açığı bandı, sınırlayıcı faktör.
    Tüm ekinler için: bugünkü iklim ile son yıl karşılaştırması.

    history verilirse (fetch_history) yıllar arası değişkenlik gerçek geçmiş
    yıllardan yeniden örneklenir; yoksa parametrik varsayım kullanılır.
    Üç senaryo aynı rastgele yılları kullanır: fark yalnızca eğilimden gelir.
    Yıl 0 = eğilimsiz, yalnızca değişkenlik ("bugünkü iklim").
    """
    crop = BY_NAME.get(crop_name)
    if crop is None:
        raise ValueError("Seçilen ekin bulunamadı: " + str(crop_name))
    rnd = random.Random(seed)
    pool = (history or {}).get("yillar") or []

    def draw():
        if not pool:
            return _synthetic_anomaly(rnd)
        a = rnd.choice(pool)        # gerçek bir geçmiş yıl + küçük pürüzsüzleştirme
        jt = rnd.gauss(0, 0.2)
        jp = 1 + rnd.gauss(0, 0.05)
        return {"T": [v + jt for v in a["T"]], "Tmin": [v + jt for v in a["Tmin"]],
                "P": [v * jp for v in a["P"]], "GW": a["GW"], "RH": a["RH"], "SW": a["SW"]}

    # Aynı hava koşullarını her yıl ve senaryoda yeniden kullanarak eğilimi karşılaştır.
    draws = [draw() for _ in range(runs)]
    crop_runs = min(crop_runs, runs)

    def year_stats(y, dT, dP, dGW):
        scores, deficits, lows = [], [], {}
        for an in draws:
            r = evaluate(crop, _apply(climate, an, dT, dP, dGW, y), sulama, soil)
            scores.append(r["puan"])
            deficits.append(r["sulama_acigi_mm"])
            f = r["faktorler"]
            low = min(f, key=f.get)
            lows[low] = lows.get(low, 0) + 1
        n = len(scores)
        scores.sort()
        deficits.sort()
        zayif = sum(1 for v in scores if v < 45) / n
        uygun = sum(1 for v in scores if v >= 75) / n
        return {"yil": y, "p10": round(_pct(scores, .10), 1), "p50": round(_pct(scores, .50), 1),
                "p90": round(_pct(scores, .90), 1),
                "uygun": round(uygun, 3), "orta": round(1 - uygun - zayif, 3),
                "zayif": round(zayif, 3),
                "su_p10": round(_pct(deficits, .10)), "su_p50": round(_pct(deficits, .50)),
                "su_p90": round(_pct(deficits, .90)),
                "sinirlayici": max(lows, key=lows.get)}

    def crop_medians(y, dT, dP, dGW):
        out = {}
        for c in CROPS:
            v = sorted(evaluate(c, _apply(climate, an, dT, dP, dGW, y), sulama, soil)["puan"]
                       for an in draws[:crop_runs])
            out[c["name"]] = (_pct(v, .10), _pct(v, .50), _pct(v, .90))
        return out

    base_year = year_stats(0, 0, 0, 0)
    base_crops = crop_medians(0, 0, 0, 0) if include_crops else {}
    senaryolar = []
    for sname, dT, dP, dGW in SCENARIOS:
        yillar = [base_year] + [year_stats(y, dT, dP, dGW) for y in range(1, years + 1)]
        son = crop_medians(years, dT, dP, dGW) if include_crops else {}
        ekinler = [{"ekin": c["name"], "grup": c["group"],
                    "bugun": round(base_crops[c["name"]][1], 1),
                    "p10": round(son[c["name"]][0], 1), "p50": round(son[c["name"]][1], 1),
                    "p90": round(son[c["name"]][2], 1),
                    "degisim": round(son[c["name"]][1] - base_crops[c["name"]][1], 1)}
                   for c in CROPS if c["name"] in son]
        ekinler.sort(key=lambda e: -e["p50"])
        senaryolar.append({"ad": sname, "yillar": yillar, "ekinler": ekinler,
                           "iklim": {"dT": round(dT * years, 2),
                                     "dP_yuzde": round(dP * years * 100, 1)}})
    return {"ekin": crop_name, "yil_sayisi": years, "calistirma": runs,
            "yontem": "gecmis" if pool else "parametrik",
            "gecmis": ({"baslangic": history["baslangic"], "bitis": history["bitis"],
                        "yil": len(pool), "egilim_T": history.get("egilim_T")}
                       if pool else None),
            "senaryolar": senaryolar}


# ---------------------------------------------------------------- açıklama
FACTOR_NAMES = {"sicaklik": "sıcaklık", "su": "yağış/su", "toprak_nemi": "toprak nemi",
                "nem": "bağıl nem", "gunes": "güneş enerjisi", "don": "don riski",
                "soguklama": "soğuklama ihtiyacı"}


def explain(result, climate, soil, sulama):
    """Ekin önerisi için gerekçe + risk + bilgi boşluğu metni."""
    f = result["faktorler"]
    weak = sorted(f.items(), key=lambda x: x[1])[:2]
    gerekce = (f"{result['ekin']}, {result['ekim_ayi'] or 'yıl boyu'} döneminde "
               f"{result['ortalama_sicaklik']} °C ortalama sıcaklık ve "
               f"{result['toplam_yagis_mm']} mm yağışla {result['puan']}/100 uygunluk alıyor.")
    risk = []
    for k, v in weak:
        if v < .7:
            risk.append(f"{FACTOR_NAMES[k]} sınırlayıcı (puan {int(v * 100)}/100)")
    if result["sulama_acigi_mm"] > 150 and not sulama:
        risk.append(f"sezon boyunca ≈{result['sulama_acigi_mm']} mm sulama gerekir")
    bosluk = ("Değerlendirme aylık NASA klimatolojisi ve bölgesel toprak profiline dayanır; "
              "tarla bazlı toprak analizi, çeşit seçimi ve yerel don olaylarıyla doğrulanmalıdır.")
    return {"gerekce": gerekce, "riskler": risk, "bilgi_boslugu": bosluk}


# ---------------------------------------------------------------- komut satırı
def main():
    ap = argparse.ArgumentParser(description="NASA POWER verisine göre en uygun ekin önerisi")
    ap.add_argument("konum", help="yer adı ya da 'enlem, boylam'")
    ap.add_argument("--sulama", action="store_true", help="sulama imkânım var")
    ap.add_argument("--top", type=int, default=8, help="gösterilecek ekin sayısı")
    ap.add_argument("--json", action="store_true", help="çıktıyı JSON ver")
    ap.add_argument("--demo", action="store_true", help="internetsiz örnek (Konya) veriyle çalış")
    a = ap.parse_args()

    if a.demo:
        ad, clim = "Konya (örnek veri)", DEMO
    else:
        ad, lat, lon = geocode(a.konum)
        try:
            clim = fetch_nasa(lat, lon)
        except Exception as e:
            sys.exit(f"NASA POWER verisi alınamadı: {e}")
    soil = soil_for(ad)

    tum = rank(clim, a.sulama, soil)
    sonuc = tum[:a.top]
    if a.json:
        print(json.dumps({"konum": ad, "sulama": a.sulama, "toprak": soil, "sonuclar": sonuc},
                         ensure_ascii=False, indent=2))
        return
    print(f"\nKonum: {ad}   Sulama: {'var' if a.sulama else 'yok'}   Toprak: {soil['label']}\n")
    print(f"{'#':>2}  {'Ekin':<16}{'Puan':>6}  {'Ekim':<10}{'Yağış':>8}{'Su açığı':>10}")
    for i, r in enumerate(sonuc, 1):
        print(f"{i:>2}  {r['ekin']:<16}{r['puan']:>6.1f}  {(r['ekim_ayi'] or 'çok yıllık'):<10}"
              f"{r['toplam_yagis_mm']:>6} mm{r['sulama_acigi_mm']:>7} mm")
    en = sonuc[0]
    ex = explain(en, clim, soil, a.sulama)
    print(f"\nÖneri: {en['ekin']} — {tier(en['puan'])}")
    print("  " + ex["gerekce"])
    for r in ex["riskler"]:
        print("  risk: " + r)
    rots = build_rotations(tum, a.sulama)
    if rots:
        print("\nRotasyon stratejileri:")
        for r in rots:
            print(f"  {r['puan']:>5.1f}  {r['name']:<30} {' → '.join(r['seq'])}")


if __name__ == "__main__":
    main()
