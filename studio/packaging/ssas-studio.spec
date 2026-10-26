# PyInstaller spec for SSAS Studio (Windows, no console window).
# Build from the studio/ folder:  pyinstaller packaging/ssas-studio.spec --noconfirm
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
apk = os.environ.get("SSAS_BOARD_APK", "")
datas = []
if apk and Path(apk).exists():
    datas.append((apk, "board"))

a = Analysis(
    [str(ROOT / "run_studio.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=["openpyxl.cell._writer"],
    excludes=["tkinter", "matplotlib", "scipy", "skimage", "pytest", "IPython", "PIL.ImageQt"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SSAS Studio",
    console=False,  # no cmd window
    icon=str(ROOT / "packaging" / "icon.ico"),
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SSAS Studio")
