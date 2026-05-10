# SafariBooks
Download and generate *EPUB* of your favorite books from [*Safari Books Online*](https://www.safaribooksonline.com) library.  
I'm not responsible for the use of this program, this is only for *personal* and *educational* purpose.  
Before any usage please read the *O'Reilly*'s [Terms of Service](https://learning.oreilly.com/terms/).  

<a href='https://ko-fi.com/Y8Y0MPEGU' target='_blank'><img height='80' style='border:0px;height:60px;' src='https://storage.ko-fi.com/cdn/kofi6.png?v=6' border='0' alt='Buy Me a Coffee at ko-fi.com'/></a>

## ✨✨ *Attention needed* ✨✨
- This project is no longer actively maintained.  
- *Login through `safaribooks` no longer works due to changes in ORLY APIs.*
- *The program needs a major refactor to include new features and integrate new APIs.*
- **However... it still work for downloading books.**  
(Use SSO hack: log in via browser, then copy cookies into `cookies.json`, see below and issues. Love ❤️)

## Compatibility work in this workspace
This workspace keeps the original EPUB downloader path as the default behavior, but adds a separate PDF compatibility path so broken-layout books can be handled without destabilizing the normal EPUB flow.

The main additions are:
- a separate PDF renderer path, isolated from the working EPUB packaging logic
- `--output-pdf` and `--output-to-pdf` to download directly to PDF when needed
- `--output-pdf 1` or `--output-to-pdf 1` to keep the packaged `.epub` alongside the PDF when you want both files
- `convert_to_pdf.py` to convert an already-downloaded book folder or an existing EPUB file to PDF without redownloading
- improved PDF ordering so cover, contents, appendices, and index pages are preserved when they exist in the downloaded source
- automatic PDF fallback for known compatibility cases, such as fixed-layout books or books with many oversized figures and wide tables

### Warning about problematic books
Some books download correctly but still look broken in common EPUB readers. This is usually not a download failure: the XHTML, CSS, images, and chapters are present on disk, but the reader does a poor job rendering that layout.

Typical symptoms include:
- wide images or wide tables being clipped on the right side
- fixed-layout pages relying on absolute positioning, with text overlays rendered badly or missing in some readers
- books that technically open as EPUB, but are uncomfortable to read because figures, code blocks, or page composition are not respected

When that happens, PDF is often the safest workaround because Chromium renders the original downloaded XHTML/CSS more faithfully than many EPUB readers.

You can solve it in either of these ways:
- use `python safaribooks.py --output-pdf <BOOK_ID>` while downloading the book
- use `python safaribooks.py --output-to-pdf 1 <BOOK_ID>` if you want the PDF and the packaged EPUB from the same download
- use `python convert_to_pdf.py <BOOK_FOLDER_OR_EXISTING_EPUB>` later if you already downloaded the book and do not want to redownload it

### Practical repair workflow for a broken book
If a book is already downloaded and the problem is only the final reading experience in your EPUB reader, the fastest fix is usually to convert that existing download to PDF.

This is the typical workflow on Windows when using the local `venv`:

```powershell
venv\Scripts\python.exe -m pip install Pillow playwright
venv\Scripts\python.exe -m playwright install chromium
venv\Scripts\python.exe convert_to_pdf.py "Books\Some Book (1234567890123)"
```

If you want to convert the EPUB file directly and choose the destination PDF name yourself:

```powershell
venv\Scripts\python.exe convert_to_pdf.py "Books\Some Book (1234567890123)\1234567890123.epub" "Books\Some Book (1234567890123)\1234567890123-fixed.pdf"
```

Activation is optional. Running `venv\Scripts\python.exe ...` already uses the virtual environment directly, so installs and commands go into that `venv`, not into the global Python installation.

If Playwright prints a message such as `Please run the following command to download new browsers: playwright install`, it means the Python package is installed but the browser runtime is not yet available. Run:

```powershell
venv\Scripts\python.exe -m playwright install chromium
```

This repair path is meant for books that are downloaded correctly but rendered badly by an EPUB reader. It does not restore content that was never downloaded in the first place.

---

## Overview:
  * [Requirements & Setup](#requirements--setup)
  * [Usage](#usage)
  * [Single Sign-On (SSO), Company, University Login](https://github.com/lorenzodifuccia/safaribooks/issues/150#issuecomment-555423085)
  * [Calibre EPUB conversion](https://github.com/lorenzodifuccia/safaribooks#calibre-epub-conversion)
  * [Example: Download *Test-Driven Development with Python, 2nd Edition*](#download-test-driven-development-with-python-2nd-edition)
  * [Example: Use or not the `--kindle` option](#use-or-not-the---kindle-option)

## Requirements & Setup:
You need Python 3 installed first. For normal reflowable books, the downloader only needs the base Python dependencies from `requirements.txt`. PDF generation is now handled by a separate renderer path, used either when you explicitly ask for PDF output or when the downloader detects a book layout that common EPUB readers are likely to break.

The dependencies are split into two groups:

- Base EPUB dependencies: always needed.
  - `requests`: downloads metadata, chapters, CSS, images, and other book assets.
  - `lxml`: parses the downloaded HTML/XML and builds the EPUB structure.
- Optional PDF dependencies: only needed when you use `--output-pdf`, `convert_to_pdf.py`, or when the downloader automatically falls back to PDF for a compatibility case.
  - `playwright`: renders the downloaded XHTML/CSS with Chromium, which handles complex layouts, wide images, and fixed-layout pages much better than many EPUB readers.
  - `Pillow`: combines page screenshots into the final PDF for fixed-layout books.
  - `chromium` via `playwright install chromium`: the `playwright` Python package does not ship the browser executable by itself, so this extra step downloads the actual browser runtime used for rendering.
- Optional cookie helper dependency: only needed if you want to generate `cookies.json` automatically from an already logged-in browser session.
  - `browser_cookie3`: reads cookies from supported local browsers so `retrieve_cookies.py` can export the O'Reilly session cookies directly into `cookies.json`.

### Option 1: plain `pip`
```shell
$ git clone https://github.com/lorenzodifuccia/safaribooks.git
$ cd safaribooks/
$ pip3 install -r requirements.txt
```

If you also want PDF support:
```shell
$ pip3 install Pillow playwright
$ python3 -m playwright install chromium
```

If you also want the browser cookie helper:
```shell
$ pip3 install browser_cookie3
$ python3 retrieve_cookies.py
```

### Option 2: recommended `venv`
Using a virtual environment is fully supported and is the safest approach, because it keeps this project's Python packages isolated from the rest of your system.

On Windows PowerShell:
```powershell
py -3 -m venv venv
venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If you also want PDF support inside that same virtual environment:
```powershell
python -m pip install Pillow playwright
python -m playwright install chromium
```

Equivalent explicit commands without activating the virtual environment first:

```powershell
venv\Scripts\python.exe -m pip install Pillow playwright
venv\Scripts\python.exe -m playwright install chromium
```

If you also want the browser cookie helper inside that same virtual environment:
```powershell
python -m pip install browser_cookie3
python retrieve_cookies.py
```

If you prefer not to activate the virtual environment, you can still install everything into it explicitly:
```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install Pillow playwright
venv\Scripts\python.exe -m playwright install chromium
venv\Scripts\python.exe -m pip install browser_cookie3
venv\Scripts\python.exe retrieve_cookies.py
```

### Option 3: `pipenv`
`pipenv` is also fine, but note that the `Pipfile` only covers the base downloader dependencies. The optional PDF stack still needs to be installed explicitly.

```shell
$ pipenv install
$ pipenv shell
$ pip install -r requirements.txt
```

If you also want PDF support:
```shell
$ pip install Pillow playwright
$ python -m playwright install chromium
```

If you also want the browser cookie helper:
```shell
$ pip install browser_cookie3
$ python retrieve_cookies.py
```

### Important notes about the PDF path
- You do not need `Pillow`, `playwright`, or Chromium for ordinary books that stay on the EPUB path.
- You do need them for any explicit PDF conversion and for books that are automatically routed to PDF because their layout is known to break in EPUB readers.
- If a book is already downloaded and the problem is only the way your EPUB reader renders it, converting the existing folder or `.epub` file to PDF is usually enough. A redownload is not normally required.
- Direct `--output-pdf` or `--output-to-pdf` mode defaults to PDF-only. If you want the downloader to also package the `.epub`, pass `1`, for example `--output-to-pdf 1`.
- Install and run the PDF stack in the same Python environment. If you launch `venv\Scripts\python.exe safaribooks.py --output-pdf ...`, install `Pillow` and `playwright` and run `playwright install chromium` with that same `venv\Scripts\python.exe` as well.
- You do not need to activate the virtual environment if you call its interpreter explicitly. `venv\Scripts\python.exe -m pip ...` and `venv\Scripts\python.exe convert_to_pdf.py ...` already use that `venv` directly.
- Installing the Python package `playwright` inside a virtual environment is enough for the Python side. The Chromium browser binaries downloaded by `python -m playwright install chromium` are managed by Playwright itself, not as normal site-packages files.
- If Playwright says it was installed or updated and asks you to run `playwright install`, do that with the same interpreter you plan to use for conversion, for example `venv\Scripts\python.exe -m playwright install chromium`.
- On Linux, Playwright may additionally ask for OS-level libraries. On Windows, the commands above are usually enough.
- The separated PDF entry points are:
  - `python safaribooks.py --output-pdf <BOOK_ID>` to download and render directly to PDF.
  - `python convert_to_pdf.py <BOOK_ID_OR_BOOK_FOLDER>` to convert an already-downloaded book folder to PDF.
  - `python convert_to_pdf.py <PATH_TO_EXISTING_EPUB>` to convert an existing EPUB file to PDF without redownloading.
- The downloader may also auto-select PDF for known compatibility cases, such as fixed-layout books and books with many oversized figures/tables that are commonly clipped in EPUB readers.
- When the downloaded source contains `default_cover.xhtml`, `contents.xhtml`, appendices, or index pages, the separate PDF renderer preserves that reading order in the generated PDF and rewrites TOC links to point at the merged PDF content.
- If a downloaded book folder already contains `OEBPS`, `META-INF`, or an `.epub` file, you can reuse those local files directly. You do not need to redownload the book just to try the PDF path.
  
## Usage:
It's really simple to use, just choose a book from the library and replace in the following command:
  * X-es with its ID, 
  * `email:password` with your own. 

```shell
$ python3 safaribooks.py --cred "account_mail@mail.com:password01" XXXXXXXXXXXXX
$ python3 safaribooks.py --output-pdf XXXXXXXXXXXXX
$ python3 safaribooks.py --output-to-pdf 1 XXXXXXXXXXXXX
$ python3 safaribooks.py 9781633436541,9781491958698
$ python3 safaribooks.py 9781633436541, 9781491958698 --output-to-pdf
$ python3 safaribooks.py 9781633436541 9781491958698 --output-pdf
$ python3 convert_to_pdf.py XXXXXXXXXXXXX
$ python3 convert_to_pdf.py "/path/to/Books/Some Book (1234567890123)"
$ python3 convert_to_pdf.py "/path/to/Books/Some Book (1234567890123)/1234567890123.epub"
$ python3 convert_to_pdf.py "/path/to/book.epub" "/path/to/book.pdf"
$ venv\Scripts\python.exe -m pip install Pillow playwright
$ venv\Scripts\python.exe -m playwright install chromium
$ venv\Scripts\python.exe convert_to_pdf.py "Books\Some Book (1234567890123)\1234567890123.epub" "Books\Some Book (1234567890123)\1234567890123-fixed.pdf"
```

The ID is the digits that you find in the URL of the book description page:  
`https://www.safaribooksonline.com/library/view/book-name/XXXXXXXXXXXXX/`  
Like: `https://www.safaribooksonline.com/library/view/test-driven-development-with/9781491958698/`  
  
#### Program options:
```shell
$ python3 safaribooks.py --help
usage: safaribooks.py [--cred <EMAIL:PASS> | --login] [--no-cookies]
                      [--kindle] [--output-pdf {0,1}] [--preserve-log]
                      [--help]
                      <BOOK ID> [<BOOK ID> ...]

Download and generate an EPUB of your favorite books from Safari Books Online,
or render PDF output when requested.

positional arguments:
  <BOOK ID>            One or more book digits IDs that you want to download.
                       You can find them in the URL (X-es):
                       `https://learning.oreilly.com/library/view/book-
                       name/XXXXXXXXXXXXX/`

optional arguments:
  --cred <EMAIL:PASS>  Credentials used to perform the auth login on Safari
                       Books Online. Es. ` --cred
                       "account_mail@mail.com:password01" `.
  --login              Prompt for credentials used to perform the auth login
                       on Safari Books Online.
  --no-cookies         Prevent your session data to be saved into
                       `cookies.json` file.
  --kindle             Add some CSS rules that block overflow on `table` and
                       `pre` elements. Use this option if you're going to
                       export the EPUB to E-Readers like Amazon Kindle.
  --output-pdf, --output-to-pdf {0,1}
                       Render PDF output using the separate PDF renderer
                       instead of packaging an EPUB. Use `1` to also create
                       the EPUB; omit the value or use `0` for PDF only.
  --preserve-log       Leave the `info_XXXXXXXXXXXXX.log` file even if there
                       isn't any error.
  --help               Show this help message.
```

`<BOOK ID>` accepts single IDs, multiple space-separated IDs, multiple comma-separated IDs, or a mix of both. For example, all of the following are valid:

```shell
$ python3 safaribooks.py 9781633436541,9781491958698
$ python3 safaribooks.py 9781633436541 9781491958698
$ python3 safaribooks.py 9781633436541, 9781491958698 --output-to-pdf
```

The downloader will process them sequentially and wait briefly between books to reduce rate limiting.
  
The first time you use the program, you'll have to specify your Safari Books Online account credentials (look [`here`](/../../issues/15) for special character).  
The next times you'll download a book, before session expires, you can omit the credential, because the program save your session cookies in a file called `cookies.json`.  
For **SSO**, use the `retrieve_cookies.py` helper to create `cookies.json` from the cookies already stored in your browser session. Install `browser_cookie3` first if needed, then run `python retrieve_cookies.py` after you have logged into `learning.oreilly.com` in your browser (please follow [`these steps`](/../../issues/150#issuecomment-555423085)).  
  
Pay attention if you use a shared PC, because everyone that has access to your files can steal your session. 
If you don't want to cache the cookies, just use the `--no-cookies` option and provide all time your credential through the `--cred` option or the more safe `--login` one: this will prompt you for credential during the script execution.

You can configure proxies by setting on your system the environment variable `HTTPS_PROXY` or using the `USE_PROXY` directive into the script.

#### Calibre EPUB conversion
**Important**: since the script only download HTML pages and create a raw EPUB, many of the CSS and XML/HTML directives are wrong for an E-Reader. To ensure best quality of the output, I suggest you to always convert the `EPUB` obtained by the script to standard-`EPUB` with [Calibre](https://calibre-ebook.com/).
You can also use the command-line version of Calibre with `ebook-convert`, e.g.:
```bash
$ ebook-convert "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698.epub" "XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)/9781491958698_CLEAR.epub"
```
After the execution, you can read the `9781491958698_CLEAR.epub` in every E-Reader and delete all other files.

The program offers also an option to ensure best compatibilities for who wants to export the `EPUB` to E-Readers like Amazon Kindle: `--kindle`, it blocks overflow on `table` and `pre` elements (see [example](#use-or-not-the---kindle-option)).  
In this case, I suggest you to convert the `EPUB` to `AZW3` with Calibre or to `MOBI`, remember in this case to select `Ignore margins` in the conversion options:  

When the source book is a fixed-layout title, or when it is detected as a compatibility case with many oversized figures/tables, the downloader keeps the original XHTML/CSS untouched on disk and routes that book through the separate PDF renderer. This is why the optional PDF stack needs both the Python packages and the separate `playwright install chromium` step.
  
![Calibre IgnoreMargins](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_calibre_IgnoreMargins.png "Select Ignore margins")  
  
## Examples:
  * ## Download [Test-Driven Development with Python, 2nd Edition](https://www.safaribooksonline.com/library/view/test-driven-development-with/9781491958698/):  
    ```shell
    $ python3 safaribooks.py --cred "my_email@gmail.com:MyPassword1!" 9781491958698

           ____     ___         _ 
          / __/__ _/ _/__ _____(_)
         _\ \/ _ `/ _/ _ `/ __/ / 
        /___/\_,_/_/ \_,_/_/ /_/  
          / _ )___  ___  / /__ ___
         / _  / _ \/ _ \/  '_/(_-<
        /____/\___/\___/_/\_\/___/

    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    [-] Logging into Safari Books Online...
    [*] Retrieving book info... 
    [-] Title: Test-Driven Development with Python, 2nd Edition                     
    [-] Authors: Harry J.W. Percival                                                
    [-] Identifier: 9781491958698                                                   
    [-] ISBN: 9781491958704                                                         
    [-] Publishers: O'Reilly Media, Inc.                                            
    [-] Rights: Copyright © O'Reilly Media, Inc.                                    
    [-] Description: By taking you through the development of a real web application 
    from beginning to end, the second edition of this hands-on guide demonstrates the 
    practical advantages of test-driven development (TDD) with Python. You’ll learn 
    how to write and run tests before building each part of your app, and then develop
    the minimum amount of code required to pass those tests. The result? Clean code
    that works.In the process, you’ll learn the basics of Django, Selenium, Git, 
    jQuery, and Mock, along with curre...
    [-] Release Date: 2017-08-18
    [-] URL: https://learning.oreilly.com/library/view/test-driven-development-with/9781491958698/
    [*] Retrieving book chapters...                                                 
    [*] Output directory:                                                           
        /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition (9781491958698)
    [-] Downloading book contents... (53 chapters)                                  
        [#####################################################################] 100%
    [-] Downloading book CSSs... (2 files)                                          
        [#####################################################################] 100%
    [-] Downloading book images... (142 files)                                      
        [#####################################################################] 100%
    [-] Creating EPUB file...                                                       
    [*] Done: /XXXX/safaribooks/Books/Test-Driven Development with Python 2nd Edition 
    (9781491958698)/9781491958698.epub
    
        If you like it, please * this project on GitHub to make it known:
            https://github.com/lorenzodifuccia/safaribooks
        e don't forget to renew your Safari Books Online subscription:
            https://learning.oreilly.com
    
    [!] Bye!!
    ```  
     The result will be (opening the `EPUB` file with Calibre):  

    ![Book Appearance](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example01_TDD.png "Book opened with Calibre")  
 
  * ## Use or not the `--kindle` option:
    ```bash
    $ python3 safaribooks.py --kindle 9781491958698
    ```  
    On the right, the book created with `--kindle` option, on the left without (default):  
    
    ![NoKindle Option](https://github.com/lorenzodifuccia/cloudflare/raw/master/Images/safaribooks/safaribooks_example02_NoKindle.png "Version compare")  
    
---  
  
## Thanks!!
For any kind of problem, please don't hesitate to open an issue here on *GitHub*.  
  
*Lorenzo Di Fuccia*
