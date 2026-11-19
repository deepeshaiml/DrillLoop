from __future__ import annotations

import io
import math
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

OCR_DPI = 200
OCR_MAX_PAGE_PIXELS = 12_000_000
OCR_PAGE_TIMEOUT_SECONDS = 4
OCR_MAX_PAGE_IMAGE_OBJECTS = 64
OCR_MAX_PAGE_IMAGE_REGIONS = 8
OCR_IMAGE_REGION_PADDING_POINTS = 2


class PdfOcrError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 422):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class PdfOcrRuntime:
    command: str
    engine_version: str
    renderer_version: str


@dataclass(frozen=True)
class PdfOcrRegionsResult:
    text: str
    duration_seconds: float
    attempted_regions: int
    omitted_regions: int
    issues: tuple[tuple[str, str], ...] = ()


def check_pdf_ocr_runtime() -> tuple[PdfOcrRuntime, object]:
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:
        raise PdfOcrError(
            "OCR_UNAVAILABLE",
            "Scanned PDF extraction is unavailable because the PDF renderer is not installed.",
            503,
        ) from exc

    tesseract = shutil.which("tesseract")
    if not tesseract:
        raise PdfOcrError(
            "OCR_UNAVAILABLE",
            "Scanned PDF extraction is unavailable because Tesseract is not installed.",
            503,
        )
    try:
        version_result = subprocess.run(
            [tesseract, "--version"], capture_output=True, timeout=2, check=False
        )
        languages_result = subprocess.run(
            [tesseract, "--list-langs"], capture_output=True, timeout=2, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PdfOcrError("OCR_UNAVAILABLE", "Tesseract did not become ready.", 503) from exc
    version_output = version_result.stdout.decode("utf-8", errors="replace")
    language_output = languages_result.stdout.decode("utf-8", errors="replace")
    if version_result.returncode != 0 or languages_result.returncode != 0:
        raise PdfOcrError("OCR_UNAVAILABLE", "Tesseract is not ready for OCR.", 503)
    if "eng" not in language_output.split():
        raise PdfOcrError(
            "OCR_LANGUAGE_UNAVAILABLE",
            "English OCR data is not installed; the PDF was not imported.",
            503,
        )
    engine_version = next(
        (line.strip() for line in version_output.splitlines() if line.startswith("tesseract ")),
        "tesseract version unknown",
    )
    try:
        renderer_version = version("pypdfium2")
    except PackageNotFoundError:
        renderer_version = "unknown"
    return PdfOcrRuntime(tesseract, engine_version, renderer_version), pdfium


def ocr_pdf_page(
    document, page_index: int, runtime: PdfOcrRuntime
) -> tuple[str, float, tuple[int, ...]]:
    page_number = page_index + 1
    page = None
    bitmap = None
    image = None
    try:
        page = document[page_index]
        width_points, height_points = page.get_size()
        width_pixels = math.ceil(width_points * OCR_DPI / 72)
        height_pixels = math.ceil(height_points * OCR_DPI / 72)
        if width_pixels * height_pixels > OCR_MAX_PAGE_PIXELS:
            raise PdfOcrError(
                "OCR_PAGE_TOO_LARGE",
                f"PDF page {page_number} exceeds the {OCR_MAX_PAGE_PIXELS:,}-pixel OCR limit at {OCR_DPI} DPI.",
                413,
            )
        bitmap = page.render(scale=OCR_DPI / 72)
        image = bitmap.to_pil()
        image_bytes = io.BytesIO()
        image.save(image_bytes, format="PNG", optimize=False)
    except PdfOcrError:
        raise
    except Exception as exc:
        raise PdfOcrError(
            "OCR_RENDER_FAILED", f"Could not render PDF page {page_number} for OCR."
        ) from exc
    finally:
        if image is not None:
            image.close()
        if bitmap is not None:
            bitmap.close()
        if page is not None:
            page.close()

    started = time.perf_counter()
    deadline = started + OCR_PAGE_TIMEOUT_SECONDS
    segmentation_modes = [6]
    try:
        result = subprocess.run(
            [runtime.command, "stdin", "stdout", "-l", "eng", "--psm", "6"],
            input=image_bytes.getvalue(),
            capture_output=True,
            timeout=max(0.01, deadline - time.perf_counter()),
            check=False,
            env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
        )
    except subprocess.TimeoutExpired as exc:
        raise PdfOcrError(
            "OCR_TIMEOUT",
            f"OCR exceeded the {OCR_PAGE_TIMEOUT_SECONDS}-second limit on page {page_number}.",
        ) from exc
    except OSError as exc:
        raise PdfOcrError("OCR_UNAVAILABLE", "Tesseract could not be started.", 503) from exc
    if result.returncode != 0:
        raise PdfOcrError("OCR_FAILED", f"OCR could not process PDF page {page_number}.")
    text = result.stdout.decode("utf-8", errors="replace").strip()
    if any(
        len(re.findall(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", line)) > 1 for line in text.splitlines()
    ):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise PdfOcrError(
                "OCR_TIMEOUT",
                f"OCR exceeded the {OCR_PAGE_TIMEOUT_SECONDS}-second limit on page {page_number}.",
            )
        try:
            retry = subprocess.run(
                [runtime.command, "stdin", "stdout", "-l", "eng", "--psm", "3"],
                input=image_bytes.getvalue(),
                capture_output=True,
                timeout=remaining,
                check=False,
                env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
            )
        except subprocess.TimeoutExpired as exc:
            raise PdfOcrError(
                "OCR_TIMEOUT",
                f"OCR exceeded the {OCR_PAGE_TIMEOUT_SECONDS}-second limit on page {page_number}.",
            ) from exc
        except OSError as exc:
            raise PdfOcrError("OCR_UNAVAILABLE", "Tesseract could not be started.", 503) from exc
        if retry.returncode != 0:
            raise PdfOcrError("OCR_FAILED", f"OCR could not process PDF page {page_number}.")
        text = retry.stdout.decode("utf-8", errors="replace").strip()
        segmentation_modes.append(3)
    return text, time.perf_counter() - started, tuple(segmentation_modes)


def ocr_pdf_image_regions(document, page_index: int, runtime: PdfOcrRuntime) -> PdfOcrRegionsResult:
    """OCR visible embedded image regions on a page that also has native text.

    Each crop is rendered directly from the original PDF page. This keeps hidden or
    covered image-object text from becoming evidence and bounds raster work to the
    image rectangles instead of OCRing the selectable-text page as a whole.
    """
    page_number = page_index + 1
    page = None
    objects = []
    issues: list[tuple[str, str]] = []
    try:
        import pypdfium2 as pdfium

        page = document[page_index]
        page_width, page_height = page.get_size()
        object_iterator = page.get_objects(filter=[pdfium.raw.FPDF_PAGEOBJ_IMAGE])
        rectangles = []
        overflow = False
        for image_object in object_iterator:
            objects.append(image_object)
            if len(objects) > OCR_MAX_PAGE_IMAGE_OBJECTS:
                overflow = True
                break
            try:
                x0, y0, x1, y1 = image_object.get_bounds()
            except Exception:
                issues.append(
                    (
                        "OCR_IMAGE_BOUNDS_UNAVAILABLE",
                        f"Some embedded images on page {page_number} could not be located; review the original page.",
                    )
                )
                continue
            x0 = max(0.0, min(float(x0), page_width))
            y0 = max(0.0, min(float(y0), page_height))
            x1 = max(0.0, min(float(x1), page_width))
            y1 = max(0.0, min(float(y1), page_height))
            if x1 <= x0 or y1 <= y0:
                continue
            rectangles.append((x0, y0, x1, y1))

        if overflow:
            issues.append(
                (
                    "OCR_IMAGE_OBJECT_LIMIT",
                    f"Page {page_number} contains more than {OCR_MAX_PAGE_IMAGE_OBJECTS} embedded images; some areas were not OCR processed.",
                )
            )
        regions = _merge_image_rectangles(rectangles)
        regions.sort(key=lambda rect: (-rect[3], rect[0]))
        omitted_regions = max(0, len(regions) - OCR_MAX_PAGE_IMAGE_REGIONS)
        if omitted_regions:
            issues.append(
                (
                    "OCR_IMAGE_REGION_LIMIT",
                    f"Page {page_number} has more than {OCR_MAX_PAGE_IMAGE_REGIONS} separate image areas; some were not OCR processed.",
                )
            )
        regions = regions[:OCR_MAX_PAGE_IMAGE_REGIONS]

        started = time.perf_counter()
        deadline = started + OCR_PAGE_TIMEOUT_SECONDS
        texts = []
        attempted_regions = 0
        for x0, y0, x1, y1 in regions:
            padding = OCR_IMAGE_REGION_PADDING_POINTS
            left = max(0.0, x0 - padding)
            bottom = max(0.0, y0 - padding)
            right = min(page_width, x1 + padding)
            top = min(page_height, y1 + padding)
            crop = (left, bottom, page_width - right, page_height - top)
            bitmap = None
            image = None
            try:
                crop_width_pixels = math.ceil((right - left) * OCR_DPI / 72)
                crop_height_pixels = math.ceil((top - bottom) * OCR_DPI / 72)
                if crop_width_pixels * crop_height_pixels > OCR_MAX_PAGE_PIXELS:
                    raise PdfOcrError(
                        "OCR_PAGE_TOO_LARGE",
                        f"An embedded image area on page {page_number} exceeds the OCR pixel limit.",
                        413,
                    )
                bitmap = page.render(
                    scale=OCR_DPI / 72,
                    crop=crop,
                    grayscale=True,
                    limit_image_cache=True,
                )
                image = bitmap.to_pil()
                image_bytes = io.BytesIO()
                image.save(image_bytes, format="PNG", optimize=False)
            except PdfOcrError as exc:
                issues.append((exc.code, exc.message))
                continue
            except Exception:
                issues.append(
                    (
                        "OCR_RENDER_FAILED",
                        f"An embedded image area on page {page_number} could not be rendered; review the original page.",
                    )
                )
                continue
            finally:
                if image is not None:
                    image.close()
                if bitmap is not None:
                    bitmap.close()

            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                issues.append(
                    (
                        "OCR_TIMEOUT",
                        f"Image OCR exceeded the {OCR_PAGE_TIMEOUT_SECONDS}-second page limit on page {page_number}.",
                    )
                )
                break
            attempted_regions += 1
            try:
                result = subprocess.run(
                    [runtime.command, "stdin", "stdout", "-l", "eng", "--psm", "6"],
                    input=image_bytes.getvalue(),
                    capture_output=True,
                    timeout=remaining,
                    check=False,
                    env={**os.environ, "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1"},
                )
            except subprocess.TimeoutExpired:
                issues.append(
                    (
                        "OCR_TIMEOUT",
                        f"Image OCR exceeded the {OCR_PAGE_TIMEOUT_SECONDS}-second page limit on page {page_number}.",
                    )
                )
                break
            except OSError:
                issues.append(("OCR_UNAVAILABLE", "Tesseract could not be started."))
                break
            if result.returncode != 0:
                issues.append(
                    (
                        "OCR_FAILED",
                        f"OCR could not process an embedded image on page {page_number}.",
                    )
                )
                continue
            recognized = result.stdout.decode("utf-8", errors="replace").strip()
            if recognized:
                texts.append(recognized)

        return PdfOcrRegionsResult(
            text="\n".join(texts),
            duration_seconds=time.perf_counter() - started,
            attempted_regions=attempted_regions,
            omitted_regions=omitted_regions + int(overflow),
            issues=tuple(issues),
        )
    except PdfOcrError:
        raise
    except Exception as exc:
        raise PdfOcrError(
            "OCR_IMAGE_INSPECTION_FAILED",
            f"Could not inspect embedded images on PDF page {page_number}.",
        ) from exc
    finally:
        for image_object in objects:
            try:
                image_object.close()
            except Exception:
                pass
        if page is not None:
            page.close()


def _merge_image_rectangles(
    rectangles: list[tuple[float, float, float, float]],
) -> list[tuple[float, float, float, float]]:
    """Combine overlapping or closely tiled image objects into bounded OCR areas."""
    merged: list[tuple[float, float, float, float]] = []
    for rectangle in rectangles:
        x0, y0, x1, y1 = rectangle
        index = 0
        while index < len(merged):
            other_x0, other_y0, other_x1, other_y1 = merged[index]
            if (
                x0 <= other_x1 + 2
                and x1 >= other_x0 - 2
                and y0 <= other_y1 + 2
                and y1 >= other_y0 - 2
            ):
                x0 = min(x0, other_x0)
                y0 = min(y0, other_y0)
                x1 = max(x1, other_x1)
                y1 = max(y1, other_y1)
                merged.pop(index)
                index = 0
                continue
            index += 1
        merged.append((x0, y0, x1, y1))
    return merged
