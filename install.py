#!/usr/bin/python3
"""Register this checkout as a desktop application for the current user."""

import argparse
import os
from pathlib import Path
import shlex
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
HOME = Path.home()
APP_ID = "io.github.folio.Reader.desktop"


def install(make_default=False):
    data = Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share"))
    binary = HOME / ".local/bin/folio"
    applications = data / "applications"
    icons = data / "icons/hicolor/scalable/apps"
    for folder in (binary.parent, applications, icons):
        folder.mkdir(parents=True, exist_ok=True)
    binary.write_text(f'#!/bin/sh\nexec /usr/bin/python3 {shlex.quote(str(ROOT / "folio/app.py"))} "$@"\n')
    binary.chmod(0o755)
    (ROOT / "folio.sh").chmod(0o755)
    shutil.copyfile(ROOT / "assets/folio.svg", icons / "io.github.folio.Reader.svg")
    desktop = applications / APP_ID
    desktop.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Fólio\n"
        "GenericName=Visualizador de Markdown\n"
        "Comment=Markdown com calma. Um leitor leve e sem distrações.\n"
        f'Exec="{binary}" %F\n'
        "Icon=io.github.folio.Reader\n"
        "Terminal=false\n"
        "Categories=Office;Viewer;\n"
        "MimeType=text/markdown;text/x-markdown;\n"
        "StartupNotify=true\n"
        "Keywords=markdown;md;reader;leitor;outline;\n"
    )
    if shutil.which("desktop-file-validate"):
        subprocess.run(["desktop-file-validate", str(desktop)], check=True)
    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(applications)], check=True)
    if make_default:
        for mime in ("text/markdown", "text/x-markdown"):
            subprocess.run(["xdg-mime", "default", APP_ID, mime], check=True)
    print(f"Fólio instalado: {binary}\nLançador: {desktop}")
    if make_default:
        print("Leitor padrão para arquivos Markdown registrado.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--default", action="store_true", help="Usar Fólio como leitor padrão de Markdown")
    install(parser.parse_args().default)
