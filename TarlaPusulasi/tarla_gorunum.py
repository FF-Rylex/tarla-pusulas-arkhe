"""Açık Tk ve yerel HTML pencerelerine ortak tema/dil yayını."""
from html import escape
import json
import re
import urllib.parse
import tarla_dil as dil

PALETTES={}
ACTIVE_PALETTE={}
RECENT_PALETTES=[]
THEME='koyu'
MOTION=True
_reverse={}
_source_cache={}
_canonical={phrase[0] for phrase in dil.PHRASES}


def set_theme(name, palettes, active=None):
    global THEME, PALETTES, ACTIVE_PALETTE
    if ACTIVE_PALETTE and ACTIVE_PALETTE not in RECENT_PALETTES:
        RECENT_PALETTES.append(ACTIVE_PALETTE)
    THEME, PALETTES = name, palettes
    ACTIVE_PALETTE = active if active is not None else palettes[name]


def state():
    return dict(theme=THEME,motion=MOTION,lang=dil.lang(),palette=ACTIVE_PALETTE,palettes=PALETTES,phrases=dil.PHRASES)


def source(text, code=None):
    if not isinstance(text,str) or isinstance(text,dil.NoTr):return text
    code=code or dil.lang()
    if code=='tr' or text in _canonical:return text
    cached=_source_cache.get((code,text))
    if cached is not None:return cached
    if code not in _reverse:
        table={p[1 if code=='en' else 2]:p[0] for p in dil.PHRASES}
        keys=sorted(table,key=len,reverse=True)
        rx=re.compile('|'.join((r'(?<!\w)' if k[0].isalnum() else '')+re.escape(k)+(r'(?!\w)' if k[-1].isalnum() else '') for k in keys))
        _reverse[code]=(table,rx)
    table,rx=_reverse[code]
    result=rx.sub(lambda m:table[m.group()],text)
    if len(_source_cache)>4000:_source_cache.clear()
    _source_cache[(code,text)]=result
    return result


def color(value,option=''):
    if not isinstance(value,str) or not value.startswith('#'):return value
    matches=[]
    for palette in (*PALETTES.values(), *RECENT_PALETTES, ACTIVE_PALETTE):
        matches += [k for k,v in palette.items() if v.lower()==value.lower()]
    if not matches:return value
    if value.lower()=='#ffffff':key='ON_ACC' if option in ('fg','foreground','activeforeground') else 'CARD'
    else:key=matches[0]
    return ACTIVE_PALETTE.get(key,value)

COLOR_OPTIONS=('bg','background','fg','foreground','activebackground','activeforeground','disabledbackground',
               'disabledforeground','insertbackground','selectbackground','selectforeground','highlightbackground',
               'highlightcolor','troughcolor','selectcolor','fill','outline')


def transform(kw, item_type=None):
    out=dict(kw)
    for k,v in out.items():
        if k in COLOR_OPTIONS:out[k]=color(v,"foreground" if k=="fill" and item_type=="text" else k)
    return out


