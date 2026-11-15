"""Tarla Pusulası — kullanıcı ayarları (tema, dil, API anahtarı).

Ayarlar exe'nin yanında DEĞİL, kullanıcının kendi uygulama klasöründe tutulur:
  Windows : %APPDATA%\\TarlaPusulasi\\ayarlar.json
  diğer   : ~/.config/TarlaPusulasi/ayarlar.json
Böylece exe masaüstüne ya da başka bir klasöre taşınsa da ayarlar ve API
anahtarı kaybolmaz. (Çalışan bir exe kendi dosyasının içine yazamaz.)

Eski sürümlerdeki exe yanındaki ayarlar.json hâlâ okunur; uygulama içinden
bir kez kaydedildiğinde yeni yere taşınmış olur.
"""
import json
import os
import sys
import tempfile
import threading

APP_NAME = "TarlaPusulasi"
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"
RETIRED_MODELS = ("anthropic/claude-3.5-haiku",)   # OpenRouter artık sunmuyor
DEFAULTS = {"tema": "koyu", "palet": "varsayilan", "dil": "tr", "mod": "",
            "api_key": "", "model": DEFAULT_MODEL}
DEFAULTS.update(telegram_token="", telegram_chat_id="")
THEMES = ("koyu", "acik")
PALETTE_IDS = ("varsayilan", "okyanus", "lavanta", "toprak", "sahil", "gunbatimi")
LANGS = ("tr", "en", "de")
MODES = ("kolay", "gelismis")


def app_dir():
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, APP_NAME)


def settings_path():
    return os.path.join(app_dir(), "ayarlar.json")


def legacy_path():
    """Eski konum: exe'nin (ya da .py dosyasının) yanındaki ayarlar.json."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "ayarlar.json")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load():
    """Varsayılanlar + eski dosya + kullanıcı dosyası (sonuncusu kazanır)."""
    out = dict(DEFAULTS)
    legacy = _read(legacy_path())
    key = str(legacy.get("api_key") or "").strip()
    if key and not key.startswith("BURAYA"):
        out["api_key"] = key
    if "/" in str(legacy.get("model") or ""):
        out["model"] = str(legacy["model"]).strip()
    for k, v in _read(settings_path()).items():
        if k in DEFAULTS and isinstance(v, str):
            out[k] = v.strip()
    if out["tema"] not in THEMES:
        out["tema"] = DEFAULTS["tema"]
    if out["palet"] not in PALETTE_IDS:
        out["palet"] = DEFAULTS["palet"]
    if out["dil"] not in LANGS:
        out["dil"] = DEFAULTS["dil"]
    if out["mod"] not in MODES:
        out["mod"] = DEFAULTS["mod"]
    if "/" not in out["model"] or out["model"] in RETIRED_MODELS:
        out["model"] = DEFAULT_MODEL
    return out


def save(**changes):
    """Verilen alanları güncelleyip dosyaya yaz (yarım yazılmış dosya kalmaz)."""
    data = load()
    for k, v in changes.items():
        if k in DEFAULTS:
            data[k] = str(v or "").strip()
    _write_json(settings_path(), data)
    return data


_crop_lock = threading.Lock()


def field_crops(points, year=None, crop=None):
    """Aynı tarla sınırı için kullanıcının kaydettiği yıllık ürünler."""
    path = os.path.join(app_dir(), "ekim-gecmisi.json")
    # Köşe sırası ve başlangıç köşesi değişse de tarla kaydı bulunur.
    key = json.dumps(sorted(tuple(p) for p in points), separators=(",", ":"))
    with _crop_lock:
        all_records = _read(path)
        records = all_records.get(key, {})
        if not isinstance(records, dict):
            records = {}
        if year is not None:
            if crop:
                records[str(year)] = crop
            else:
                records.pop(str(year), None)
            all_records[key] = records
            _write_json(path, all_records)
        return dict(records)


def _write_json(path, data):
    folder = os.path.dirname(path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".ayarlar-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def mask(key):
    """Ekranda göstermek için: sk-or-v1-ab…9f2c"""
    key = (key or "").strip()
    if len(key) <= 14:
        return "•" * len(key)
    return key[:10] + "…" + key[-4:]
