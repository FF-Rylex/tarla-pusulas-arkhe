"""Eski toprak haritası girişinin uyumluluk köprüsü."""
import tarla_toprak


def page(lat, lon, name, field=None, soil=None):
    return tarla_toprak.build_page(dict(lat=lat, lon=lon, name=name,
        points=(field or {}).get("noktalar", []), example=False)).encode("utf-8")
