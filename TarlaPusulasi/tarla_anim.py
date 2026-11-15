"""Tarla Pusulası animasyon motoru: yumuşatma eğrileri + tek merkezi zamanlayıcı.

Tüm sürekli animasyonlar (nabız, parıltı, kayma) tek bir `after` döngüsünü paylaşır;
böylece onlarca ayrı zamanlayıcı yerine kare başına bir kez çalışılır.
"""
import math
import time


def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def out_cubic(t):
    t = clamp(t)
    return 1 - (1 - t) ** 3


def in_cubic(t):
    t = clamp(t)
    return t * t * t


def in_out(t):
    t = clamp(t)
    return 4 * t * t * t if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def out_back(t, s=1.70158):
    t = clamp(t) - 1
    return 1 + (s + 1) * t ** 3 + s * t ** 2


def out_elastic(t):
    t = clamp(t)
    if t in (0.0, 1.0):
        return t
    return 2 ** (-10 * t) * math.sin((t * 10 - .75) * (2 * math.pi) / 3) + 1


def stagger(t, i, step=.08, span=.6):
    """i. öğe için 0→1 yerel ilerleme (sırayla başlayan animasyonlar)."""
    return clamp((t - i * step) / span)


class Ticker:
    """Kayıtlı işleri ~60 fps'de çağırır. İş False döndürürse kaldırılır."""

    def __init__(self, root, enabled=lambda: True, interval=16):
        self.root = root
        self.enabled = enabled
        self.interval = interval
        self.jobs = {}
        self._job = None

    def add(self, key, fn):
        self.jobs[key] = fn
        if self._job is None:
            self._job = self.root.after(self.interval, self._loop)

    def remove(self, key):
        self.jobs.pop(key, None)

    def has(self, key):
        return key in self.jobs

    def _loop(self):
        self._job = None
        try:
            if not self.root.winfo_exists():
                return
        except Exception:
            return
        now = time.perf_counter()
        for key, fn in list(self.jobs.items()):
            try:
                keep = fn(now)
            except Exception:
                keep = False
            if keep is False and self.jobs.get(key) is fn:
                del self.jobs[key]
        if self.jobs:
            self._job = self.root.after(self.interval, self._loop)
