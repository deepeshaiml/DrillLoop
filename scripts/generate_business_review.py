"""Generate the independent Business Review PPTX and PDF from local source."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "presentation/generate_business_review.js"
PPTX_OUT = ROOT / "DrillLoop_Business_Review.pptx"
PDF_OUT = ROOT / "DrillLoop_Business_Review.pdf"
FONT_REVISION = "66285aa2951a3634d74aa447951a8ca7362d3c7d"
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    f"{FONT_REVISION}/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
)
LICENSE_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    f"{FONT_REVISION}/ofl/notosans/OFL.txt"
)
FONT_SHA256 = "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d"
LICENSE_SHA256 = "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a"


def download_verified(url: str, destination: Path, sha256: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "DrillLoop-document-generator/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        destination.write_bytes(response.read())
    actual = hashlib.sha256(destination.read_bytes()).hexdigest()
    if actual != sha256:
        raise RuntimeError(f"Pinned asset digest mismatch for {destination.name}")


def fontconfig_file(font_dir: Path, cache_dir: Path, temp: Path) -> Path:
    candidates = (
        Path("/opt/homebrew/etc/fonts/fonts.conf"),
        Path("/usr/local/etc/fonts/fonts.conf"),
        Path("/etc/fonts/fonts.conf"),
    )
    base = next((path for path in candidates if path.is_file()), None)
    if base is None:
        raise RuntimeError("A system Fontconfig configuration is required for PDF export")
    config = temp / "fontconfig.xml"
    config.write_text(
        "<?xml version=\"1.0\"?>\n"
        "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">\n"
        "<fontconfig>\n"
        f"  <dir>{escape(str(font_dir))}</dir>\n"
        f"  <cachedir>{escape(str(cache_dir))}</cachedir>\n"
        f"  <include>{escape(str(base))}</include>\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )
    return config


def verify_font(font_path: Path, environment: dict[str, str]) -> None:
    fc_match = shutil.which("fc-match")
    if not fc_match:
        raise RuntimeError("fc-match is required to verify the pinned rendering font")
    result = subprocess.run(
        [fc_match, "-f", "%{file}", "Noto Sans"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    matched = Path(result.stdout.strip()).resolve()
    if matched != font_path.resolve():
        raise RuntimeError("Fontconfig did not resolve Noto Sans to the pinned font file")


def main() -> None:
    node = shutil.which("node")
    soffice = shutil.which("soffice")
    if not node:
        raise RuntimeError("Node.js is required to generate the editable presentation")
    if not soffice:
        raise RuntimeError("LibreOffice soffice is required to export the PDF")
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Presentation source is missing: {SOURCE.name}")

    with tempfile.TemporaryDirectory(prefix="drillloop-business-review-") as temp_name:
        temp = Path(temp_name)
        fonts = temp / "fonts"
        cache = temp / "font-cache"
        fonts.mkdir()
        cache.mkdir()
        font_path = fonts / "NotoSans-VF.ttf"
        license_path = temp / "Noto-Sans-OFL.txt"
        download_verified(FONT_URL, font_path, FONT_SHA256)
        download_verified(LICENSE_URL, license_path, LICENSE_SHA256)

        config = fontconfig_file(fonts, cache, temp)
        environment = os.environ.copy()
        environment["FONTCONFIG_FILE"] = str(config)
        verify_font(font_path, environment)

        pptx_temp = temp / PPTX_OUT.name
        pdf_temp_dir = temp / "pdf"
        pdf_temp_dir.mkdir()
        subprocess.run(
            [node, str(SOURCE), str(pptx_temp)],
            cwd=ROOT,
            check=True,
            env=environment,
        )
        profile = (temp / "libreoffice-profile").as_uri()
        subprocess.run(
            [
                soffice,
                "--headless",
                f"-env:UserInstallation={profile}",
                "--convert-to",
                "pdf",
                "--outdir",
                str(pdf_temp_dir),
                str(pptx_temp),
            ],
            cwd=ROOT,
            check=True,
            env=environment,
        )
        pdf_temp = pdf_temp_dir / PDF_OUT.name
        if not pptx_temp.is_file() or not pdf_temp.is_file():
            raise RuntimeError("Presentation generation or PDF export did not produce both outputs")

        # Replace the two reviewed deliverables only after both temporary outputs exist.
        shutil.copyfile(pptx_temp, PPTX_OUT)
        shutil.copyfile(pdf_temp, PDF_OUT)
        print(f"Generated {PPTX_OUT.name} and {PDF_OUT.name}")
        print(f"Font: Noto Sans, Google Fonts revision {FONT_REVISION}, SIL OFL 1.1")


if __name__ == "__main__":
    main()
