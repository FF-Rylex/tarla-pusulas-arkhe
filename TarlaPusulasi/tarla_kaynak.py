"""Veri, yöntem ve proje varsayımlarının kullanıcıya açık kaydı.

Bir yayına bağlantı vermek, uygulamadaki bütün katsayıları o yayına mal etmez.
Sayısal saha doğrulaması olmayan değerler açıkça proje varsayımıdır.
"""
from html import escape

REFERENCES = {
    'power': ('NASA POWER · aylık iklim verileri', 'https://power.larc.nasa.gov/docs/services/api/temporal/climatology/'),
    'daily': ('NASA POWER · günlük veriler', 'https://power.larc.nasa.gov/docs/services/api/temporal/daily/'),
    'fao': ('FAO-56 · su hesabı, bölüm 3 ve 5', 'https://www.fao.org/4/X0490E/x0490e07.htm'),
    'crop': ('FAO-56 · ürüne özgü su tüketimi', 'https://www.fao.org/4/X0490E/x0490e0a.htm'),
    'soil': ('ISRIC SoilGrids · toprak tahmin haritaları', 'https://isric.org/explore/soilgrids'),
    'cover': ('USDA NRCS · örtü bitkileri', 'https://www.nrcs.usda.gov/conservation-basics/conservation-by-state/new-york/cover-crops'),
    'carbon': ('Poeplau & Don (2015) · örtü ve toprak karbonu', 'https://doi.org/10.1016/j.agee.2014.10.024'),
    'gibs': ('NASA GIBS · uydu katmanları', 'https://nasa-gibs.github.io/gibs-api-docs/'),
    'osm': ('OpenStreetMap · harita katkıcıları', 'https://www.openstreetmap.org/copyright'),
    'esri': ('Esri · World Imagery', 'https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9'),
    'gbif': ('GBIF · gözlem kayıtları', 'https://www.gbif.org/occurrence/search'),
    'forecast': ('Open-Meteo · hava tahmini', 'https://open-meteo.com/en/docs'),
    'irrigation': ('FAO · sulama uygulama verimi, Ek I', 'https://www.fao.org/4/t7202e/t7202e08.htm'),
    'fertilizer': ('FAO · bitki besleme, Tablo 31', 'https://www.fao.org/4/a0443e/a0443e.pdf'),
    'salt_status': ('FAO (2024) · Global status of salt-affected soils', 'https://openknowledge.fao.org/handle/20.500.14283/cd3044en'),
    'salt_economics': ('Qadir et al. (2014) · Economics of salt-induced land degradation and restoration', 'https://doi.org/10.1111/1477-8947.12054'),
    'rice_awd': ('Carrijo, Lundy & Linquist (2017) · Rice yields and water use under alternate wetting and drying irrigation: A meta-analysis', 'https://doi.org/10.1016/j.fcr.2016.12.002'),
}

MODEL_NOTE = ('Puanlar ve öneriler proje modelinin hesabıdır; ölçülmüş verim, gübre dozu '
              'veya kesin hava tahmini değildir. Ekin eşikleri ve göreli katsayılar proje varsayımıdır.')


def context_note(title):
    if any(s in title for s in ('haritada', 'Tarlamı', 'Tarlanı', 'Tarlalarım')):
        return 'Sınır: sizin çiziminiz → alan yaklaşık hesaplanır. Altlık: Esri / OpenStreetMap; uydu katmanları: NASA GIBS.'
    if 'Toprak' in title or 'toprak' in title:
        return 'Renkler SoilGrids organik karbon tahminini gösterir → ürün verimi veya yerinde toprak analizi değildir.'
    if 'Haşere' in title or 'haşere' in title:
        return 'GBIF geçmiş kayıtları + hava koşulları → tarlada kontrol edilecek riski gösterir; zararlının varlığını kanıtlamaz.'
    if 'Kaynak kaybı' in title:
        return 'Girdi: sizin miktarlarınız. Sonuç: miktar × kullanım oranı → bir senaryo; ölçülmüş kayıp değildir. Oran dayanakları ayrıntılardadır.'
    if 'Frekans' in title:
        return 'Deneysel ses protokolü → tarlada zararlı kontrolü sağladığı doğrulanmış değildir. Değerler proje deneme ayarlarıdır.'
    return MODEL_NOTE


