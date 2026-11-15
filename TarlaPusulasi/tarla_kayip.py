"""Tarla ve dönem için kaynak dengesi; NASA referansları ayrıdır (v3.5).

Yararlı kullanım oranları seçili tarlaya göre TAHMİNİ olarak önerilir ve ekranda öyle
etiketlenir; kullanıcı kendi ölçümünü yazınca o kullanılır.

Tahmin dayanakları
  Su     : tarla uygulama randımanı — FAO (Brouwer vd. 1989, Irrigation Water Management
           Training Manual 4): yüzey/karık ~%60, yağmurlama ~%75, damla ~%90.
           Kumlu toprakta derine sızma, killi toprakta yüzey akışı; sıcak-kurak iklimde
           yağmurlamada buharlaşma kaybı için küçük düzeltmeler.
  Gübre  : azot kullanım verimi — Raun & Johnson (1999) dünya tahıl ortalaması ~%33.
           Kumlu toprak / yağışlı iklim (yıkanma) ve damla ile gübreleme için düzeltme.
  Enerji : sulama pompa grubu toplam verimi — Nebraska pompa performans ölçütü elektrikli
           pompa için ~%66; sahadaki pompalar çoğu zaman bunun altında, tahmin %55.
  Diğer  : dayanak yok, tahmin üretilmez.
"""
from datetime import date, timedelta
import json
import math
import re
import threading
import urllib.parse
import urllib.request

NASA_WATER_URL = 'https://www.nasa.gov/missions/station/iss-research/nasa-achieves-water-recovery-milestone-on-international-space-station/'
POWER_DOCS = 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'
CACHE = {}


def parse_number(text):
    """'1.200,5' · '1200.5' · '%70' · '70 %' · ' 1 200 ' gibi yazımları sayıya çevir."""
    t = str(text or '').strip().replace('%', '').replace(' ', '').replace('\u00a0', '')
    if not t:
        return None
    if ',' in t and '.' in t:
        t = t.replace('.', '').replace(',', '.') if t.rfind(',') > t.rfind('.') else t.replace(',', '')
    elif ',' in t:
        t = t.replace(',', '.')
    elif t.count('.') > 1 or re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')          # 1.200 / 1.200.000 = binlik ayırıcı
    return float(t)


def calculate(field, start, end, resources):
    if not field or len(field.get('noktalar') or []) < 3:
        raise ValueError('Önce bir tarla seçin.')
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError:
        raise ValueError('Tarihleri YYYY-AA-GG biçiminde girin.') from None
    days = (b-a).days + 1
    if not 1 <= days <= 366:
        raise ValueError('Tarih aralığı 1–366 gün olmalı.')
    lat, lon = float(field['lat']), float(field['lon'])
    area = float(field.get('alan_m2') or 0)
    if not all(math.isfinite(v) for v in (lat, lon, area)) or area <= 0 or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Tarla sınırı ve alanı geçerli değil.')
    rows = []
    for key, label, unit, amount, useful in resources:
        # Miktarı boş satır hesaba girmez (oran tahminle dolu olsa bile).
        try:
            amount = parse_number(amount)
        except ValueError:
            raise ValueError(f'{label}: miktar sayı olmalı (ör. 1200 ya da 1.200,5).') from None
        if amount is None:
            continue
        try:
            useful = parse_number(useful)
        except ValueError:
            raise ValueError(f'{label}: yararlı kullanım yüzde olarak yazılmalı (ör. 70).') from None
        if useful is None:
            raise ValueError(f'{label}: yararlı kullanım oranını da girin (0–100).')
        if not math.isfinite(amount) or amount < 0:
            raise ValueError(f'{label}: miktar negatif olamaz.')
        if not math.isfinite(useful) or not 0 <= useful <= 100:
            raise ValueError(f'{label}: yararlı kullanım 0 ile 100 arasında olmalı.')
        loss = amount*(1-useful/100)
        rows.append(dict(key=key, label=label, unit=unit, amount=amount, useful=amount-loss,
                         loss=loss, percent=100-useful, per_ha=loss/(area/10000), per_day=loss/days))
    if not rows:
        raise ValueError('En az bir kaynağın miktarını girin (ör. sulama suyu m³).')
    return dict(start=start, end=end, days=days, lat=lat, lon=lon, area_m2=area, rows=rows)


