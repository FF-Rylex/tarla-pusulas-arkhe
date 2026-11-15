"""
Arduino buzzer bağlantısı — Tarla Pusulası

pyserial KURULU DEĞİLSE de uygulama çalışır: bu modül o durumda kendini
"kullanılamaz" diye bildirir, frekans penceresi yine açılır.

Kurulum (isteğe bağlı):   pip install pyserial

Arduino tarafına yüklenecek taslak OKU-BENI.txt içinde.
Gönderilen komut biçimi:  F<frekans>,<saniye>,<tekrar>   →  örn. F180,600,3
Durdurma:                 F0,0,0  (yeni taslak "STOPPED" diye yanıt verir)

Durdurma iki kademelidir: önce F0,0,0 gönderilir ve kartın "STOPPED" yanıtı
beklenir. Yanıt gelmezse (eski, delay() kullanan taslak ya da takılmış kart)
kart DTR hattıyla yeniden başlatılır; Uno/Nano gibi kartlarda bu, sesi
taslaktan bağımsız olarak hemen keser.
"""
import threading
import time

try:
    import serial                      # pyserial
    from serial.tools import list_ports
    HAVE_SERIAL = True
except Exception:                      # pyserial yok
    serial = None
    list_ports = None
    HAVE_SERIAL = False


def ports():
    """Bilgisayarda görünen seri portlar: [(aygıt, açıklama), ...]"""
    if not HAVE_SERIAL:
        return []
    out = []
    for p in list_ports.comports():
        desc = (p.description or "").strip()
        if desc and desc.lower() != "n/a":
            out.append((p.device, desc))
        else:
            out.append((p.device, p.device))
    return out


def looks_like_arduino(desc):
    """Port açıklaması Arduino/CH340/CP210x gibi mi? (otomatik seçim için)"""
    d = (desc or "").lower()
    return any(k in d for k in ("arduino", "ch340", "ch341", "cp210", "usb serial",
                                "usb-serial", "ftdi", "wch"))


class Buzzer:
    """Tek port üzerinden komut gönderen küçük yardımcı."""

    def __init__(self):
        self.ser = None
        self.port = None
        self.lock = threading.RLock()   # durdurma arka planda çalışır; yazmalar çakışmasın
        self._ready_at = 0.0            # kart yeniden başlatıldıysa önyükleyicinin bitiş anı

    # ---------------------------------------------------------------- durum
    @property
    def connected(self):
        return self.ser is not None and getattr(self.ser, "is_open", False)

    def info(self):
        return f"{self.port}" if self.connected else ""

    # ---------------------------------------------------------------- bağlan
    def connect(self, port=None, baud=9600):
        """Porta bağlan. port=None ise Arduino'ya benzeyen ilk portu dener.
        Döner: (ok, mesaj)"""
        if not HAVE_SERIAL:
            return False, ("pyserial kurulu değil. Komut satırında "
                           "pip install pyserial çalıştırın.")
        self.close()
        cands = [port] if port else [p for p, d in ports() if looks_like_arduino(d)]
        if not cands:
            return False, "Arduino bulunamadı. USB kablosunu ve portu kontrol edin."
        last = ""
        for p in cands:
            try:
                self.ser = serial.Serial(p, baud, timeout=1, write_timeout=1)
                self.port = p
                # Arduino yeniden başlar; açılışı bekle
                import time as _t
                _t.sleep(1.8)
                self.ser.reset_input_buffer()
                return True, f"Bağlandı · {p}"
            except Exception as e:
                last = str(e)
                self.ser = None
                self.port = None
        return False, ("Port açılamadı (" + last + "). Arduino IDE'nin Seri Port "
                       "Monitörü açıksa kapatın.")

    def close(self):
        with self.lock:
            try:
                if self.ser is not None:
                    self.ser.close()
            except Exception:
                pass
            self.ser = None
            self.port = None

    # ---------------------------------------------------------------- gönder
    def send(self, freq, seconds=600, repeat=3):
        """F180,600,3 biçiminde komut gönder. Döner: (ok, mesaj)"""
        with self.lock:
            if not self.connected:
                return False, "Arduino bağlı değil."
            wait = self._ready_at - time.monotonic()
            if wait > 0:                # yeni sıfırlandı: önyükleyici komutu yutmasın
                time.sleep(wait)
            cmd = f"F{int(freq)},{int(seconds)},{int(repeat)}\n"
            try:
                self.ser.write(cmd.encode("ascii"))
                self.ser.flush()
                return True, cmd.strip()
            except Exception as e:
                self.close()
                return False, f"Gönderilemedi: {e}"

    def _wait_reply(self, word, timeout):
        """Karttan 'word' içeren satır gelirse True."""
        end = time.monotonic() + timeout
        buf = b""
        while time.monotonic() < end:
            try:
                n = self.ser.in_waiting
                buf += self.ser.read(n or 1)
            except Exception:
                return False
            if word.encode("ascii") in buf:
                return True
        return False

    def _hard_reset(self):
        """DTR darbesiyle kartı yeniden başlat (otomatik reset devreli kartlar)."""
        try:
            self.ser.dtr = False
            time.sleep(0.12)
            self.ser.dtr = True
            self._ready_at = time.monotonic() + 2.0
            return True
        except Exception:
            return False

    def stop(self, confirm_timeout=0.45):
        """Sesi kes. Döner: (ok, mesaj)

        1) F0,0,0 gönder, "STOPPED" yanıtını kısa süre bekle.
        2) Yanıt yoksa kartı DTR ile yeniden başlat (eski taslakta da ses kesilir).
        """
        with self.lock:
            if not self.connected:
                return False, "Arduino bağlı değil."
            old_timeout = self.ser.timeout
            try:
                self.ser.reset_input_buffer()
                self.ser.write(b"F0,0,0\n")
                self.ser.flush()
                self.ser.timeout = 0.05
                if self._wait_reply("STOPPED", confirm_timeout):
                    return True, "Arduino durdu (onaylandı)."
            except Exception as e:
                self.close()
                return False, f"Durdurma gönderilemedi: {e}"
            finally:
                try:
                    if self.ser is not None:
                        self.ser.timeout = old_timeout
                except Exception:
                    pass
            if self._hard_reset():
                return True, ("Arduino yanıt vermedi; kart yeniden başlatılarak ses kesildi. "
                              "Kalıcı çözüm için TarlaBuzzer.ino'yu karta yükleyin.")
            return False, ("Arduino yanıt vermedi. TarlaBuzzer.ino'yu karta yükleyin ya da "
                           "USB kablosunu çıkarıp takın.")


# uygulama genelinde tek bağlantı
BUZZER = Buzzer()


def status_text():
    """Şerit/pencere için kısa durum."""
    if not HAVE_SERIAL:
        return "pyserial yok"
    if BUZZER.connected:
        return BUZZER.port
    return "bağlı değil"
