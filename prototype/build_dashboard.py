#!/usr/bin/env python3
"""build_dashboard.py config.json snapshot.json history.json out.html [--date YYYY-MM-DD]
Matches config items against today's snapshot, updates history.json in place, writes dashboard HTML."""
import sys, json, datetime, html

def nz(x): return x.lower().replace(' ', '').replace('　', '')

def matches(name, item):
    n = nz(name)
    return all(nz(k) in n for k in item.get('match', [])) and \
           not any(nz(k) in n for k in item.get('exclude', []))

def main():
    a = sys.argv[1:]
    date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date().isoformat()  # Asia/Taipei
    if '--date' in a:
        i = a.index('--date'); date = a[i+1]; del a[i:i+2]
    cfg_p, snap_p, hist_p, out_p = a
    cfg = json.load(open(cfg_p, encoding='utf-8'))
    snap = json.load(open(snap_p, encoding='utf-8'))
    try: hist = json.load(open(hist_p, encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError): hist = {}

    def in_cat(r, cat): return not cat or cat.lower() in r['cat'].lower()
    today_items, total, missing = {}, 0, []
    for it in cfg['items']:
        cands = sorted((r for r in snap if in_cat(r, it.get('category')) and matches(r['name'], it)),
                       key=lambda r: r['price'])
        if cands:
            c = cands[0]; q = it.get('qty', 1)
            today_items[it['slot']] = {"name": c['name'], "price": c['price'], "qty": q, "alts": len(cands) - 1}
            if not it.get('optional'): total += c['price'] * q
        else:
            today_items[it['slot']] = None
            if not it.get('optional'): missing.append(it['slot'])
    cat_min = {}
    for w in cfg.get('watch_categories', []):
        ps = [r['price'] for r in snap if w.lower() in r['cat'].lower()]
        if ps: cat_min[w] = {"min": min(ps), "count": len(ps)}
    hist[date] = {"items": today_items, "total": total, "complete": not missing, "cat_min": cat_min}
    hist = dict(sorted(hist.items()))
    json.dump(hist, open(hist_p, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    dates = list(hist); prev = hist[dates[-2]] if len(dates) > 1 else None
    def fmt(n): return f"{n:,}"
    def delta(cur, old):
        if old is None or cur is None: return '<span class="mut">—</span>'
        d = cur - old
        if d == 0: return '<span class="mut">±0</span>'
        cls = 'dn' if d < 0 else 'up'
        return f'<span class="{cls}">{"▼" if d < 0 else "▲"} {fmt(abs(d))}</span>'

    hits = sum(1 for it in cfg['items'] if today_items.get(it['slot']) and it.get('target_price') is not None and today_items[it['slot']]['price'] <= it['target_price'])
    n_tp = sum(1 for it in cfg['items'] if it.get('target_price') is not None)
    rows = []
    for it in cfg['items']:
        s = it['slot']; t = today_items.get(s)
        lows = [h['items'][s]['price'] for h in hist.values() if h['items'].get(s)]
        old = prev['items'].get(s)['price'] if prev and prev['items'].get(s) else None
        tp = it.get('target_price')
        if t:
            hit = tp is not None and t['price'] <= tp
            rows.append(f"<tr{' class=opt' if it.get('optional') else ''}><td><b>{html.escape(s)}</b>{'<div class=mut>升級選項，不計入總價</div>' if it.get('optional') else ''}</td><td>{html.escape(t['name'])}"
                        + (' <span class=mut>(+%d 個符合)</span>' % t['alts'] if t['alts'] else '') + "</td>"
                        + f"<td class=r>{t['qty']}</td><td class=r>{fmt(t['price'])}</td><td class=r>{delta(t['price'], old)}</td>"
                        f"<td class=r>{fmt(min(lows))}</td><td class=r>{'<span class=hit>✓ ' if hit else ''}{fmt(tp) if tp else '—'}{'</span>' if hit else ''}</td></tr>")
        else:
            rows.append(f"<tr class=miss><td><b>{html.escape(s)}</b></td><td colspan=6>今天在原價屋找不到符合「{html.escape(' '.join(it.get('match', [])))}」的品項（可能缺貨或改名）</td></tr>")

    totals = [(d, h['total']) for d, h in hist.items() if h.get('complete')]
    tgt = cfg.get('target_total')
    # SVG trend
    svg = '<p class=mut>累積兩天以上的完整資料後會出現走勢圖。</p>'
    if len(totals) >= 2:
        W, Hh, pad = 760, 220, 48
        vals = [v for _, v in totals] + ([tgt] if tgt else [])
        lo, hi = min(vals), max(vals); hi = hi if hi > lo else lo + 1
        X = lambda i: pad + i * (W - 2 * pad) / (len(totals) - 1)
        Y = lambda v: Hh - 30 - (v - lo) * (Hh - 60) / (hi - lo)
        pts = ' '.join(f"{X(i):.1f},{Y(v):.1f}" for i, (_, v) in enumerate(totals))
        tl = f'<line x1={pad} x2={W-pad} y1={Y(tgt):.1f} y2={Y(tgt):.1f} class=tgt /><text x={W-pad} y={Y(tgt)-6:.1f} text-anchor=end class=lbl>目標 {fmt(tgt)}</text>' if tgt else ''
        dots = ''.join(f'<circle cx={X(i):.1f} cy={Y(v):.1f} r=3><title>{d}: {fmt(v)}</title></circle>' for i, (d, v) in enumerate(totals))
        svg = (f'<svg viewBox="0 0 {W} {Hh}" class=chart>{tl}<polyline points="{pts}" class=ln />{dots}'
               f'<text x={pad} y={Hh-8} class=lbl>{totals[0][0]}</text><text x={W-pad} y={Hh-8} text-anchor=end class=lbl>{totals[-1][0]}</text>'
               f'<text x=4 y={Y(hi)+4:.1f} class=lbl>{fmt(hi)}</text><text x=4 y={Y(lo)+4:.1f} class=lbl>{fmt(lo)}</text></svg>')

    watch = [r for r in snap if any(w.lower() in r['cat'].lower() for w in cfg.get('watch_categories', []))]
    prev_total = prev['total'] if prev and prev.get('complete') else None
    low_total = min((v for _, v in totals), default=None)
    page = f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8"><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(cfg.get('build_name','目標配置'))} 價格追蹤</title><style>
:root{{--bg:#fafaf9;--fg:#1c1917;--mut:#78716c;--card:#fff;--line:#e7e5e4;--up:#b91c1c;--dn:#15803d;--acc:#2563eb}}
@media(prefers-color-scheme:dark){{:root{{--bg:#1c1917;--fg:#f5f5f4;--mut:#a8a29e;--card:#292524;--line:#44403c;--up:#f87171;--dn:#4ade80;--acc:#60a5fa}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,"Noto Sans TC",sans-serif}}
main{{max-width:1000px;margin:auto;padding:24px 16px}}h1{{font-size:22px;margin:0}}h2{{font-size:17px;margin:28px 0 10px}}
.mut{{color:var(--mut)}}.up{{color:var(--up)}}.dn{{color:var(--dn)}}.hit{{color:var(--dn);font-weight:600}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin-top:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}.card .v{{font-size:22px;font-weight:650;font-variant-numeric:tabular-nums}}
table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}}
th,td{{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}th{{font-size:13px;color:var(--mut);font-weight:500}}
.r{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}tr.miss td{{color:var(--up)}}tr.opt td{{background:color-mix(in srgb,var(--acc) 6%,transparent)}}
.chart{{width:100%;background:var(--card);border:1px solid var(--line);border-radius:10px}}.ln{{fill:none;stroke:var(--acc);stroke-width:2}}
circle{{fill:var(--acc)}}.tgt{{stroke:var(--dn);stroke-dasharray:4 4}}.lbl{{fill:var(--mut);font-size:11px}}
input,select{{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}}
#list td{{font-size:14px}}</style></head><body><main>
<h1>{html.escape(cfg.get('build_name','目標配置'))} 價格追蹤</h1><div class=mut>原價屋線上估價 · 資料日期 {date} · 已追蹤 {len(dates)} 天</div>
<div class=cards>
<div class=card><div class=mut>今日總價{'（有缺項）' if missing else ''}</div><div class=v>NT$ {fmt(total)}</div></div>
<div class=card><div class=mut>較前次</div><div class=v>{delta(total if not missing else None, prev_total)}</div></div>
<div class=card><div class=mut>目標總價</div><div class=v>{('NT$ '+fmt(tgt)) if tgt else '—'}</div>{f'<div class={"dn" if total<=tgt else "up"}>{"已低於目標 " if total<=tgt else "還差 "}{fmt(abs(total-tgt))}</div>' if tgt and not missing else ''}</div>
<div class=card><div class=mut>追蹤以來最低總價</div><div class=v>{('NT$ '+fmt(low_total)) if low_total else '—'}</div></div></div>
<h2>目標配置 <span class=mut style="font-size:14px;font-weight:400">· {hits}/{n_tp} 已達目標價</span></h2><table><tr><th>部件</th><th>今日最便宜的符合品項</th><th class=r>數量</th><th class=r>單價</th><th class=r>較前次</th><th class=r>歷史最低</th><th class=r>目標價</th></tr>{''.join(rows)}</table>
<h2>總價走勢</h2>{svg}
<h2>原價屋今日報價（追蹤分類）</h2>
<div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap"><input id=q placeholder="搜尋型號，例如 4090、DDR5 64G" style="flex:1;min-width:200px"><select id=c><option value="">全部分類</option>{''.join(f'<option>{html.escape(w)}</option>' for w in cfg.get('watch_categories', []))}</select></div>
<table id=list><thead><tr><th>分類</th><th>品項</th><th class=r>價格</th></tr></thead><tbody></tbody></table><div id=more class=mut style="margin-top:6px"></div>
<script>const D={json.dumps(watch, ensure_ascii=False)};
const q=document.getElementById('q'),c=document.getElementById('c'),tb=document.querySelector('#list tbody'),more=document.getElementById('more');
const esc=s=>s.replace(/[&<>]/g,m=>({{'&':'&amp;','<':'&lt;','>':'&gt;'}})[m]);
function draw(){{const k=q.value.trim().toLowerCase().split(/\\s+/).filter(Boolean),cc=c.value.toLowerCase();
const r=D.filter(x=>(!cc||x.cat.toLowerCase().includes(cc))&&k.every(w=>x.name.toLowerCase().includes(w)));
tb.innerHTML=r.slice(0,300).map(x=>`<tr><td class=mut>${{esc(x.cat)}}${{x.group?' · '+esc(x.group):''}}</td><td>${{esc(x.name)}}</td><td class=r>${{x.price.toLocaleString()}}</td></tr>`).join('');
more.textContent=r.length>300?`共 ${{r.length}} 筆，只顯示前 300 筆，請用搜尋縮小範圍`:`共 ${{r.length}} 筆`;}}
q.oninput=c.onchange=draw;draw();</script>
<p class=mut style="margin-top:24px">價格以原價屋線上估價當日顯示為準，實際成交價需經原價屋客服確認。</p></main></body></html>"""
    open(out_p, 'w', encoding='utf-8').write(page)
    print(f"{date}: total {total:,}  missing={missing}  history days={len(dates)}")

if __name__ == '__main__':
    main()