def install(tk):
    if getattr(tk,'_tarla_gorunum',False):return
    tk._tarla_gorunum=True
    base=tk.BaseWidget.__init__
    def init(self,master,widgetName,cnf={},kw={},extra=()):
        opts=dict(cnf) if isinstance(cnf,dict) else {};opts.update(kw)
        original=source(opts['text']) if 'text' in opts else None
        if original is not None:opts['text']=dil.tr(original)
        base(self,master,widgetName,{},transform(opts),extra)
        if original is not None:self._ui_text=original
    tk.BaseWidget.__init__=init
    configure=tk.Misc._configure
    def conf(self,cmd,cnf,kw):
        if isinstance(cnf,(dict,type(None))):
            opts=dict(cnf or {});opts.update(kw)
            if 'text' in opts and cmd == 'configure':
                self._ui_text=source(opts['text']);opts['text']=dil.tr(self._ui_text)
            return configure(self,cmd,{},transform(opts))
        return configure(self,cmd,cnf,kw)
    tk.Misc._configure=conf
    create=tk.Canvas._create
    def make(self,itemType,args,kw):
        raw=source(kw['text']) if itemType=='text' and 'text' in kw else None
        opts = dict(kw)
        if raw is not None:
            opts['text'] = dil.tr(raw)
        if not getattr(self, "_ui_fixed_palette", False):
            opts = transform(opts, itemType)
        i=create(self,itemType,args,opts)
        if raw is not None:
            if not hasattr(self,'_ui_items'):self._ui_items={}
            self._ui_items[i]=raw
        return i
    tk.Canvas._create=make
    itemconf=tk.Canvas.itemconfigure
    def iconf(self,tag,cnf=None,**kw):
        if isinstance(cnf,(dict,type(None))):
            opts=dict(cnf or {});opts.update(kw)
            if 'text' in opts:
                raw = source(opts['text'])
                if not hasattr(self,'_ui_items'):self._ui_items={}
                for i in self.find_withtag(tag):self._ui_items[i]=raw
                opts['text'] = dil.tr(raw)
            items=self.find_withtag(tag)
            kind=self.type(items[0]) if items else None
            if not getattr(self, "_ui_fixed_palette", False):
                opts = transform(opts, kind)
            return itemconf(self,tag,**opts)
        return itemconf(self,tag,cnf,**kw)
    tk.Canvas.itemconfigure=tk.Canvas.itemconfig=iconf
    delete=tk.Canvas.delete
    def remove(self,*tags):
        sources=getattr(self,'_ui_items',{})
        for tag in tags:
            for i in self.find_withtag(tag):sources.pop(i,None)
        return delete(self,*tags)
    tk.Canvas.delete=remove
    title=tk.Wm.title
    def name(self,string=None):
        if string is None:
            return title(self)
        self._ui_title=source(string)
        return title(self,dil.tr(self._ui_title))
    tk.Wm.wm_title=tk.Wm.title=name
    text_insert=tk.Text.insert
    def insert(self,index,chars,*tags):
        return text_insert(self,index,dil.tr(chars),*tags)
    tk.Text.insert=insert
    menu_add=tk.Menu.add
    def add(self,itemType,cnf={},**kw):
        opts=dict(cnf);opts.update(kw)
        raw=source(opts['label']) if 'label' in opts else None
        if raw is not None:opts['label']=dil.tr(raw)
        result=menu_add(self,itemType,**transform(opts))
        if raw is not None:
            if not hasattr(self,'_ui_menu'):self._ui_menu={}
            self._ui_menu[self.index('end')]=raw
        return result
    tk.Menu.add=add
    option_init=tk.OptionMenu.__init__
    def option(self,master,variable,value,*values,**kw):
        option_init(self,master,variable,value,*values,**kw)
        display=tk.StringVar(master=self,value=dil.tr(variable.get()))
        self._ui_choice_source=variable;self._ui_choice_display=display
        self.configure(textvariable=display)
        variable.trace_add('write',lambda *a: display.set(dil.tr(variable.get())) if self.winfo_exists() else None)
    tk.OptionMenu.__init__=option


def refresh(root, previous_lang=None):
    import tkinter as tk
    def visit(w):
        if not w.winfo_exists():return
        opts={}
        for k in COLOR_OPTIONS:
            try:
                v=w.cget(k);v2=color(v,k)
                if v!=v2:opts[k]=v2
            except tk.TclError:pass
        if opts:w.configure(**opts)
        if hasattr(w,'_ui_text'):w.configure(text=w._ui_text)
        if isinstance(w,(tk.Tk,tk.Toplevel)) and hasattr(w,'_ui_title'):w.title(w._ui_title)
        if isinstance(w,tk.Canvas):
            for i in w.find_all():
                cfg={}
                for k in ('fill','outline'):
                    try:
                        v=w.itemcget(i,k);v2=v if getattr(w,'_ui_fixed_palette',False) else color(v,"foreground" if k=="fill" and w.type(i)=="text" else k)
                        if v!=v2:cfg[k]=v2
                    except tk.TclError:pass
                if i in getattr(w,'_ui_items',{}):cfg['text']=w._ui_items[i]
                if cfg:w.itemconfigure(i,**cfg)
        if isinstance(w,tk.Menu):
            for i,label in getattr(w,'_ui_menu',{}).items():
                try:w.entryconfigure(i,label=dil.tr(label))
                except tk.TclError:pass
        if hasattr(w,'_ui_choice_source'):w._ui_choice_display.set(dil.tr(w._ui_choice_source.get()))
        if isinstance(w,tk.Text) and str(w.cget('state'))=='disabled':
            text=source(w.get('1.0','end-1c'), previous_lang);w.configure(state='normal');w.delete('1.0','end');w.insert('1.0',dil.tr(text));w.configure(state='disabled')
        for child in w.winfo_children():visit(child)
        if hasattr(w,'_appearance_refresh'):w._appearance_refresh()
    visit(root)


