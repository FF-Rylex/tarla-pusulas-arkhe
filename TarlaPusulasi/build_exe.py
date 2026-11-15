"""Derleme yollarını Python içinde Unicode olarak sakla."""

import os
from pathlib import Path
import shutil
import tempfile

import PyInstaller.__main__


def build():
    root = Path(__file__).resolve().parent
    os.chdir(root)
    dist = root / "dist"
    dist.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="yeni-", dir=dist))

    try:
        with tempfile.TemporaryDirectory(prefix="build-", dir=stage) as work:
            PyInstaller.__main__.run([
                "--noconfirm",
                "--distpath", str(stage),
                "--workpath", work,
                str(root / "TarlaPusulasi.spec"),
            ])
        executable = stage / "TarlaPusulasi.exe"
        if not executable.is_file():
            raise RuntimeError("TarlaPusulasi.exe olusturulamadi.")
    except (Exception, SystemExit, KeyboardInterrupt):
        shutil.rmtree(stage, ignore_errors=True)
        raise

    target = dist / executable.name
    try:
        executable.replace(target)
    except PermissionError:
        # Windows, calismakta olan EXE'nin degistirilmesine izin vermez.
        print("Mevcut EXE degistirilemedi. Yeni EXE ayri klasorde hazir.")
        return executable

    shutil.rmtree(stage)
    return target


if __name__ == "__main__":
    executable = build()
    print(f"\nHazir: {executable}")
    print("Hedef bilgisayarda Windows Edge WebView2 Runtime bulunmalidir.")
    if os.name == "nt":
        os.startfile(executable.parent)
