#!/usr/bin/env python3
"""Build the landing page: inject the recorded demo session into page.html.

Writes site/index.html (a complete document, for GitHub Pages) and, with --fragment PATH, the same
page without the document wrapper.
"""
import json
import pathlib
import sys

here = pathlib.Path(__file__).parent
transcript = json.loads((here.parent / "docs" / "assets" / "demo-transcript.json").read_text())
page = (here / "page.html").read_text().replace("/*TRANSCRIPT*/null", json.dumps(transcript))
head, _, body = page.partition("</style>")
document = (
    '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
    '<meta name="description" content="Offload: the model on your own GPU does the typing. '
    'Claude only plans, reviews and rescues. Open source, with receipts.">\n'
    f"{head}</style>\n</head>\n<body>{body}</body>\n</html>\n"
)
(here / "index.html").write_text(document)
if "--fragment" in sys.argv:
    pathlib.Path(sys.argv[sys.argv.index("--fragment") + 1]).write_text(page)
print("built", here / "index.html", len(document), "bytes")