_TOOL_HELP = {
    "Günlük Rehber": (
        "Şehrini veya ilçeni yazıp Bölgeyi incele düğmesine bas.",
        "Tarlamı seç ile tarlanın köşelerini haritada işaretle.",
        "Özelleştirme’den dili ve kullanım modunu değiştirebilirsin.",
    ),
    "Ne ekmeliyim?": (
        "Bölgene en uygun görünen ekinler en üstte.",
        "Ne ekmeliyim? ile ekinleri, Su ve gelecek ile tahmini su açığını gör.",
    ),
    "Su ve gelecek": (
        "Yağıştan sonra ekin için ne kadar su eksik kalabilir?",
        "Model tahmini. Sulama öncesi toprağın nemini kontrol et.",
    ),
    "Ana ekran": (
        "Konumu gir veya tarlanı haritada seç. Analiz et ile seçili konumun ürün uyumunu gör.",
        "Bir ürün seçip puanın bileşenlerini incele. Uyum, koşulların ekinin tercih aralıklarına yakınlığını gösterir.",
        "Planla, İzle ve Ayarlar menüleri diğer araçları açar. Tanıtım turunu Özelleştirme'den yeniden başlatabilirsin.",
    ),
    "Miktar ve yararlı pay": (
        "Dönem boyunca uyguladığın miktarı kendi birimiyle yaz. Boş satırlar hesaba katılmaz.",
        "Yararlı pay, kullandığın miktarın işe yarayan yüzdesidir. 100 m³ ve %75 girersen sonuç 75 m³ yararlı, 25 m³ kalan su olur.",
        "Azot satırına gübre ürününün toplam kilosunu değil, etiketteki yüzdeye göre hesaplanan azot kilosunu gir.",
    ),
    "Tarla asistanı": (
        "Ekin listesinden bir ürün seç. Puan, sulama ihtiyacı veya riskler hakkında sorunu yaz ve Enter’a bas.",
        "Yanıt seçili konumun analizini kullanır. ↻ yeni sohbet açar. Serbest sorular için API anahtarını Özelleştirme’den gir.",
    ),
    "Tarla araçları": (
        "Tarla Takip Paneli’ni harita katmanları için, Sesli saha modu’nu parselde sesli yönlendirme için aç.",
        "Veri & açıklanabilirlik kaynakları gösterir. Frekans protokolü Arduino ses denemelerini, Özelleştirme uygulama ayarlarını açar.",
    ),
    "Özelleştirme": (
        "Açık veya koyu temayı ve TR, EN ya da DE dilini seç. Ayarlar hemen kaydedilir.",
        "OpenRouter anahtarını burada ayarlayabilir ve ana ekranın tanıtım turunu yeniden başlatabilirsin.",
    ),
    "Tarlalarım": (
        "Yeni tarla çiz ile haritada sınır oluştur. Daha önce çizdiğin tarlalar adlarıyla listelenir.",
        "Analiz et sonuçları ana ekrana getirir. Haritada aç sınırı gösterir. Sil, seçili kaydı listeden çıkarır.",
    ),
    "Kaynak kaybı analizi": (
        "Tarlayı ve tarih aralığını seç. Su, gübre veya enerji miktarını ve yararlı kullanım oranını gir.",
        "Grafikteki kayıp, girilen oranlardan hesaplanır. NASA POWER seçili dönemin iklim bağlamını gösterir.",
    ),
    "Ekim nöbeti önerileri": (
        "Her yıl için mevcut ekini seç. Su tasarrufu, toprak sağlığı, gelir veya dengeli hedeflerden birini seçip Öneri bul’a bas.",
        "Üst kart seçili sırayı ve mevcut ekimle puan farkını gösterir. Diğer seçeneklere tıklayarak gerekçeleri ve kaynaklarını karşılaştır.",
    ),
    "10 yıllık senaryo": (
        "Risk ve su görünümü model sonuçlarının dağılımını gösterir. Ekin seçenekleri tipik ve zayıf koşullardaki puanları karşılaştırır.",
        "Tarla Planı'nda bir yıl seç veya Yılları oynat ile 2026–2036 arasındaki görselleri sırayla gör.",
    ),
    "Tarla geçmişi": (
        "Yıllık iklim grafiğinde yağış ve sıcaklığı incele. Ekim kaydı eklemek için yılı ve ürün adını gir.",
        "Kaydettiğin ürünler seçili tarlanın sınırına bağlıdır. Uydu arşivi varsa seçilen tarihin görüntüsünü açabilirsin.",
    ),
    "Telegram sohbeti": (
        "Ana ekrandaki ürün için sıcaklık veya bağıl nem sürgüsünü ideal aralığın dışına taşı ve bırak. Bot, seçilen değeri ve ideal aralığı Telegram’a gönderir.",
        "Hava durumu Open-Meteo’dan gelir. Deneme düğmeleri örnek senaryoları Telegram’a yollar.",
        "Deprem takibi USGS kayıtlarını dakikada bir kontrol eder. Haşere ekranı yarınki sıcaklıkla geçmiş bölge gözlemlerini karşılaştırır.",
        "Bot anahtarı veya sohbet numarası değişirse Telegram bağlantısı bölümünden güncelle.",
    ),
    "Riskler": (
        "Afet ve erozyon sekmesinde renk ve dolu kutular gösterge düzeyini belirtir. Kartın sağındaki değeri ve açıklamayı birlikte oku.",
        "Haşere riski sekmesinde ürün ve ay seç. Kartlar hangi böceğin ürüne zarar verebileceğini, sıcaklığın uygunluğunu ve bölgedeki geçmiş kayıtları gösterir.",
    ),
    "Rotasyon planlayıcı": (
        "Her karttaki ekinleri soldan sağa oku. Oklar ekim sırasını, rozetler örtü bitkisini gösterir.",
        "Su, toprak sağlığı ve çeşitlilik çubuklarını karşılaştır. Kartın altındaki uyarılar o sıraya ait kısıtları gösterir.",
    ),
    "Veri & açıklanabilirlik": (
        "Özet sekmesini açarak seçili konumun iklim ve toprak girdilerini incele.",
        "Kaynakça bağlantıları veri sağlayıcılarını açar. Hesap yöntemi puanların hangi girdiler ve varsayımlarla üretildiğini açıklar.",
    ),
    "Frekans protokolü": (
        "Neden ses kullanıyoruz? Toprağa ses gönderildiğinde titreşim dalgaları oluşur. Bazı frekansların bitki ve zararlılar üzerindeki olası etkileri deneysel olarak araştırılıyor.",
        "Bazı frekansların haşereleri uzaklaştırabileceği; bazılarının bitkilerin hücre zarından su geçişini artırabileceği veya azaltabileceği öne sürülüyor. Ancak bu üç frekans için böyle bir tarımsal etki kanıtlanmış değil.",
        "4000, 1000 veya 25000 Hz deneyini seç, Arduino'yu bağla ve Protokolü çal'a bas. Bunlar yalnızca test sinyalleridir; 25000 Hz için uygun donanım ve güncel Arduino kodu gerekir.",
    ),
    "Derin Uzay ikizi": (
        "Parsel ve rotasyon seçeneklerini değiştirerek su, azot ve karbon göstergelerini incele.",
        "Grafikler modeldeki farkları gösterir. Seçili parselin konumunu ve verinin kaynağını panelden kontrol et.",
    ),
    "Tarlamı seç": (
        "Uydu haritasında köşeleri sırayla işaretle. Köşeyi sürükleyerek düzelt veya son köşeyi geri al.",
        "Bu tarlayı kullan ana ekranda analizi açar. Bu tarlayı kaydet çizdiğin sınırı verdiğin adla saklar.",
    ),
    "Tarla Takip Paneli": (
        "Uydu haritasındaki düğmelerle stres, nem ve diğer göstergeler arasında geç. Isı haritası toprak organik karbonunu açar.",
        "Parseli ve rotasyon stratejisini seçerek sonuçları karşılaştır. Bir katmanın renklerini harita anahtarından oku.",
    ),
    "Toprak verimi ısı haritası": (
        "Haritada toprak organik karbonu katmanını aç. Kaydırıcıyla renk kaplamasının görünürlüğünü ayarla.",
        "Renk ölçeği 0–5 cm derinlikteki organik karbonu gösterir. Saydam alanlarda veri bulunmayabilir.",
    ),
    "Saha modu": (
        "Konum izni vererek GPS’i aç veya simülasyonla tarlayı gez. Harita konumunu ve parsel sınırlarını gösterir.",
        "Parsel değişince önerileri sesli dinleyebilirsin. Ses, hız ve tekrar düğmeleriyle okumayı ayarla.",
    ),
}


