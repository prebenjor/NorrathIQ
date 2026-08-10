# Build from updater/: pyinstaller NorrathIQUpdater.spec
from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import sys

hiddenimports = collect_submodules("norrathiq")
root = Path(SPECPATH)
legacy_tk = root.parent / "dist" / "NorrathIQUpdater-1.2.0" / "_internal"
if not (legacy_tk / "_tcl_data" / "init.tcl").is_file():
    raise RuntimeError("A matching Tcl/Tk runtime is required to build the updater GUI.")
tkinter_source = Path(sys.base_prefix) / "Lib" / "tkinter"
tk_binaries = [(str(legacy_tk / name), ".") for name in ("_tkinter.pyd", "tcl86t.dll", "tk86t.dll")]
tk_datas = [
    (str(legacy_tk / "_tcl_data"), "_tcl_data"),
    (str(legacy_tk / "_tk_data"), "_tk_data"),
    (str(legacy_tk / "tcl8"), "tcl8"),
    (str(tkinter_source), "tkinter"),
]

a = Analysis(
    ["norrathiq/gui.py"],
    pathex=["."],
    binaries=tk_binaries,
    datas=tk_datas,
    hiddenimports=hiddenimports + ["_tkinter"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["norrathiq_tk_runtime.py"],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="NorrathIQUpdater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True, name="NorrathIQUpdater")
