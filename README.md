EDITS:
This is a fork modified for v2 api of oreilly and it's sometimes imperfect.
safaribooks.py -> Works vor api v2 for most books
safaribooks_method_b.py -> Alternative method to run if previous script fails

Explanation:
It just so happens that they heavily modified the api and how books are served.
Therefore as soon as you downloaded a book I suggest you to check out if it works: Check if TOC is correct, if TOC links work, if pages are missing or not present at all and differ from the
page number specified in the book home page.

Both methods work for certain types of books. There are some books which still give me troubles and won't download correctly.
PR are welcome about that or about global fixing so we can have a single script.

I will work my way through the non working books as soon as I meet them.

Paciox 08/05/26

+++Fixed++++
As of now all my test return success. Might be some edge cases that still fail but it works now

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

---

## Overview:
  * [Requirements & Setup](#requirements--setup)
  * [Usage](#usage)
  * [Single Sign-On (SSO), Company, University Login](https://github.com/lorenzodifuccia/safaribooks/issues/150#issuecomment-555423085)
  * [Calibre EPUB conversion](https://github.com/lorenzodifuccia/safaribooks#calibre-epub-conversion)
  * [Example: Download *Test-Driven Development with Python, 2nd Edition*](#download-test-driven-development-with-python-2nd-edition)
  * [Example: Use or not the `--kindle` option](#use-or-not-the---kindle-option)

## Requirements & Setup:
You need Python 3 installed first. For normal reflowable books, the script only needs the base Python dependencies from `requirements.txt`. For fixed-layout books, the script may generate a compatibility PDF instead of an EPUB, and that requires extra packages plus a Chromium browser installed by Playwright.

The dependencies are split into two groups:

- Base EPUB dependencies: always needed.
  - `requests`: downloads metadata, chapters, CSS, images, and other book assets.
  - `lxml`: parses the downloaded HTML/XML and builds the EPUB structure.
- Optional PDF dependencies: only needed for fixed-layout books.
  - `playwright`: renders the downloaded XHTML/CSS with Chromium, which handles complex fixed-layout pages much better than many EPUB readers.
  - `Pillow`: combines the rendered page images into the final PDF.
  - `chromium` via `playwright install chromium`: the `playwright` Python package does not ship the browser executable by itself, so this extra step downloads the actual browser runtime used for rendering.

### Option 1: plain `pip`
```shell
$ git clone https://github.com/lorenzodifuccia/safaribooks.git
$ cd safaribooks/
$ pip3 install -r requirements.txt
```

If you also want fixed-layout PDF support:
```shell
$ pip3 install Pillow playwright
$ python3 -m playwright install chromium
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

If you also want fixed-layout PDF support inside that same virtual environment:
```powershell
python -m pip install Pillow playwright
python -m playwright install chromium
```

If you prefer not to activate the virtual environment, you can still install everything into it explicitly:
```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m pip install Pillow playwright
venv\Scripts\python.exe -m playwright install chromium
```

### Option 3: `pipenv`
`pipenv` is also fine, but note that the `Pipfile` only covers the base downloader dependencies. The optional PDF stack still needs to be installed explicitly.

```shell
$ pipenv install
$ pipenv shell
$ pip install -r requirements.txt
```

If you also want fixed-layout PDF support:
```shell
$ pip install Pillow playwright
$ python -m playwright install chromium
```

### Important notes about the PDF path
- You do not need `Pillow`, `playwright`, or Chromium for ordinary books that stay on the EPUB path.
- You do need them for fixed-layout books, because this script currently creates a compatibility PDF for those titles instead of trying to ship a broken EPUB.
- Installing the Python package `playwright` inside a virtual environment is enough for the Python side. The Chromium browser binaries downloaded by `python -m playwright install chromium` are managed by Playwright itself, not as normal site-packages files.
- On Linux, Playwright may additionally ask for OS-level libraries. On Windows, the commands above are usually enough.
  
## Usage:
It's really simple to use, just choose a book from the library and replace in the following command:
  * X-es with its ID, 
  * `email:password` with your own. 

```shell
$ python3 safaribooks.py --cred "account_mail@mail.com:password01" XXXXXXXXXXXXX
```

The ID is the digits that you find in the URL of the book description page:  
`https://www.safaribooksonline.com/library/view/book-name/XXXXXXXXXXXXX/`  
Like: `https://www.safaribooksonline.com/library/view/test-driven-development-with/9781491958698/`  
  
#### Program options:
```shell
$ python3 safaribooks.py --help
usage: safaribooks.py [--cred <EMAIL:PASS> | --login] [--no-cookies]
                      [--kindle] [--preserve-log] [--help]
                      <BOOK ID>

Download and generate an EPUB of your favorite books from Safari Books Online.

positional arguments:
  <BOOK ID>            Book digits ID that you want to download. You can find
                       it in the URL (X-es):
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
  --preserve-log       Leave the `info_XXXXXXXXXXXXX.log` file even if there
                       isn't any error.
  --help               Show this help message.
```
  
The first time you use the program, you'll have to specify your Safari Books Online account credentials (look [`here`](/../../issues/15) for special character).  
The next times you'll download a book, before session expires, you can omit the credential, because the program save your session cookies in a file called `cookies.json`.  
For **SSO**, please use the `sso_cookies.py` program in order to create the `cookies.json` file from the SSO cookies retrieved by your browser session (please follow [`these steps`](/../../issues/150#issuecomment-555423085)).  
  
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

When the source book is a fixed-layout title, the downloader keeps the original XHTML/CSS untouched on disk, downloads any referenced font files, and renders a PDF with Chromium instead of packaging an EPUB. This is why the optional PDF stack needs both the Python packages and the separate `playwright install chromium` step.
  
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
