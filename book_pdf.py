#!/usr/bin/env python3
# coding: utf-8
import os
import pathlib
import re
import sys
from io import BytesIO

from lxml import etree


KNOWN_PDF_ONLY_BOOKS = {
    "9781633436541": (
        "contains many oversized figures and wide tables that are clipped in common EPUB readers"
    ),
}

WIDE_IMAGE_WIDTH_THRESHOLD = 900
WIDE_IMAGE_COUNT_THRESHOLD = 6
WIDE_TABLE_COUNT_THRESHOLD = 2

FRONT_MATTER_ORDER = [
    "default_cover.xhtml",
    "cover.xhtml",
    "titlepage.xhtml",
    "title.xhtml",
    "copyright.xhtml",
    "dedication.xhtml",
    "contents.xhtml",
    "toc.xhtml",
]


def _is_content_document(file_name):
    return file_name.endswith((".xhtml", ".html"))


def _alternate_doc_name(file_name):
    base_name, extension = os.path.splitext(file_name)
    return base_name + (".html" if extension == ".xhtml" else ".xhtml")


class PdfProfile:
    def __init__(
        self,
        mode="reflowable",
        should_auto_pdf=False,
        reason="",
        viewport=(0, 0),
        wide_image_count=0,
        wide_table_count=0,
        largest_image_width=0,
    ):
        self.mode = mode
        self.should_auto_pdf = should_auto_pdf
        self.reason = reason
        self.viewport = viewport
        self.wide_image_count = wide_image_count
        self.wide_table_count = wide_table_count
        self.largest_image_width = largest_image_width


def _normalize_book_path(book_path):
    book_path = os.path.abspath(book_path)
    if os.path.basename(book_path).lower() == "oebps":
        return os.path.dirname(book_path)
    return book_path


def _get_oebps_path(book_path):
    book_path = _normalize_book_path(book_path)
    oebps_path = os.path.join(book_path, "OEBPS")
    return oebps_path if os.path.isdir(oebps_path) else book_path


def extract_book_id(book_path):
    match = re.search(r"\((\d+)\)\s*$", os.path.basename(_normalize_book_path(book_path)))
    return match.group(1) if match else ""


def resolve_book_path(target, workspace_root=None):
    if os.path.isdir(target):
        return os.path.abspath(target)

    if workspace_root is None:
        workspace_root = os.path.dirname(os.path.realpath(__file__))

    books_dir = os.path.join(workspace_root, "Books")
    if not os.path.isdir(books_dir):
        return ""

    for entry in os.listdir(books_dir):
        if entry.endswith("({0})".format(target)):
            candidate = os.path.join(books_dir, entry)
            if os.path.isdir(candidate):
                return candidate

    return ""


def _read_text(file_path):
    return open(file_path, encoding="utf-8", errors="replace").read()


def _set_progress_state(display, value):
    if display is None or not hasattr(display, "state_status"):
        return
    try:
        display.state_status.value = value
    except Exception:
        pass


def _info(display, message, state=False):
    if display is not None and hasattr(display, "info"):
        display.info(message, state=state)
    else:
        print(message)


def _error(display, message):
    if display is not None and hasattr(display, "error"):
        display.error(message)
    else:
        print(message, file=sys.stderr)


def _progress(display, total, done):
    if display is not None and hasattr(display, "state"):
        display.state(total, done)


def _detect_fixed_layout(book_path):
    styles_path = os.path.join(_get_oebps_path(book_path), "Styles")
    if not os.path.isdir(styles_path):
        return False, 0, 0

    for css_name in sorted(os.listdir(styles_path)):
        css_path = os.path.join(styles_path, css_name)
        try:
            content = _read_text(css_path)
        except Exception:
            continue

        if "position:absolute" in content and "overflow:hidden" in content:
            match = re.search(r"width:(\d+)px;height:(\d+)px", content)
            if match:
                return True, int(match.group(1)), int(match.group(2))

    return False, 0, 0