def fetch_period(lat, lon, start, end, timeout=18):
    """Tam istenen konum/dönem; eksik günler sıfır kabul edilmez."""
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if b >= date.today():
        return {'future': True}
    key=(round(lat,5),round(lon,5),start,end)
    if key in CACHE:return CACHE[key]
    q=urllib.parse.urlencode(dict(latitude=lat,longitude=lon,start=a.strftime('%Y%m%d'),
        end=b.strftime('%Y%m%d'),parameters='T2M,PRECTOTCORR',community='AG',format='JSON'))
    url='https://power.larc.nasa.gov/api/temporal/daily/point?'+q
    req=urllib.request.Request(url,headers={'User-Agent':'TarlaPusulasi/3.4'})
    with urllib.request.urlopen(req,timeout=timeout) as r:data=json.load(r)
    params=data['properties']['parameter'];total=(b-a).days+1
    valid={}
    for param in ('T2M','PRECTOTCORR'):
        vals=[]
        for i in range(total):
            d=(a+timedelta(days=i)).strftime('%Y%m%d');v=params.get(param,{}).get(d)
            if isinstance(v,(int,float)) and math.isfinite(v) and v > -900 and (param != "PRECTOTCORR" or v >= 0):
                vals.append(v)
            else:
                vals.append(None)
        valid[param]=vals
    temps, rain = ([v for v in valid[key] if v is not None] for key in ('T2M', 'PRECTOTCORR'))
    result=dict(temperature=sum(temps)/len(temps) if temps else None,
                rain=sum(rain) if rain else None,temp_days=len(temps),rain_days=len(rain),days=total,url=url,series=valid)
    CACHE[key]=result
    return result


METHODS = (("yuzey", "Karık / salma"), ("yagmur", "Yağmurlama"), ("damla", "Damla"))
RESOURCES = (("water", "Sulama suyu", "m³", "≋"), ("fertilizer", "Azot miktarı (kg N)", "kg N", "✦"),
             ("energy", "Enerji (pompa)", "kWh", "ϟ"), ("other", "Diğer girdi", "kg", "◇"))


def estimate(soil, clim, crop=None, method="yuzey"):
    """FAO'nun yöntem referansı; tarla verim ölçümü değildir.

    Gübre ve pompa için genel literatür senaryoları kullanılır; saha ölçümü değildir.
    """
    if method not in dict(METHODS):
        return {}
    base = {"yuzey": 60, "yagmur": 75, "damla": 90}[method]
    return {
        "water": dict(deger=base, alt=base, ust=base,
            neden=f"{dict(METHODS)[method]} için genel uygulama verimi %{base}. "
                  "Saha ölçümü değildir. Kaynak: FAO sulama randımanları (t7202e)."),
        "fertilizer": dict(deger=33, alt=33, ust=33,
            neden="Azot kullanımında genel tahıl literatüründen yaklaşık %33 örnek oran. "
                  "Ürüne, toprağa ve uygulamaya göre çok değişir; ölçüm değildir. "
                  "Kaynak: Raun ve Johnson (1999), Agronomy Journal."),
        "energy": dict(deger=55, alt=55, ust=55,
            neden="Pompa+motor için varsayımsal %55 toplam faydalı enerji senaryosu. "
                  "Gerçek verim pompa eğrisi ve ölçümlerle belirlenir; saha ölçümü değildir. "
                  "Referans: Nebraska pompa performans ölçütleri."),
    }

def water_need_m3(result, area_m2, efficiency_pct):
    """Seçili ekinin sezonluk su açığından tarla için TAHMİNİ brüt sulama ihtiyacı (m³)."""
    if not result or not area_m2 or not efficiency_pct:
        return None
    deficit = float(result.get("sulama_acigi_mm") or 0)
    if deficit <= 0:
        return 0.0
    return deficit / 1000.0 * area_m2 / (efficiency_pct / 100.0)


