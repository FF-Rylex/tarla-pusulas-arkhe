"""SoilGrids gerçek WMS katmanıyla konuma bağlı toprak haritası.
Kaynak: https://maps.isric.org/generated/soilgrids/soc.html
Organik karbon doğrudan ürün verimi veya eksiksiz bir verimlilik ölçümü değildir.
"""
import json
import math


SOIL_LAYER_JS = r"""
function createSoilLayer(showStatus, legend, pane = 'tilePane') {
 const service = 'https://maps.isric.org/mapserv/soc';
 const layerName = 'soc_0-5cm_mean';
 const layer = L.tileLayer.wms(service, {
   layers: layerName, format: 'image/png', transparent: true, version: '1.1.1',
   opacity: .75, maxNativeZoom: 13, maxZoom: 19, pane,
   attribution: 'ISRIC SoilGrids · Organik karbon (dg/kg)'
 });
 let failed = 0, loaded = 0, timer;
 layer.on('loading', () => {
   failed = 0;
   loaded = 0;
   showStatus('Toprak katmanı yükleniyor…');
   clearTimeout(timer);
   timer = setTimeout(() => showStatus('Toprak servisi yanıt vermiyor. Yeniden yüklemeyi deneyin.'), 20000);
 });
 layer.on('tileload', () => { loaded++; });
 layer.on('tileerror', () => { failed++; });
 layer.on('load', () => {
   clearTimeout(timer);
   showStatus(!loaded ? 'Bu konum için katman alınamadı.' :
     failed ? 'Toprak katmanının tamamı alınamadı; görünmeyen alanlar için yorum yapmayın.' :
     'Organik karbon katmanı yüklendi. Şeffaf alanlarda veri bulunmayabilir.');
 });
 layer.on('remove', () => clearTimeout(timer));
 legend.onload = () => { legend.hidden = false; };
 legend.onerror = () => { legend.hidden = true; };
 legend.src = service + '?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetLegendGraphic&FORMAT=image/png&LAYER=' +
   encodeURIComponent(layerName);
 return layer;
}
"""


def build_page(data):
    # JavaScript bağlamına kullanıcı metni ham olarak yerleştirilmez.
    lat, lon = float(data['lat']), float(data['lon'])
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError('Harita konumu geçerli değil.')
    payload = dict(data, lat=lat, lon=lon)
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    return PAGE.replace('__SOIL_LAYER__', SOIL_LAYER_JS).replace('__DATA__', encoded)


