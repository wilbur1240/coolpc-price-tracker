#!/usr/bin/env python3
"""Parse CoolPC evaluate.php (saved HTML, Big5/UTF-8) or browser-extracted JSON
into normalized [{cat, group, name, price}] JSON."""
import sys, json, re, html as H
from html.parser import HTMLParser

PRICE = re.compile(r'\$\s*([\d,]+)')

def norm(cat, group, text):
    text = H.unescape(text).strip()
    m = PRICE.findall(text)
    if not m:
        return None
    price = int(m[-1].replace(',', ''))          # "$6990↘$5990" -> last one
    name = PRICE.split(text)[0].rstrip(' ,，↘').strip()
    return {"cat": cat.strip(), "group": group.strip(), "name": name, "price": price}

class P(HTMLParser):
    def __init__(s):
        super().__init__(); s.out=[]; s.cat=''; s.in_td=False; s.td_buf=''
        s.group=''; s.in_opt=False; s.opt=''; s.in_select=False; s.got_cat=False
    def handle_starttag(s, t, a):
        a = dict(a)
        if t == 'tr': s.cat=''; s.got_cat=False
        elif t == 'td' and not s.got_cat and 't' in (a.get('class') or '').split(): s.in_td=True; s.td_buf=''
        elif t == 'select': s.in_select=True; s.group=''
        elif t == 'optgroup': s.group=a.get('label','')
        elif t == 'option' and s.in_select: s.in_opt=True; s.opt=''
    def handle_endtag(s, t):
        if t == 'td' and s.in_td:
            s.in_td=False
            if s.td_buf.strip(): s.cat=s.td_buf.strip(); s.got_cat=True
        elif t == 'option' and s.in_opt: s.flush()
        elif t == 'select': s.in_select=False
    def flush(s):
        s.in_opt=False
        r = norm(s.cat, s.group, s.opt)
        if r: s.out.append(r)
    def handle_data(s, d):
        if s.in_opt: s.opt += d
        elif s.in_td and not s.in_select: s.td_buf += d

def load_html(path):
    raw = open(path, 'rb').read()
    for enc in ('utf-8', 'cp950', 'big5hkscs'):
        try: return raw.decode(enc)
        except UnicodeDecodeError: pass
    return raw.decode('cp950', 'replace')

def main(src, dst):
    if src.endswith('.txt'):            # "分類|價格|品名" lines from the browser snippet
        out = []
        for line in open(src, encoding='utf-8'):
            p = line.rstrip('\n').split('|', 2)
            if len(p) == 3 and p[1].isdigit():
                out.append({"cat": p[0], "group": "", "name": p[2], "price": int(p[1])})
    elif src.endswith('.json'):
        rows = json.load(open(src, encoding='utf-8'))
        out = [r for r in (norm(x.get('cat',''), x.get('group',''), x['text']) for x in rows) if r]
    else:
        p = P(); p.feed(load_html(src)); out = p.out
    json.dump(out, open(dst, 'w', encoding='utf-8'), ensure_ascii=False)
    cats = {}
    for r in out: cats[r['cat']] = cats.get(r['cat'], 0) + 1
    print(f"{len(out)} priced items"); [print(f"  {c}: {n}") for c, n in cats.items()]

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
