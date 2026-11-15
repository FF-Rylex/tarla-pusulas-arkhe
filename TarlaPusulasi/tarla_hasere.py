"""Konukçu kataloğu ve konuma yakın GBIF böcek gözlem kayıtları."""

from dataclasses import dataclass
from datetime import date
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import math
from urllib.parse import urlencode

import tarla_pusulasi as tp


GBIF_URL = "https://www.gbif.org/occurrence/search?"
GBIF_API = "https://api.gbif.org/v1/"
PHOTO_CREDITS = {
    "Leptinotarsa decemlineata": "F. Welter-Schultes · CC0",
    "Eurygaster integriceps": "A. Sdobnikov · CC BY 4.0",
    "Spodoptera frugiperda": "USDA · Public domain",
    "Sitobion avenae": "Le grand Virg · CC BY-SA 4.0",
    "Rhopalosiphum padi": "USDA · Public domain",
}


@dataclass(frozen=True)
class Pest:
    label: str
    species: str
    crops: tuple[str, ...]
    source: str
    temperature: tuple[float, float] | None = None
    temperature_source: str = ""
    scouting: str = "Bitkinin farklı noktalarında taze zarar ve canlı bireyleri kontrol edin."


def eppo(code, page="hosts"):
    return f"https://gd.eppo.int/taxon/{code}/{page}"


def watch(label, species, crops, code, scouting, page="hosts"):
    return Pest(label, species, tuple(crops.split("|")), eppo(code, page), scouting=scouting)