PAGE = r'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Toprak verimi ısı haritası</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
*{box-sizing:border-box}html,body{margin:0;height:100%;font:16px/1.5 "Segoe UI",system-ui,sans-serif;background:#080b0a;color:#f2f6f3}
main{display:grid;grid-template-columns:320px minmax(0,1fr);height:100%}aside{padding:26px 22px;overflow-y:auto;background:#101614}
h1{font-size:23px;line-height:1.3;margin:0 0 12px}h2{font-size:16px;margin-top:24px}p{margin:10px 0;color:#cdd8d1}
.note{font-size:14px;color:#8b9c92}.badge{color:#7cf0a8;font-weight:600}.box{border:1px solid #2a3630;border-radius:14px;padding:14px;margin-top:18px}
#map{height:100%;min-height:400px;background:#19221d}#status{font-size:14px;color:#e8c07d}button{padding:12px 16px;width:100%;background:#16241d;border:1px solid #37a06b;border-radius:12px;color:#f2f6f3;font:inherit;cursor:pointer}
#legend{max-width:100%;max-height:280px;margin-top:12px;background:white;border-radius:8px}label{display:block;margin:12px 0}input{width:100%;accent-color:#7cf0a8}
a{color:#7cf0a8}@media(max-width:800px){main{grid-template-columns:1fr;height:auto}#map{height:65vh;grid-row:1}aside{overflow:visible}}

/* giriş ve etkileşim animasyonları (hareketi azalt ayarında kapanır) */
@keyframes tpUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes tpFade{from{opacity:0}to{opacity:1}}
aside>*{animation:tpUp .42s cubic-bezier(.2,.8,.2,1) both}
aside>*:nth-child(2){animation-delay:0.04s}
aside>*:nth-child(3){animation-delay:0.08s}
aside>*:nth-child(4){animation-delay:0.12s}
aside>*:nth-child(5){animation-delay:0.16s}
aside>*:nth-child(6){animation-delay:0.20s}
aside>*:nth-child(7){animation-delay:0.24s}
aside>*:nth-child(8){animation-delay:0.28s}
aside>*:nth-child(9){animation-delay:0.32s}
aside>*:nth-child(10){animation-delay:0.36s}
#map{animation:tpFade .5s ease both}
button{transition:background-color .18s,border-color .18s,color .18s,box-shadow .18s,transform .12s}
button:hover:not(:disabled){box-shadow:0 0 0 3px rgba(124,240,168,.12)}
button:active:not(:disabled){transform:scale(.97)}
</style></head><body><main><aside>
<h1>Toprak verimi ısı haritası</h1><p class="badge" id="place"></p>
<p>Seçtiğiniz konumdaki toprağın organik karbon dağılımını inceleyin.</p>
<p class="note">Renkler organik karbon miktarını gösterir. Bu katman ölçülmüş ürün verimi veya tek başına toprak verimliliği puanı değildir.</p>
<div class="box"><b>Organik karbon · 0–5 cm</b><p class="note">SoilGrids · yaklaşık 250 m çözünürlük. Küçük bir tarlada tek renk görünmesi normaldir.</p>
<p id="status" role="status">Harita hazırlanıyor…</p>
<img id="legend" alt="Organik karbon renk ölçeği (dg/kg)" hidden><p class="note">Birim: dg/kg. 10 dg/kg = 1 g/kg.</p></div>
<label for="opacity">Katman görünürlüğü<input id="opacity" type="range" min="0" max="100" value="75"></label>
<button id="home">Seçtiğim konuma dön</button>
<button id="retry" style="margin-top:10px">Katmanı yeniden yükle</button>
<p class="note" id="scope"></p><p class="note">Kaynak: ISRIC SoilGrids. Harita ve toprak katmanı internet bağlantısı ister. Tarla içi kararlar için yerinde toprak analizi gerekir.</p>
</aside><div id="map" aria-label="Seçili konumun toprak organik karbon haritası"></div></main>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script><script>
'use strict';
__SOIL_LAYER__
const DATA=__DATA__;
const $=id=>document.getElementById(id);
$('place').textContent=DATA.name||'Seçili konum';
$('scope').textContent=DATA.example?'Örnek analizde Konya örnek konumu gösteriliyor. Gerçek konum için şehir veya tarla seçin.':(DATA.points.length?'Çizdiğiniz tarla sınırı haritada işaretlidir.':'Seçtiğiniz şehrin merkezi gösteriliyor; tarla sınırı seçilmedi.');
if(!window.L){$('status').textContent='Harita kütüphanesi yüklenemedi. İnternet bağlantısını kontrol edip pencereyi yeniden açın.';}
else{
 const map=L.map('map',{scrollWheelZoom:true}).setView([DATA.lat,DATA.lon],DATA.points.length?15:10);
 const base=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community'}).addTo(map);
 const roads=L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',{maxZoom:19,attribution:'Tiles © Esri'});
 L.control.layers({'Uydu':base,'Yol haritası':roads},null,{collapsed:true}).addTo(map);
 base.on('tileerror',()=>{$('status').textContent='Zemin haritası yüklenemedi. İnternet bağlantısını kontrol edin.';});
 roads.on('tileerror',()=>{$('status').textContent='Yol haritası alınamadı. Uydu katmanını deneyin.';});
 let boundary=null;
 if(DATA.points.length>=3){boundary=L.polygon(DATA.points,{color:'#ffffff',weight:3,fill:false}).addTo(map);map.fitBounds(boundary.getBounds(),{padding:[35,35],maxZoom:16});}
 else{const tip=document.createElement('span');tip.textContent=DATA.name||'Seçili konum';L.marker([DATA.lat,DATA.lon]).addTo(map).bindTooltip(tip);}
 L.control.scale({imperial:false}).addTo(map);
 const layer=createSoilLayer(text=>{$('status').textContent=text;},$('legend')).addTo(map);
 $('opacity').oninput=e=>layer.setOpacity(Number(e.target.value)/100);
 $('retry').onclick=()=>layer.redraw();
 $('home').onclick=()=>{if(boundary)map.fitBounds(boundary.getBounds(),{padding:[35,35],maxZoom:16});else map.setView([DATA.lat,DATA.lon],10);};
}
</script></body></html>'''