def tool_help(title):
    return _TOOL_HELP.get(title) or next((steps for name, steps in _TOOL_HELP.items() if name in title),
                ("Bu ekrandaki alanları sırayla incele. Terim ve veri açıklamaları Kaynaklar ve hesap bölümündedir.",))


def decorate_html(html,endpoint):
    token = urllib.parse.parse_qs(urllib.parse.urlsplit(endpoint).query).get('t', [''])[0]
    asset_base = '/assets/' + urllib.parse.quote(token, safe='')
    for remote in ('https://unpkg.com/leaflet@1.9.4/dist',
                   'https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist'):
        html = html.replace(remote, asset_base)
    # Leaflet must know its container changed after a hidden tab is shown.
    map_bridge = '''<script src="ASSET/leaflet.js"></script><script>
    if(window.L){L.Map.addInitHook(function(){const map=this,container=map.getContainer();
      let frame; const resize=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(()=>{
        if(container.clientWidth&&container.clientHeight)map.invalidateSize({pan:false});});};
      const observer=new ResizeObserver(resize);observer.observe(container);
      map.on('unload',()=>{observer.disconnect();cancelAnimationFrame(frame);});
      resize();
    });}
    </script>'''.replace('ASSET',asset_base)
    # One local library for all four map screens; never load a second copy.
    html = re.sub(r'<script src="' + re.escape(asset_base) + r'/leaflet.js"></script>', '', html)
    html = html.replace('</head>', map_bridge + '</head>', 1)
    html = html.replace('</head>', '<link rel="stylesheet" href="'+asset_base+'/leaflet.css"></head>',1)
    payload=json.dumps(state(),ensure_ascii=False).replace('<','\\u003c')
    script=BRIDGE.replace('__INITIAL__',payload).replace('__ENDPOINT__',json.dumps(endpoint)).replace('__ALIAS__',json.dumps(ALIAS))
    head = MOTION_CSS + '<script>' + script + '</script>'
    title = re.search(r"<title>(.*?)</title>", html)
    window_title = title[1] if title else ""
    steps = tool_help(window_title)
    if steps:
        offset = " tarla-tool-help-map" if ("Tarlamı seç" in window_title
                                            or "Toprak verimi ısı haritası" in window_title) else ""
        items = "".join(f"<li>{escape(step)}</li>" for step in steps)
        help_card = (f'<details class="tarla-tool-help{offset}"><summary title="Ekran yardımı" aria-label="Ekran yardımı">?</summary>'
                     f'<section><h2>{escape(window_title)}</h2><ol>{items}</ol></section></details>')
        html = html.replace('</body>', help_card + '</body>', 1)
        # HTML sayfalarında da soru işaretini ana başlığın hemen yanına sabitle.
        title_help_script = r'''<script data-ui-own>
        (function(){
          function dockHelp(){
            const help=document.querySelector('.tarla-tool-help');
            if(!help||help.dataset.docked==='1')return;
            const candidates=[...document.querySelectorAll('h1, .page-title, .hero-title, .ttl, main h2')];
            const heading=candidates.find(h=>h.getBoundingClientRect().width>0 && h.textContent.trim().length>3);
            if(!heading)return;
            heading.style.display='flex';
            heading.style.alignItems='center';
            heading.style.flexWrap='wrap';
            heading.style.gap='12px';
            help.classList.add('tarla-help-docked');
            heading.appendChild(help);
            help.dataset.docked='1';
          }
          if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',dockHelp);
          else dockHelp();
          window.addEventListener('load',dockHelp);
        })();
        </script>'''
        html = html.replace('</body>', title_help_script + '</body>', 1)
    return html.replace('</head>',head+'</head>',1) if '</head>' in html else html+head


