"""PyInstaller specification for diagnostic and release onedir builds."""

import os
from pathlib import Path

from kivy.tools.packaging.pyinstaller_hooks import get_deps_minimal, hookspath

project_root = Path(SPECPATH).parent
diagnostic = os.environ.get("SHIFT_CHECKLIST_DIAGNOSTIC") == "1"
application_name = "ShiftChecklist-Diagnostic" if diagnostic else "ShiftChecklist"

datas = [
    (str(project_root / "shift_checklist.kv"), "."),
    (
        str(project_root / "assets" / "icons" / "shift-checklist.png"),
        "assets/icons",
    ),
    (
        str(project_root / "assets" / "icons" / "shift-checklist.ico"),
        "assets/icons",
    ),
    (str(project_root / "assets" / "sounds"), "assets/sounds"),
    (str(project_root / "README.md"), "."),
    (str(project_root / "LICENSE.txt"), "."),
    (str(project_root / "CHANGELOG.md"), "."),
    (str(project_root / "RELEASE_NOTES.md"), "."),
    (str(project_root / "docs" / "USER_GUIDE.md"), "docs"),
    (str(project_root / "docs" / "WINDOWS_ACCEPTANCE.md"), "docs"),
]
kivy_dependencies = get_deps_minimal(
    audio=True,
    camera=None,
    clipboard=None,
    image=True,
    spelling=None,
    text=True,
    video=None,
    window=True,
)
hidden_imports = [
    *kivy_dependencies["hiddenimports"],
    "plyer.platforms.win.notification",
]

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=kivy_dependencies["binaries"],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=hookspath(),
    hooksconfig={},
    runtime_hooks=[],
    excludes=kivy_dependencies["excludes"],
    noarchive=False,
    optimize=0,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name=application_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=diagnostic,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "assets" / "icons" / "shift-checklist.ico"),
    version=str(project_root / "packaging" / "version_info.txt"),
    manifest=str(project_root / "packaging" / "windows.manifest"),
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=application_name,
)
