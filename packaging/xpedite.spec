# PyInstaller spec for xpedite.exe: packaging/build.py runs it (locally and in the release workflow).
# Only Python and the packages are frozen. xpedite's own code isn't: the analysis follows it to find
# every module it needs, then it's taken out of the archive and packaging/build.py copies app/,
# macro/ and data/ beside the exe as plain files (packaging/launcher.py runs them). The folder a
# player sees: xpedite.exe, _internal/ (Python and the packages), app/, macro/, data/.
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.dirname(SPECPATH)
SKIP = {"linux", "wl"}  # Linux-only modules (Wayland)

hidden = []
for dirpath, dirs, files in os.walk(os.path.join(ROOT, "macro")):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for name in files:
        if name.endswith(".py") and name[:-3] not in SKIP:
            module = os.path.relpath(os.path.join(dirpath, name), ROOT)[:-3].replace(os.sep, ".")
            hidden.append(module[: -len(".__init__")] if module.endswith(".__init__") else module)
app_modules = [n[:-3] for n in os.listdir(os.path.join(ROOT, "app")) if n.endswith(".py")]
hidden += app_modules
# RapidOCR loads its detector and recogniser modules by name from its config.
hidden += collect_submodules("rapidocr_onnxruntime")
OURS = {"macro", "app", "tools", "wlproto", *app_modules}

a = Analysis(
    [os.path.join(SPECPATH, "launcher.py")],
    pathex=[ROOT, os.path.join(ROOT, "app")],
    hiddenimports=hidden,
    datas=collect_data_files("rapidocr_onnxruntime"),
    excludes=["tkinter", "pywayland", "matplotlib", "IPython", "pytest",
              "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
              "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtPdf", "PyQt6.Qt3DCore"],
    noarchive=False,
)
a.pure = [entry for entry in a.pure if entry[0].split(".")[0] not in OURS]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="xpedite",
    icon=os.path.join(ROOT, "app", "assets", "brand", "xpedite.ico"),
    console=False,
    contents_directory="_internal",  # Python and the packages; xpedite's own files sit beside the exe
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="xpedite")