PESTS = (
    Pest("Tahıl yaprak biti", "Sitobion avenae", ("Kışlık buğday", "Arpa", "Çavdar", "Yulaf"),
         "https://www.gov.mb.ca/agriculture/crops/insects/aphids-on-cereals.html", (16, 20),
         "https://link.springer.com/article/10.1007/s10340-023-01674-w",
         "Başaklanmada başak ve üst yapraklarda kolonileri kontrol edin."),
    Pest("Süne", "Eurygaster integriceps", ("Kışlık buğday",), eppo("EURYIN"),
         scouting="Sap ve başaklarda erginleri, yapraklarda yumurta kümelerini kontrol edin."),
    Pest("Sonbahar tırtılı", "Spodoptera frugiperda", ("Mısır", "Pirinç", "Pamuk", "Soya"),
         eppo("LAPHFR", "datasheet"), (26, 30),
         scouting="Mısırda göbek yapraklarındaki delikleri ve taze dışkıyı kontrol edin."),
    Pest("Patates böceği", "Leptinotarsa decemlineata", ("Patates", "Domates", "Patlıcan"),
         eppo("LPTNDE", "datasheet"), scouting="Yaprak altındaki turuncu yumurtaları ve yaprak yiyen larvaları arayın."),
    Pest("Domates güvesi", "Phthorimaea absoluta", ("Domates", "Patates"),
         eppo("GNORAB", "datasheet"), scouting="Yaprak galerilerinde ve delik meyvelerde canlı larva arayın."),
    Pest("Yeşilkurt", "Helicoverpa armigera",
         ("Pamuk", "Domates", "Patates", "Mısır", "Soya", "Nohut", "Ayçiçeği", "Kuru fasulye"),
         eppo("HELIAR", "datasheet"), scouting="Tomurcuk, koza veya meyvelerde giriş deliği ve larva kontrolü yapın."),
    watch("Elma içkurdu", "Cydia pomonella", "Elma", "CARPPO",
          "Meyve giriş deliği ve dışkı izi görülen örnekleri keserek kontrol edin."),
    watch("Salkım güvesi", "Lobesia botrana", "Üzüm (bağ)", "POLYBO",
          "Çiçek ve tanelerde ağla birleşmiş kısımları veya delikleri kontrol edin."),
    watch("Zeytin sineği", "Bactrocera oleae", "Zeytin", "DACUOL",
          "Meyve üzerinde vuruk izleri varsa meyve örneğinde larva arayın."),
    watch("Buğday yaprak biti", "Rhopalosiphum padi", "Kışlık buğday|Arpa|Çavdar|Yulaf",
          "RHOPPA", "Çıkış ve kardeşlenmede yaprak diplerindeki kolonileri kontrol edin.", "documents"),
    watch("Hessen sineği", "Mayetiola destructor", "Kışlık buğday|Arpa|Çavdar", "MAYEDE",
          "Zayıf kardeşlerde sap dibindeki yaprak kınlarını açıp larva veya pupa arayın."),
    Pest("Rus buğday yaprak biti", "Diuraphis noxia", ("Kışlık buğday", "Arpa", "Çavdar", "Tritikale", "Yulaf"),
         "https://www.planthealthaustralia.com.au/wp-content/uploads/2024/05/NDP-28-RWA-V1-2020-1.pdf",
         scouting="Beyaz çizgili veya kıvrılmış yaprakları açıp kolonileri kontrol edin."),
    watch("Yaprak galeri sineği", "Liriomyza huidobrensis",
          "Patates|Domates|Patlıcan|Şeker pancarı|Biber|Hıyar|Kavun|Karpuz|Kabak|Marul|Ispanak|"
          "Kuru fasulye|Bakla|Bezelye|Kuru soğan|Sarımsak|Kanola|Lahana|Karnabahar|Havuç|Nohut",
          "LIRIHU", "Yeni yapraklarda kıvrımlı galerileri ve canlı larvaları kontrol edin.", "datasheet"),
    watch("Pamuk yaprak biti", "Aphis gossypii", "Pamuk|Hıyar|Kavun|Karpuz|Kabak", "APHIGO",
          "Sürgün uçlarını ve genç yaprakların altındaki kolonileri inceleyin.", "documents"),
    watch("Lahana güvesi", "Plutella xylostella", "Lahana|Karnabahar|Kanola", "PLUTMA",
          "Yaprak altlarında küçük larvaları ve pencere biçimli zarar izlerini arayın.", "documents"),
    watch("Kanatları lekeli sirke sineği", "Drosophila suzukii", "Kiraz|Kayısı|Üzüm (bağ)", "DROSSU",
          "Olgunlaşan meyvelerde yumuşama veya çökme varsa örnek alıp larva kontrolü yapın."),
    watch("Kiraz sineği", "Rhagoletis cerasi", "Kiraz", "RHAGCE",
          "Meyve renk değiştirmeye başladığında tuzakları ve meyve örneklerini kontrol edin."),
    watch("Elma çiçek hortumluböceği", "Anthonomus pomorum", "Elma", "ANTHPO",
          "Açılmadan kahverengileşen çiçek tomurcuklarını açıp larva kontrolü yapın."),
    watch("Akdeniz meyve sineği", "Ceratitis capitata", "Narenciye|Mandalina|İncir|Nar|Elma|Kayısı",
          "CERTCA", "Olgunlaşan ve yere dökülen meyvelerde giriş izi ve larva kontrolü yapın."),
    watch("Ceviz kabuk sineği", "Rhagoletis completa", "Ceviz", "RHAGCO",
          "Dış yeşil kabukta yumuşak siyah lekeler görülürse örnekte larva arayın."),
    watch("Batı çiçek tripsi", "Frankliniella occidentalis", "Biber|Hıyar|Kayısı|Kuru soğan|Şeker pancarı",
          "FRANOC", "Çiçekleri açık renk bir zemine silkerek tripsleri kontrol edin."),
    watch("Fındık kurdu", "Curculio nucum", "Fındık", "CURCNU",
          "Meyve gelişiminde dökülen fındıkları ve kabuktaki delikleri inceleyin."),
    Pest("Bezelye yaprak biti", "Acyrthosiphon pisum", ("Bezelye", "Mercimek", "Nohut"),
         "https://www.uidaho.edu/extension/food/ipm/ag-pests/pea-aphid",
         scouting="Çiçeklenmede sürgün uçlarını beyaz bir kap üzerine silkerek kontrol edin."),
    Pest("Yer fıstığı yaprak biti", "Aphis craccivora", ("Yer fıstığı", "Ayçiçeği", "Pamuk"),
         "https://epubs.icar.org.in/index.php/IJPP/article/view/106012",
         scouting="Genç sürgünlerde koyu renkli kolonileri ve yapışkan salgıyı arayın."),
    watch("Beyazsinek", "Bemisia tabaci", "Pamuk|Tütün|Domates|Hıyar|Biber|Patlıcan", "BEMITA",
          "Yaprak altlarında hareketsiz nimfler, uçuşan erginler ve yapışkan salgı arayın.", "datasheet"),
    watch("Kavun tripsi", "Thrips palmi", "Susam|Tütün|Ayçiçeği|Patlıcan|Hıyar|Kavun|Karpuz", "THRIPL",
          "Gümüş renkli izlerde trips arayın. Tür ayrımını uzmanla doğrulayın.", "datasheet"),
    watch("Çay sürgün böceği", "Helopeltis theivora", "Çay", "HELOTH",
          "Genç yaprak ve sürgünlerde yeni beslenme lekelerini inceleyin."),
    watch("Sorgum çiçek sineği", "Stenodiplosis sorghicola", "Sorgum", "SORVU",
          "Çiçeklenmede taze salkımları inceleyin. Boş kalan tanelerde larva kontrolü yapın.", "pests"),
    Pest("Badem içkurdu", "Eurytoma amygdali", ("Badem",),
         "https://arastirma.tarimorman.gov.tr/bzmai/Menu/101/Ulusal-Yayinlar",
         scouting="Dalında kalan kuru bademleri toplayıp içini ve çıkış deliğini kontrol edin."),
    Pest("Antep fıstığı psillidi", "Agonoscena pistaciae", ("Antep fıstığı",),
         "https://bku.tarimorman.gov.tr/Zararli/KaynakDetay/1130",
         scouting="Genç sürgün ve yapraklarda yumurta, nimf ve yapışkan salgı arayın."),
    Pest("Antep fıstığı dal güvesi", "Kermania pistacella", ("Antep fıstığı",),
         "https://gaziantep.tarimorman.gov.tr/Menu/105/Antepfistigi-Dal-Guvesi-_kermania-Pistacella_",
         scouting="Kuruyan veya zayıflayan sürgünlerde galeri ve çıkış deliği arayın."),
)

