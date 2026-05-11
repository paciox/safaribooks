#!/usr/bin/env python3
# coding: utf-8
import re
import os
import sys
import json
import time
import base64
import shutil
import pathlib
import getpass
import logging
import argparse
import requests
import traceback
from html import escape
from random import random
from lxml import html, etree
from multiprocessing import Process, Queue, Value
from urllib.parse import urljoin, urlparse, parse_qs, quote_plus

from book_pdf import analyze_book_layout, render_book_to_pdf


PATH = os.path.dirname(os.path.realpath(__file__))
COOKIES_FILE = os.path.join(PATH, "cookies.json")

ORLY_BASE_HOST = "oreilly.com"  # PLEASE INSERT URL HERE

SAFARI_BASE_HOST = "learning." + ORLY_BASE_HOST
API_ORIGIN_HOST = "api." + ORLY_BASE_HOST

ORLY_BASE_URL = "https://www." + ORLY_BASE_HOST
SAFARI_BASE_URL = "https://" + SAFARI_BASE_HOST
API_ORIGIN_URL = "https://" + API_ORIGIN_HOST
PROFILE_URL = SAFARI_BASE_URL + "/profile/"

# DEBUG
USE_PROXY = False
PROXIES = {"https": "https://127.0.0.1:8080"}


class Display:
    BASE_FORMAT = logging.Formatter(
        fmt="[%(asctime)s] %(message)s",
        datefmt="%d/%b/%Y %H:%M:%S"
    )

    SH_DEFAULT = "\033[0m" if "win" not in sys.platform else ""  # TODO: colors for Windows
    SH_YELLOW = "\033[33m" if "win" not in sys.platform else ""
    SH_BG_RED = "\033[41m" if "win" not in sys.platform else ""
    SH_BG_YELLOW = "\033[43m" if "win" not in sys.platform else ""

    def __init__(self, log_file):
        self.output_dir = ""
        self.output_dir_set = False
        self.log_file = os.path.join(PATH, log_file)

        self.logger = logging.getLogger("SafariBooks")
        self.logger.setLevel(logging.INFO)
        logs_handler = logging.FileHandler(filename=self.log_file)
        logs_handler.setFormatter(self.BASE_FORMAT)
        logs_handler.setLevel(logging.INFO)
        self.logger.addHandler(logs_handler)

        self.columns, _ = shutil.get_terminal_size()

        self.logger.info("** Welcome to SafariBooks! **")

        self.book_ad_info = False
        self.css_ad_info = Value("i", 0)
        self.images_ad_info = Value("i", 0)
        self.last_request = (None,)
        self.in_error = False

        self.state_status = Value("i", 0)
        sys.excepthook = self.unhandled_exception

    def set_output_dir(self, output_dir):
        self.info("Output directory:\n    %s" % output_dir)
        self.output_dir = output_dir
        self.output_dir_set = True

    def unregister(self):
        self.logger.handlers[0].close()
        sys.excepthook = sys.__excepthook__

    def log(self, message):
        try:
            self.logger.info(str(message, "utf-8", "replace"))

        except (UnicodeDecodeError, Exception):
            self.logger.info(message)

    def out(self, put):
        pattern = "\r{!s}\r{!s}\n"
        try:
            s = pattern.format(" " * self.columns, str(put, "utf-8", "replace"))

        except (TypeError, UnicodeEncodeError):
            try:
                s = pattern.format(" " * self.columns, put.encode(sys.stdout.encoding or "utf-8", "replace").decode(sys.stdout.encoding or "utf-8"))
            except (UnicodeEncodeError, AttributeError):
                s = pattern.format(" " * self.columns, put)

        sys.stdout.write(s)

    def info(self, message, state=False):
        self.log(message)
        output = (self.SH_YELLOW + "[*]" + self.SH_DEFAULT if not state else
                  self.SH_BG_YELLOW + "[-]" + self.SH_DEFAULT) + " %s" % message
        self.out(output)

    def error(self, error):
        if not self.in_error:
            self.in_error = True

        self.log(error)
        output = self.SH_BG_RED + "[#]" + self.SH_DEFAULT + " %s" % error
        self.out(output)

    def exit(self, error):
        self.error(str(error))

        if self.output_dir_set:
            output = (self.SH_YELLOW + "[+]" + self.SH_DEFAULT +
                      " Please delete the output directory '" + self.output_dir + "'"
                      " and restart the program.")
            self.out(output)

        output = self.SH_BG_RED + "[!]" + self.SH_DEFAULT + " Aborting..."
        self.out(output)

        self.save_last_request()
        sys.exit(1)

    def unhandled_exception(self, _, o, tb):
        self.log("".join(traceback.format_tb(tb)))
        self.exit("Unhandled Exception: %s (type: %s)" % (o, o.__class__.__name__))

    def save_last_request(self):
        if any(self.last_request):
            self.log("Last request done:\n\tURL: {0}\n\tDATA: {1}\n\tOTHERS: {2}\n\n\t{3}\n{4}\n\n{5}\n"
                     .format(*self.last_request))

    def intro(self):
        output = self.SH_YELLOW + (r"""
       ____     ___         _
      / __/__ _/ _/__ _____(_)
     _\ \/ _ `/ _/ _ `/ __/ /
    /___/\_,_/_/ \_,_/_/ /_/
      / _ )___  ___  / /__ ___
     / _  / _ \/ _ \/  '_/(_-<
    /____/\___/\___/_/\_\/___/
""" if random() > 0.5 else r"""
 ██████╗     ██████╗ ██╗  ██╗   ██╗██████╗
██╔═══██╗    ██╔══██╗██║  ╚██╗ ██╔╝╚════██╗
██║   ██║    ██████╔╝██║   ╚████╔╝   ▄███╔╝
██║   ██║    ██╔══██╗██║    ╚██╔╝    ▀▀══╝
╚██████╔╝    ██║  ██║███████╗██║     ██╗
 ╚═════╝     ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝
""") + self.SH_DEFAULT
        output += "\n" + "~" * (self.columns // 2)

        self.out(output)

    def parse_description(self, desc):
        if not desc:
            return "n/d"

        try:
            return html.fromstring(desc).text_content()

        except (html.etree.ParseError, html.etree.ParserError) as e:
            self.log("Error parsing the description: %s" % e)
            return "n/d"

    def book_info(self, info):
        description = self.parse_description(info.get("description", None)).replace("\n", " ")
        for t in [
            ("Title", info.get("title", "")), ("Authors", ", ".join(aut.get("name", "") for aut in info.get("authors", []))),
            ("Identifier", info.get("identifier", "")), ("ISBN", info.get("isbn", "")),
            ("Publishers", ", ".join(pub.get("name", "") for pub in info.get("publishers", []))),
            ("Rights", info.get("rights", "")),
            ("Description", description[:500] + "..." if len(description) >= 500 else description),
            ("Release Date", info.get("issued", "")),
            ("URL", info.get("web_url", ""))
        ]:
            self.info("{0}{1}{2}: {3}".format(self.SH_YELLOW, t[0], self.SH_DEFAULT, t[1]), True)

    def state(self, origin, done):
        progress = int(done * 100 / origin)
        bar = int(progress * (self.columns - 11) / 100)
        if self.state_status.value < progress:
            self.state_status.value = progress
            sys.stdout.write(
                "\r    " + self.SH_BG_YELLOW + "[" + ("#" * bar).ljust(self.columns - 11, "-") + "]" +
                self.SH_DEFAULT + ("%4s" % progress) + "%" + ("\n" if progress == 100 else "")
            )

    def done(self, epub_file):
        self.info("Done: %s\n\n" % epub_file +
                  "    If you like it, please * this project on GitHub to make it known:\n"
                  "        https://github.com/lorenzodifuccia/safaribooks\n"
                  "    e don't forget to renew your Safari Books Online subscription:\n"
                  "        " + SAFARI_BASE_URL + "\n\n" +
                  self.SH_BG_RED + "[!]" + self.SH_DEFAULT + " Bye!!")

    @staticmethod
    def api_error(response):
        message = "API: "
        if "detail" in response and "Not found" in response["detail"]:
            message += "book's not present in Safari Books Online.\n" \
                       "    The book identifier is the digits that you can find in the URL:\n" \
                       "    `" + SAFARI_BASE_URL + "/library/view/book-name/XXXXXXXXXXXXX/`"

        else:
            os.remove(COOKIES_FILE)
            message += "Out-of-Session%s.\n" % (" (%s)" % response["detail"]) if "detail" in response else "" + \
                       Display.SH_YELLOW + "[+]" + Display.SH_DEFAULT + \
                       " Use the `--cred` or `--login` options in order to perform the auth login to Safari."

        return message


class WinQueue(list):  # TODO: error while use `process` in Windows: can't pickle _thread.RLock objects
    def put(self, el):
        self.append(el)

    def qsize(self):
        return self.__len__()


def normalize_output_pdf_args(argv):
    normalized_args = []
    index = 0

    while index < len(argv):
        arg = argv[index]

        if arg in {"--output-pdf", "--output-to-pdf"}:
            next_arg = argv[index + 1] if index + 1 < len(argv) else None

            if next_arg in {"0", "1"}:
                normalized_args.append("{0}={1}".format(arg, next_arg))
                index += 2
                continue

            if next_arg is None or next_arg.startswith("-") or len(next_arg) != 1 or not next_arg.isdigit():
                normalized_args.append("{0}=0".format(arg))
                index += 1
                continue

        normalized_args.append(arg)
        index += 1

    return normalized_args


class SafariBooks:
    LOGIN_URL = ORLY_BASE_URL + "/member/auth/login/"
    LOGIN_ENTRY_URL = SAFARI_BASE_URL + "/login/unified/?next=/home/"

    API_TEMPLATE = API_ORIGIN_URL + "/api/v2/epubs/urn:orm:book:{0}/"

    BASE_01_HTML = "<!DOCTYPE html>\n" \
                   "<html lang=\"en\" xml:lang=\"en\" xmlns=\"http://www.w3.org/1999/xhtml\"" \
                   " xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"" \
                   " xsi:schemaLocation=\"http://www.w3.org/2002/06/xhtml2/" \
                   " http://www.w3.org/MarkUp/SCHEMA/xhtml2.xsd\"" \
                   " xmlns:epub=\"http://www.idpf.org/2007/ops\">\n" \
                   "<head>\n" \
                   "{0}\n" \
                   "<style type=\"text/css\">" \
                   "body{{margin:1em;background-color:transparent!important;}}" \
                   "#sbo-rt-content *{{text-indent:0pt!important;}}#sbo-rt-content .bq{{margin-right:1em!important;}}"

    KINDLE_HTML = "#sbo-rt-content *{{word-wrap:break-word!important;" \
                  "word-break:break-word!important;}}#sbo-rt-content table,#sbo-rt-content pre" \
                  "{{overflow-x:unset!important;overflow:unset!important;" \
                  "overflow-y:unset!important;white-space:pre-wrap!important;}}"

    BASE_02_HTML = "</style>" \
                   "</head>\n" \
                   "<body>{1}</body>\n</html>"

    CONTAINER_XML = "<?xml version=\"1.0\"?>" \
                    "<container version=\"1.0\" xmlns=\"urn:oasis:names:tc:opendocument:xmlns:container\">" \
                    "<rootfiles>" \
                    "<rootfile full-path=\"OEBPS/content.opf\" media-type=\"application/oebps-package+xml\" />" \
                    "</rootfiles>" \
                    "</container>"

    # Format: ID, Title, Authors, Description, Subjects, Publisher, Rights, Date, CoverId, MANIFEST, SPINE, CoverUrl
    CONTENT_OPF = "<?xml version=\"1.0\" encoding=\"utf-8\"?>\n" \
                  "<package xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"bookid\" version=\"2.0\" >\n" \
                  "<metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\" " \
                  " xmlns:opf=\"http://www.idpf.org/2007/opf\">\n" \
                  "<dc:title>{1}</dc:title>\n" \
                  "{2}\n" \
                  "<dc:description>{3}</dc:description>\n" \
                  "{4}" \
                  "<dc:publisher>{5}</dc:publisher>\n" \
                  "<dc:rights>{6}</dc:rights>\n" \
                  "<dc:language>en-US</dc:language>\n" \
                  "<dc:date>{7}</dc:date>\n" \
                  "<dc:identifier id=\"bookid\">{0}</dc:identifier>\n" \
                  "<meta name=\"cover\" content=\"{8}\"/>\n" \
                  "</metadata>\n" \
                  "<manifest>\n" \
                  "<item id=\"ncx\" href=\"toc.ncx\" media-type=\"application/x-dtbncx+xml\" />\n" \
                  "{9}\n" \
                  "</manifest>\n" \
                  "<spine toc=\"ncx\">\n{10}</spine>\n" \
                  "<guide><reference href=\"{11}\" title=\"Cover\" type=\"cover\" /></guide>\n" \
                  "</package>"

    # Format: ID, Depth, Title, Author, NAVMAP
    TOC_NCX = "<?xml version=\"1.0\" encoding=\"utf-8\" standalone=\"no\" ?>\n" \
              "<!DOCTYPE ncx PUBLIC \"-//NISO//DTD ncx 2005-1//EN\"" \
              " \"http://www.daisy.org/z3986/2005/ncx-2005-1.dtd\">\n" \
              "<ncx xmlns=\"http://www.daisy.org/z3986/2005/ncx/\" version=\"2005-1\">\n" \
              "<head>\n" \
              "<meta content=\"ID:ISBN:{0}\" name=\"dtb:uid\"/>\n" \
              "<meta content=\"{1}\" name=\"dtb:depth\"/>\n" \
              "<meta content=\"0\" name=\"dtb:totalPageCount\"/>\n" \
              "<meta content=\"0\" name=\"dtb:maxPageNumber\"/>\n" \
              "</head>\n" \
              "<docTitle><text>{2}</text></docTitle>\n" \
              "<docAuthor><text>{3}</text></docAuthor>\n" \
              "<navMap>{4}</navMap>\n" \
              "</ncx>"

    HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,"
                  "*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": SAFARI_BASE_URL + "/",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/145.0.0.0 Safari/537.36",
        "Sec-Ch-Ua": "\"Not:A-Brand\";v=\"99\", \"Google Chrome\";v=\"145\", \"Chromium\";v=\"145\"",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "\"Windows\"",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-User": "?1",
    }

    COOKIE_FLOAT_MAX_AGE_PATTERN = re.compile(r'(max-age=\d*\.\d*)', re.IGNORECASE)

    def __init__(self, args):
        self.args = args
        self.display = Display("info_%s.log" % escape(args.bookid))
        self.display.intro()

        self.session = requests.Session()
        if USE_PROXY:  # DEBUG
            self.session.proxies = PROXIES
            self.session.verify = False

        self.session.headers.update(self.HEADERS)

        self.jwt = {}

        if not args.cred:
            if not os.path.isfile(COOKIES_FILE):
                self.display.exit("Login: unable to find `cookies.json` file.\n"
                                  "    Please use the `--cred` or `--login` options to perform the login.")

            self.session.cookies.update(json.load(open(COOKIES_FILE)))
            self._browser_cookies = json.load(open(COOKIES_FILE))

        else:
            self.display.info("Logging into Safari Books Online...", state=True)
            self.do_login(*args.cred)
            self._browser_cookies = self.session.cookies.get_dict()
            if not args.no_cookies:
                json.dump(self.session.cookies.get_dict(), open(COOKIES_FILE, 'w'))

        self.book_id = args.bookid
        self.api_url = self.API_TEMPLATE.format(self.book_id)

        if self._is_jwt_expired():
            self._refresh_jwt()
        else:
            jwt = self._browser_cookies.get("orm-jwt", "")
            if jwt:
                self.session.headers["Authorization"] = "Bearer %s" % jwt

        self.check_login()

        self.display.info("Retrieving book info...")
        self.book_info = self.get_book_info()
        self.display.book_info(self.book_info)

        self.display.info("Retrieving book chapters...")
        self.book_chapters = self.get_book_chapters()

        self.chapters_queue = self.book_chapters[:]

        if len(self.book_chapters) > sys.getrecursionlimit():
            sys.setrecursionlimit(len(self.book_chapters))

        self.book_title = self.book_info["title"]
        # Base URL used to resolve relative asset paths (CSS, images) from raw XHTML files in API v2.
        # Must use learning.oreilly.com (not api.oreilly.com) to get full, uncorrupted content.
        self.base_url = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{}/files/".format(self.book_id)

        self.clean_book_title = "".join(self.escape_dirname(self.book_title).split(",")[:2]) \
                                + " ({0})".format(self.book_id)

        books_dir = os.path.join(PATH, "Books")
        if not os.path.isdir(books_dir):
            os.mkdir(books_dir)

        self.BOOK_PATH = os.path.join(books_dir, self.clean_book_title)
        self.display.set_output_dir(self.BOOK_PATH)
        self.css_path = ""
        self.images_path = ""
        self.fonts_path = ""
        self.pdf_profile = None
        self.use_pdf_output = False
        self.create_dirs()

        self.chapter_title = ""
        self.filename = ""
        self.chapter_stylesheets = []
        self.css = []
        self.images = []

        self.display.info("Downloading book contents... (%s chapters)" % len(self.book_chapters), state=True)
        self.BASE_HTML = self.BASE_01_HTML + (self.KINDLE_HTML if not args.kindle else "") + self.BASE_02_HTML

        self.cover = False
        self.get()
        if not self.cover:
            self.cover = self.get_default_cover() if "cover" in self.book_info else False
            cover_html = self.parse_html(
                html.fromstring("<div id=\"sbo-rt-content\"><img src=\"Images/{0}\"></div>".format(self.cover)), True
            )

            self.book_chapters = [{
                "filename": "default_cover.xhtml",
                "title": "Cover"
            }] + self.book_chapters

            self.filename = self.book_chapters[0]["filename"]
            self.save_page_html(cover_html)

        self.css_done_queue = Queue(0) if "win" not in sys.platform else WinQueue()
        self.display.info("Downloading book CSSs... (%s files)" % len(self.css), state=True)
        self.collect_css()
        self.pdf_profile = analyze_book_layout(self.BOOK_PATH, self.book_id)
        self.use_pdf_output = args.output_pdf is not None or self.pdf_profile.should_auto_pdf
        if self.use_pdf_output:
            if args.output_pdf is not None:
                self.display.info("PDF output requested; using the separate PDF renderer.", state=True)
            else:
                self.display.info(
                    "Compatibility PDF selected automatically: %s." % self.pdf_profile.reason,
                    state=True
                )
            self.collect_fonts()
        self.images_done_queue = Queue(0) if "win" not in sys.platform else WinQueue()
        self.display.info("Downloading book images... (%s files)" % len(self.images), state=True)
        self.collect_images()

        if self.use_pdf_output and args.output_pdf == 1:
            self.display.info("Creating EPUB file to keep alongside the PDF...", state=True)
            self.create_epub()

        self.display.info(
            "Creating PDF file..." if self.use_pdf_output else "Creating EPUB file...",
            state=True
        )
        output_file = self.create_pdf() if self.use_pdf_output else self.create_epub()

        if not args.no_cookies:
            json.dump(self.session.cookies.get_dict(), open(COOKIES_FILE, "w"))

        self.display.done(output_file)
        self.display.unregister()

        if not self.display.in_error and not args.log:
            os.remove(self.display.log_file)

    def handle_cookie_update(self, set_cookie_headers):
        for morsel in set_cookie_headers:
            # Handle Float 'max-age' Cookie
            if self.COOKIE_FLOAT_MAX_AGE_PATTERN.search(morsel):
                cookie_key, cookie_value = morsel.split(";")[0].split("=")
                self.session.cookies.set(cookie_key, cookie_value)

    AKAMAI_COOKIE_KEYS = {'_abck', 'ak_bmsc', 'bm_sz', 'bm_s', 'bm_so', 'bm_ss', 'bm_mi', 'bm_sv'}

    def _restore_browser_cookies(self):
        if not hasattr(self, '_browser_cookies'):
            return
        try:
            session_jwt = None
            for cookie in self.session.cookies:
                if cookie.name == 'orm-jwt':
                    session_jwt = cookie.value
                    break
            if session_jwt and session_jwt != self._browser_cookies.get('orm-jwt'):
                self._browser_cookies['orm-jwt'] = session_jwt
        except Exception:
            pass
        self.session.cookies.clear()
        self.session.cookies.update(self._browser_cookies)

    def _decode_jwt_payload(self, token):
        try:
            payload_b64 = token.split('.')[1]
            padding = 4 - len(payload_b64) % 4
            if padding != 4:
                payload_b64 += '=' * padding
            return json.loads(base64.urlsafe_b64decode(payload_b64))
        except Exception:
            return None

    def _is_jwt_expired(self):
        jwt_token = self._browser_cookies.get("orm-jwt", "") if hasattr(self, '_browser_cookies') else ""
        if not jwt_token:
            return True
        payload = self._decode_jwt_payload(jwt_token)
        if not payload:
            return True
        return payload.get('exp', 0) < time.time()

    def _extract_session_jwt(self):
        try:
            for cookie in self.session.cookies: 
                if cookie.name == 'orm-jwt':
                    return cookie.value
        except Exception:
            pass
        return None

    def _refresh_jwt(self):
        if not hasattr(self, '_browser_cookies'):
            return False
        refresh_token = self._browser_cookies.get("orm-rt", "")
        if not refresh_token:
            return False

        self.display.info("JWT expired, attempting refresh...")
        original_jwt = self._browser_cookies.get('orm-jwt', '')

        try:
            refresh_session = requests.Session()
            refresh_session.cookies.update(self._browser_cookies)
            refresh_session.headers.update(self.HEADERS)
            refresh_session.get(
                API_ORIGIN_URL + "/api/v1/auth/openid/token/",
                allow_redirects=False, timeout=15)
            for cookie in refresh_session.cookies:
                if cookie.name == 'orm-jwt' and cookie.value != original_jwt:
                    new_jwt = cookie.value
                    self._browser_cookies['orm-jwt'] = new_jwt
                    self.session.cookies.clear()
                    self.session.cookies.update(self._browser_cookies)
                    self.session.headers["Authorization"] = "Bearer %s" % new_jwt
                    self.display.info("JWT refreshed successfully.", state=True)
                    return True
        except Exception:
            pass

        if original_jwt:
            self.session.headers["Authorization"] = "Bearer %s" % original_jwt

        self.display.error(
            "Unable to auto-refresh JWT. Please re-run retrieve_cookies.py for fresh cookies.")
        return False

    REQUEST_TIMEOUT = 30
    RATE_LIMIT_STATUS_CODES = {403, 429}
    RATE_LIMIT_MAX_RETRIES = 2
    RATE_LIMIT_BASE_DELAY = 5

    def requests_provider(self, url, is_post=False, data=None, perform_redirect=True, **kwargs):
        kwargs.setdefault('timeout', self.REQUEST_TIMEOUT)
        rate_limit_retry = kwargs.pop("_rate_limit_retry", 0)
        try:
            response = getattr(self.session, "post" if is_post else "get")(
                url,
                data=data,
                allow_redirects=False,
                **kwargs
            )

            self.handle_cookie_update(response.raw.headers.getlist("Set-Cookie"))
            self._restore_browser_cookies()

            self.display.last_request = (
                url, data, kwargs, response.status_code, "\n".join(
                    ["\t{}: {}".format(*h) for h in response.headers.items()]
                ), response.text
            )

        except (requests.ConnectionError, requests.ConnectTimeout, requests.RequestException) as request_exception:
            self.display.error(str(request_exception))
            return 0

        if response.status_code in self.RATE_LIMIT_STATUS_CODES and rate_limit_retry < self.RATE_LIMIT_MAX_RETRIES:
            retry_after = response.headers.get("Retry-After", "").strip()
            delay = int(retry_after) if retry_after.isdigit() else self.RATE_LIMIT_BASE_DELAY * (rate_limit_retry + 1)
            self.display.info(
                "HTTP %d received for %s. Waiting %ss before retry %d/%d." % (
                    response.status_code,
                    url,
                    delay,
                    rate_limit_retry + 1,
                    self.RATE_LIMIT_MAX_RETRIES,
                ),
                state=True,
            )
            time.sleep(delay)
            return self.requests_provider(
                url,
                is_post=is_post,
                data=data,
                perform_redirect=perform_redirect,
                _rate_limit_retry=rate_limit_retry + 1,
                **kwargs
            )

        if response.is_redirect and perform_redirect:
            return self.requests_provider(response.next.url, is_post, None, perform_redirect)
            # TODO How about **kwargs?

        return response

    @staticmethod
    def parse_cred(cred):
        if ":" not in cred:
            return False

        sep = cred.index(":")
        new_cred = ["", ""]
        new_cred[0] = cred[:sep].strip("'").strip('"')
        if "@" not in new_cred[0]:
            return False

        new_cred[1] = cred[sep + 1:]
        return new_cred

    def do_login(self, email, password):
        response = self.requests_provider(self.LOGIN_ENTRY_URL)
        if response == 0:
            self.display.exit("Login: unable to reach Safari Books Online. Try again...")

        next_parameter = None
        try:
            next_parameter = parse_qs(urlparse(response.request.url).query)["next"][0]

        except (AttributeError, ValueError, IndexError):
            self.display.exit("Login: unable to complete login on Safari Books Online. Try again...")

        redirect_uri = API_ORIGIN_URL + quote_plus(next_parameter)

        response = self.requests_provider(
            self.LOGIN_URL,
            is_post=True,
            json={
                "email": email,
                "password": password,
                "redirect_uri": redirect_uri
            },
            perform_redirect=False
        )

        if response == 0:
            self.display.exit("Login: unable to perform auth to Safari Books Online.\n    Try again...")

        if response.status_code != 200:  # TODO To be reviewed
            try:
                error_page = html.fromstring(response.text)
                errors_message = error_page.xpath("//ul[@class='errorlist']//li/text()")
                recaptcha = error_page.xpath("//div[@class='g-recaptcha']")
                messages = (["    `%s`" % error for error in errors_message
                             if "password" in error or "email" in error] if len(errors_message) else []) + \
                           (["    `ReCaptcha required (wait or do logout from the website).`"] if len(
                               recaptcha) else [])
                self.display.exit(
                    "Login: unable to perform auth login to Safari Books Online.\n" + self.display.SH_YELLOW +
                    "[*]" + self.display.SH_DEFAULT + " Details:\n" + "%s" % "\n".join(
                        messages if len(messages) else ["    Unexpected error!"])
                )
            except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
                self.display.error(parsing_error)
                self.display.exit(
                    "Login: your login went wrong and it encountered in an error"
                    " trying to parse the login details of Safari Books Online. Try again..."
                )

        self.jwt = response.json()  # TODO: save JWT Tokens and use the refresh_token to restore user session
        response = self.requests_provider(self.jwt["redirect_uri"])
        if response == 0:
            self.display.exit("Login: unable to reach Safari Books Online. Try again...")

    def check_login(self):
        response = self.requests_provider(self.api_url)

        if response == 0:
            self.display.exit("Login: unable to reach Safari Books Online. Try again...")

        if response.status_code == 401:
            self.display.exit(
                "Authentication issue: session expired or invalid cookies.\n"
                "    Please update your `cookies.json` file.")

        if response.status_code == 403:
            self.display.exit(
                "Authentication issue: access denied (HTTP 403).\n"
                "    Please update your `cookies.json` file.")

        if response.status_code != 200:
            self.display.exit(
                "Authentication issue: unexpected status %d from API." % response.status_code)

        self._cached_api_response = response
        self.display.info("Successfully authenticated.", state=True)

    def _parse_publisher_opf(self):
        meta = {"authors": [], "publishers": [], "subjects": [], "rights": "", "cover": ""}
        opf_url = API_ORIGIN_URL + "/api/v2/epubs/urn:orm:book:{}/files/content.opf".format(self.book_id)
        response = self.requests_provider(opf_url)
        if response == 0 or response.status_code != 200:
            return meta

        try:
            opf_tree = etree.fromstring(response.content)
        except Exception:
            return meta

        ns = {
            "opf": "http://www.idpf.org/2007/opf",
            "dc": "http://purl.org/dc/elements/1.1/",
        }

        for el in opf_tree.findall(".//dc:creator", ns):
            name = (el.text or "").strip()
            if name:
                meta["authors"].append({"name": name})

        for el in opf_tree.findall(".//dc:publisher", ns):
            name = (el.text or "").strip()
            if name:
                meta["publishers"].append({"name": name})

        for el in opf_tree.findall(".//dc:subject", ns):
            name = (el.text or "").strip()
            if name:
                meta["subjects"].append({"name": name})

        rights_el = opf_tree.find(".//dc:rights", ns)
        if rights_el is not None and rights_el.text:
            meta["rights"] = rights_el.text.strip()

        cover_meta = opf_tree.find(".//opf:meta[@name='cover']", ns)
        if cover_meta is not None:
            cover_id = cover_meta.get("content", "")
            if cover_id:
                cover_item = opf_tree.find(".//opf:manifest/opf:item[@id='%s']" % cover_id, ns)
                if cover_item is not None:
                    href = cover_item.get("href", "")
                    if href:
                        meta["cover"] = API_ORIGIN_URL + \
                            "/api/v2/epubs/urn:orm:book:{}/files/{}".format(self.book_id, href)

        return meta

    def get_book_info(self):
        # Reuse the response from check_login to avoid duplicate requests (Akamai rate-limits)
        if hasattr(self, '_cached_api_response') and self._cached_api_response:
            response = self._cached_api_response
            del self._cached_api_response
        else:
            response = self.requests_provider(self.api_url)
            if response == 0:
                self.display.exit("API: unable to retrieve book info.")

        if response.status_code != 200:
            self.display.exit("API: unable to retrieve book info (HTTP %d)." % response.status_code)

        try:
            epub_info = response.json()
        except (ValueError, Exception) as e:
            self.display.exit("API: unable to parse book info response: %s" % e)

        if not isinstance(epub_info, dict) or not epub_info.get("title"):
            self.display.exit(self.display.api_error(epub_info))

        # Extract supplemental metadata from the publisher's original content.opf
        opf_meta = self._parse_publisher_opf()

        combined = {}

        combined["title"] = epub_info.get("title", "")
        combined["identifier"] = epub_info.get("identifier", self.book_id)
        combined["isbn"] = epub_info.get("isbn", self.book_id)

        descriptions = epub_info.get("descriptions") or {}
        description_html = descriptions.get("text/html") or descriptions.get("text/plain") or ""
        combined["description"] = description_html

        combined["issued"] = epub_info.get("publication_date", "")

        combined["authors"] = opf_meta.get("authors", [])
        combined["publishers"] = opf_meta.get("publishers", [])
        combined["subjects"] = opf_meta.get("subjects", [])
        combined["rights"] = opf_meta.get("rights", "")

        combined["web_url"] = SAFARI_BASE_URL + "/library/view/-/{}/".format(self.book_id)
        combined["cover"] = opf_meta.get("cover", "")

        for key, value in combined.items():
            if value is None:
                combined[key] = "n/a"

        return combined

    def _get_file_paths(self):
        """Query the files API to build a mapping of filenames to their correct full paths."""
        file_map = {}
        files_url = API_ORIGIN_URL + "/api/v2/epubs/urn:orm:book:{}/files/".format(self.book_id)
        while files_url:
            response = self.requests_provider(files_url, headers=self._get_content_headers())
            if response == 0 or response.status_code != 200:
                break
            try:
                data = response.json()
                for f in data.get("results", []):
                    filename = f.get("filename", "")
                    full_path = f.get("full_path", "")
                    if filename and full_path:
                        file_map[filename] = full_path
                files_url = data.get("next")
            except (ValueError, Exception):
                break
        return file_map

    def get_book_chapters(self, offset=0, limit=20):
        chapters = []
        params = {
            "epub_identifier": "urn:orm:book:{0}".format(self.book_id),
            "limit": limit,
            "offset": offset,
        }

        chapters_url = API_ORIGIN_URL + "/api/v2/epub-chapters/"
        response = self.requests_provider(chapters_url, params=params)
        if response == 0:
            self.display.exit("API: unable to retrieve book chapters.")

        if response.status_code != 200:
            self.display.exit("API: unable to retrieve book chapters (HTTP %d)." % response.status_code)

        try:
            response = response.json()
        except (ValueError, Exception) as e:
            self.display.exit("API: unable to parse chapters response: %s" % e)

        if not isinstance(response, dict) or "results" not in response:
            self.display.exit(self.display.api_error(response))

        if not response["results"]:
            self.display.exit("API: unable to retrieve book chapters.")

        if response["count"] > sys.getrecursionlimit():
            sys.setrecursionlimit(response["count"])

        # asset_base_url uses learning.oreilly.com for full uncorrupted content
        asset_base_url = SAFARI_BASE_URL + "/api/v2/epubs/urn:orm:book:{0}/files".format(self.book_id)

        page_results = []
        for ch in response["results"]:
            content_url = ch.get("content_url", "")
            # Extract filename from content_url
            filename = content_url.split("/")[-1] if content_url else ""

            related_assets = ch.get("related_assets", {})
            images = related_assets.get("images", [])
            stylesheets_urls = related_assets.get("stylesheets", [])

            stylesheets = [{"url": url} for url in stylesheets_urls]

            # Use content_url directly from the API response - it already points to
            # learning.oreilly.com which returns full, uncorrupted chapter content.
            if content_url:
                files_url = content_url
            else:
                files_url = asset_base_url + "/" + filename
            normalized = {
                "filename": filename,
                "title": ch.get("title", ""),
                "content": files_url,
                "asset_base_url": asset_base_url,
                "images": images,
                "stylesheets": stylesheets,
                "site_styles": [],
                "file_path": filename,
            }
            page_results.append(normalized)

        # Preserve behavior of placing cover-like chapters first
        result = []
        result.extend([c for c in page_results if "cover" in c["filename"] or "cover" in c["title"]])
        for c in result:
            del page_results[page_results.index(c)]

        result += page_results

        chapters += result

        if response.get("next"):
            chapters += self.get_book_chapters(offset + limit, limit)

        return chapters

    def get_default_cover(self):
        response = self.requests_provider(self.book_info["cover"], stream=True)
        if response == 0:
            self.display.error("Error trying to retrieve the cover: %s" % self.book_info["cover"])
            return False

        file_ext = response.headers["Content-Type"].split("/")[-1]
        with open(os.path.join(self.images_path, "default_cover." + file_ext), 'wb') as i:
            for chunk in response.iter_content(1024):
                i.write(chunk)

        return "default_cover." + file_ext

    MAX_CONTENT_RETRIES = 5

    def _get_content_headers(self):
        headers = {
            "Accept": "*/*",
            "Referer": SAFARI_BASE_URL + "/library/view/-/{}/".format(self.book_id),
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }
        jwt = self._browser_cookies.get("orm-jwt", "") if hasattr(self, '_browser_cookies') else ""
        if jwt:
            headers["Authorization"] = "Bearer %s" % jwt
        return headers

    @staticmethod
    def _wrap_content_fragments(response_text):
        wrapper = html.fromstring('<div id="sbo-rt-content"></div>')
        fragments = html.fragments_fromstring(response_text)
        last_node = None

        for fragment in fragments:
            if isinstance(fragment, str):
                if last_node is None:
                    wrapper.text = (wrapper.text or "") + fragment
                else:
                    last_node.tail = (last_node.tail or "") + fragment
                continue

            wrapper.append(fragment)
            last_node = fragment

        return wrapper

    def get_html(self, url):
        response = None
        for attempt in range(self.MAX_CONTENT_RETRIES):
            response = self.requests_provider(url, headers=self._get_content_headers())
            if response == 0 or response.status_code != 200:
                if attempt < self.MAX_CONTENT_RETRIES - 1:
                    delay = 2 ** (attempt + 1)
                    self.display.log(
                        "Retry %d/%d in %ds for %s (status: %s)" %
                        (attempt + 1, self.MAX_CONTENT_RETRIES,
                         delay, self.filename,
                         response.status_code if response != 0 else "timeout"))
                    time.sleep(delay)
                    continue
                self.display.exit(
                    "Crawler: error trying to retrieve this page: %s (%s)\n    From: %s" %
                    (self.filename, self.chapter_title, url)
                )
            break

        root = None
        try:
            root = html.fromstring(response.text, base_url=API_ORIGIN_URL)

            # Some titles return chapter XHTML as multiple top-level fragments instead of a full HTML document.
            # Preserve all fragments by wrapping them before parse_html() looks for the content container.
            if not root.xpath("//body") and not root.xpath("//div[@id='sbo-rt-content']"):
                root = self._wrap_content_fragments(response.text)

        except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
            self.display.error(parsing_error)
            self.display.exit(
                "Crawler: error trying to parse this page: %s (%s)\n    From: %s" %
                (self.filename, self.chapter_title, url)
            )

        return root

    @staticmethod
    def url_is_absolute(url):
        return bool(urlparse(url).netloc)

    @staticmethod
    def is_image_link(url: str):
        return pathlib.Path(url).suffix[1:].lower() in ["jpg", "jpeg", "png", "gif"]

    def link_replace(self, link):
        if link and not link.startswith("mailto"):
            if not self.url_is_absolute(link):
                if any(x in link for x in ["cover", "images", "graphics"]) or \
                        self.is_image_link(link):
                    image = link.split("/")[-1]
                    return "Images/" + image

                return link.replace(".html", ".xhtml")

            else:
                if self.book_id in link:
                    return self.link_replace(link.split(self.book_id)[-1])

        return link

    @staticmethod
    def get_cover(html_root):
        lowercase_ns = etree.FunctionNamespace(None)
        lowercase_ns["lower-case"] = lambda _, n: n[0].lower() if n and len(n) else ""

        images = html_root.xpath("//img[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                                 "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover') or"
                                 "contains(lower-case(@alt), 'cover')]")
        if len(images):
            return images[0]

        divs = html_root.xpath("//div[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                               "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover')]//img")
        if len(divs):
            return divs[0]

        a = html_root.xpath("//a[contains(lower-case(@id), 'cover') or contains(lower-case(@class), 'cover') or"
                            "contains(lower-case(@name), 'cover') or contains(lower-case(@src), 'cover')]//img")
        if len(a):
            return a[0]

        return None

    def parse_html(self, root, first_page=False):
        if random() > 0.8:
            if len(root.xpath("//div[@class='controls']/a/text()")):
                self.display.exit(self.display.api_error(" "))

        book_content = [root] if getattr(root, "tag", None) == "div" and root.attrib.get("id") == "sbo-rt-content" \
            else root.xpath("//div[@id='sbo-rt-content']")
        if not len(book_content):
            body_elements = root.xpath("//body")
            if body_elements:
                body = body_elements[0]
                sbo_div = body.makeelement("div", {"id": "sbo-rt-content"})
                sbo_div.text = body.text
                for child in list(body):
                    sbo_div.append(child)
                book_content = [sbo_div]
        if not len(book_content):
            self.display.exit(
                "Parser: book content's corrupted or not present: %s (%s)" %
                (self.filename, self.chapter_title)
            )

        page_css = ""
        if len(self.chapter_stylesheets):
            for chapter_css_url in self.chapter_stylesheets:
                if chapter_css_url not in self.css:
                    self.css.append(chapter_css_url)
                    self.display.log("Crawler: found a new CSS at %s" % chapter_css_url)

                page_css += "<link href=\"Styles/Style{0:0>2}.css\" " \
                            "rel=\"stylesheet\" type=\"text/css\" />\n".format(self.css.index(chapter_css_url))

        stylesheet_links = root.xpath("//link[@rel='stylesheet']")
        if len(stylesheet_links):
            for s in stylesheet_links:
                css_url = urljoin("https:", s.attrib["href"]) if s.attrib["href"][:2] == "//" \
                    else urljoin(self.base_url, s.attrib["href"])

                if css_url not in self.css:
                    self.css.append(css_url)
                    self.display.log("Crawler: found a new CSS at %s" % css_url)

                page_css += "<link href=\"Styles/Style{0:0>2}.css\" " \
                            "rel=\"stylesheet\" type=\"text/css\" />\n".format(self.css.index(css_url))

        stylesheets = root.xpath("//style")
        if len(stylesheets):
            for css in stylesheets:
                if "data-template" in css.attrib and len(css.attrib["data-template"]):
                    css.text = css.attrib["data-template"]
                    del css.attrib["data-template"]

                try:
                    page_css += html.tostring(css, method="xml", encoding='unicode') + "\n"

                except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
                    self.display.error(parsing_error)
                    self.display.exit(
                        "Parser: error trying to parse one CSS found in this page: %s (%s)" %
                        (self.filename, self.chapter_title)
                    )

        # TODO: add all not covered tag for `link_replace` function
        svg_image_tags = root.xpath("//image")
        if len(svg_image_tags):
            for img in svg_image_tags:
                image_attr_href = [x for x in img.attrib.keys() if "href" in x]
                if len(image_attr_href):
                    svg_url = img.attrib.get(image_attr_href[0])
                    svg_root = img.getparent().getparent()
                    new_img = svg_root.makeelement("img")
                    new_img.attrib.update({"src": svg_url})
                    svg_root.remove(img.getparent())
                    svg_root.append(new_img)

        book_content = book_content[0]
        book_content.rewrite_links(self.link_replace)

        xhtml = None
        try:
            if first_page:
                is_cover = self.get_cover(book_content)
                if is_cover is not None:
                    page_css = "<style>" \
                               "body{margin:0;padding:0;}" \
                               "#Cover{display:flex;justify-content:center;align-items:center;min-height:100vh;}" \
                               "img{max-width:100%;max-height:100vh;width:auto;height:auto;}" \
                               "</style>"
                    cover_html = html.fromstring("<div id=\"Cover\"></div>")
                    cover_div = cover_html.xpath("//div")[0]
                    cover_img = cover_div.makeelement("img")
                    cover_img.attrib.update({"src": is_cover.attrib["src"]})
                    cover_div.append(cover_img)
                    book_content = cover_html

                    self.cover = is_cover.attrib["src"]

            xhtml = html.tostring(book_content, method="xml", encoding='unicode')

        except (html.etree.ParseError, html.etree.ParserError) as parsing_error:
            self.display.error(parsing_error)
            self.display.exit(
                "Parser: error trying to parse HTML of this page: %s (%s)" %
                (self.filename, self.chapter_title)
            )

        return page_css, xhtml

    @staticmethod
    def escape_dirname(dirname, clean_space=False):
        if ":" in dirname:
            if dirname.index(":") > 15:
                dirname = dirname.split(":")[0]

            elif "win" in sys.platform:
                dirname = dirname.replace(":", ",")

        for ch in ['~', '#', '%', '&', '*', '{', '}', '\\', '<', '>', '?', '/', '`', '\'', '"', '|', '+', ':']:
            if ch in dirname:
                dirname = dirname.replace(ch, "_")

        return dirname if not clean_space else dirname.replace(" ", "")

    def create_dirs(self):
        if os.path.isdir(self.BOOK_PATH):
            self.display.log("Book directory already exists: %s" % self.BOOK_PATH)

        else:
            os.makedirs(self.BOOK_PATH)

        oebps = os.path.join(self.BOOK_PATH, "OEBPS")
        if not os.path.isdir(oebps):
            self.display.book_ad_info = True
            os.makedirs(oebps)

        self.css_path = os.path.join(oebps, "Styles")
        if os.path.isdir(self.css_path):
            self.display.log("CSSs directory already exists: %s" % self.css_path)

        else:
            os.makedirs(self.css_path)
            self.display.css_ad_info.value = 1

        self.images_path = os.path.join(oebps, "Images")
        if os.path.isdir(self.images_path):
            self.display.log("Images directory already exists: %s" % self.images_path)

        else:
            os.makedirs(self.images_path)
            self.display.images_ad_info.value = 1

        self.fonts_path = os.path.join(oebps, "fonts")
        if os.path.isdir(self.fonts_path):
            self.display.log("Fonts directory already exists: %s" % self.fonts_path)

        else:
            os.makedirs(self.fonts_path)

    def save_page_html(self, contents):
        self.filename = self.filename.replace(".html", ".xhtml")
        open(os.path.join(self.BOOK_PATH, "OEBPS", self.filename), "wb") \
            .write(self.BASE_HTML.format(contents[0], contents[1]).encode("utf-8", 'xmlcharrefreplace'))
        self.display.log("Created: %s" % self.filename)

    def get(self):
        len_books = len(self.book_chapters)

        for _ in range(len_books):
            if not len(self.chapters_queue):
                return

            first_page = len_books == len(self.chapters_queue)

            next_chapter = self.chapters_queue.pop(0)
            self.chapter_title = next_chapter["title"]
            self.filename = next_chapter["filename"]

            if "images" in next_chapter and len(next_chapter["images"]):
                for img_url in next_chapter['images']:
                    self.images.append(img_url)


            # Stylesheets
            self.chapter_stylesheets = []
            if "stylesheets" in next_chapter and len(next_chapter["stylesheets"]):
                self.chapter_stylesheets.extend(x["url"] for x in next_chapter["stylesheets"])

            if "site_styles" in next_chapter and len(next_chapter["site_styles"]):
                self.chapter_stylesheets.extend(next_chapter["site_styles"])

            if os.path.isfile(os.path.join(self.BOOK_PATH, "OEBPS", self.filename.replace(".html", ".xhtml"))):
                if not self.display.book_ad_info and \
                        next_chapter not in self.book_chapters[:self.book_chapters.index(next_chapter)]:
                    self.display.info(
                        ("File `%s` already exists.\n"
                         "    If you want to download again all the book,\n"
                         "    please delete the output directory '" + self.BOOK_PATH + "' and restart the program.")
                         % self.filename.replace(".html", ".xhtml")
                    )
                    self.display.book_ad_info = 2

            else:
                self.save_page_html(self.parse_html(self.get_html(next_chapter["content"]), first_page))

            self.display.state(len_books, len_books - len(self.chapters_queue))

    def _thread_download_css(self, url):
        css_file = os.path.join(self.css_path, "Style{0:0>2}.css".format(self.css.index(url)))
        if os.path.isfile(css_file):
            if not self.display.css_ad_info.value and url not in self.css[:self.css.index(url)]:
                self.display.info(("File `%s` already exists.\n"
                                   "    If you want to download again all the CSSs,\n"
                                   "    please delete the output directory '" + self.BOOK_PATH + "'"
                                   " and restart the program.") %
                                  css_file)
                self.display.css_ad_info.value = 1

        else:
            response = self.requests_provider(url)
            if response == 0:
                self.display.error("Error trying to retrieve this CSS: %s\n    From: %s" % (css_file, url))

            with open(css_file, 'wb') as s:
                s.write(response.content)

        self.css_done_queue.put(1)
        self.display.state(len(self.css), self.css_done_queue.qsize())


    def _thread_download_images(self, url):
        image_name = url.split("/")[-1]
        image_path = os.path.join(self.images_path, image_name)
        if os.path.isfile(image_path):
            if not self.display.images_ad_info.value and url not in self.images[:self.images.index(url)]:
                self.display.info(("File `%s` already exists.\n"
                                   "    If you want to download again all the images,\n"
                                   "    please delete the output directory '" + self.BOOK_PATH + "'"
                                   " and restart the program.") %
                                  image_name)
                self.display.images_ad_info.value = 1

        else:
            response = self.requests_provider(urljoin(API_ORIGIN_URL, url), stream=True)
            if response == 0:
                self.display.error("Error trying to retrieve this image: %s\n    From: %s" % (image_name, url))
                return

            with open(image_path, 'wb') as img:
                for chunk in response.iter_content(1024):
                    img.write(chunk)

        self.images_done_queue.put(1)
        self.display.state(len(self.images), self.images_done_queue.qsize())

    def _start_multiprocessing(self, operation, full_queue):
        if len(full_queue) > 5:
            for i in range(0, len(full_queue), 5):
                self._start_multiprocessing(operation, full_queue[i:i + 5])

        else:
            process_queue = [Process(target=operation, args=(arg,)) for arg in full_queue]
            for proc in process_queue:
                proc.start()

            for proc in process_queue:
                proc.join()

    def collect_css(self):
        self.display.state_status.value = -1

        # "self._start_multiprocessing" seems to cause problem. Switching to mono-thread download.
        for css_url in self.css:
            self._thread_download_css(css_url)

    def collect_images(self):
        if self.display.book_ad_info == 2:
            self.display.info("Some of the book contents were already downloaded.\n"
                              "    If you want to be sure that all the images will be downloaded,\n"
                              "    please delete the output directory '" + self.BOOK_PATH +
                              "' and restart the program.")

        self.display.state_status.value = -1

        # "self._start_multiprocessing" seems to cause problem. Switching to mono-thread download.
        for image_url in self.images:
            self._thread_download_images(image_url)

    FONT_URL_PATTERN = re.compile(r'url\(([^)]+)\)', re.IGNORECASE)

    def _collect_font_urls(self):
        font_assets = []
        seen = set()
        for index, css_url in enumerate(self.css):
            css_file = os.path.join(self.css_path, "Style{0:0>2}.css".format(index))
            if not os.path.isfile(css_file):
                continue

            try:
                content = open(css_file, encoding='utf-8', errors='replace').read()
            except Exception:
                continue

            for raw_font_url in self.FONT_URL_PATTERN.findall(content):
                font_ref = raw_font_url.strip().strip('"\'')
                if not font_ref or font_ref.startswith('data:'):
                    continue

                resolved_font_url = urljoin(css_url, font_ref)
                relative_path = font_ref.split('#', 1)[0].split('?', 1)[0].replace('/', os.sep)
                while relative_path.startswith('..' + os.sep):
                    relative_path = relative_path[3:]
                if not relative_path:
                    relative_path = os.path.join("fonts", os.path.basename(urlparse(resolved_font_url).path))

                asset_key = (resolved_font_url, relative_path)
                if asset_key not in seen:
                    font_assets.append(asset_key)
                    seen.add(asset_key)

        return font_assets

    def _download_font(self, url, relative_path):
        font_name = os.path.basename(relative_path) or os.path.basename(urlparse(url).path)
        if not font_name:
            return

        font_path = os.path.join(self.BOOK_PATH, "OEBPS", relative_path)
        if os.path.isfile(font_path):
            return

        font_dir = os.path.dirname(font_path)
        if font_dir and not os.path.isdir(font_dir):
            os.makedirs(font_dir)

        response = self.requests_provider(url, headers=self._get_content_headers(), stream=True)
        if response == 0 or response.status_code != 200:
            self.display.error("Error trying to retrieve this font: %s\n    From: %s" % (font_name, url))
            return

        with open(font_path, 'wb') as font_file:
            for chunk in response.iter_content(1024):
                font_file.write(chunk)

    def collect_fonts(self):
        font_assets = self._collect_font_urls()
        if not font_assets:
            self.display.info("No embedded fonts referenced by the downloaded CSS.", state=True)
            return

        self.display.info("Downloading book fonts... (%s files)" % len(font_assets), state=True)
        self.display.state_status.value = -1
        for index, font_asset in enumerate(font_assets, 1):
            self._download_font(*font_asset)
            self.display.state(len(font_assets), index)

    def _detect_fixed_layout(self):
        """Scan downloaded CSS files for fixed-layout indicators (absolute-positioned pages with fixed px dimensions).
        Returns (is_fixed_layout, viewport_width, viewport_height). Result is cached."""
        if hasattr(self, '_fixed_layout_cache'):
            return self._fixed_layout_cache
        if not os.path.isdir(self.css_path):
            self._fixed_layout_cache = (False, 0, 0)
            return self._fixed_layout_cache
        for css_file in sorted(os.listdir(self.css_path)):
            try:
                content = open(
                    os.path.join(self.css_path, css_file), encoding='utf-8', errors='replace'
                ).read()
                if 'position:absolute' in content and 'overflow:hidden' in content:
                    m = re.search(r'width:(\d+)px;height:(\d+)px', content)
                    if m:
                        self._fixed_layout_cache = (True, int(m.group(1)), int(m.group(2)))
                        return self._fixed_layout_cache
            except Exception:
                continue
        self._fixed_layout_cache = (False, 0, 0)
        return self._fixed_layout_cache

    def _get_spine_xhtml_files(self):
        files = []
        seen = set()
        for chapter in self.book_chapters:
            filename = chapter.get("filename", "").replace(".html", ".xhtml")
            if not filename or filename in seen:
                continue

            chapter_path = os.path.join(self.BOOK_PATH, "OEBPS", filename)
            if os.path.isfile(chapter_path):
                files.append(chapter_path)
                seen.add(filename)

        return files

    def _render_fixed_layout_pdf(self, viewport_w, viewport_h):
        try:
            import asyncio
            from io import BytesIO
            from PIL import Image
            from playwright.async_api import async_playwright
        except ImportError as import_error:
            self.display.error(
                "Fixed-layout PDF skipped: install optional dependencies `Pillow` and `playwright`, "
                "then run `playwright install chromium` (%s)." % import_error
            )
            return False

        xhtml_files = self._get_spine_xhtml_files()
        if not xhtml_files:
            self.display.error("Fixed-layout PDF skipped: no XHTML pages were found in the spine.")
            return False

        pdf_path = os.path.join(self.BOOK_PATH, self.book_id + ".pdf")
        self.display.info("Fixed-layout content detected; rendering companion PDF...", state=True)

        async def _capture_pages():
            screenshots = []
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                page = await browser.new_page(
                    viewport={"width": viewport_w, "height": viewport_h},
                    device_scale_factor=2,
                )

                self.display.state_status.value = -1
                total = len(xhtml_files)
                for index, xhtml_path in enumerate(xhtml_files, 1):
                    await page.goto(pathlib.Path(xhtml_path).as_uri(), wait_until="networkidle")
                    try:
                        await page.evaluate("document.fonts ? document.fonts.ready : Promise.resolve(true)")
                    except Exception:
                        pass
                    try:
                        await page.wait_for_function(
                            "!document.fonts || document.fonts.status === 'loaded'", timeout=10000
                        )
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
                    self.display.state(total, index)

                await browser.close()

            return screenshots

        try:
            screenshots = asyncio.run(_capture_pages())
        except Exception as render_error:
            self.display.error("Fixed-layout PDF render failed: %s" % render_error)
            return False

        if not screenshots:
            self.display.error("Fixed-layout PDF render failed: no pages were captured.")
            return False

        images = []
        try:
            for screenshot in screenshots:
                images.append(Image.open(BytesIO(screenshot)).convert("RGB"))

            images[0].save(pdf_path, save_all=True, append_images=images[1:])
        except Exception as save_error:
            self.display.error("Fixed-layout PDF build failed: %s" % save_error)
            return False
        finally:
            for image in images:
                try:
                    image.close()
                except Exception:
                    pass

        self.display.info("Created compatibility PDF: %s" % pdf_path, state=True)
        return True

    def create_content_opf(self):
        self.css = next(os.walk(self.css_path))[2]
        self.images = next(os.walk(self.images_path))[2]

        manifest = []
        spine = []
        for c in self.book_chapters:
            c["filename"] = c["filename"].replace(".html", ".xhtml")
            item_id = escape("".join(c["filename"].split(".")[:-1]))
            manifest.append("<item id=\"{0}\" href=\"{1}\" media-type=\"application/xhtml+xml\" />".format(
                item_id, c["filename"]
            ))
            spine.append("<itemref idref=\"{0}\"/>".format(item_id))

        for i in set(self.images):
            dot_split = i.split(".")
            head = "img_" + escape("".join(dot_split[:-1]))
            extension = dot_split[-1]
            manifest.append("<item id=\"{0}\" href=\"Images/{1}\" media-type=\"image/{2}\" />".format(
                head, i, "jpeg" if "jp" in extension else extension
            ))

        for i in range(len(self.css)):
            manifest.append("<item id=\"style_{0:0>2}\" href=\"Styles/Style{0:0>2}.css\" "
                            "media-type=\"text/css\" />".format(i))

        authors = "\n".join("<dc:creator opf:file-as=\"{0}\" opf:role=\"aut\">{0}</dc:creator>".format(
            escape(aut.get("name", "n/d"))
        ) for aut in self.book_info.get("authors", []))

        subjects = "\n".join("<dc:subject>{0}</dc:subject>".format(escape(sub.get("name", "n/d")))
                             for sub in self.book_info.get("subjects", []))

        opf = self.CONTENT_OPF.format(
            (self.book_info.get("isbn",  self.book_id)),
            escape(self.book_title),
            authors,
            escape(self.book_info.get("description", "")),
            subjects,
            ", ".join(escape(pub.get("name", "")) for pub in self.book_info.get("publishers", [])),
            escape(self.book_info.get("rights", "")),
            self.book_info.get("issued", ""),
            self.cover,
            "\n".join(manifest),
            "\n".join(spine),
            self.book_chapters[0]["filename"].replace(".html", ".xhtml")
        )

        return opf

    @staticmethod
    def parse_toc(l, c=0, mx=0):
        r = ""
        for cc in l:
            c += 1
            depth = int(cc.get("depth", 0))
            if depth > mx:
                mx = depth

            # Derive a stable ID and href from v2 fields.
            reference_id = cc.get("reference_id", "")
            href = reference_id.split("-/", 1)[-1] if "-/" in reference_id else reference_id
            fragment = cc.get("fragment", "")
            ourn = cc.get("ourn", "")
            nav_id = fragment or ourn or href or "navpoint-{0}".format(c)

            # Build the content src with fragment for proper navigation
            file_href = href.replace(".html", ".xhtml").split("/")[-1]
            if fragment and file_href:
                content_src = "{0}#{1}".format(file_href, fragment)
            else:
                content_src = file_href

            r += "<navPoint id=\"{0}\" playOrder=\"{1}\">" \
                 "<navLabel><text>{2}</text></navLabel>" \
                 "<content src=\"{3}\"/>".format(
                    nav_id, c,
                    escape(cc.get("title", "")), content_src
                 )

            if cc["children"]:
                sr, c, mx = SafariBooks.parse_toc(cc["children"], c, mx)
                r += sr

            r += "</navPoint>\n"

        return r, c, mx

    def create_toc(self):
        response = self.requests_provider(urljoin(self.api_url, "table-of-contents/"))
        if response == 0:
            self.display.exit("API: unable to retrieve book chapters. "
                              "Don't delete any files, just run again this program"
                              " in order to complete the `.epub` creation!")

        response = response.json()

        if not isinstance(response, list):
            self.display.exit(
                self.display.api_error(response) +
                " Don't delete any files, just run again this program"
                " in order to complete the `.epub` creation!"
            )

        navmap, _, max_depth = self.parse_toc(response)
        return self.TOC_NCX.format(
            (self.book_info["isbn"] if self.book_info["isbn"] else self.book_id),
            max_depth,
            self.book_title,
            ", ".join(aut.get("name", "") for aut in self.book_info.get("authors", [])),
            navmap
        )

    def create_pdf(self):
        if self.pdf_profile is None:
            self.pdf_profile = analyze_book_layout(self.BOOK_PATH, self.book_id)

        pdf_path = os.path.join(self.BOOK_PATH, self.book_id + ".pdf")
        rendered_path = render_book_to_pdf(
            self.BOOK_PATH,
            output_path=pdf_path,
            profile=self.pdf_profile,
            display=self.display,
        )
        if not rendered_path:
            self.display.exit("PDF creation failed for this book.")

        return rendered_path

    def create_epub(self):
        open(os.path.join(self.BOOK_PATH, "mimetype"), "w").write("application/epub+zip")
        meta_info = os.path.join(self.BOOK_PATH, "META-INF")
        if os.path.isdir(meta_info):
            self.display.log("META-INF directory already exists: %s" % meta_info)

        else:
            os.makedirs(meta_info)

        open(os.path.join(meta_info, "container.xml"), "wb").write(
            self.CONTAINER_XML.encode("utf-8", "xmlcharrefreplace")
        )
        open(os.path.join(self.BOOK_PATH, "OEBPS", "content.opf"), "wb").write(
            self.create_content_opf().encode("utf-8", "xmlcharrefreplace")
        )
        open(os.path.join(self.BOOK_PATH, "OEBPS", "toc.ncx"), "wb").write(
            self.create_toc().encode("utf-8", "xmlcharrefreplace")
        )

        zip_file = os.path.join(PATH, "Books", self.book_id)
        if os.path.isfile(zip_file + ".zip"):
            os.remove(zip_file + ".zip")

        shutil.make_archive(zip_file, 'zip', self.BOOK_PATH)
        epub_path = os.path.join(self.BOOK_PATH, self.book_id) + ".epub"
        os.rename(zip_file + ".zip", epub_path)
        return epub_path


# MAIN
if __name__ == "__main__":
    arguments = argparse.ArgumentParser(prog="safaribooks.py",
                                        description="Download and generate an EPUB of your favorite books"
                                                    " from Safari Books Online, or render PDF output when requested.",
                                        add_help=False,
                                        allow_abbrev=False)

    login_arg_group = arguments.add_mutually_exclusive_group()
    login_arg_group.add_argument(
        "--cred", metavar="<EMAIL:PASS>", default=False,
        help="Credentials used to perform the auth login on Safari Books Online."
             " Es. ` --cred \"account_mail@mail.com:password01\" `."
    )
    login_arg_group.add_argument(
        "--login", action='store_true',
        help="Prompt for credentials used to perform the auth login on Safari Books Online."
    )

    arguments.add_argument(
        "--no-cookies", dest="no_cookies", action='store_true',
        help="Prevent your session data to be saved into `cookies.json` file."
    )
    arguments.add_argument(
        "--kindle", dest="kindle", action='store_true',
        help="Add some CSS rules that block overflow on `table` and `pre` elements."
             " Use this option if you're going to export the EPUB to E-Readers like Amazon Kindle."
    )
    arguments.add_argument(
        "--output-pdf", "--output-to-pdf", dest="output_pdf", type=int, choices=[0, 1], default=None,
        help="Render PDF output using the separate PDF renderer instead of packaging an EPUB."
             " Use `1` to also create the EPUB; omit the value or use `0` for PDF only."
    )
    arguments.add_argument(
        "--preserve-log", dest="log", action='store_true', help="Leave the `info_XXXXXXXXXXXXX.log`"
                                                                " file even if there isn't any error."
    )
    arguments.add_argument("--help", action="help", default=argparse.SUPPRESS, help='Show this help message.')
    arguments.add_argument(
           "bookid", metavar='<BOOK ID>', nargs='+',
           help="One or more book digits IDs that you want to download."
               " You can find them in the URL (X-es):"
               " `" + SAFARI_BASE_URL + "/library/view/book-name/XXXXXXXXXXXXX/`"
    )

    args_parsed = arguments.parse_args(normalize_output_pdf_args(sys.argv[1:]))
    if args_parsed.cred or args_parsed.login:
        print("WARNING: Due to recent changes on ORLY website, \n" \
                "the `--cred` and `--login` options are temporarily disabled.\n"
                "    Please use the `cookies.json` file to authenticate your account.\n"
                "    See: https://github.com/lorenzodifuccia/safaribooks/issues/358")
        arguments.exit()
        
        # user_email = ""
        # pre_cred = ""

        # if args_parsed.cred:
        #     pre_cred = args_parsed.cred

        # else:
        #     user_email = input("Email: ")
        #     passwd = getpass.getpass("Password: ")
        #     pre_cred = user_email + ":" + passwd

        # parsed_cred = SafariBooks.parse_cred(pre_cred)

        # if not parsed_cred:
        #     arguments.error("invalid credential: %s" % (
        #         args_parsed.cred if args_parsed.cred else (user_email + ":*******")
        #     ))

        # args_parsed.cred = parsed_cred

    else:
        if args_parsed.no_cookies:
            arguments.error("invalid option: `--no-cookies` is valid only if you use the `--cred` option")

    raw_book_ids = []
    for raw_book_id in args_parsed.bookid:
        raw_book_ids.extend(raw_book_id.split(","))

    book_ids = [book_id.strip() for book_id in raw_book_ids if book_id.strip()]
    failed_ids = []
    batch_pause_seconds = 5

    for index, book_id in enumerate(book_ids, 1):
        current_args = argparse.Namespace(**vars(args_parsed))
        current_args.bookid = book_id

        try:
            SafariBooks(current_args)
        except SystemExit as exit_error:
            exit_code = exit_error.code if isinstance(exit_error.code, int) else 1
            if exit_code:
                failed_ids.append(book_id)

        if index < len(book_ids):
            print("Waiting %ss before the next book to reduce rate limiting..." % batch_pause_seconds)
            time.sleep(batch_pause_seconds)

    if failed_ids:
        print("Failed book IDs: %s" % ", ".join(failed_ids), file=sys.stderr)
        sys.exit(1)

    # Hint: do you want to download more then one book once, initialized more than one instance of `SafariBooks`...
    sys.exit(0)
