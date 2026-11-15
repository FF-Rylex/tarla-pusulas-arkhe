"""Tarla Pusulası — AI açıklama katmanı (OpenRouter üzerinden Claude Haiku).

Model seçimi: ayarlar.json'daki model denenir. OpenRouter o modeli artık sunmuyorsa
(HTTP 404 — örn. Claude 3.5 Haiku kullanımdan kaldırıldı) güncel bir Claude Haiku
modeline otomatik geçilir ve hangi modelin yanıtladığı arayüze bildirilir.

Model yalnızca uygulamanın hesapladığı verileri (faktör puanları, sıralama,
rotasyonlar, senaryo özeti) cümleye çevirir; yeni veri, tahmin veya garanti
üretmez. Anahtar (sk-or-...) ayarlar.json içinde durur; yoksa NotConfigured fırlatılır; arayüz bu durumda kendi
çevrimdışı özetini gösterir.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

import tarla_ayarlar

# EXE veya Python dosyasının bulunduğu klasör
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "ayarlar.json")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"      # herkese açık model listesi
DEFAULT_MODEL = "anthropic/claude-haiku-4.5"     # istenen model (OpenRouter kimliği)
FALLBACK_MODELS = ["anthropic/claude-haiku-4.5"]  # liste alınamazsa denenecek yedekler
LABELS = {"anthropic/claude-3.5-haiku": "Claude 3.5 Haiku", "anthropic/claude-haiku-4.5": "Claude Haiku 4.5"}

_active = {"model": None}       # bu oturumda yanıt veren model (404 sonrası yedek olabilir)
_notice = []                    # arayüze bir kez gösterilecek bilgi satırı


def label_of(model):
    """'anthropic/claude-haiku-4.5' -> 'Claude Haiku 4.5'."""
    if model in LABELS:
        return LABELS[model]
    name = model.split("/")[-1].split(":")[0].replace("-", " ").strip()
    return " ".join(w.capitalize() if w.isalpha() else w for w in name.split()) or model


def pop_notice():
    """Model değiştiyse arayüzün sohbete düşeceği kısa not; yoksa None."""
    return _notice.pop(0) if _notice else None


def available_haiku(timeout=12):
    """OpenRouter'ın şu an sunduğu Claude Haiku modelleri, en yeniden eskiye."""
    req = urllib.request.Request(MODELS_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8")).get("data") or []
    found = []
    for m in data:
        mid = str((m or {}).get("id") or "")
        if mid.startswith("anthropic/") and "haiku" in mid and ":" not in mid:
            found.append((float(m.get("created") or 0), mid))
    return [mid for _, mid in sorted(found, reverse=True)]

SYSTEM = (
    "Sen Tarla Pusulası uygulamasının içindeki tarla asistanısın. Çiftçiyle sade, sıcak ve "
    "kısa bir Türkçe ile konuş; teknik terim kullanırsan bir cümleyle açıkla.\n"
    "KURALLAR\n"
    "- Her öneriyi neden → sonuç sırasıyla yaz. Her sayının yanında uygulama bağlamındaki "
    "kaynağını (dış veri, kullanıcı girişi, örnek veri veya proje varsayımı) belirt. "
    "Kaynağı bağlamda yoksa sayıyı verme; eksik kaynağı söyle. Kaynak URL'si uydurma.\n"
    "- Model puanını başarı olasılığı, referans su açığını sulama dozu, göreli azot "
    "dengesini kg gübre, karbon senaryosunu ölçülmüş kazanım gibi sunma.\n"
    "- Yalnızca aşağıdaki 'Uygulama verileri' bölümündeki sayıları kullan. Verim, gelir, "
    "fiyat, hava tahmini ya da burada olmayan bir ölçüm UYDURMA; veri yoksa 'bu veri "
    "uygulamada yok' de.\n"
    "- Ekinleri karşılaştırman istenirse sıralamadaki puanları ve faktörleri kullan.\n"
    "- Önce soruyu doğrudan yanıtla, sonra en fazla 3 kısa madde ile gerekçe ya da yapılacak "
    "iş ver. Toplam 120 kelimeyi geçme.\n"
    "- Biçim: düz metin; madde için satır başında '- ', vurgu için **kalın** kullanabilirsin. "
    "Tablo, başlık (#) ve kod bloğu kullanma.\n"
    "- Somut bir ekim/sulama önerisi verdiğinde, sonucun aylık NASA iklim ortalamalarına "
    "dayandığını ve kararın ziraat mühendisiyle doğrulanması gerektiğini tek cümleyle hatırlat; "
    "bunu her mesajda tekrarlama.\n"
    "- Tarım dışı konularda kibarca konuya dön."
)


class NotConfigured(ValueError):
    """ayarlar.json yok ya da içinde API anahtarı tanımlı değil."""


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        if not isinstance(config, dict):
            raise ValueError("ayarlar.json bir JSON nesnesi olmalı.")
        return config
    except FileNotFoundError:
        raise NotConfigured("ayarlar.json bulunamadı. Dosya uygulamayla aynı klasörde olmalı:\n"
                            + CONFIG_PATH)
    except json.JSONDecodeError as exc:
        raise ValueError("ayarlar.json içinde JSON hatası: " + str(exc))


LANG_NOTE = {"en": "Reply in English.", "de": "Antworte auf Deutsch."}
_lang = {"code": "tr"}


def set_language(code):
    """Arayüz dili değişince asistan da o dilde yanıt versin."""
    _lang["code"] = code if code in LANG_NOTE else "tr"


def _settings():
    """Anahtar ve model: önce uygulama içi ayarlar, yoksa eski ayarlar.json."""
    cfg = tarla_ayarlar.load()
    api_key = cfg["api_key"]
    model = cfg["model"]
    if not api_key or api_key.startswith("BURAYA"):
        raise NotConfigured("OpenRouter API anahtarı tanımlı değil. "
                            "Diğer araçlar > Özelleştirme bölümünden girin.")
    if not api_key.startswith("sk-or-"):
        raise ValueError("Bu bir OpenRouter anahtarı değil (sk-or- ile başlamalı). "
                         "openrouter.ai/keys adresinden alın.")
    if "/" not in model:
        model = DEFAULT_MODEL
    return api_key, model


def reset_model():
    """Ayarlarda model ya da anahtar değişince yedek model seçimini unut."""
    _active["model"] = None


def status():
    """Arayüz başlığı için: (hazır_mı, model_adı_ya_da_neden)."""
    try:
        return True, label_of(_active["model"] or _settings()[1])
    except NotConfigured:
        return False, "anahtar tanımlı değil"
    except ValueError as exc:
        return False, str(exc)


def _friendly(code, body, model):
    """HTTP hatasını kullanıcıya gösterilecek kısa Türkçe mesaja çevir."""
    try:
        detail = str(json.loads(body)["error"]["message"])
    except Exception:
        detail = body
    detail = " ".join(str(detail).split())[:180]
    if code in (401, 403):
        msg = "API anahtarı geçersiz ya da yetkisiz. Diğer araçlar > Özelleştirme'den anahtarı kontrol edin."
    elif code == 402:
        msg = "OpenRouter hesabında yeterli kredi yok. openrouter.ai üzerinden kredi ekleyin."
    elif code == 404 and "data policy" in detail.lower():
        msg = ("OpenRouter gizlilik ayarlarınız bu modele izin vermiyor. "
               "openrouter.ai/settings/privacy sayfasından izinleri açın.")
    elif code == 404:
        msg = (f"OpenRouter bu modeli sunmuyor: {model}. Güncel bir model adı için "
               "openrouter.ai/models sayfasına bakın ve Özelleştirme'deki model adını güncelleyin.")
    elif code == 429:
        msg = "Kullanım sınırı aşıldı. Bir dakika bekleyip tekrar deneyin."
    elif code >= 500:
        msg = "Model şu anda yanıt vermiyor. Biraz sonra tekrar deneyin."
    else:
        msg = "İstek kabul edilmedi."
    return f"{msg} (HTTP {code}: {detail})" if detail else f"{msg} (HTTP {code})"


def build_payload(question, context="", history=None, model=DEFAULT_MODEL):
    """OpenRouter (OpenAI uyumlu) sohbet gövdesi: sistem + rollere ayrılmış geçmiş."""
    note = LANG_NOTE.get(_lang["code"], "")
    messages = [{"role": "system",
                 "content": SYSTEM + ("\n" + note if note else "")
                 + "\n\nUygulama verileri:\n" + str(context)}]
    turns = []
    for role, text in (history or []):
        r = "user" if role == "sen" else "assistant"
        if turns and turns[-1]["role"] == r:            # aynı rol art arda gelmesin
            turns[-1]["content"] += "\n" + str(text)
        else:
            turns.append({"role": r, "content": str(text)})
    if turns and turns[0]["role"] != "user":            # konuşma kullanıcıyla başlamalı
        turns.pop(0)
    if turns and turns[-1]["role"] == "user":
        turns[-1]["content"] += "\n" + str(question)
    else:
        turns.append({"role": "user", "content": str(question)})
    return {"model": model, "messages": messages + turns,
            "temperature": 0.3, "max_tokens": MAX_TOKENS}


# Yanıt sınırı. Eskiden 700'dü: "düşünen" (reasoning) modeller uzun / varsayımsal sorularda
# bu payın tamamını iç düşünmeye harcayıp boş yanıt döndürüyordu ("Yanıtta metin bulunamadı").
MAX_TOKENS = 1500
RETRY_TOKENS = 4000


def _text_of(content):
    """Yanıt içeriği düz metin ya da parça listesi olabilir."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for p in content:
            if isinstance(p, str):
                parts.append(p)
            elif isinstance(p, dict) and p.get("type") not in ("reasoning", "thinking"):
                text = p.get("text")
                if isinstance(text, dict):          # {"text": {"value": ...}} biçimi
                    text = text.get("value")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return ""


def _answer_of(choice):
    """Seçenekten yanıt metni: message.content, yoksa eski 'text' alanı, yoksa ret açıklaması."""
    message = choice.get("message") or choice.get("delta") or {}
    answer = _text_of(message.get("content"))
    if not answer:
        answer = _text_of(choice.get("text"))
    if not answer and message.get("refusal"):
        answer = str(message["refusal"]).strip()
    return answer


class _ModelGone(Exception):
    """OpenRouter modeli tanımıyor ya da artık hiçbir sağlayıcı sunmuyor (HTTP 404)."""


def _call(api_key, model, payload):
    """Tek model için istek gönder; yanıt metnini döndür."""
    payload = dict(payload, model=model)
    req = urllib.request.Request(
        API_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key,
                 "X-Title": "Tarla Pusulasi"},
        method="POST")
    result = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=40) as response:
                raw = response.read().decode("utf-8", errors="replace")
            try:
                result = json.loads(raw)
            except ValueError:
                raise RuntimeError("OpenRouter anlaşılamayan bir yanıt döndürdü. Biraz sonra tekrar deneyin.")
            break
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 502, 503) and attempt < 2:
                time.sleep(2 + 2 * attempt)
                continue
            if exc.code == 404 and "data policy" not in body.lower():
                raise _ModelGone(_friendly(404, body, model)) from exc
            raise RuntimeError(_friendly(exc.code, body, model)) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt < 2:
                time.sleep(2 + 2 * attempt)
                continue
            raise RuntimeError("OpenRouter'a bağlanılamadı. İnternet bağlantınızı kontrol edin.") from exc

    if not isinstance(result, dict):
        raise RuntimeError("Sunucudan yanıt alınamadı.")
    if result.get("error"):         # OpenRouter bazı hataları 200 gövdesinde döndürür
        err = result["error"]
        code = int(err["code"]) if str(err.get("code", "")).isdigit() else 500
        body = json.dumps({"error": err})
        if code == 404 and "data policy" not in body.lower():
            raise _ModelGone(_friendly(404, body, model))
        raise RuntimeError(_friendly(code, body, model))
    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError("Model boş yanıt verdi. Model adını ve hesabınızı kontrol edin.")
    choice = choices[0] if isinstance(choices[0], dict) else {}
    answer = _answer_of(choice)
    if not answer:
        raise _EmptyAnswer(str(choice.get("finish_reason") or choice.get("native_finish_reason") or ""))
    return answer


class _EmptyAnswer(RuntimeError):
    """HTTP 200 geldi ama yanıtta görünür metin yok (çoğunlukla sınır düşünmeye harcandı)."""


def _call_text(api_key, model, payload, allow_empty=False):
    """_call + boş yanıt kurtarma: daha geniş sınır ve kısa düşünme ile bir kez daha dener."""
    try:
        return _call(api_key, model, payload)
    except _EmptyAnswer as empty:
        if allow_empty:
            return ""
        reason = str(empty)
    retry = dict(payload, max_tokens=max(RETRY_TOKENS, int(payload.get("max_tokens") or 0)),
                 reasoning={"effort": "low", "exclude": True})
    try:
        return _call(api_key, model, retry)
    except _EmptyAnswer as empty:
        reason = str(empty) or reason
    except RuntimeError as exc:
        if isinstance(exc, _ModelGone):
            raise
        # bazı modeller 'reasoning' alanını kabul etmez: yalnızca sınırı büyüterek dene
        try:
            return _call(api_key, model, dict(payload, max_tokens=retry["max_tokens"]))
        except _EmptyAnswer as again:
            reason = str(again) or reason
    hint = (" Yanıt sınırı dolmuş." if reason == "length" else
            " Model içerik filtresine takılmış olabilir." if reason == "content_filter" else "")
    raise RuntimeError(f"Model metin içermeyen bir yanıt döndürdü ({label_of(model)}).{hint} "
                       "Soruyu kısaltıp tekrar deneyin ya da Özelleştirme'den başka bir model seçin.")


def ask(question, context="", history=None):
    """history: [(rol, metin), ...] — önceki soru/cevaplar, rol 'sen' veya 'asistan'.

    İstenen model 404 verirse güncel Claude Haiku modelleri sırayla denenir; çalışan
    model oturum boyunca hatırlanır (her soruda yeniden 404 beklenmez).
    """
    api_key, wanted = _settings()
    payload = build_payload(question, context, history, wanted)
    first = _active["model"] or wanted
    try:
        answer = _call_text(api_key, first, payload)
        _active["model"] = first
        return answer
    except _ModelGone as gone:
        first_error = str(gone)

    try:                                    # yedekler: canlı liste + sabit liste
        candidates = available_haiku()
    except Exception:
        candidates = []
    tried = {first}
    for model in candidates[:3] + FALLBACK_MODELS:
        if model in tried:
            continue
        tried.add(model)
        try:
            answer = _call_text(api_key, model, payload)
        except _ModelGone:
            continue
        _active["model"] = model
        _notice.append(f"model: {label_of(model)} · {label_of(wanted)} artık sunulmuyor")
        return answer
    _active["model"] = None
    raise RuntimeError(first_error)


def test_key(api_key, model=None):
    """Ayarlar ekranındaki "Anahtarı dene": çok kısa bir istek gönderir. Döner: (ok, mesaj)"""
    api_key = (api_key or "").strip()
    if not api_key.startswith("sk-or-"):
        return False, "Bu bir OpenRouter anahtarı değil (sk-or- ile başlamalı)."
    model = model if model and "/" in model else DEFAULT_MODEL
    payload = {"messages": [{"role": "user", "content": "OK"}], "max_tokens": 16}
    tried = [model]
    try:
        _call_text(api_key, model, payload, allow_empty=True)
        return True, f"Anahtar çalışıyor · {label_of(model)}"
    except _ModelGone:
        pass
    except RuntimeError as exc:
        return False, str(exc)
    try:
        candidates = available_haiku()
    except Exception:
        candidates = []
    for alt in candidates[:3] + FALLBACK_MODELS:
        if alt in tried:
            continue
        tried.append(alt)
        try:
            _call_text(api_key, alt, payload, allow_empty=True)
            return True, (f"Anahtar çalışıyor. {label_of(model)} artık sunulmadığı için "
                          f"{label_of(alt)} kullanılacak.")
        except _ModelGone:
            continue
        except RuntimeError as exc:
            return False, str(exc)
    return False, "Anahtar geçerli olabilir ama uygun bir Claude Haiku modeli bulunamadı."
