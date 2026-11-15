"""Tekrar çalıştırılabilir regresyon kontrolleri: python verify_revision.py.
--ui: kullanıcı kayıtlarından ayrı örnek uygulama; --build: güncel EXE üretir.
"""
import ast
import json
import math
from pathlib import Path
import sys
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import tarla_harita as maps
import tarla_optimizer as opt
import tarla_gorunum as ui
import tarla_kaynak as sources

SQUARE = [[37.87,32.48],[37.87,32.481],[37.871,32.481],[37.871,32.48]]


class Regression(unittest.TestCase):
    def test_python_syntax(self):
        for path in ROOT.glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=path.name)

    def test_geometry_area_and_orientation(self):
        f=maps.describe_field(SQUARE)
        self.assertAlmostEqual(f['alan_m2'],9760,delta=100)
        self.assertEqual(f['alan_m2'],maps.describe_field(list(reversed(SQUARE)))['alan_m2'])
        self.assertEqual(f['alan_m2'],maps.describe_field(SQUARE+[SQUARE[0]])['alan_m2'])

    def test_bad_boundaries(self):
        for points in ([], SQUARE[:2], [SQUARE[0]]*3,
                       [SQUARE[0],SQUARE[2],SQUARE[1],SQUARE[3]],
                       [[37,32],[37,33],[37,34]], [[math.nan,32]], [[90,0]], [[True,0]]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                maps.describe_field(points)

    def test_point_selection(self):
        f=maps.describe_field(SQUARE[:1])
        self.assertEqual(f['alan_m2'],0)
        self.assertEqual(f['kose'],1)

    def test_server_assets_and_callback(self):
        received=[]
        srv=maps.MapServer(received.append)
        srv.on_save=lambda f: dict(f,kayit_adi='Deneme')
        srv.prepare(points=SQUARE, center=SQUARE[0])
        try:
            page=urlopen(srv.url).read().decode()
            self.assertNotIn('https://unpkg.com/leaflet',page)
            self.assertIn('ResizeObserver',page)
            for name in ('leaflet.js','leaflet.css','images/marker-icon.png'):
                self.assertGreater(len(urlopen(f'http://127.0.0.1:{srv.port}/assets/{srv.token}/{name}').read()),100)
            for path in ('/assets/wrong/leaflet.js','/assets/'+srv.token+'/../tarla_ayarlar.py','/?t=wrong'):
                with self.assertRaises(HTTPError):
                    urlopen(f'http://127.0.0.1:{srv.port}'+path)
            data=json.dumps({'points':SQUARE}).encode()
            req=Request(srv.page_url('/tarla'),data=data,headers={'Content-Type':'application/json'})
            self.assertTrue(json.load(urlopen(req))['ok'])
            self.assertEqual(received[0]['kose'],4)
            bad=Request(srv.page_url('/tarla'),data=json.dumps({'points':SQUARE[:2]}).encode(),headers={'Content-Type':'application/json'})
            with self.assertRaises(HTTPError) as err:
                urlopen(bad)
            self.assertEqual(err.exception.code,400)
            self.assertIn('Kaynaklar ve hesap',urlopen(srv.page_url('/kaynaklar')).read().decode())
        finally:
            srv.stop()

    def loop(self,n=0.7,c=0.31,rain=394,water=1746):
        return opt.closed_loop({'ciplak_ay':1.68,'n_baglanan':1+n,'n_tuketilen':1,
                                'karbon':{'c_ha':[c,c,c]}},
                               {'iklim':{'Pm':[rain/12]*12},'et0':[water/12]*12},3)

    def test_explanations_follow_sign_and_unit(self):
        d=self.loop()
        self.assertEqual(d['su']['denge'],-1352)
        self.assertEqual(d['ortu']['oran'],86)
        self.assertIn('doğrudan sulama miktarı değildir',d['su']['not_'])
        self.assertIn('kg gübre değildir',d['azot']['not_'])
        self.assertIn('tüm plan',d['azot']['birim'])
        for row in d.values():
            self.assertIn('→',row['not_'])
            self.assertTrue(row['kaynak'])
        self.assertIn('tüketimi modelde katkıdan fazla',self.loop(n=-.3)['azot']['not_'])
        self.assertIn('kaybı riski',self.loop(c=-.1)['karbon']['not_'])
        self.assertIn('yıllık açık görünmüyor',self.loop(rain=1800)['su']['not_'])

    def test_all_map_templates_localized(self):
        import tarla_mc,tarla_saha,tarla_toprak
        for module in (maps,tarla_mc,tarla_saha,tarla_toprak):
            html=ui.decorate_html(module.PAGE,'/ui?t=test')
            self.assertNotIn('https://unpkg.com/leaflet',html)
            self.assertEqual(html.count('<script src="/assets/test/leaflet.js">'),1)
            self.assertIn('href="/assets/test/leaflet.css"',html)
            self.assertIn('touch-action:none',html)

    def test_source_registry_contains_actual_parameters(self):
        page=sources.page()
        self.assertIn('saha deneyiyle kalibre edilmedi',page)
        self.assertIn('Kışlık buğday',page)
        self.assertNotIn('CROPS',page)
        self.assertNotIn('REF_',page)

    def test_window_dragging_disabled(self):
        tree=ast.parse((ROOT/'tarla_pencere.py').read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call)
                  and isinstance(n.func,ast.Attribute) and n.func.attr=='create_window')
        args={k.arg:ast.literal_eval(k.value) for k in call.keywords if k.arg in ('easy_drag','draggable')}
        self.assertEqual(args,{'easy_drag':False,'draggable':False})


