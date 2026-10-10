# Third-party notices

The browser tool contains no bundled third-party JavaScript, fonts, CDN assets,
or image libraries. Its image processing and store-only ZIP code are original.

The optional Python CLI and test fixture generator use separately installed
dependencies. Their own licenses apply to those packages:

| Dependency | Upstream | License |
| --- | --- | --- |
| NumPy | https://github.com/numpy/numpy | BSD-3-Clause |
| SciPy | https://github.com/scipy/scipy | BSD-3-Clause |
| Pillow | https://github.com/python-pillow/Pillow | MIT-CMU (older releases: HPND) |

No dependency source code or wheels are redistributed in this snapshot.
Binary wheels can contain additional libraries; preserve the license notices
supplied by their distributors when redistributing those wheels.

All included example images are generated from mathematical curves by
`test/generate_fixtures.py`. They contain no real handwriting, names, or
signatures and are covered by this project's MIT license.
