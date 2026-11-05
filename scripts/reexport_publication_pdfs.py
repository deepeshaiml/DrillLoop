#!/usr/bin/env python3
"""Re-export selected source documents with the pinned, rights-verified Noto Sans font.

The source DOCX, PPTX, and SVG are copied to a temporary directory. Font-family
references are normalized there, the Idea Document's Symbol private-use bullets are
mapped to the equivalent Noto Sans Symbols bullet, and its point sizes are scaled to
95% to preserve the existing eight-page pagination. Source files and databases are
never written.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
FONT_REVISION = "66285aa2951a3634d74aa447951a8ca7362d3c7d"
FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    f"{FONT_REVISION}/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
)
LICENSE_URL = f"https://raw.githubusercontent.com/google/fonts/{FONT_REVISION}/ofl/notosans/OFL.txt"
FONT_SHA256 = "bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d"
LICENSE_SHA256 = "cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a"
SYMBOLS_FONT_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    f"{FONT_REVISION}/ofl/notosanssymbols/NotoSansSymbols%5Bwght%5D.ttf"
)
SYMBOLS_LICENSE_URL = (
    f"https://raw.githubusercontent.com/google/fonts/{FONT_REVISION}/ofl/notosanssymbols/OFL.txt"
)
SYMBOLS_FONT_SHA256 = "f7e7e04b4a24b6c78893d50cbfd2b2f6cae49617ab047bfef668d252adb128f7"
SYMBOLS_LICENSE_SHA256 = "b118dd41337806a5d4797052c77caf3bd096aed783e5eb21b4d11154351e1ac0"
IDEA_FONT_SIZE_SCALE = 0.95
OFFICE_FONTS = re.compile(
    rb'((?:typeface|w:(?:ascii|hAnsi|eastAsia|cs))=")'
    rb'(?:Aptos Display|Aptos|Courier New|Courier|Arial|Helvetica|Calibri|Cambria|Times New Roman)(")'
)
WORD_FONT_SIZE = re.compile(rb'(<w:sz(?:Cs)? w:val=")([0-9]+)(")')
ARROW = "→".encode()
WORD_RUN = re.compile(rb"<w:r\b(?:(?!</w:r>).)*?" + ARROW + rb"(?:(?!</w:r>).)*?</w:r>", re.DOTALL)
DRAWING_RUN = re.compile(
    rb"<a:r\b(?:(?!</a:r>).)*?" + ARROW + rb"(?:(?!</a:r>).)*?</a:r>", re.DOTALL
)
SVG_FONTS = re.compile(
    rb"font-family\s*:\s*(?:Arial\s*,\s*Helvetica\s*,\s*sans-serif|Arial|Helvetica)"
)
LOCAL_PATH = re.compile(r"(?:/Users/[^\s<>\"']+|/Volumes/[^\s<>\"']+|/home/[^\s<>\"']+)")

SOURCES = (
    ("DrillLoop_Idea_Document.docx", "DrillLoop_Idea_Document.pdf", "office"),
    ("DrillLoop_Pitch_Deck.pptx", "DrillLoop_Pitch_Deck.pdf", "office"),
    ("DrillLoop_Architecture.svg", "DrillLoop_Architecture.pdf", "svg"),
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download_verified(url: str, destination: Path, expected: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "DrillLoop-PDF-export/1"})
    with urllib.request.urlopen(request, timeout=45) as response:
        content = response.read()
    if sha256(content) != expected:
        raise RuntimeError(f"Pinned Noto Sans asset digest mismatch: {destination.name}")
    destination.write_bytes(content)


def fontconfig_file(font_dir: Path, cache_dir: Path, temp: Path) -> Path:
    candidates = (
        Path("/opt/homebrew/etc/fonts/fonts.conf"),
        Path("/usr/local/etc/fonts/fonts.conf"),
        Path("/etc/fonts/fonts.conf"),
    )
    base = next((candidate for candidate in candidates if candidate.is_file()), None)
    if base is None:
        raise RuntimeError("A system Fontconfig configuration is required for PDF export")
    config = temp / "fontconfig.xml"
    config.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        f"  <dir>{escape(str(font_dir))}</dir>\n"
        f"  <cachedir>{escape(str(cache_dir))}</cachedir>\n"
        f"  <include>{escape(str(base))}</include>\n"
        "</fontconfig>\n",
        encoding="utf-8",
    )
    return config


def patch_office_fonts(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as input_zip, zipfile.ZipFile(destination, "w") as output_zip:
        for item in input_zip.infolist():
            content = input_zip.read(item.filename)
            if item.filename.endswith((".xml", ".rels")):
                content = OFFICE_FONTS.sub(rb"\1Noto Sans\2", content)
                if source.suffix.lower() == ".docx":
                    content = WORD_RUN.sub(set_word_symbol_run, content)
                    if item.filename == "word/numbering.xml":
                        content = content.replace('w:val="\uf0b7"'.encode(), 'w:val="•"'.encode())
                        content = content.replace(
                            b'w:ascii="Symbol"', b'w:ascii="Noto Sans Symbols"'
                        )
                        content = content.replace(
                            b'w:hAnsi="Symbol"', b'w:hAnsi="Noto Sans Symbols"'
                        )
                elif source.suffix.lower() == ".pptx" and item.filename.startswith("ppt/"):
                    content = DRAWING_RUN.sub(set_drawing_symbol_run, content)
                if source.suffix.lower() == ".docx" and item.filename.startswith("word/"):
                    content = WORD_FONT_SIZE.sub(
                        lambda match: (
                            match.group(1)
                            + str(
                                max(1, round(int(match.group(2)) * IDEA_FONT_SIZE_SCALE))
                            ).encode()
                            + match.group(3)
                        ),
                        content,
                    )
            output_zip.writestr(item, content)
    if office_text(source) != office_text(destination):
        raise RuntimeError(f"Office text content changed while preparing {source.name}")


def set_word_symbol_run(match: re.Match[bytes]) -> bytes:
    run = match.group(0)
    if ARROW not in run:
        return run
    fonts = re.compile(rb"<w:rFonts\b[^>]*/?>")
    replacement = (
        b'<w:rFonts w:ascii="Noto Sans Symbols" w:hAnsi="Noto Sans Symbols" '
        b'w:eastAsia="Noto Sans Symbols" w:cs="Noto Sans Symbols"/>'
    )
    if fonts.search(run):
        return fonts.sub(replacement, run, count=1)
    properties = re.compile(rb"<w:rPr\b[^>]*>")
    if properties.search(run):
        return properties.sub(lambda item: item.group(0) + replacement, run, count=1)
    return re.sub(
        rb"(<w:r\b[^>]*>)",
        rb"\1<w:rPr>" + replacement + rb"</w:rPr>",
        run,
        count=1,
    )


def set_drawing_symbol_run(match: re.Match[bytes]) -> bytes:
    run = match.group(0)
    if ARROW not in run:
        return run
    latin_font = re.compile(rb"<a:latin\b[^>]*/?>")
    replacement = b'<a:latin typeface="Noto Sans Symbols"/>'
    if latin_font.search(run):
        return latin_font.sub(replacement, run, count=1)
    properties = re.compile(rb"<a:rPr\b[^>]*>")
    if properties.search(run):
        return properties.sub(lambda item: item.group(0) + replacement, run, count=1)
    return re.sub(
        rb"(<a:r\b[^>]*>)",
        rb"\1<a:rPr>" + replacement + rb"</a:rPr>",
        run,
        count=1,
    )


def office_text(source: Path) -> tuple[tuple[str, str], ...]:
    chunks: list[tuple[str, str]] = []
    with zipfile.ZipFile(source) as package:
        for name in package.namelist():
            if not name.endswith(".xml"):
                continue
            root = ET.fromstring(package.read(name))
            for element in root.iter():
                if element.tag.rsplit("}", 1)[-1] == "t" and element.text:
                    chunks.append((name, element.text))
    return tuple(chunks)


def patch_svg_fonts(source: Path, destination: Path) -> None:
    content = source.read_bytes()
    patched, count = SVG_FONTS.subn(b"font-family:Noto Sans", content)
    if count == 0:
        raise RuntimeError("No recognized source font declaration was found in the SVG")
    destination.write_bytes(patched)
    if svg_visible_text(source) != svg_visible_text(destination):
        raise RuntimeError("SVG visible text changed while preparing its PDF export")


def svg_visible_text(source: Path) -> tuple[str, ...]:
    root = ET.fromstring(source.read_bytes())
    return tuple(
        "".join(element.itertext())
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] in {"title", "desc", "text"}
    )


def normalized_text(reader: PdfReader) -> str:
    return re.sub(r"\s+", " ", " ".join(page.extract_text() or "" for page in reader.pages)).strip()


def font_names(reader: PdfReader) -> set[str]:
    names: set[str] = set()
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for font_ref in (resources.get("/Font") or {}).values():
            font = font_ref.get_object()
            names.add(str(font.get("/BaseFont", "")))
            for descendant_ref in font.get("/DescendantFonts", []):
                descendant = descendant_ref.get_object()
                names.add(str(descendant.get("/BaseFont", "")))
    return names


def embedded_font_count(reader: PdfReader) -> tuple[int, int]:
    used = 0
    embedded = 0
    for page in reader.pages:
        resources = page.get("/Resources") or {}
        for font_ref in (resources.get("/Font") or {}).values():
            font = font_ref.get_object()
            candidates = [font]
            candidates.extend(ref.get_object() for ref in font.get("/DescendantFonts", []))
            used += 1
            for candidate in candidates:
                descriptor_ref = candidate.get("/FontDescriptor")
                if descriptor_ref:
                    descriptor = descriptor_ref.get_object()
                    if any(
                        descriptor.get(key) for key in ("/FontFile", "/FontFile2", "/FontFile3")
                    ):
                        embedded += 1
                        break
    return used, embedded


def active_content_counts(reader: PdfReader) -> tuple[int, int, int]:
    root = reader.trailer["/Root"].get_object()
    attachments = 0
    names_ref = root.get("/Names")
    if names_ref:
        names = names_ref.get_object()
        embedded = names.get("/EmbeddedFiles")
        if embedded:
            attachments = len(embedded.get_object().get("/Names", [])) // 2
        if names.get("/JavaScript"):
            raise RuntimeError("JavaScript name tree is present in generated PDF")
    if root.get("/OpenAction") or root.get("/AA"):
        raise RuntimeError("Automatic PDF action is present in generated PDF")
    annotations = 0
    for page in reader.pages:
        annotations += len(page.get("/Annots", []))
        if page.get("/AA"):
            raise RuntimeError("Automatic page action is present in generated PDF")
        for annotation_ref in page.get("/Annots", []):
            annotation = annotation_ref.get_object()
            action_ref = annotation.get("/A")
            if action_ref and action_ref.get_object().get("/S") == "/JavaScript":
                raise RuntimeError("JavaScript annotation is present in generated PDF")
    return annotations, attachments, int(bool(root.get("/OpenAction")))


def validate_pdf(source_pdf: Path, candidate_pdf: Path, target_name: str) -> str:
    original = PdfReader(source_pdf)
    candidate = PdfReader(candidate_pdf)
    if len(original.pages) != len(candidate.pages):
        raise RuntimeError(
            f"Page count changed for {target_name}: {len(original.pages)} -> {len(candidate.pages)}"
        )
    for page_number, (before, after) in enumerate(zip(original.pages, candidate.pages), start=1):
        old_box, new_box = before.mediabox, after.mediabox
        if any(abs(float(a) - float(b)) > 2 for a, b in zip(old_box, new_box)):
            raise RuntimeError(f"Page dimensions changed for {target_name}, page {page_number}")
    names = font_names(candidate)
    allowed_font_names = {"notosans", "notosanssymbols"}
    if not names or any(
        not any(allowed in name.lower().replace(" ", "") for allowed in allowed_font_names)
        for name in names
    ):
        raise RuntimeError(f"Non-Noto font found in {target_name}: {sorted(names)}")
    used, embedded = embedded_font_count(candidate)
    if used == 0 or embedded < used:
        raise RuntimeError(f"Not all used font resources are embedded in {target_name}")
    annotations, attachments, _ = active_content_counts(candidate)
    original_annotations, original_attachments, _ = active_content_counts(original)
    if attachments:
        raise RuntimeError(f"Unexpected embedded files in {target_name}")
    if attachments != original_attachments or annotations != original_annotations:
        raise RuntimeError(f"PDF annotations or attachments changed for {target_name}")
    text = normalized_text(candidate)
    if LOCAL_PATH.search(text):
        raise RuntimeError(f"Developer-machine path found in generated {target_name}")
    for key in ("/Author", "/Title", "/Subject"):
        prior = original.metadata.get(key) if original.metadata else None
        current = candidate.metadata.get(key) if candidate.metadata else None
        if prior and current and str(prior) != str(current):
            raise RuntimeError(f"PDF metadata field {key} changed for {target_name}")
    return (
        f"{target_name}: {len(candidate.pages)} pages; source text runs unchanged; "
        f"{used} font resources with embedded Noto Sans / Noto Sans Symbols; {annotations} annotations; "
        "no embedded files or automatic actions"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT,
        help="Directory to receive the verified PDFs (defaults to the project root).",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    soffice = shutil.which("soffice")
    fc_match = shutil.which("fc-match")
    if not soffice or not fc_match:
        raise RuntimeError("LibreOffice soffice and fc-match are required")
    libreoffice_version = subprocess.run(
        [soffice, "--version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    if "26.8.1.1" not in libreoffice_version:
        raise RuntimeError(f"Expected reviewed LibreOffice 26.8.1.1, found {libreoffice_version}")
    for source_name, target_name, _ in SOURCES:
        if not (ROOT / source_name).is_file() or not (ROOT / target_name).is_file():
            raise FileNotFoundError(f"Required source or baseline PDF is missing: {source_name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="drillloop-pdf-reexport-") as temp_name:
        temp = Path(temp_name)
        fonts = temp / "fonts"
        cache = temp / "font-cache"
        converted = temp / "converted"
        fonts.mkdir()
        cache.mkdir()
        converted.mkdir()
        font_path = fonts / "NotoSans-VF.ttf"
        symbols_font_path = fonts / "NotoSansSymbols-VF.ttf"
        download_verified(FONT_URL, font_path, FONT_SHA256)
        download_verified(LICENSE_URL, temp / "Noto-Sans-OFL.txt", LICENSE_SHA256)
        download_verified(SYMBOLS_FONT_URL, symbols_font_path, SYMBOLS_FONT_SHA256)
        download_verified(
            SYMBOLS_LICENSE_URL, temp / "Noto-Sans-Symbols-OFL.txt", SYMBOLS_LICENSE_SHA256
        )
        config = fontconfig_file(fonts, cache, temp)
        environment = os.environ.copy()
        environment["FONTCONFIG_FILE"] = str(config)
        matched = subprocess.run(
            [fc_match, "-f", "%{file}", "Noto Sans"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        if Path(matched).resolve() != font_path.resolve():
            raise RuntimeError("Fontconfig did not resolve to the pinned Noto Sans font")
        symbols_match = subprocess.run(
            [fc_match, "-f", "%{file}", "Noto Sans Symbols"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout.strip()
        if Path(symbols_match).resolve() != symbols_font_path.resolve():
            raise RuntimeError("Fontconfig did not resolve to the pinned Noto Sans Symbols font")

        candidates: list[tuple[Path, Path, str]] = []
        for index, (source_name, target_name, source_type) in enumerate(SOURCES):
            source = ROOT / source_name
            patched_source = temp / f"source-{index}-{source.name}"
            if source_type == "office":
                patch_office_fonts(source, patched_source)
            else:
                patch_svg_fonts(source, patched_source)
            profile = (temp / f"lo-profile-{index}").as_uri()
            subprocess.run(
                [
                    soffice,
                    "--headless",
                    f"-env:UserInstallation={profile}",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(converted),
                    str(patched_source),
                ],
                check=True,
                capture_output=True,
                text=True,
                env=environment,
            )
            candidate = converted / f"{patched_source.stem}.pdf"
            if not candidate.is_file():
                raise RuntimeError(f"LibreOffice did not produce {candidate.name}")
            report = validate_pdf(ROOT / target_name, candidate, target_name)
            candidates.append((candidate, output_dir / target_name, report))

        for source, destination, _ in candidates:
            shutil.copyfile(source, destination)
        for _, _, report in candidates:
            print(report)
        print(
            f"Fonts: Noto Sans and Noto Sans Symbols, Google Fonts revision {FONT_REVISION}, SIL OFL 1.1"
        )
        print(f"Renderer: {libreoffice_version}")
        print(
            f"Noto Sans SHA-256: {FONT_SHA256}; OFL SHA-256: {LICENSE_SHA256}; "
            f"Symbols SHA-256: {SYMBOLS_FONT_SHA256}; "
            f"Symbols OFL SHA-256: {SYMBOLS_LICENSE_SHA256}"
        )
        print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
