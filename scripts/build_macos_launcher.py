#!/usr/bin/env python3
"""Build a clickable local macOS launcher bundle for Archive Studio for Mac.

This is intentionally a developer/local-machine launcher. It points at the
current checkout and virtualenv; it is not a standalone redistributable app.
"""

from __future__ import annotations

import plistlib
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter


APP_NAME = "Archive Studio for Mac 1.1"
BUNDLE_NAME = f"{APP_NAME}.app"
IDENTIFIER = "com.archivestudio.desktop"


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    python_bin = project_root / ".venv" / "bin" / "python"
    dist_dir = project_root / "dist"
    bundle_dir = dist_dir / BUNDLE_NAME
    contents_dir = bundle_dir / "Contents"
    macos_dir = contents_dir / "MacOS"
    resources_dir = contents_dir / "Resources"

    if not python_bin.exists():
        raise SystemExit(f"Missing virtualenv Python: {python_bin}")

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    icon_path = resources_dir / f"{APP_NAME}.icns"
    _build_icns(icon_path)
    _write_info_plist(contents_dir / "Info.plist")
    _write_launcher_script(macos_dir / APP_NAME, project_root=project_root, python_bin=python_bin)
    _write_local_launcher_readme(resources_dir / "LOCAL_LAUNCHER_README.txt", project_root=project_root)

    print(bundle_dir)
    print(
        "Built a local launcher only. It depends on this checkout and .venv; "
        "rebuild it if either path moves."
    )
    return 0


def _write_info_plist(path: Path) -> None:
    info = {
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": APP_NAME,
        "CFBundleIconFile": APP_NAME,
        "CFBundleIdentifier": IDENTIFIER,
        "CFBundleInfoDictionaryVersion": "6.0",
        "CFBundleName": APP_NAME,
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.1",
        "CFBundleVersion": "1.1",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with path.open("wb") as handle:
        plistlib.dump(info, handle)


def _write_launcher_script(path: Path, *, project_root: Path, python_bin: Path) -> None:
    launcher = f"""#!/bin/zsh
set -euo pipefail

PROJECT_ROOT="{project_root}"
PYTHON_BIN="{python_bin}"
LOG_DIR="$HOME/Library/Logs/ArchiveStudio"
LOG_FILE="$LOG_DIR/launcher.log"

mkdir -p "$LOG_DIR"
exec >>"$LOG_FILE" 2>&1

echo "=== ArchiveStudio launch $(date '+%Y-%m-%d %H:%M:%S') ==="

if [[ ! -d "$PROJECT_ROOT" ]]; then
  /usr/bin/osascript -e 'display alert "ArchiveStudio Project Missing" message "The launcher expected the project at:\\n{_escape_applescript(str(project_root))}" as critical'
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  /usr/bin/osascript -e 'display alert "ArchiveStudio Python Missing" message "The launcher expected the virtualenv Python at:\\n{_escape_applescript(str(python_bin))}" as critical'
  exit 1
fi

cd "$PROJECT_ROOT"
export PYTHONUNBUFFERED=1
exec "$PYTHON_BIN" -m archivestudio
"""
    path.write_text(launcher, encoding="utf-8")
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _write_local_launcher_readme(path: Path, *, project_root: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "ArchiveStudio local launcher",
                "",
                "This .app is a convenience launcher for this machine.",
                "It is not a standalone redistributable macOS application.",
                "",
                f"Expected project checkout: {project_root}",
                "Expected Python: <project checkout>/.venv/bin/python",
                "",
                "If you move or delete the checkout or virtualenv, rebuild the launcher.",
                "For distribution to other machines, build a bundled app with a packaging tool.",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _build_icns(output_path: Path) -> None:
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        master_png = temp_dir / "master.png"
        iconset_dir = temp_dir / f"{APP_NAME}.iconset"
        iconset_dir.mkdir(parents=True, exist_ok=True)

        _draw_master_icon(master_png)

        sizes = {
            "icon_16x16.png": 16,
            "icon_16x16@2x.png": 32,
            "icon_32x32.png": 32,
            "icon_32x32@2x.png": 64,
            "icon_128x128.png": 128,
            "icon_128x128@2x.png": 256,
            "icon_256x256.png": 256,
            "icon_256x256@2x.png": 512,
            "icon_512x512.png": 512,
            "icon_512x512@2x.png": 1024,
        }

        with Image.open(master_png) as master:
            for filename, size in sizes.items():
                resized = master.resize((size, size), Image.Resampling.LANCZOS)
                resized.save(iconset_dir / filename)

        subprocess.run(
            ["/usr/bin/iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path)],
            check=True,
        )


def _draw_master_icon(path: Path) -> None:
    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))

    background = Image.new("RGBA", image.size, (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(background)
    bg_draw.rounded_rectangle(
        (72, 72, 952, 952),
        radius=210,
        fill=(231, 221, 201, 255),
    )
    shadow = background.filter(ImageFilter.GaussianBlur(28))
    image.alpha_composite(shadow, dest=(0, 24))
    image.alpha_composite(background)

    box = Image.new("RGBA", image.size, (0, 0, 0, 0))
    box_draw = ImageDraw.Draw(box)
    box_draw.rounded_rectangle((220, 380, 804, 760), radius=72, fill=(74, 96, 106, 255))
    box_draw.rounded_rectangle((180, 300, 844, 470), radius=84, fill=(94, 120, 131, 255))
    box_draw.rounded_rectangle((424, 520, 600, 618), radius=26, fill=(228, 214, 189, 255))
    image.alpha_composite(box)

    page = Image.new("RGBA", image.size, (0, 0, 0, 0))
    page_draw = ImageDraw.Draw(page)
    page_draw.rounded_rectangle((318, 190, 706, 640), radius=36, fill=(252, 249, 242, 255))
    page_draw.polygon([(626, 190), (706, 190), (706, 270)], fill=(232, 226, 214, 255))
    line_color = (155, 121, 92, 255)
    for top in (310, 372, 434, 496):
        page_draw.rounded_rectangle((384, top, 640, top + 18), radius=9, fill=line_color)
    page_draw.rounded_rectangle((384, 558, 560, 576), radius=9, fill=line_color)
    image.alpha_composite(page)

    accent = Image.new("RGBA", image.size, (0, 0, 0, 0))
    accent_draw = ImageDraw.Draw(accent)
    accent_draw.polygon(
        [(676, 170), (760, 170), (760, 370), (718, 338), (676, 370)],
        fill=(166, 87, 61, 255),
    )
    image.alpha_composite(accent)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


if __name__ == "__main__":
    raise SystemExit(main())