def for_crop(crop):
    return tuple(pest for pest in PESTS if crop in pest.crops)


def climate_month(climate, month):
    """Seçilen ayın ortalaması; eksik değişkenler ayrı ayrı boş kalır."""
    def value(key, lo, hi):
        try:
            number = float((climate or {})[key][month - 1])
        except (KeyError, IndexError, TypeError, ValueError):
            return None
        return number if lo <= number <= hi else None

    if not 1 <= month <= 12:
        raise ValueError("Ay 1–12 arasında olmalı.")
    return value("T", -100, 70), value("RH", 0, 100), value("Pm", 0, 10000)


def temperature_comparison(pest, temperature):
    if pest.temperature is None or temperature is None:
        return None
    return pest.temperature[0] <= temperature <= pest.temperature[1]


def risk_rows(crop, temperature, observations_by_pest):
    """Konukçu, sıcaklık ve gözlem bulgularını risk ekranının kart biçimine çevir."""
    rows = []
    for pest in for_crop(crop):
        comparison = temperature_comparison(pest, temperature)
        links = [("Bitki uyumu kaynağı", pest.source)]
        details = [f"{pest.species} · Bu böcek seçtiğiniz ürüne zarar verebilir."]
        if pest.temperature:
            low, high = pest.temperature
            if temperature is None:
                details.append("Konuma ait aylık sıcaklık verisi yok.")
            else:
                if temperature < low:
                    status = "Bu ayın ortalaması böcek için fazla soğuk. Sıcaklık tek başına riski artırmıyor."
                elif temperature > high:
                    status = "Bu ayın ortalaması böcek için fazla sıcak. Sıcaklık tek başına riski artırmıyor."
                else:
                    status = "Bu ayın ortalaması böcek için elverişli."
                details.append(f"{status} NASA POWER {temperature:.1f} °C · Çalışma aralığı {low}–{high} °C.")
            links.append(("Sıcaklık kaynağı", pest.temperature_source or pest.source))
        else:
            details.append("Bu tür için sıcaklığın etkisini değerlendirecek veri yok.")
        result = observations_by_pest.get(pest)
        count, urls = result or (0, ())
        if result is None:
            value = "Bölge geçmişi taranmadı"
        elif not result:
            value = "Bölge geçmişi alınamadı"
        else:
            value = f"Bölgede {count} kayıt" if count else "Bölgede kayıt bulunamadı"
            links.extend(("GBIF kayıtları" if len(urls) == 1 else f"GBIF {i}", url)
                         for i, url in enumerate(urls, 1))
        rows.append(dict(ad=pest.label, species=pest.species, grup="Haşere", duzey=int(comparison is True) + int(count > 0),
                         oran=0, deger=value, aciklama="\n".join(details) + "\n" + pest.scouting,
                         links=links))
    return rows