def _natural_sort_key(text):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def _file_order_key(file_name):
    if file_name in FRONT_MATTER_ORDER:
        return (0, FRONT_MATTER_ORDER.index(file_name), file_name)
    if file_name.startswith("part-"):
        return (1, _natural_sort_key(file_name), file_name)
    if file_name.startswith("chapter-"):
        return (2, _natural_sort_key(file_name), file_name)
    if file_name.startswith("appendix-"):
        return (3, _natural_sort_key(file_name), file_name)
    if file_name == "index.xhtml":
        return (4, 0, file_name)
    return (5, _natural_sort_key(file_name), file_name)


def _resolve_href_file_name(href, available_names, current_name=None):
    href = (href or "").strip()
    if not href or href.startswith(("http://", "https://", "mailto:", "javascript:")):
        return "", ""

    if href.startswith("#"):
        return current_name or "", href[1:]

    path, fragment = href.split("#", 1) if "#" in href else (href, "")
    if not path:
        return current_name or "", fragment

    file_name = os.path.basename(path)
    if file_name in available_names:
        return file_name, fragment

    alt_name = os.path.splitext(file_name)[0] + ".xhtml"
    if alt_name in available_names:
        return alt_name, fragment

    alt_name = os.path.splitext(file_name)[0] + ".html"
    if alt_name in available_names:
        return alt_name, fragment

    return "", ""


def _infer_xhtml_reading_order(oebps_path):
    available_paths = {}
    for entry in os.listdir(oebps_path):
        if _is_content_document(entry):
            chapter_path = os.path.join(oebps_path, entry)
            if os.path.isfile(chapter_path):
                available_paths[entry] = chapter_path

    if not available_paths:
        return []

    ordered_names = []
    seen = set()

    def add_name(file_name):
        resolved_name = file_name if file_name in available_paths else _alternate_doc_name(file_name)
        if resolved_name in available_paths and resolved_name not in seen:
            ordered_names.append(resolved_name)
            seen.add(resolved_name)

    for file_name in FRONT_MATTER_ORDER:
        add_name(file_name)

    contents_path = available_paths.get("contents.xhtml") or available_paths.get("toc.xhtml")
    if contents_path:
        try:
            contents_tree = etree.parse(contents_path)
            for link in contents_tree.xpath("//*[local-name()='a' and @href]"):
                file_name, _ = _resolve_href_file_name(link.get("href", ""), available_paths, "contents.xhtml")
                if file_name:
                    add_name(file_name)
        except Exception:
            pass

    for file_name in sorted(available_paths, key=_file_order_key):
        add_name(file_name)

    return [available_paths[file_name] for file_name in ordered_names]


def _augment_spine_order(file_paths, oebps_path):
    available_paths = {}
    for entry in os.listdir(oebps_path):
        if _is_content_document(entry):
            chapter_path = os.path.join(oebps_path, entry)
            if os.path.isfile(chapter_path):
                available_paths[entry] = chapter_path

    ordered_names = []
    seen = set()

    def add_name(file_name):
        resolved_name = file_name if file_name in available_paths else _alternate_doc_name(file_name)
        if resolved_name in available_paths and resolved_name not in seen:
            ordered_names.append(resolved_name)
            seen.add(resolved_name)

    for file_name in FRONT_MATTER_ORDER:
        add_name(file_name)

    for file_path in file_paths:
        add_name(os.path.basename(file_path))

    return [available_paths[file_name] for file_name in ordered_names]


def _make_doc_anchor(file_name):
    anchor = re.sub(r"[^a-zA-Z0-9]+", "-", os.path.splitext(file_name)[0]).strip("-").lower()
    return "doc-" + (anchor or "page")


def _prefix_body_ids(body_node, doc_anchor):
    if body_node.get("id"):
        body_node.set("id", "{0}__{1}".format(doc_anchor, body_node.get("id")))

    for node in body_node.xpath(".//*[@id]"):
        node.set("id", "{0}__{1}".format(doc_anchor, node.get("id")))