MOTION_CSS = """<style data-ui-own>
html,body{font-family:"Segoe UI",system-ui,sans-serif!important;overscroll-behavior:none}
button,input,select,textarea{font-family:inherit!important}
.mono,.num,.v,.tele,.ttl,.h{font-family:inherit!important;font-variant-numeric:tabular-nums}
svg text{font-family:"Segoe UI",system-ui,sans-serif!important}
.leaflet-container{touch-action:none;overscroll-behavior:contain;user-select:none}
.leaflet-container img{max-width:none!important;max-height:none!important}
.leaflet-control-attribution{font-size:11px;max-width:100%;overflow-wrap:anywhere}
button:focus-visible,a:focus-visible,summary:focus-visible{outline:2px solid var(--tp-help-accent,#37a06b);outline-offset:3px}
.note,.sub,.disc{line-height:1.6;overflow-wrap:anywhere}
.card,.left,.right{min-width:0}
.ttl{gap:12px;flex-wrap:wrap;letter-spacing:.02em!important}
button,summary,th,td{overflow-wrap:anywhere}
.leaflet-control-attribution{white-space:normal}
header .logo,header .brand,.tabs>*,.loop>*{min-width:0}
.loop .h{overflow-wrap:anywhere;letter-spacing:0!important}
.tarla-tool-help{position:fixed;top:8px;right:8px;z-index:3000;color:var(--tp-help-fg,CanvasText);
  font:14px/1.5 system-ui}
.tarla-tool-help-map{right:64px}
.tarla-tool-help.tarla-help-docked{position:relative;top:auto;right:auto;display:inline-flex;vertical-align:middle;flex:none;z-index:3000}
.tarla-help-docked summary{width:44px;height:44px;font-size:25px}
.tarla-help-docked section{right:0;top:calc(100% + 9px)}
.tarla-tool-help summary{cursor:pointer;display:grid;place-items:center;width:38px;height:38px;font-size:20px;font-weight:700;
  color:var(--tp-help-fg,CanvasText);background:var(--tp-help-card,Canvas);border:1px solid var(--tp-help-accent,GrayText);border-radius:8px}
.tarla-tool-help[open] summary{background:var(--tp-help-accent,Canvas);color:var(--tp-help-on-accent,CanvasText)}
.tarla-tool-help section{position:absolute;right:0;top:calc(100% + 8px);box-sizing:border-box;
  width:min(400px,calc(100vw - 84px));max-height:calc(100vh - 58px);overflow:auto;padding:16px 18px;
  background:var(--tp-help-card,Canvas);border:1px solid var(--tp-help-accent,GrayText);border-radius:12px;
  box-shadow:0 12px 28px #0006}
.tarla-tool-help h2{margin:0 0 12px;font-size:18px;color:inherit}
.tarla-tool-help ol{counter-reset:step;list-style:none;margin:0;padding:0}
.tarla-tool-help li{counter-increment:step;position:relative;padding-left:32px}
.tarla-tool-help li+li{margin-top:12px}
.tarla-tool-help li::before{content:counter(step);position:absolute;left:0;top:0;width:22px;
  text-align:center;border:1px solid var(--tp-help-accent,GrayText);border-radius:50%;font-weight:bold}
@keyframes tarla-panel-in {
  from {opacity:.55;transform:translateY(8px)}
  to {opacity:1;transform:translateY(0)}
}
@keyframes tarla-map-in {from {opacity:.62} to {opacity:1}}
html[data-motion="on"] :is(#side, main > aside, #mapWrap, body > header) {
  animation:tarla-panel-in .34s cubic-bezier(.22,.75,.26,1);
}
html[data-motion="on"] #map {
  animation:tarla-map-in .36s ease-out;
}
button, .leaflet-control-layers label {transition:background-color .18s,color .18s,border-color .18s,transform .12s}
html[data-motion="on"] button:active:not(:disabled) {transform:translateY(1px)}
html[data-motion="off"] *,html[data-motion="off"] *::before,html[data-motion="off"] *::after {
  animation:none!important;transition:none!important;scroll-behavior:auto!important;
}
@media (prefers-reduced-motion:reduce) {
  *,*::before,*::after {animation:none!important;transition:none!important;scroll-behavior:auto!important}
}
</style>"""


