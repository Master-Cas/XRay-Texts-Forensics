from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

project_root = Path(SPECPATH).parents[1]
webview_datas, webview_binaries, webview_hiddenimports = collect_all("webview")

datas = collect_data_files("xray_text_forensics.web") + webview_datas
hiddenimports = webview_hiddenimports + [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.lifespan.on",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]

a = Analysis(
    [str(project_root / "packaging" / "windows" / "desktop_entry.py")],
    pathex=[str(project_root / "src")],
    binaries=webview_binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="XRay-Texts-Forensics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="XRay-Texts-Forensics",
)
