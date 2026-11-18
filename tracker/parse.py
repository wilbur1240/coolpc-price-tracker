"""Parse CoolPC evaluate.php HTML into [{cat, group, name, price}].

The page is old-school HTML: <TD class=t> and most <OPTION>s have no closing
tag, so cells/options are terminated implicitly by the next tag.
"""
from __future__ import annotations

import html as H
import re
from html.parser import HTMLParser

# Trailing price block: ", $6650 ★" or ", $6990↘$5990 ◆ ★" (last $ wins)
PRICE_TAIL = re.compile(r',?\s*\$\s*[\d,]+(?:\s*↘\s*\$\s*[\d,]+)*[^$]*$')
PRICE = re.compile(r'\$\s*([\d,]+)')


def parse_option(text: str):
    """Return (name, price) from an option label, or None for notices / no price."""
    text = H.unescape(text).replace('\xa0', ' ').strip()
    if not text or text.startswith('↪'):
        return None
    m = PRICE_TAIL.search(text)
    if not m:
        return None
    nums = PRICE.findall(m.group(0))
    if not nums:
        return None
    price = int(nums[-1].replace(',', ''))
    name = text[:m.start()].strip()
    if not name or price <= 0:
        return None
    return name, price


class _Parser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[dict] = []
        self.cat = ''
        self.group = ''
        self.in_cat_td = False
        self.cat_buf = ''
        self.in_select = False
        self.opt_buf: str | None = None   # None = not inside a usable option

    # -- helpers
    def _end_cat(self):
        if self.in_cat_td:
            self.in_cat_td = False
            name = ' '.join(self.cat_buf.split())
            if name:
                self.cat = name

    def _end_opt(self):
        if self.opt_buf is not None:
            r = parse_option(self.opt_buf)
            if r and self.cat:
                self.rows.append({"cat": self.cat, "group": self.group, "name": r[0], "price": r[1]})
            self.opt_buf = None

    # -- events
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ('td', 'th', 'tr'):
            self._end_cat()
        if tag == 'tr':
            self.cat = ''
        elif tag == 'td' and 't' in (a.get('class') or '').split():
            self.in_cat_td = True
            self.cat_buf = ''
        elif tag == 'select':
            self._end_cat()
            self.in_select = True
            self.group = ''
        elif tag == 'optgroup':
            self._end_opt()
            self.group = (a.get('label') or '').strip()
        elif tag == 'option':
            self._end_opt()
            if self.in_select and 'disabled' not in a:
                self.opt_buf = ''

    def handle_endtag(self, tag):
        if tag == 'td':
            self._end_cat()
        elif tag == 'option':
            self._end_opt()
        elif tag == 'optgroup':
            self._end_opt()
            self.group = ''
        elif tag == 'select':
            self._end_opt()
            self.in_select = False

    def handle_data(self, data):
        if self.opt_buf is not None:
            self.opt_buf += data
        elif self.in_cat_td:
            self.cat_buf += data


def parse_html(text: str) -> list[dict]:
    p = _Parser()
    p.feed(text)
    p.close()
    p._end_opt()
    return p.rows


def parse_pipe_txt(text: str) -> list[dict]:
    """Parse "分類|價格|品名" lines (browser-extracted sample format)."""
    out = []
    for line in text.splitlines():
        p = line.split('|', 2)
        if len(p) == 3 and p[1].strip().isdigit():
            out.append({"cat": p[0].strip(), "group": "", "name": p[2].strip(), "price": int(p[1])})
    return out


def category_counts(rows: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r['cat']] = out.get(r['cat'], 0) + 1
    return out