def _rewrite_internal_links(body_node, current_name, file_anchor_map):
    available_names = set(file_anchor_map)
    current_anchor = file_anchor_map.get(current_name, "")

    for node in body_node.xpath(".//*[@href]"):
        target_name, fragment = _resolve_href_file_name(node.get("href", ""), available_names, current_name)
        if not target_name:
            continue

        target_anchor = file_anchor_map.get(target_name, "")
        if not target_anchor:
            continue

        if fragment:
            if target_name == current_name:
                node.set("href", "#{0}__{1}".format(current_anchor, fragment))
            else:
                node.set("href", "#{0}__{1}".format(target_anchor, fragment))
        else:
            node.set("href", "#{0}".format(target_anchor))


def _get_spine_xhtml_files(book_path):
    oebps_path = _get_oebps_path(book_path)
    opf_path = os.path.join(oebps_path, "content.opf")
    files = []
    seen = set()

    if os.path.isfile(opf_path):
        try:
            opf_tree = etree.parse(opf_path)
            manifest = {}
            for item in opf_tree.xpath("//*[local-name()='manifest']/*[local-name()='item']"):
                item_id = item.get("id", "")
                href = item.get("href", "")
                if item_id and href:
                    manifest[item_id] = href

            for itemref in opf_tree.xpath("//*[local-name()='spine']/*[local-name()='itemref']"):
                href = manifest.get(itemref.get("idref", ""), "")
                if not href or not href.endswith((".xhtml", ".html")):
                    continue

                rel_path = os.path.normpath(href.replace("/", os.sep))
                chapter_path = os.path.join(oebps_path, rel_path)
                if os.path.isfile(chapter_path) and chapter_path not in seen:
                    files.append(chapter_path)
                    seen.add(chapter_path)
        except Exception:
            files = []

    if files:
        return _augment_spine_order(files, oebps_path)

    return _infer_xhtml_reading_order(oebps_path)


def _scan_wide_visual_content(book_path):
    wide_image_count = 0
    wide_table_count = 0
    largest_image_width = 0

    for xhtml_path in _get_spine_xhtml_files(book_path):
        try:
            content = _read_text(xhtml_path)
        except Exception:
            continue

        for width_text in re.findall(r"<img[^>]*\bwidth=\"(\d+)\"", content, re.IGNORECASE):
            width = int(width_text)
            largest_image_width = max(largest_image_width, width)
            if width >= WIDE_IMAGE_WIDTH_THRESHOLD:
                wide_image_count += 1

        wide_table_count += len(
            re.findall(r"(?:browsable-table-container|framemaker-table-container)", content, re.IGNORECASE)
        )

    return wide_image_count, wide_table_count, largest_image_width


def analyze_book_layout(book_path, book_id=None):
    book_path = _normalize_book_path(book_path)
    book_id = book_id or extract_book_id(book_path)

    is_fixed_layout, viewport_w, viewport_h = _detect_fixed_layout(book_path)
    if is_fixed_layout:
        return PdfProfile(
            mode="fixed-layout",
            should_auto_pdf=True,
            reason="fixed-layout pages rely on browser rendering for compatibility",
            viewport=(viewport_w, viewport_h),
        )

    wide_image_count, wide_table_count, largest_image_width = _scan_wide_visual_content(book_path)
    reason = ""

    if book_id in KNOWN_PDF_ONLY_BOOKS:
        reason = KNOWN_PDF_ONLY_BOOKS[book_id]
    elif wide_image_count >= WIDE_IMAGE_COUNT_THRESHOLD and wide_table_count >= 1:
        reason = "contains many oversized figures that are likely to be clipped in EPUB readers"
    elif largest_image_width >= 1000 and wide_table_count >= WIDE_TABLE_COUNT_THRESHOLD:
        reason = "contains wide figures and tables that render more reliably as PDF"

    return PdfProfile(
        mode="wide-visuals" if reason else "reflowable",
        should_auto_pdf=bool(reason),
        reason=reason,
        wide_image_count=wide_image_count,
        wide_table_count=wide_table_count,
        largest_image_width=largest_image_width,
    )


