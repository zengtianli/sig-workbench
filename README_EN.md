# Sig · Signature workbench

[中文](README.md) | **English**

Turn a photo of dark handwriting on light paper into a transparent PNG for
Word, PDF, and other documents. Images are processed in your own browser and
are never uploaded. The light interface is self-contained, with no CDN,
account, or server dependency.

## Use

[Download the source](https://github.com/zengtianli/sig-workbench/archive/refs/heads/main.zip),
extract it, and open `web/index.html` in a modern browser. No build is required.
You can also clone the [public repository](https://github.com/zengtianli/sig-workbench):

```sh
git clone https://github.com/zengtianli/sig-workbench.git
cd sig-workbench
```

Alternatively, run this from the source root:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

Open <http://127.0.0.1:8000/web/>, drop, select, or paste an image, then download
a transparent PNG. Supported formats depend on your browser's image decoder;
convert HEIC to JPG or PNG if necessary. Output includes 300 dpi metadata.
Ink color, scale, noise removal, and rule-line removal are configurable;
thresholds are adaptive by default.

Your local collection is stored in the current browser's IndexedDB. No
preloaded signature collection is included. Switching devices, browsers, or
private sessions, or clearing browser data may lose saved images. Export your
own backups. Storage behavior for directly opened files varies by browser;
a local server provides a stable origin. Clipboard support also depends on
browser permissions and a secure context; use PNG download if unavailable.

## Settings, shortcuts, and versions

Settings and Updates exports/imports portable JSON preferences. Processing parameters and both
options persist in this browser's localStorage; exported settings contain no images, accounts,
or permissions. Alt / Option + Shift + S opens settings and can be disabled. Editing controls,
Ctrl / Command combinations, and repeated keys are excluded. Use the button if the browser or
operating system reserves this combination. A plain Web page has no native Apple iCloud
container; transfer preferences by export/import and back up images separately.

Check Updates reads the same-origin version.json. A newer version is obtained by reloading the
same page, preserving preferences and IndexedDB. Startup checks are off by default and can be
enabled. Unavailable or malformed version information produces an explicit failure. For file://
fetch restrictions, use the local server described above.

Node reads the same exported settings format and source version without opening a user browser profile:

```sh
node tools/sig_config.cjs config status --config ./exported-sig.json --json
node tools/sig_config.cjs config import --config ./portable-sig.json --input ./exported-sig.json --json
node tools/sig_config.cjs update check --json
```

The complete agent entry is `bin/sig`, without a resident service. Prepare the Python environment below
and set `SIG_PYTHON=.venv/bin/python`. Chrome/Chromium runs the real Web workspace; `CHROME` overrides its path.

```sh
SIG_PYTHON=.venv/bin/python bin/sig status --json
SIG_PYTHON=.venv/bin/python bin/sig extract test/fixtures/sig-a.png --output sample.png --json
SIG_PYTHON=.venv/bin/python bin/sig workspace add --profile ./sig-profile --input test/fixtures/sig-a.png --json
SIG_PYTHON=.venv/bin/python bin/sig workspace export --profile ./sig-profile --output signatures.zip --json
```

Workspace commands use the actual Web IndexedDB and support list, rename, remove, clear,
config-import/config-export, and update. Deletion requires `--yes`. Profiles must be empty or owned
by this tool; ordinary browser profiles are refused. This workspace is separate from daily browsers;
transfer preferences with the same Web JSON and images with exported PNGs. Clipboard permissions and
physical keys remain window-only actions. JSON includes ok:true on success or ok:false/error on failure;
exit codes are 0 success, 1 operation failure, and 2 usage error.

## Optional Python CLI

Requires Python 3.10 or newer. These dependencies are not needed for the web UI:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python engine/sig_extract.py test/fixtures/sig-a.png -o output --preview
```

Pass multiple input files for batch processing, add `--deline` for horizontal
rule removal, or use `--ink blue` to change the ink color. Synthetic examples
are algorithm fixtures and are not anyone's signatures.

## Verification and development

Python and the browser implement the same processing stages: background
normalization, Otsu thresholding, soft alpha, noise removal, optional rule
removal with vertical stroke bridging, cropping, and coloring. Check both
implementations after algorithm changes and run:

```sh
PYTHON=.venv/bin/python ./verify.sh
```

Verification requires Google Chrome or compatible Chromium. The script finds
common executable locations; set `CHROME=/path/to/chromium` to override it.
Browsers run headlessly with separate temporary directories. Numerical and
real-page loading tests run in parallel. Maximum differences are 3 for Otsu
thresholds and 0.6 percentage points for ink coverage. Tests also check the
actual rule-removal delta. Page checks cover image processing, two previews,
action buttons, 300 dpi PNG output, and browser storage. They do not read user
files or the system clipboard.

All fixtures are fictional strokes generated from mathematical curves by
`test/generate_fixtures.py`. Regenerate them with
`.venv/bin/python test/generate_fixtures.py`. Keep the browser core inside an
IIFE, exporting only `window.SigCore`, to avoid global name collisions.

This is a one-way source snapshot from a private development location. It
contains no private history, author assets, deployment configuration, or
access gate. Snapshots are updated when needed. Use the browser tool directly
from source; no installation package is needed.

## License

Original code is licensed under [MIT](LICENSE). See
[THIRD-PARTY-NOTICES](THIRD-PARTY-NOTICES.md) for dependency information.
