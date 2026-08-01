"""Release metadata, asset, and PyInstaller configuration tests."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from constants import APP_NAME, APP_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_release_uses_semantic_version_and_consistent_metadata() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", APP_VERSION)
    assert APP_NAME == "Shift Checklist"
    for relative_path in (
        "packaging/version_info.txt",
        "packaging/windows.manifest",
        "CHANGELOG.md",
        "RELEASE_NOTES.md",
    ):
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert APP_VERSION in text


def test_icon_assets_are_valid_and_transparent() -> None:
    png_path = PROJECT_ROOT / "assets" / "icons" / "shift-checklist.png"
    ico_path = PROJECT_ROOT / "assets" / "icons" / "shift-checklist.ico"
    with Image.open(png_path) as icon:
        assert icon.mode == "RGBA"
        assert icon.width == icon.height
        assert icon.getchannel("A").getextrema() == (0, 255)
    with Image.open(ico_path) as icon:
        assert icon.format == "ICO"
        assert (256, 256) in icon.info["sizes"]
        assert (16, 16) in icon.info["sizes"]


def test_pyinstaller_spec_includes_runtime_assets_and_windows_metadata() -> None:
    spec = (PROJECT_ROOT / "packaging" / "shift_checklist.spec").read_text(
        encoding="utf-8"
    )
    for required in (
        "shift_checklist.kv",
        "assets/sounds",
        "shift-checklist.png",
        "shift-checklist.ico",
        "plyer.platforms.win",
        "version_info.txt",
        "windows.manifest",
    ):
        assert required in spec


def test_release_scripts_and_end_user_documents_exist() -> None:
    for relative_path in (
        "packaging/build.ps1",
        "packaging/audit_pyinstaller_warnings.ps1",
        "packaging/package_smoke.ps1",
        "packaging/package_release.ps1",
        "packaging/scan_release.ps1",
        "packaging/KNOWN_WARNINGS.md",
        "docs/USER_GUIDE.md",
        "docs/DEVELOPMENT.md",
        "LICENSE.txt",
    ):
        assert (PROJECT_ROOT / relative_path).is_file()