def _build_combined_pdf_source(book_path, xhtml_files):
    oebps_path = _get_oebps_path(book_path)
    source_path = os.path.join(oebps_path, "_pdf_source.xhtml")
    head_chunks = []
    seen_head_chunks = set()
    body_chunks = []
    file_anchor_map = {
        os.path.basename(xhtml_path): _make_doc_anchor(os.path.basename(xhtml_path))
        for xhtml_path in xhtml_files
    }

    for xhtml_path in xhtml_files:
        file_name = os.path.basename(xhtml_path)
        doc_anchor = file_anchor_map[file_name]
        try:
            document = etree.parse(xhtml_path)
        except Exception:
            continue

        head_nodes = document.xpath("//*[local-name()='head']")
        if head_nodes:
            for child in head_nodes[0]:
                if not isinstance(child.tag, str):
                    continue
                local_name = etree.QName(child).localname.lower()
                if local_name not in {"link", "style"}:
                    continue
                serialized = etree.tostring(child, encoding="unicode", method="xml")
                if serialized not in seen_head_chunks:
                    head_chunks.append(serialized)
                    seen_head_chunks.add(serialized)

        body_nodes = document.xpath("//*[local-name()='body']")
        if not body_nodes:
            continue

        body_node = body_nodes[0]
        _prefix_body_ids(body_node, doc_anchor)
        _rewrite_internal_links(body_node, file_name, file_anchor_map)

        body_parts = []
        if body_node.text and body_node.text.strip():
            body_parts.append(body_node.text)

        for child in body_node:
            body_parts.append(etree.tostring(child, encoding="unicode", method="xml"))

        if body_parts:
            body_chunks.append(
                "<section class=\"pdf-chapter\" id=\"{0}\">{1}</section>".format(
                    doc_anchor,
                    "\n".join(body_parts),
                )
            )

    override_css = """
<style>
@page { size: A4; margin: 12mm 10mm; }
html, body { margin: 0; padding: 0; background: #fff; }
body { overflow: visible !important; }
.pdf-chapter { break-before: page; page-break-before: always; }
.pdf-chapter:first-child { break-before: auto; page-break-before: auto; }
img, svg, canvas, video, object, embed {
    max-width: 100% !important;
    width: auto !important;
    height: auto !important;
}
.browsable-container,
.figure-container,
.browsable-table-container,
.framemaker-table-container,
.listing-container,
.code-area-container {
    max-width: 100% !important;
    width: auto !important;
    overflow: visible !important;
    box-sizing: border-box !important;
}
.browsable-container.figure-container > img,
.browsable-container img {
    max-width: 100% !important;
    width: auto !important;
    height: auto !important;
}
table {
    max-width: 100% !important;
    width: auto !important;
    table-layout: auto !important;
    font-size: 0.92em !important;
}
pre, code {
    white-space: pre-wrap !important;
    word-break: break-word !important;
    overflow-wrap: anywhere !important;
}
</style>
"""

    preview_html = "<!DOCTYPE html>\n" \
                   "<html lang=\"en\" xmlns=\"http://www.w3.org/1999/xhtml\">\n" \
                   "<head>\n<meta charset=\"utf-8\" />\n{0}\n{1}\n</head>\n" \
                   "<body>\n{2}\n</body>\n</html>".format(
                        "\n".join(head_chunks), override_css, "\n".join(body_chunks)
                    )

    with open(source_path, "wb") as source_file:
        source_file.write(preview_html.encode("utf-8", "xmlcharrefreplace"))

    return source_path