def open_window(app):
    import tkinter as tk
    import sys
    import time
    ui = sys.modules[app.__class__.__module__]
    import tarla_dil as lang
    NoTr = lang.NoTr
    if not app._require_field(app.open_resource_loss, 'Kaynak kaybı analizi',
        'için önce tarla sınırını seçin. Haritada en az 3 köşe işaretleyip “Bu tarlayı kullan”a basın. Sonra tarih aralığını ve kaynak miktarlarını girebilirsiniz.'):
        return
    field = dict(app.field)
    name = app.name or 'Seçili tarla'
    crop = app.current() or {}
    crop_info = next((c for c in ui.tp.CROPS if c["name"] == crop.get("ekin")), None)
    win = app._window('Kaynak kaybı analizi')
    form = dict(getattr(app, '_loss_form', {}) or {})
    today = date.today()
    form.setdefault('start', (today - timedelta(days=31)).isoformat())
    form.setdefault('end', (today - timedelta(days=2)).isoformat())
    form.setdefault('method', 'yuzey')
    S = dict(busy=False, report=None, nasa=None, error=None, t=1.0, gen=0, details=False,
             hits=[], phase=0.0, est=None, guard=False, used_est=set())
    V = {}
    entries = {}

    # ---------------------------------------------------------------- başlık
    head = tk.Frame(win, bg=ui.BG)
    head.pack(fill='x', padx=26, pady=(20, 6))
    badge = tk.Canvas(head, width=50, height=50, bg=ui.BG, highlightthickness=0)
    badge.pack(side='left')
    tb = tk.Frame(head, bg=ui.BG)
    tb.pack(side='left', padx=(12, 0), fill='x', expand=True)
    heading = tk.Label(tb, text='Kaynak kaybı analizi', bg=ui.BG, fg=ui.FG,
                       font=app.F(17, True), anchor='w', justify='left')
    heading.pack(anchor='w', fill='x')
    tk.Label(tb, text='Miktarı ve işe yarayan payı girin. Sonuçta kalan miktarı görün.',
             bg=ui.BG, fg=ui.MUT, font=app.F(9), justify='left', wraplength=560).pack(anchor='w')
    chips = tk.Canvas(win, bg=ui.BG, height=34, highlightthickness=0)
    chips.pack(fill='x', padx=26, pady=(2, 12))

    def draw_badge():
        badge.delete('all')
        ph = S['phase']
        badge.create_oval(3, 3, 47, 47, fill=ui.ACC_SOFT, outline=ui.ACC2, width=2)
        r = 10 + 3 * math.sin(ph * 2)
        badge.create_oval(25 - r, 25 - r, 25 + r, 25 + r, outline=ui.lerp(ui.ACC_SOFT, ui.ACC, .5), width=2)
        badge.create_text(25, 25, text='◈', fill=ui.ACC, font=app.F(15, True))

    def draw_chips():
        chips.delete('all')
        x = 0
        items = [(NoTr(name), ui.FG2),
                 (f"{field['alan_m2'] / 1000:.1f} da".replace('.', ','), ui.FG2)]
        if crop.get('ekin'):
            items.append((crop['ekin'], ui.ACC))
        if app.soil:
            items.append((app.soil.get('label', ''), ui.MUT))
        for txt, col in items:
            if x + app.tw(txt, 9) + 24 > chips.winfo_width():
                break
            x = app.chip(chips, x, 6, txt, col)

    # ---------------------------------------------------------------- gövde: sol girdi, sağ sonuç
    body = tk.Frame(win, bg=ui.BG)
    body.pack(fill='both', expand=True, padx=26, pady=(0, 18))
    panel = tk.Frame(body, bg=ui.CARD, width=380, highlightthickness=1, highlightbackground=ui.LINE)
    panel.pack(side='left', fill='y')
    panel.pack_propagate(False)
    # Düğme ve durum satırı önce, alta yerleşir: yazı ölçeği büyük olsa da hep görünür.
    run_btn = app.button(panel, 'Sonucu göster', lambda: run(), primary=True, height=44)
    run_btn.pack(side='bottom', fill='x', padx=18, pady=(6, 16))
    status = tk.Label(panel, text='', bg=ui.CARD, fg=ui.MUT, font=app.F(10, True), justify='left',
                      wraplength=400)
    status.pack(side='bottom', anchor='w', padx=18, pady=(8, 0))
    tk.Frame(panel, bg=ui.LINE, height=1).pack(side='bottom', fill='x')
    scroll = tk.Canvas(panel, bg=ui.CARD, highlightthickness=0, bd=0, yscrollincrement=24)
    scroll.pack(side='top', fill='both', expand=True)
    left = tk.Frame(scroll, bg=ui.CARD)
    left_id = scroll.create_window(0, 0, window=left, anchor='nw')
    left.bind('<Configure>', lambda e: scroll.configure(scrollregion=scroll.bbox('all')))
    scroll.bind('<Configure>', lambda e: scroll.itemconfigure(left_id, width=e.width))
    right = tk.Frame(body, bg=ui.BG)
    right.pack(side='left', fill='both', expand=True, padx=(18, 0))
    cv = tk.Canvas(right, bg=ui.BG, highlightthickness=0, yscrollincrement=30)
    cv.pack(side='left', fill='both', expand=True)

    def section(parent, title, top=16):
        tk.Label(parent, text=title, bg=ui.CARD, fg=ui.MUT2, font=app.F(9, True)).pack(
            anchor='w', padx=18, pady=(top, 6))

    def entry(parent, var, width=12):
        e = tk.Entry(parent, textvariable=var, bg=ui.CARD2, fg=ui.FG, insertbackground=ui.ACC,
                     relief='flat', font=app.F(11), width=width, highlightthickness=1,
                     highlightbackground=ui.LINE2, highlightcolor=ui.ACC2, justify='right')
        e.bind('<Return>', lambda ev: run())
        var.trace_add('write', lambda *_a: schedule())
        entries[id(var)] = e
        return e

    # -- dönem
    section(left, '1. Tarih aralığı')
    dates = tk.Frame(left, bg=ui.CARD)
    dates.pack(fill='x', padx=18)
    for i, (key, title) in enumerate((('start', 'Başlangıç'), ('end', 'Bitiş'))):
        tk.Label(dates, text=title, bg=ui.CARD, fg=ui.FG2, font=app.F(9)).grid(row=0, column=i, sticky='w', padx=(0, 10))
        V[key] = tk.StringVar(value=form[key])
        e = entry(dates, V[key], 14)
        e.configure(justify='left')
        e.grid(row=1, column=i, sticky='ew', padx=(0, 10), ipady=5)
        dates.columnconfigure(i, weight=1)
    quick = tk.Frame(left, bg=ui.CARD)
    quick.pack(fill='x', padx=18, pady=(8, 0))
    Q = (('Son 30 gün', 31), ('Son 90 gün', 91), ('Geçen yıl', 'yil'))
    def quick_pick(val):
        if val == 'yil':
            y = today.year - 1
            V['start'].set(f'{y}-01-01')
            V['end'].set(f'{y}-12-31')
        else:
            V['start'].set((today - timedelta(days=val)).isoformat())
            V['end'].set((today - timedelta(days=2)).isoformat())
    for column, (label, val) in enumerate(Q):
        button = app.button(quick, label, lambda value=val: quick_pick(value), small=True)
        button.configure(width=1)
        button.grid(row=0, column=column, sticky='nsew', padx=(0, 4))
        quick.columnconfigure(column, weight=1, uniform='dates')

    # -- sulama yöntemi (tahmini etkiler)
    input_head = tk.Frame(left, bg=ui.CARD)
    input_head.pack(fill='x', padx=18, pady=(12, 4))
    app._help_button(input_head, 'Miktar ve yararlı pay').pack(side='right')
    tk.Label(input_head, text='2. Miktar ve yararlı pay', bg=ui.CARD, fg=ui.FG,
             font=app.F(11, True), anchor='w').pack(side='left', fill='x', expand=True)
    method_host = tk.Frame(left, bg=ui.CARD)
    method_host.pack(fill='x', padx=18, pady=(0, 8))
    tk.Label(method_host, text='Sulama yöntemi', bg=ui.CARD, fg=ui.MUT,
             font=app.F(9)).pack(anchor='w')
    methods = dict(METHODS)
    method = tk.StringVar(value=methods.get(form['method'], METHODS[0][1]))
    def change_method(label):
        form['method'] = next(key for key, title in METHODS if title == label)
        apply_estimates()
    menu = tk.OptionMenu(method_host, method, *methods.values(), command=change_method)
    menu.configure(bg=ui.CARD2, fg=ui.FG, highlightthickness=0, relief='flat', anchor='w')
    menu.pack(fill='x')

    # -- kaynaklar
    grid = tk.Frame(left, bg=ui.CARD)
    grid.pack(fill='x', padx=18)
    for j, title in enumerate(('', 'Miktar', 'Yararlı %', '')):
        tk.Label(grid, text=title, bg=ui.CARD, fg=ui.MUT, font=app.F(9)).grid(row=0, column=j, sticky='e' if j in (1, 2) else 'w', padx=4)
    tags = {}
    for i, (key, title, unit, icon) in enumerate(RESOURCES, 1):
        cell = tk.Frame(grid, bg=ui.CARD)
        cell.grid(row=i, column=0, sticky='w', pady=6)
        tk.Label(cell, text=title, bg=ui.CARD, fg=ui.FG, font=app.F(10, True),
                 wraplength=125, justify='left').pack(anchor='w')
        tk.Label(cell, text=unit, bg=ui.CARD, fg=ui.MUT, font=app.F(8)).pack(anchor='w')
        V[key + '_amount'] = tk.StringVar(value=form.get(key + '_amount', ''))
        V[key + '_useful'] = tk.StringVar(value=form.get(key + '_useful', ''))
        entry(grid, V[key + '_amount'], 6).grid(row=i, column=1, sticky='ew', padx=4, ipady=4)
        entry(grid, V[key + '_useful'], 5).grid(row=i, column=2, sticky='ew', padx=4, ipady=4)
        tg = tk.Canvas(grid, bg=ui.CARD, width=74, height=42, highlightthickness=0, cursor='hand2')
        tg.grid(row=i, column=3, padx=(4, 0))
        tags[key] = tg

        def typed(*_a, key=key):
            if not S['guard']:
                form[key + '_src'] = 'kullanici' if V[key + '_useful'].get().strip() else ''
                draw_tag(key)
        V[key + '_useful'].trace_add('write', typed)
        tg.bind('<Button-1>', lambda e, key=key: reset_estimate(key))
    grid.columnconfigure(1, weight=1)
    tk.Label(left, text='Boş satırları atlayın. Örnek: 100 m³ su ve %75 yararlı pay → 25 m³ kalan su.',
             bg=ui.CARD, fg=ui.MUT, font=app.F(9), justify='left', wraplength=360).pack(anchor='w', padx=18, pady=8)
    from tarla_arayuz import fold
    details = fold(left, 'Oranlar nasıl belirleniyor?', ui.CARD2, ui.FG, app.F(9, True))
    hint = tk.Label(details, text='', bg=ui.CARD2, fg=ui.MUT, font=app.F(9), justify='left', wraplength=350)
    hint.pack(anchor='w', padx=18, pady=(4, 0))
    use_need = tk.Label(details, text='', bg=ui.CARD2, fg=ui.WATER, font=app.F(9, True), cursor='hand2')
    use_need.pack(anchor='w', padx=18)
    note = tk.Label(details, text='', bg=ui.CARD2, fg=ui.GOLD, font=app.F(9), justify='left', wraplength=350)
    note.pack(anchor='w', padx=18, pady=(8, 0))
    tk.Frame(left, bg=ui.CARD, height=12).pack()

    def draw_tag(key):
        tg = tags[key]
        tg.delete('all')
        src = form.get(key + '_src', '')
        if key == 'other' and src != 'kullanici':
            tg.create_text(37, 12, text='—', fill=ui.MUT2, font=app.F(9))
            return
        if src == 'tahmin':
            app.rrect(tg, 1, 2, 73, 22, 10, fill=ui.lerp(ui.CARD, ui.GOLD, .14), outline=ui.GOLD)
            tg.create_text(37, 15, text='Tahmin', fill=ui.GOLD, font=app.F(8, True), width=68)
        elif src == 'kullanici':
            app.rrect(tg, 1, 2, 73, 22, 10, fill=ui.ACC_SOFT, outline=ui.ACC2)
            tg.create_text(37, 15, text='Elle girildi', fill=ui.ACC, font=app.F(8, True), width=68)
        else:
            tg.create_text(37, 12, text='—', fill=ui.MUT2, font=app.F(9))

    def apply_estimates(force=False):
        """Kullanıcının yazmadığı oranlara tarlaya göre tahmini yaz."""
        S['est'] = est = estimate(app.soil, app.clim, crop_info, form['method'])
        S['guard'] = True
        for key, _t, _u, _i in RESOURCES:
            if key not in est:
                if form.get(key + '_src') != 'kullanici':
                    V[key + '_useful'].set('')
                    form[key + '_src'] = ''
                continue
            if force or form.get(key + '_src', 'tahmin') in ('tahmin', ''):
                if force or form.get(key + '_src') != 'kullanici':
                    V[key + '_useful'].set(str(est[key]['deger']))
                    form[key + '_src'] = 'tahmin'
        S['guard'] = False
        for key in tags:
            draw_tag(key)
        lines = [f"{key.upper()} · %{value['deger']}: {value['neden']}" for key, value in est.items()]
        hint.configure(text=NoTr(lang.tr('Tahmin dayanağı') + ' — ' + ' · '.join(lang.tr(l) for l in lines)))
        note.configure(text='Su oranı sulama yönteminin genel FAO referansıdır; tarlanızda ölçülmedi. '
                            'Azotu gübre ürününün toplam kg miktarı olarak girmeyin: ürün kg × azot yüzdesi / 100 kullanın. '
                            'Azot için %33, pompa enerjisi için %55 genel deneme varsayımıdır; tarlanızdaki gerçek verimi göstermez. ')
        need = water_need_m3(crop, field.get('alan_m2'), est['water']['deger'])
        if need:
            use_need.configure(text=NoTr('≋ ' + lang.tr('Tahmini sezonluk sulama ihtiyacı') + f' ≈ {number(need)} m³ · '
                                         + lang.tr('miktara yaz')))
            use_need._need = need
        else:
            use_need.configure(text='')

    def reset_estimate(key):
        if form.get(key + '_src') == 'kullanici' and S['est'] and key in S['est']:
            form[key + '_src'] = 'tahmin'
            S['guard'] = True
            V[key + '_useful'].set(str(S['est'][key]['deger']))
            S['guard'] = False
            draw_tag(key)

    def fill_need(e=None):
        need = getattr(use_need, '_need', None)
        if need:
            V['water_amount'].set(str(round(need)))
    use_need.bind('<Button-1>', fill_need)

    def number(value):
        out = f'{value:,.1f}'.rstrip('0').rstrip('.')
        if lang.lang() in ('tr', 'de'):
            out = out.replace(',', '_').replace('.', ',').replace('_', '.')
        return out

    # ---------------------------------------------------------------- sonuç çizimi
    def text(x, y, string, size=11, color=None, bold=False, width=None, anchor='nw'):
        item = cv.create_text(x, y, text=string, fill=color or ui.FG2, font=app.F(size, bold),
                              width=width or 0, anchor=anchor)
        b = cv.bbox(item)
        return b[3] if b else y + size * 2

    def ring(cx, cy, r, useful_pct, t, width=11):
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=ui.LINE2, width=width)
        good = max(0, min(100, useful_pct)) / 100
        a = 360 * good * t
        if a > .1:
            cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=90, extent=-min(359.9, a),
                          style='arc', outline=ui.ACC, width=width)
        b_ = 360 * (1 - good) * t
        if b_ > .1:
            cv.create_arc(cx - r, cy - r, cx + r, cy + r, start=90 - a, extent=-min(359.9, b_),
                          style='arc', outline=ui.GOLD, width=width)
        text(cx, cy, number(useful_pct) + '%', 17, ui.ACC, True, anchor='center')

    def stag(t, i, n=4):
        """i. kartın kendi animasyon payı (sırayla belirir)."""
        return max(0.0, min(1.0, t * (1 + .18 * n) - .18 * i))

    def render():
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        cv.delete('all')
        S['hits'] = []
        w = cv.winfo_width() - 6
        h = cv.winfo_height()
        if w < 260:
            return
        rep, t = S['report'], S['t']
        if not rep:                      # boş durum: nefes alan halkalar
            y = text(23, 28, '3. Sonucu inceleyin', 17, ui.FG, True, width=w - 46)
            bottom = text(23, y + 10, 'Soldaki formda en az bir kaynağın miktarını ve yararlı payını girin. '
                          'Sonucu göster düğmesine basın.', 11, ui.MUT, width=w - 46)
            surface = app.rrect(cv, 2, 5, w - 1, bottom + 26, 14, fill=ui.CARD, outline=ui.LINE)
            cv.tag_lower(surface)
            cv.configure(scrollregion=(0, 0, w, max(h, bottom + 30)))
            return
        y = 4
        # -- özet şeridi
        tot = [r for r in rep['rows'] if r['amount'] > 0]
        y = text(4, y, 'Ne kadarı yararlı kullanılıyor?', 17, ui.FG, True, width=w - 8) + 4
        y = text(4, y, NoTr(f"{rep['start']} — {rep['end']} · {rep['days']} " + lang.tr('gün')), 10, ui.MUT) + 12
        if any(r['key'] in S['used_est'] for r in rep['rows']):
            end = text(16, y + 10, 'TAHMİNİ ORAN KULLANILDI · ' + ', '.join(lang.tr(r['label']) for r in rep['rows']
                 if r['key'] in S['used_est']) + ' — sonuçlar tahmindir, ölçüm değildir.',
                 9, ui.GOLD, True, width=w - 30)
            bg = app.rrect(cv, 2, y, w - 2, end + 10, 12,
                           fill=ui.lerp(ui.CARD, ui.GOLD, .10), outline=ui.GOLD)
            cv.tag_lower(bg)
            y = end + 24
        gap, cw = 16, w
        for i, row in enumerate(rep['rows']):
            k = stag(t, i, len(rep['rows']))
            x, top = 0, y
            est = row['key'] in S['used_est']
            end = text(x + 20, top + 16, row['label'], 13, ui.FG, True, width=cw - 40)
            if est:
                end = text(x + 20, end + 2, 'Tahmin', 9, ui.GOLD, width=cw - 40)
            end = text(x + 20, end + 6, NoTr(lang.tr('Tüm dönem') + f": {number(row['amount'])} {row['unit']} · "
                                        + lang.tr('yararlı') + f" %{number(100 - row['percent'])}"), 9, ui.MUT,
                 width=cw - 40)
            columns = ((20, 'Yararlı kullanılan', row['useful'], ui.ACC),
                       (cw / 2 + 6, 'Yararlı kullanılmayan', row['loss'], ui.GOLD))
            label_bottoms = [text(xx, end + 12, label, 9, ui.MUT, width=cw / 2 - 27)
                             for xx, label, _, _ in columns]
            values = [text(xx, max(label_bottoms) + 3, NoTr(f"{number(value * k)} {row['unit']}"),
                           16, color, True, width=cw / 2 - 27) for xx, _, value, color in columns]
            # NASA karşılaştırmasındaki gibi okunabilir yüzde halkası.
            # Kullanılan oran kullanıcı girdisi/tahminidir; geri kazanım verisi değildir.
            by = max(values) + 20
            share = max(0.0, min(100.0, 100.0 - row['percent']))
            radius = 43 if cw >= 370 else 33
            cx, cy = x + 24 + radius, by + radius + 5
            ring(cx, cy, radius, share, k, width=10)
            xx = cx + radius + 22
            detail_width = max(90, cw - xx - 20)
            detail = text(xx, by + 2, NoTr(f"%{number(share)} yararlı kullanıldı"),
                          13, ui.ACC, True, width=detail_width)
            detail = text(xx, detail + 5, NoTr(f"%{number(row['percent'])} yararlı kullanılmadı"),
                          11, ui.GOLD, True, width=detail_width)
            detail = text(xx, detail + 7, 'Ölçüm değil; girdiğiniz kullanım oranına göre hesaplandı.'
                          if est else 'Girdiğiniz kullanım oranına göre hesaplandı.',
                          9, ui.MUT, width=detail_width)
            bottom = text(x + 20, max(by + 2 * radius + 19, detail + 10),
                          NoTr(f"{number(row['per_ha'])} {row['unit']}/ha · "
                          f"{number(row['per_day'])} {row['unit']}/" + lang.tr('gün') + ' '
                          + lang.tr('kullanılmayan')), 9, ui.MUT, width=cw - 40)
            bg = app.rrect(cv, x + 1, top, x + cw - 1, bottom + 14, 14, fill=ui.CARD, outline=ui.LINE)
            cv.tag_lower(bg)
            y = bottom + 14 + gap
        # -- NASA ISS kıyası
        k = stag(t, len(rep['rows']), len(rep['rows']) + 1)
        top = y
        y = text(20, top + 18, 'NASA’dan bir örnek: uzayda su döngüsü', 15, ui.FG, True, width=w - 40) + 4
        y = text(20, y, 'ISS · 2023 · yaşam destek sistemi', 9, ui.MUT, width=w - 40) + 10
        ring(76, y + 58, 42, 98, k)
        xx = 138
        e = text(xx, y + 8, 'Suyun %98’i geri kazanıldı.', 15, ui.ACC, True, width=w - xx - 20) + 6
        e = text(xx, e, 'Bu tarla hedefi değil; farklı bir sistem.', 11, ui.GOLD, True, width=w - xx - 20) + 6
        water = next((r for r in rep['rows'] if r['key'] == 'water' and r['amount'] > 0), None)
        msg = lang.tr('Su geri kazanımı, tarladaki yararlı kullanımla aynı şey değildir.')
        if water:
            msg += ' ' + lang.tr('Aynı miktarla sadece ölçek örneği:') + \
                f" {number(water['amount'])} m³ → {number(water['amount'] * .02)} m³ " + lang.tr('geri kazanılmayan su.')
        e = text(xx, e, NoTr(msg), 10, ui.FG2, width=w - xx - 20)
        e = text(20, max(y + 120, e + 10), 'Gübre ve enerji için doğrulanmış NASA kıyas oranı yok; sayı üretilmez.',
                 9, ui.MUT, width=w - 40)
        bg = app.rrect(cv, 0, top, w, e + 16, 16, fill=ui.lerp(ui.BG, ui.CARD, k), outline=ui.lerp(ui.BG, ui.ACC2, k))
        cv.tag_lower(bg)
        y = e + 34
        # -- dönem havası
        y = text(4, y, 'Seçtiğin dönemde hava nasıldı?', 15, ui.FG, True, width=w - 8) + 4
        y = text(4, y, 'NASA POWER · seçili konum ve dönem', 9, ui.MUT, width=w - 8) + 10
        climate = S['nasa']
        if S['error'] or climate is None or climate.get('future'):
            msg = ('NASA verisi alınamadı. Senaryo hesabı NASA ölçümü olarak sunulmaz.' if S['error'] else
                   'NASA dönem verileri yükleniyor' + '.' * (1 + int(S['phase'] * 3) % 3) if climate is None else
                   'Bu dönem henüz tamamlanmadı; NASA POWER gözlemi yerine tahmin üretilmedi.')
            app.rrect(cv, 0, y, w, y + 70, 14, fill=ui.CARD, outline=ui.LINE)
            text(20, y + 35, msg, 10, ui.MUT, anchor='w', width=w - 40)
            y += 86
        else:
            for title, key, unit, cnt, col, param in (
                    ('Ortalama sıcaklık', 'temperature', '°C', 'temp_days', ui.GOLD, 'T2M'),
                    ('Toplam yağış', 'rain', 'mm', 'rain_days', ui.WATER, 'PRECTOTCORR')):
                top = y
                y = text(20, y + 12, title, 10, ui.MUT, width=w - 40) + 3
                val = climate[key]
                y = text(20, y, '—' if val is None else NoTr(f'{number(val)} {unit}'),
                         17, col, True, width=w - 40) + 4
                y = text(20, y, NoTr(f"{climate[cnt]}/{climate['days']} " + lang.tr('gün veri var')),
                         9, ui.MUT, width=w - 40) + 10
                series = climate.get('series', {}).get(param, [])
                data = [value for value in series if value is not None]
                if data:
                    lo = min(data) if param == 'T2M' else 0
                    hi = max(data)
                    x, width, height = 20, w - 40, 58
                    step = width / max(1,len(series) - 1)
                    previous = None
                    cv.create_line(x, y + height, x + width, y + height, fill=ui.LINE2)
                    for index, value in enumerate(series):
                        if value is None:
                            previous = None
                            continue
                        px = x + index * step
                        py = y + height - 4 - (height - 8) * (value - lo) / max(1e-6, hi - lo)
                        if param == 'PRECTOTCORR':
                            if value > 0:
                                cv.create_line(px, py, px, y + height, fill=col, width=max(1, min(4, step * .65)))
                        else:
                            if previous is not None:
                                cv.create_line(*previous, px, py, fill=col, width=2)
                            if previous is None:
                                cv.create_oval(px - 2, py - 2, px + 2, py + 2, fill=col, outline='')
                            previous = (px, py)
                    y += height + 8
                    y = text(20, y, NoTr(f"{rep['start']}  →  {rep['end']}"), 9, ui.MUT, width=w - 40) + 3
                bg = app.rrect(cv, 0, top, w, y + 10, 14, fill=ui.CARD, outline=ui.LINE)
                cv.tag_lower(bg)
                y += 24
        y = text(4, y, 'Bu bir senaryodur; gerçek kayıp ölçülmedi. TAHMİNİ etiketli oranlar uygulamanın önerisidir.',
                 10, ui.GOLD, width=w - 8) + 14
        more = ('− ' if S['details'] else '+ ') + lang.tr('Hesap ve kaynak ayrıntılarını gizle' if S['details']
                                                          else 'Hesap ve kaynak ayrıntıları')
        bottom = text(4, y, NoTr(more), 10, ui.ACC, True, width=w - 8)
        S['hits'].append((0, y - 5, w, bottom + 8))
        y = bottom + 14
        if S['details']:
            lines = ['Yöntem: yararlı kullanılmayan = uygulanan miktar × (1 − yararlı kullanım oranı / 100).',
                     'Gübrede ilk ürünün almadığı azot toprakta kalabilir; kalan miktarın tamamı çevreye kayıp sayılmaz. Günlük değer dönem ortalamasıdır, günlük ölçüm değildir.']
            if S['est']:
                for key, label in (('water', 'Su'), ('fertilizer', 'Gübre'), ('energy', 'Enerji')):
                    ee = S['est'].get(key)
                    if ee is None:
                        continue
                    lines.append(NoTr(lang.tr(label) + f" · " + lang.tr('tahmin') + f" %{ee['deger']} "
                                      f"(%{ee['alt']}–%{ee['ust']}): " + lang.tr(ee['neden'])))
            lines += ['Eksik günler sıfır sayılmaz. POWER verisi bölgeseldir; parsel sensörü veya su/gübre kayıp ölçümü değildir.',
                      'Su yöntemi: FAO Ek I — https://www.fao.org/4/t7202e/t7202e08.htm. Diğer oranlar kullanıcı girdisidir.',
                      NoTr(NASA_WATER_URL), NoTr(POWER_DOCS)]
            for m in lines:
                y = text(4, y, m, 9, ui.MUT, width=w - 8) + 8
        cv.configure(scrollregion=(0, 0, w, y + 16))

    def animate():
        S['gen'] += 1
        g = S['gen']
        if not ui.ANIM:
            S['t'] = 1.0
            render()
            return
        S['t'] = 0.0

        def frame(e):
            if g == S['gen']:
                S['t'] = e
                render()
        app._tween(1100, frame, win)

    def save_form():
        app._loss_form = dict(form, **{k: v.get() for k, v in V.items()})
    win._before_rebuild = save_form

    def mark_bad(msg):
        """Hatanın ait olduğu satırın kutularını kırmızı çerçevele."""
        for e in entries.values():
            e.configure(highlightbackground=ui.LINE2)
        for key, title, _u, _i in RESOURCES:
            if msg.startswith(lang.tr(title)) or msg.startswith(title):
                for k in ('_amount', '_useful'):
                    e = entries.get(id(V[key + k]))
                    if e is not None:
                        e.configure(highlightbackground=ui.BAD)

    def schedule():
        """Yazmayı bırakınca (0,7 sn) sonuç kendiliğinden güncellenir."""
        if S.get('job'):
            try:
                win.after_cancel(S['job'])
            except Exception:
                pass
        S['job'] = win.after(700, lambda: run(auto=True))

    def run(auto=False):
        S['job'] = None
        if S['busy']:
            if not auto:
                S['again'] = True
            return
        try:
            rep = calculate(field, V['start'].get(), V['end'].get(),
                            [(key, title, unit, V[key + '_amount'].get(), V[key + '_useful'].get())
                             for key, title, unit, _i in RESOURCES])
        except (ValueError, KeyError) as exc:
            msg = str(exc)
            if auto and not S['report'] and 'En az bir' in msg:
                status.configure(text='Miktarları yazın; sonuç kendiliğinden hesaplanır.', fg=ui.MUT)
                mark_bad('')
                return
            status.configure(text='⚠ ' + lang.tr(msg), fg=ui.BAD)
            mark_bad(msg)
            return
        mark_bad('')
        quiet = auto and S['report'] is not None and (rep['start'], rep['end']) == (
            S['report']['start'], S['report']['end'])
        S['used_est'] = {key for key, *_ in RESOURCES if form.get(key + '_src') == 'tahmin'
                         and any(r['key'] == key for r in rep['rows'])}
        save_form()
        run_btn.set_text('Grafikleri güncelle')
        if quiet:                           # aynı dönem: yalnızca rakamları güncelle
            S['report'] = rep
            status.configure(text='✓ ' + lang.tr('Sonuç güncellendi.'), fg=ui.ACC)
            render()
            return
        S.update(busy=True, report=rep, nasa=None, error=None)
        cv.yview_moveto(0)
        animate()
        status.configure(text='NASA dönem verileri yükleniyor…', fg=ui.MUT)
        box = {}

        def work():
            try:
                box['data'] = fetch_period(rep['lat'], rep['lon'], rep['start'], rep['end'])
            except Exception:
                box['error'] = True

        def wait():
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            if not box:
                win.after(120, wait)
                return
            S.update(busy=False, nasa=box.get('data'), error=box.get('error'))
            render()
            status.configure(text='✓ ' + lang.tr('Sonucun hazır. NASA bölümü için aşağı kaydır.'), fg=ui.ACC)
            if S.pop('again', False):
                run()
        threading.Thread(target=work, daemon=True).start()
        win.after(120, wait)

    def click(e):
        y = cv.canvasy(e.y)
        if any(x0 <= e.x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in S['hits']):
            S['details'] = not S['details']
            render()

    def hover(e):
        y = cv.canvasy(e.y)
        cv.configure(cursor='hand2' if any(x0 <= e.x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in S['hits']) else '')

    def tick():
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        S['phase'] += .05
        draw_badge()
        if not S['report'] or (S['nasa'] is None and not S['error']):
            if S['t'] >= 1:
                render()
        if ui.ANIM:
            win.after(60, tick)

    cv.bind('<Configure>', lambda e: render())
    cv.bind('<Button-1>', click)
    cv.bind('<Motion>', hover)
    draw_chips()
    apply_estimates()
    win._loss_vars = V
    win._loss_run = run
    win._loss_state = S
    win._appearance_refresh = lambda: (apply_estimates(), draw_chips(), render())
    chips.bind('<Configure>', lambda _e: draw_chips())
    draw_badge()
    render()
    if ui.ANIM:
        win.after(60, tick)
    return win