def links(keys):
    return ' · '.join('<a target="_blank" rel="noopener noreferrer" href="'+escape(REFERENCES[k][1])+'">'+escape(REFERENCES[k][0])+'</a>' for k in keys)


def page():
    import tarla_pusulasi as tp
    import tarla_optimizer as opt
    crops = ''.join('<tr>' + ''.join('<td>'+escape(str(v))+'</td>' for v in
                   (c['name'], c['need'], c['t'], c['soil'], c['rh'], c['sun'], c['frost'],
                    ', '.join(tp.MONTHS[m] for m in c['sow']))) + '</tr>' for c in tp.CROPS)
    traits = ''.join('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in
                     (name, t['n'], t['res'], t['mkt']))+'</tr>' for name,t in opt.TRAITS.items())
    body = '''<h1>Kaynaklar ve hesap dayanakları</h1>
    <p>Her sonuç için üç şeyi ayırın: veri nereden geldi, hangi hesap yapıldı, sonuç neyi söyleyemez?</p>
    <section><h2>Veri türleri</h2><p><b>Dış veri:</b> NASA POWER iklim serileri, SoilGrids toprak tahminleri ve harita servisleri. Bunlar tarlanızdaki sensör ölçümü değildir.</p>
    <p><b>Sizin girdiniz:</b> tarla sınırı, uygulanan miktarlar, tarihler ve elle girilen uydu değerleri. Kaynak ve birimlerini giriş sırasında doğrulayın.</p>
    <p><b>Proje varsayımı:</b> ekin eşikleri, azot ve pazar katsayıları, puan ağırlıkları. Bunlar saha deneyiyle kalibre edilmedi; bir kurumun doğruladığı standart gibi okunmamalıdır.</p>
    <p><b>Örnek veri:</b> internet verisi alınamadığında veya demo modunda kullanılan sabit senaryo. Seçili tarlanın ölçümü değildir.</p></section>
    <section><h2>Su: yağış → olası açık</h2><p>Aylık yağış ve sıcaklık NASA POWER verisinden alınır; örnek modunda demo iklimidir. Referans su kaybı Hargreaves yöntemiyle hesaplanır. Yağış bu kaybı karşılamıyorsa su açığı oluşur. Bu fark doğrudan sulama dozu değildir: ürün, toprak nemi ve sulama verimi ayrıca gerekir.</p>REF_WATER</section>
    <section><h2>Azot: ürün sırası → göreli katkı</h2><p>Baklagil ve örtü katkısından ürün tüketimi çıkarılır. Sonuç göreli model birimidir, kg gübre değildir. Pozitif sonuç ancak modelde katkının tüketimden büyük olduğunu söyler. Gübre azaltma miktarı için toprak ve bitki analizi gerekir. Baklagil ve örtü prensibi: REF_COVER</p></section>
    <section><h2>Karbon: bitki artığı ve örtü → tahmini değişim</h2><p>Örtü katsayısı 0,24 / 0,32 / 0,40 t C/ha/yıl değerlerini kullanır; dayanak aşağıdaki meta-analizdir. Baklagil katkısı 0 / 0,10 / 0,20 ve artık katsayısı 0,15 proje varsayımlarıdır. Bu birleşik model tarla ölçümü veya karbon kredisi doğrulaması değildir. Alt/orta/üst senaryolar istatistiksel güven aralığı değildir.</p>REF_CARBON</section>
    <section><h2>Örtü: ekim takvimi → toprağın korunması</h2><p>Örtü oranı = (12 − yılda çıplak kalan ay) / 12 × 100. Takvimden hesaplanır, uyduyla ölçülmez. Örtü yağmurun toprağı taşımasını azaltmaya yardımcı olabilir; erozyonun tamamen önlendiğini söylemez. Örtünün 40 mm su tüketimi proje varsayımıdır.</p>REF_COVER</section>
    <section><h2>Harita ve toprak</h2><p>Çizdiğiniz sınırdan yerel düzlem hesabıyla yaklaşık alan bulunur; resmi kadastro alanı değildir. SoilGrids renkleri 0–5 cm organik karbon tahminidir; haritanın yaklaşık 250 m çözünürlüğü küçük tarla içindeki farkları gösteremeyebilir. Uydu katmanının tarihini ve çözünürlüğünü katman açıklamasından okuyun.</p>REF_MAP</section>
    <section><h2>Öneriler, riskler ve puanlar</h2><p>Uygunluk, toprak bozulma ve kararlılık göstergeleri proje modelinin 0–100 puanlarıdır; başarı olasılığı değildir. 10 yıllık görünüm, varsayımlar altında senaryodur. Haşere ve afet göstergeleri tarla tespiti veya kesin uyarı değildir. GBIF kaydı bulunmaması zararlının yokluğunu kanıtlamaz.</p>REF_RISK</section>
    <section><h2>Kaynak kullanım hesabı</h2><p>Su verimleri ve mineral gübre geri alım oranları FAO genel referanslarıdır. Girdi miktarı ve seçilen oran birleştirilir → yararlı kullanılan ve kullanılmayan miktar hesaplanır. Gübrede ilk ürünün almadığı kısmın tamamı çevreye kayıp değildir.</p>REF_INPUT
    <ul data-no-tr>REF_RESEARCH</ul></section>
    <details><summary>Ekinlerin sayısal varsayımları</summary><p>Kaynak: projenin ekin parametre tablosu. Aşağıdaki sayılar tek tek bir dış yayına bağlanmış değildir; bu nedenle tamamı doğrulanmayı bekleyen model varsayımı olarak gösterilir. Sıcaklık ve nem dizileri: alt sınır, uygun aralığın başlangıcı, bitişi, üst sınır.</p><div class="scroll"><table><thead><tr><th>Ekin</th><th>Sezon suyu (mm)</th><th>Sıcaklık (°C)</th><th>Kök nemi (0–1)</th><th>Hava nemi (%)</th><th>Güneş (kWh/m²/gün)</th><th>Soğuk sınırı (°C)</th><th>Ekim ayları</th></tr></thead><tbody>CROPS</tbody></table></div></details>
    <details><summary>Rotasyonun sayısal varsayımları</summary><p>Azot göreli birimdir. Artık ve pazar 0–1 göstergeleridir; yerel fiyat veya ölçülen organik madde değildir.</p><table><thead><tr><th>Ekin</th><th>Azot</th><th>Bitki artığı</th><th>Pazar</th></tr></thead><tbody>TRAITS</tbody></table><p>Hedef ağırlıkları: WEIGHTS</p><p>Toprak bozulma puanının ağırlıkları: ENTROPY</p></details>
    <p class="mut">Kaynaklar incelendi: 14 Kasım 2026. Dış servislerin erişilebilirliği değişebilir; alınamayan veri ölçülmüş sıfır olarak sunulmaz.</p>'''
    replacements = {'REF_WATER':links(['power','fao','crop']), 'REF_COVER':links(['cover']),
                    'REF_CARBON':links(['carbon']), 'REF_MAP':links(['soil','esri','osm','gibs']),
                    'REF_RISK':links(['power','gbif','forecast']), 'REF_INPUT':links(['irrigation','fertilizer']),
                    'REF_RESEARCH':''.join('<li>'+links([key])+'</li>'
                                           for key in ('salt_status', 'salt_economics', 'rice_awd')),
                    'CROPS':crops, 'TRAITS':traits, 'WEIGHTS':escape(str(opt.BASE_W)),
                    'ENTROPY':escape(str(opt.ENTROPY_W))}
    for key,value in replacements.items():
        body = body.replace(key,value)
    return '''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kaynaklar ve hesap dayanakları</title><style>
    *{box-sizing:border-box}body{margin:0;background:#080b0a;color:#f2f6f3;font:16px/1.65 "Segoe UI",sans-serif}main{max-width:1050px;margin:auto;padding:32px 24px 60px}h1{font-size:30px}h2{font-size:20px;margin:0 0 10px}section,details{background:#101614;border:1px solid #2a3630;border-radius:14px;padding:22px;margin:16px 0}p{margin:8px 0 14px}a{color:#7cf0a8}summary{cursor:pointer;font-weight:600}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:10px;border-bottom:1px solid #2a3630;text-align:left;vertical-align:top}th{color:#7cf0a8}.mut{color:#8b9c92}</style></head><body><main>'''+body+'</main></body></html>'