@lru_cache(maxsize=32)
def _taxon_key(species):
    match = tp.http_json(GBIF_API + "species/match?" + urlencode({
        "name": species, "class": "Insecta", "rank": "SPECIES", "strict": "true",
    }), timeout=6, tries=1)
    key = match.get("acceptedUsageKey") or match.get("usageKey")
    if match.get("matchType") != "EXACT" or match.get("rank") != "SPECIES" or not isinstance(key, int):
        raise ValueError("GBIF tür eşleşmesi bulunamadı.")
    return key


def _query_areas(lat, lon):
    """Konum merkezli yaklaşık 100 km yarı genişlikli dikdörtgen alan."""
    half_lat = 100 / 111.2
    south, north = max(-90, lat - half_lat), min(90, lat + half_lat)
    if south == -90 or north == 90:
        return ((south, north, -180, 180),)
    half_lon = min(180, half_lat / math.cos(math.radians(lat)))
    west, east = lon - half_lon, lon + half_lon
    if half_lon == 180:
        return ((south, north, -180, 180),)
    if west < -180:
        return ((south, north, west + 360, 180), (south, north, -180, east))
    if east > 180:
        return ((south, north, west, 180), (south, north, -180, east - 360))
    return ((south, north, west, east),)


@lru_cache(maxsize=128)
def _observations(species, lat, lon, as_of, month):
    key = _taxon_key(species)
    urls, count = [], 0
    for south, north, west, east in _query_areas(lat, lon):
        filters = {
            "taxonKey": key, "hasCoordinate": "true", "hasGeospatialIssue": "false",
            "occurrenceStatus": "PRESENT", "year": f"{as_of.year - 9},{as_of.year}",
            "decimalLatitude": f"{south:.5f},{north:.5f}",
            "decimalLongitude": f"{west:.5f},{east:.5f}",
        }
        if month is not None:
            filters["month"] = month
        data = tp.http_json(GBIF_API + "occurrence/search?" + urlencode(dict(filters, limit=0)),
                            timeout=6, tries=1)
        value = data.get("count")
        if type(value) is not int or value < 0:
            raise ValueError("GBIF kayıt sayısı alınamadı.")
        count += value
        filters["advanced"] = "1"
        urls.append(GBIF_URL + urlencode(filters))
    return count, tuple(urls)


def observations(pest, lat, lon, month=None):
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Konum geçerli değil.")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("Ay 1–12 arasında olmalı.")
    return _observations(pest.species, round(lat, 4), round(lon, 4), date.today(), month)


def scouting_signals(crop, forecast_temperature, lat, lon, month):
    """Yarın sıcaklık aralığına uyan türlerde geçmiş bölge kayıtlarını ara."""
    candidates = [p for p in for_crop(crop) if temperature_comparison(p, forecast_temperature)]

    def check(pest):
        try:
            count, _urls = observations(pest, lat, lon, month)
        except (OSError, ValueError, TypeError, AttributeError):
            return pest.label, None
        return pest.label, count

    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(check, candidates))
