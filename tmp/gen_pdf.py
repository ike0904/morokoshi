# -*- coding: utf-8 -*-
"""Generate PDF from markdown using Playwright (headless Chromium)."""
import subprocess, sys, os, pathlib

DOCS = pathlib.Path(r"E:\Users\takashi\Desktop\ClaudeCode\morokoshi\docs")
MD   = DOCS / "morokoshi_readme.md"
CSS  = DOCS / "readme_style.css"
HTML = DOCS / "_tmp_readme.html"
PDF  = DOCS / "morokoshi_readme.pdf"

# 1. Convert MD → HTML with pandoc
result = subprocess.run(
    ["pandoc", str(MD), "-o", str(HTML),
     "--standalone",
     f"--css={CSS.name}",
     "--metadata", "pagetitle=もろこしタイム ユーザーマニュアル",
     "--from=markdown+raw_html",
    ],
    capture_output=True, text=True, cwd=str(DOCS)
)
if result.returncode != 0:
    print("pandoc error:", result.stderr)
    sys.exit(1)
print("HTML generated:", HTML)

# 2. Print HTML → PDF with Playwright Chromium
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(HTML.as_uri())
    page.wait_for_load_state("networkidle")
    page.pdf(
        path=str(PDF),
        format="A4",
        margin={"top": "15mm", "bottom": "15mm", "left": "18mm", "right": "18mm"},
        print_background=True,
    )
    browser.close()
    print("PDF generated:", PDF)

# cleanup
HTML.unlink(missing_ok=True)
