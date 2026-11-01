# -*- coding: utf-8 -*-
"""UI language support for Morokoshi Time.

The English text written in morokoshi.py is the key; each language module maps it to its
translation. Missing entries fall back to English, so a language file may be partial.

Keys may contain {0}, {1}, ... for parts that change at run time (file names, numbers).
tr() matches such texts against these templates and translates the parts again
(so "Tempo" inside a tooltip header is translated too).

To add a language:
  1. copy ja.py to <code>.py (e.g. fr.py) and translate the values
  2. add (code, name shown in the menu, module.STRINGS) to LANGUAGES below
"""
import re

from . import ja

LANGUAGES = [
    ("en", "English", {}),
    ("ja", "日本語", ja.STRINGS),
]

_cur = "en"
_table = {}
_templates = []


def codes():
    return [c for c, _, _ in LANGUAGES]


def current():
    return _cur


def default_code():
    """OS language when it is supported, otherwise English."""
    try:
        from PyQt6.QtCore import QLocale
        name = QLocale.system().name().split("_")[0].lower()   # "ja_JP" -> "ja"
    except Exception:
        name = "en"
    return name if name in codes() else "en"


def set_language(code):
    global _cur, _table, _templates
    table = next((t for c, _, t in LANGUAGES if c == code), None)
    if table is None:
        code, table = "en", {}
    _cur, _table = code, table
    _templates = []
    for key, val in table.items():
        if re.search(r"\{\d+\}", key):
            parts = re.split(r"(\{\d+\})", key)
            rx = "".join("(.*?)" if re.fullmatch(r"\{\d+\}", p) else re.escape(p) for p in parts)
            fixed = len(re.sub(r"\{\d+\}", "", key))
            _templates.append((fixed, re.compile(rx + r"\Z", re.S), val))
    # more specific first: "Saved: {0} ({1}s)" before "Saved: {0}"
    _templates.sort(key=lambda t: -t[0])
    _templates = [(rx, val) for _, rx, val in _templates]


def tr(text):
    """Translate a UI text (fixed text or one built from a {n} template)."""
    if not _table or not isinstance(text, str) or not text:
        return text
    t = _table.get(text)
    if t is not None:
        return t
    for rx, val in _templates:
        m = rx.match(text)
        if m:
            try:
                return val.format(*[tr(g) for g in m.groups()])
            except (IndexError, KeyError, ValueError):
                return text
    return text