def launch_ui():
    import tarla_ayarlar,tarla_masaustu as desktop,tarla_tanitim
    folder=ROOT/'build'/'revision-test-profile'
    folder.mkdir(parents=True,exist_ok=True)
    tarla_ayarlar.app_dir=lambda:str(folder)
    tarla_tanitim.first_run=lambda app:None
    sys.argv.append('--demo')
    desktop.main()


def verify_graphics(desktop, report):
    """Gerçek Tk çizimini kaynak koddan ve paketlenmiş EXE'den sınar."""
    import threading
    import time
    import traceback
    from tempfile import TemporaryDirectory
    import tkinter as tk

    checks = []
    failure = None
    root = None
    offline = threading.Event()
    with TemporaryDirectory(prefix="tarla-grafik-") as profile:
        try:
            settings = desktop.tarla_ayarlar
            settings.app_dir = lambda: profile
            settings.load = lambda: {**settings.DEFAULTS, "mod": "gelismis"}
            desktop.tarla_tanitim.first_run = lambda app: None
            desktop.App._splash = lambda app: None
            desktop.App._fade_in = lambda *args, **kwargs: None
            desktop.tp.geocode = lambda query: (query, 37.872 if query == "Konya" else 37.884, 32.481)

            def climate(lat, lon):
                if lat == 37.872:
                    offline.wait(12)
                    raise OSError("Deneme: çevrimdışı")
                return {**desktop.tp.DEMO, "T": [value + 2 for value in desktop.tp.DEMO["T"]]}

            desktop.tp.fetch_nasa = climate
            desktop.tarla_gorunum.install(tk)
            root = tk.Tk()
            root.attributes("-alpha", 0)
            errors = []
            root.report_callback_exception = lambda exc, err, tb: errors.append(
                "".join(traceback.format_exception(exc, err, tb)))
            app = desktop.App(root)
            root.update()

            def require(condition, label):
                if not condition:
                    raise AssertionError(label)
                checks.append(label)

            def until(condition, seconds=5):
                deadline = time.monotonic() + seconds
                while not condition() and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                root.update()
                return condition()

            def charts_ready():
                return bool(app._cgeo and len(app.cc.find_all()) > 25 and len(app.cf.find_all()) > 10
                            and len(app.hits) == len(app.results) > 0)

            require(app.busy and app.kaynak == "ornek" and charts_ready(), "pending request draws sample charts")
            offline.set()
            require(until(lambda: not app.busy) and app.kaynak == "ornek" and charts_ready(),
                    "offline startup keeps sample charts")

            for dpi, theme, language, width in ((96,"koyu","tr",1000), (120,"acik","en",1100),
                                                (144,"koyu","de",1250), (192,"acik","tr",1320)):
                root.tk.call("tk", "scaling", dpi / 72)
                root.geometry(f"{width}x760")
                root.update()
                # Bazı Tcl/Tk sürümleri bu ayarları piksel yerine birimli metin olarak döndürür.
                originals = [(widget, widget.cget) for widget in (app.cv,app.cf,app.cr)]
                try:
                    for widget, getter in originals:
                        widget.cget = lambda key, original=getter: "7c" if key == "height" else original(key)
                    app.apply_appearance(theme, language)
                    require(charts_ready(), f"{dpi} DPI, {theme}/{language}, 7c canvas sizes")
                finally:
                    for widget, getter in originals:
                        widget.cget = getter
                root.update()

            draw_rank = app.draw_rank
            def fail_once():
                app.draw_rank = draw_rank
                raise RuntimeError("Deneme: tek çizim hatası")
            app.draw_rank = fail_once
            app.demo()
            require(until(lambda: len(errors) > 0) and "tek çizim hatası" in errors[0], "simulated callback failure")
            require(until(lambda: not app.busy), "failed callback released analysis controls")
            app.analyze("Deneme")
            require(until(lambda: not app.busy and app.kaynak == "nasa" and app.intro_t == 1.0),
                    "next analysis renders after callback failure")
            require(app.name == "Deneme" and charts_ready(), "live result replaces sample with animated charts")
            app.toggle_irr()
            require(charts_ready(), "changing irrigation redraws charts")
            app._apply_mode("kolay")
            root.update()
            require(app.easy_home.winfo_ismapped(), "simple home is visible")
            app._apply_mode("gelismis")
            root.update()
            require(charts_ready() and len(errors) == 1, "advanced home redraws with no unexpected callbacks")
            desktop.ANIM = False
            check_layout_variants(app, desktop, root, require, until)
            require(len(errors) == 1, "layout matrix has no unexpected Tk callbacks")
            runtime = root.tk.call("info", "patchlevel")
        except Exception:
            runtime = root.tk.call("info", "patchlevel") if root is not None else None
            failure = traceback.format_exc()
        finally:
            offline.set()
            if root is not None:
                root.destroy()
    Path(report).write_text(json.dumps({"ok": failure is None, "tk": runtime, "checks": checks,
                                       "error": failure}, ensure_ascii=False, indent=2), encoding="utf-8")
    return int(failure is not None)


