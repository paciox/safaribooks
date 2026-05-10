#!/usr/bin/env python3
# coding: utf-8
import argparse
import os
import re
import shutil
import sys
import tempfile
import zipfile
from xml.etree import ElementTree

from book_pdf import analyze_book_layout, render_book_to_pdf, resolve_book_path


class _ConsoleState:
    def __init__(self):
        self.value = 0


class ConsoleDisplay:
    def __init__(self):
        self.state_status = _ConsoleState()

    def info(self, message, state=False):
        prefix = "[-]" if state else "[*]"
        print("%s %s" % (prefix, message))

    def error(self, message):
        print("[#] %s" % message, file=sys.stderr)

    def state(self, origin, done):
        if origin:
            print("    %s%%" % int(done * 100 / origin))


def _split_targets(raw_targets):
    targets = []
    for raw_target in raw_targets:
        targets.extend([target.strip() for target in raw_target.split(",") if target.strip()])
    return targets


def _is_epub_target(target):
    return os.path.isfile(target) and target.lower().endswith(".epub")


def _extract_book_id_from_name(target):
    match = re.search(r"(\d{10,13})", os.path.basename(target))
    return match.group(1) if match else None


def _normalize_targets_and_output(raw_targets, explicit_output):
    targets = _split_targets(raw_targets)
    output_path = explicit_output

    if not output_path and len(targets) == 2 and targets[0].lower().endswith(".epub") and targets[1].lower().endswith(".pdf"):
        output_path = targets[1]
        targets = [targets[0]]

    return targets, output_path


def _find_extracted_book_path(extract_dir):
    container_path = os.path.join(extract_dir, "META-INF", "container.xml")
    if os.path.isfile(container_path):
        try:
            container_tree = ElementTree.parse(container_path)
            rootfile = container_tree.find(".//{*}rootfile")
            if rootfile is not None:
                full_path = rootfile.attrib.get("full-path", "")
                if full_path:
                    opf_path = os.path.join(extract_dir, full_path.replace("/", os.sep))
                    if os.path.isfile(opf_path):
                        return os.path.dirname(opf_path)
        except Exception:
            pass

    oebps_path = os.path.join(extract_dir, "OEBPS")
    if os.path.isdir(oebps_path):
        return extract_dir

    for root, _, files in os.walk(extract_dir):
        if any(file_name.endswith((".xhtml", ".html")) for file_name in files):
            return root

    return extract_dir


def _extract_epub_target(epub_path):
    extract_dir = tempfile.mkdtemp(prefix="safaribooks_epub_")
    with zipfile.ZipFile(epub_path) as epub_archive:
        epub_archive.extractall(extract_dir)
    return _find_extracted_book_path(extract_dir), extract_dir


def _default_output_path(target, explicit_output, single_target):
    if single_target and explicit_output:
        return explicit_output
    if _is_epub_target(target):
        return os.path.splitext(os.path.abspath(target))[0] + ".pdf"
    return None


if __name__ == "__main__":
    arguments = argparse.ArgumentParser(
        prog="convert_to_pdf.py",
        description="Convert an already-downloaded Safari/O'Reilly book folder or EPUB file to PDF.",
        allow_abbrev=False,
    )
    arguments.add_argument(
        "targets",
        nargs="+",
        help="One or more downloaded book folders, EPUB files, or book IDs. Comma-separated values are supported.",
    )
    arguments.add_argument(
        "--output",
        help="Output PDF path. Valid only when converting a single target. For a single EPUB you can also use: convert_to_pdf.py input.epub output.pdf",
    )

    args_parsed = arguments.parse_args()
    targets, resolved_output = _normalize_targets_and_output(args_parsed.targets, args_parsed.output)
    if resolved_output and len(targets) != 1:
        arguments.error("`--output` can be used only when converting a single target.")

    workspace_root = os.path.dirname(os.path.realpath(__file__))
    display = ConsoleDisplay()
    failures = []

    for target in targets:
        cleanup_dir = ""
        book_id = None

        try:
            if _is_epub_target(target):
                display.info("Extracting EPUB archive: %s" % target, state=True)
                book_path, cleanup_dir = _extract_epub_target(target)
                book_id = _extract_book_id_from_name(target)
            else:
                book_path = resolve_book_path(target, workspace_root)

            if not book_path:
                display.error("Unable to resolve a downloaded book folder or EPUB file for `%s`." % target)
                failures.append(target)
                continue

            profile = analyze_book_layout(book_path, book_id=book_id)
            if profile.reason:
                display.info("Detected PDF profile: %s." % profile.reason, state=True)

            output_path = _default_output_path(target, resolved_output, len(targets) == 1)
            if not render_book_to_pdf(book_path, output_path=output_path, profile=profile, display=display):
                failures.append(target)
        except zipfile.BadZipFile as archive_error:
            display.error("Unable to read EPUB archive `%s`: %s." % (target, archive_error))
            failures.append(target)
        finally:
            if cleanup_dir:
                shutil.rmtree(cleanup_dir, ignore_errors=True)

    if failures:
        print("Failed conversions: %s" % ", ".join(failures), file=sys.stderr)
        sys.exit(1)

    sys.exit(0)