def _render_fixed_layout_pdf(book_path, output_path, profile, display=None):
    try:
        import asyncio
        from PIL import Image
        from playwright.async_api import async_playwright
    except ImportError as import_error:
        _error(
            display,
            "PDF render skipped: install optional dependencies `Pillow` and `playwright`, "
            "then run `playwright install chromium` ({0}).".format(import_error),
        )
        return ""

    viewport_w, viewport_h = profile.viewport
    if not viewport_w or not viewport_h:
        _error(display, "Fixed-layout PDF render skipped: viewport dimensions were not detected.")
        return ""

    xhtml_files = _get_spine_xhtml_files(book_path)
    if not xhtml_files:
        _error(display, "Fixed-layout PDF render skipped: no XHTML pages were found in the spine.")
        return ""

    _info(display, "Rendering fixed-layout PDF page by page for compatibility.", state=True)

    async def _capture_pages():
        screenshots = []
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(
                viewport={"width": viewport_w, "height": viewport_h},
                device_scale_factor=2,
            )

            _set_progress_state(display, -1)
            total = len(xhtml_files)
            for index, xhtml_path in enumerate(xhtml_files, 1):
                await page.goto(pathlib.Path(xhtml_path).as_uri(), wait_until="networkidle")
                try:
                    await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve(true)")
                except Exception:
                    pass
                try:
                    await page.wait_for_function(
                        "Array.from(document.images).every((img) => img.complete)", timeout=10000
                    )
                except Exception:
                    pass

                screenshot = await page.screenshot(
                    clip={"x": 0, "y": 0, "width": viewport_w, "height": viewport_h}
                )
                screenshots.append(screenshot)
                _progress(display, total, index)

            await browser.close()

        return screenshots

    try:
        screenshots = asyncio.run(_capture_pages())
    except Exception as render_error:
        _error(display, "Fixed-layout PDF render failed: {0}".format(render_error))
        return ""

    if not screenshots:
        _error(display, "Fixed-layout PDF render failed: no pages were captured.")
        return ""

    images = []
    try:
        for screenshot in screenshots:
            images.append(Image.open(BytesIO(screenshot)).convert("RGB"))

        images[0].save(output_path, save_all=True, append_images=images[1:])
    except Exception as save_error:
        _error(display, "Fixed-layout PDF build failed: {0}".format(save_error))
        return ""
    finally:
        for image in images:
            try:
                image.close()
            except Exception:
                pass

    return output_path


def _render_reflowable_pdf(book_path, output_path, display=None):
    try:
        import asyncio
        from playwright.async_api import async_playwright
    except ImportError as import_error:
        _error(
            display,
            "PDF render skipped: install optional dependency `playwright`, then run "
            "`playwright install chromium` ({0}).".format(import_error),
        )
        return ""

    xhtml_files = _get_spine_xhtml_files(book_path)
    if not xhtml_files:
        _error(display, "PDF render skipped: no XHTML pages were found in the spine.")
        return ""

    source_path = _build_combined_pdf_source(book_path, xhtml_files)
    _info(display, "Rendering PDF from downloaded XHTML content.", state=True)

    async def _print_pdf():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            page = await browser.new_page(viewport={"width": 1400, "height": 1800})
            await page.goto(pathlib.Path(source_path).as_uri(), wait_until="networkidle")

            try:
                await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve(true)")
            except Exception:
                pass
            try:
                await page.wait_for_function(
                    "Array.from(document.images).every((img) => img.complete)", timeout=10000
                )
            except Exception:
                pass

            await page.emulate_media(media="screen")
            await page.pdf(
                path=output_path,
                format="A4",
                print_background=True,
                margin={"top": "12mm", "right": "10mm", "bottom": "12mm", "left": "10mm"},
                scale=0.95,
            )
            await browser.close()

    try:
        asyncio.run(_print_pdf())
    except Exception as render_error:
        _error(display, "PDF render failed: {0}".format(render_error))
        return ""
    finally:
        if os.path.isfile(source_path):
            os.remove(source_path)

    return output_path


def render_book_to_pdf(book_path, output_path=None, profile=None, display=None):
    book_path = _normalize_book_path(book_path)
    book_id = extract_book_id(book_path)
    profile = profile or analyze_book_layout(book_path, book_id)
    output_path = output_path or os.path.join(book_path, "{0}.pdf".format(book_id or "book"))

    if profile.mode == "fixed-layout":
        rendered_path = _render_fixed_layout_pdf(book_path, output_path, profile, display=display)
    else:
        rendered_path = _render_reflowable_pdf(book_path, output_path, display=display)

    if rendered_path:
        _info(display, "Created PDF: {0}".format(rendered_path), state=True)

    return rendered_path