def check_layout_variants(app, desktop, root, require, until):
    import tkinter as tk

    def text_inside(canvas):
        width, height = canvas.winfo_width(), canvas.winfo_height()
        for item in canvas.find_all():
            if canvas.type(item) == "text":
                x1, y1, x2, y2 = canvas.bbox(item)
                if not (0 <= x1 <= x2 <= width and 0 <= y1 <= y2 <= height):
                    raise AssertionError(
                        f"{canvas.itemcget(item, 'text')!r} {x1,y1,x2,y2} outside {width}×{height}")

    app.demo()
    require(until(lambda: not app.busy and app.kaynak == "ornek"), "layout tests use local sample data")
    app._apply_mode("kolay")
    root.update()
    app.open_easy_water()
    water = app._active_tab
    require(until(lambda: hasattr(water, "_heading_help")), "water page help attached")
    heading = next(widget for widget in water.winfo_children()
                   if isinstance(widget, tk.Label) and widget.cget("text") == desktop.tarla_dil.tr("Su ve gelecek"))
    button = water._heading_help
    require(button.master is heading.master, "water page has one title and adjacent help")

    settings = desktop.tarla_ayarlar
    for width, height, dpi in ((1024, 680, 120), (1600, 900, 144)):
        root.tk.call("tk", "scaling", dpi / 72)
        root.geometry(f"{width}x{height}+0+0")
        root.update()
        for theme in settings.THEMES:
            for palette in settings.PALETTE_IDS:
                for language in settings.LANGS:
                    case = f"{width}×{height}/{dpi} DPI {language}/{theme}/{palette}"
                    app.apply_appearance(theme, language, accent=palette)
                    app._show_tab(water)
                    root.update()
                    label = desktop.tarla_dil.tr("Su ve gelecek")
                    require(heading.cget("text") == label and button.winfo_ismapped(), f"kolay {case}: water title translated")
                    text_width = root.tk.call("font", "measure", heading.cget("font"), label)
                    available = water.winfo_width() - heading.winfo_x() - button.winfo_width()
                    if text_width + 28 <= available:
                        # Eski dar genişlik kalırsa 'gelecek' gibi kelimeler ikiye bölünür.
                        heading.configure(wraplength=48)
                        heading.event_generate("<Configure>")
                        root.update()
                        wrap_px = heading.winfo_pixels(heading.cget("wraplength"))
                        require(wrap_px == 0 and heading.winfo_width() >= text_width
                                and button.winfo_x() >= heading.winfo_x() + text_width,
                                f"kolay {case}: title reflows into one line")
                    require(button.winfo_x() + button.winfo_width() <= water.winfo_width(),
                            f"kolay {case}: help button fits")

                    app._show_tab(app.layout_root)
                    root.update()
                    require(all(card.winfo_ismapped() and card.winfo_width() > 80
                                for card in app.easy_cards.values()), f"kolay {case}: six home cards visible")
                    app._apply_mode("gelismis")
                    root.update()
                    for canvas in (app.cv, app.cc, app.cf):
                        text_inside(canvas)
                    require(app._cgeo and len(app.hits) == len(app.results) == 50,
                            f"gelismis {case}: climate, components and crop ranking")
                    app._apply_mode("kolay")
                    root.update()
    water.request_close()


if __name__=='__main__':
    if '--ui' in sys.argv:
        launch_ui()
    elif '--build' in sys.argv:
        from build_exe import build
        print(build())
    else:
        unittest.main(verbosity=2)