# Web sayfalarında palet dışında kalmış koyu renkler -> palet anahtarı (koyu temada aynen kalır)
ALIAS={
    "#080b0a":"BG","#0c100e":"SIDE","#101614":"CARD","#161d1a":"CARD2","#1c2521":"CARD3",
    # Görev Kontrol (Quantum) sayfasının kendi paleti
    "#05080a":"BG","#060a0c":"BG","#070b0e":"BG","#0a1014":"CARD","#0a1116":"CARD","#0a1217":"CARD2",
    "#0e161b":"CARD2","#18242b":"LINE","#22323b":"LINE2","#e8f1f2":"FG","#b9c8cc":"FG2","#6f858c":"MUT",
    "#5cf2c4":"ACC","#1f9e7c":"ACC2","#5cc8f2":"WATER","#f2c35c":"GOLD","#f2706a":"BAD","#12352b":"BAND",
    "#04130e":"ON_ACC","#060b0e":"CARD",
    # saha / harita / toprak sayfalarında kalan tonlar
    "#24302a":"LINE2","#0b100e":"BG","#10161a":"CARD","#19221d":"CARD2","#0b1110":"BG","#0e1412":"CARD",
}


BRIDGE=r'''(()=>{
let ui=__INITIAL__, endpoint=__ENDPOINT__, ALIAS=__ALIAS__, texts=new WeakMap(), styles=new WeakMap(), attrs=new WeakMap(), busy=false, lastLang=null, lastTitle=null;
document.documentElement.dataset.motion=ui.motion?'on':'off';
const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
let rx=null,table={};
function prepare(){table={};for(const p of ui.phrases)table[p[0]]=p[ui.lang==='en'?1:ui.lang==='de'?2:0];
const W=/[\p{L}\p{N}_]/u;
const keys=Object.keys(table).sort((a,b)=>b.length-a.length).map(k=>(W.test(k[0])?'(?<![\\p{L}\\p{N}_])':'')+esc(k)+(W.test(k[k.length-1])?'(?![\\p{L}\\p{N}_])':''));
rx=new RegExp(keys.join('|'),'gu');}
function translate(s){return ui.lang==='tr'?s:s.replace(rx,m=>table[m]);}
function keyOf(v){v=v.toLowerCase();for(const p of Object.values(ui.palettes)){for(const [k,c] of Object.entries(p)){if(c.toLowerCase()===v)return k;}}
return ALIAS[v]||null;}
const hex2=n=>(+n).toString(16).padStart(2,'0');
function colors(s){if(!s)return s;
s=s.replace(/#[0-9a-fA-F]{6}\b/g,v=>{const key=keyOf(v);return key?(ui.palette[key]||v):v;});
return s.replace(/rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*(,\s*[\d.]+\s*)?\)/g,(m,r,g,b,a)=>{
const key=keyOf('#'+hex2(r)+hex2(g)+hex2(b));const t=key&&ui.palette[key];if(!t)return m;
const R=parseInt(t.slice(1,3),16),G=parseInt(t.slice(3,5),16),B=parseInt(t.slice(5,7),16);
return a?`rgba(${R},${G},${B}${a})`:`rgb(${R},${G},${B})`;});}
let originalTitle=document.title;
function apply(){if(busy||!document.body)return;busy=true;
const languageChanged=lastLang!==ui.lang;
document.title=translate(originalTitle);
if(lastTitle!==document.title && window.pywebview && window.pywebview.api && window.pywebview.api.set_title){window.pywebview.api.set_title(document.title);lastTitle=document.title;}
document.documentElement.lang=ui.lang;document.documentElement.dataset.theme=ui.theme;document.documentElement.dataset.motion=ui.motion?'on':'off';document.documentElement.style.colorScheme=ui.theme==='acik'?'light':'dark';
for (const [name, key] of Object.entries({fg:'FG',card:'CARD',accent:'ACC2','on-accent':'ON_ACC'})) {
  const value = ui.palette[key];
  if (value) document.documentElement.style.setProperty('--tp-help-' + name, value);
}
for(const e of document.querySelectorAll('style:not([data-ui-own])')){let a=styles.get(e);if(!a||a.last!==e.textContent)a={source:e.textContent};let out=colors(a.source);if(e.textContent!==out)e.textContent=out;a.last=out;styles.set(e,a);}
for(const e of document.querySelectorAll('[style]')){const now=e.getAttribute('style');let a=styles.get(e);if(!a||a.last!==now)a={source:now};let out=colors(a.source);if(out!==now)e.setAttribute('style',out);a.last=out;styles.set(e,a);}
for(const e of document.querySelectorAll('[fill],[stroke]')){let a=attrs.get(e)||{};
for(const key of ['fill','stroke']){let value=e.getAttribute(key);if(value===null)continue;let v=a[key];if(!v||v.last!==value)v={source:value};let out=colors(v.source);if(out!==value)e.setAttribute(key,out);v.last=out;a[key]=v;}attrs.set(e,a);}
for(const e of document.querySelectorAll('[title],[aria-label],[placeholder],[alt]')){let a=attrs.get(e)||{};
for(const key of ['title','aria-label','placeholder','alt']){let value=e.getAttribute(key);if(value===null)continue;let v=a[key];if(!v||v.last!==value)v={source:value};let out=translate(v.source);if(out!==value)e.setAttribute(key,out);v.last=out;a[key]=v;}attrs.set(e,a);}
const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
while(node=walker.nextNode()){if(/^(SCRIPT|STYLE|TEXTAREA|NOSCRIPT)$/.test(node.parentNode.tagName)||node.parentElement.closest('[data-no-tr]'))continue;
let a=texts.get(node);if(!a||a.last!==node.nodeValue)a={source:node.nodeValue};
if(node.parentElement.tagName==='OPTION'&&!node.parentElement.hasAttribute('value'))node.parentElement.value=node.parentElement.textContent;
let out=translate(a.source);if(node.nodeValue!==out)node.nodeValue=out;a.last=out;texts.set(node,a);}
lastLang=ui.lang;busy=false;
if(languageChanged)window.dispatchEvent(new CustomEvent('tarla-appearance',{detail:{lang:ui.lang,theme:ui.theme}}));}
window.TarlaUI={translate:s=>translate(s),lang:()=>ui.lang};
prepare();document.addEventListener('pywebviewready',apply);document.addEventListener('DOMContentLoaded',()=>{apply();new MutationObserver(()=>{clearTimeout(window.__uiTimer);window.__uiTimer=setTimeout(apply,60)}).observe(document.body,{subtree:true,childList:true,characterData:true});});
setInterval(async()=>{try{let r=await fetch(endpoint,{cache:'no-store'});if(!r.ok)return;let next=await r.json();if(next.lang!==ui.lang||next.theme!==ui.theme||next.motion!==ui.motion||JSON.stringify(next.palette)!==JSON.stringify(ui.palette)){ui=next;prepare();apply();}}catch(e){}},800);
})();'''
