"""把全部 50 条视频的归类和结构签名列出来，供人工核对聚类是否合理。

跑法：
    python3 scripts/show_labels.py @wavytalkofficial          # 终端
    python3 scripts/show_labels.py @wavytalkofficial --html   # 生成网页并打开

零成本，只读 result_*.json。

看什么：同一个 pattern 里的 beats 应该高度一致。如果某一条的节拍顺序明显不同，
说明它是被硬塞进去的 —— 那正是这个视图要暴露的东西。
"""
import argparse
import html as H
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, funnel                        # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def load(handle: str):
    d = json.loads((FIX / f"brand_{handle}.json").read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    raws = []
    for name in (f"recall_{handle}.json", f"recall2_{handle}.json"):
        p = FIX / name
        if p.exists():
            raws += json.loads(p.read_text())
    kept = funnel.hard_filter(dedupe(parse_many(raws)), brand,
                              window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=FunnelStats())
    ranked = funnel.final_rank(kept)
    res = json.loads((FIX / f"result_{handle}.json").read_text())
    return brand, ranked, res


def beats_str(b) -> str:
    return "  →  ".join(b) if b else "（未给出节拍）"


def term(handle: str) -> None:
    brand, ranked, res = load(handle)
    by_id = {v.id: v for v in ranked}
    by_pat: dict = {}
    for a in res.get("assignments", []):
        by_pat.setdefault(a.get("pattern_id"), []).append(a)

    pats = {p["id"]: p for p in res.get("patterns", [])}
    print("=" * 96)
    print(f"全部 {len(ranked)} 条的归类与结构签名　{brand.nickname}")
    print("=" * 96)

    for pid in sorted([k for k in by_pat if k is not None]) + [None]:
        rows = by_pat.get(pid, [])
        if not rows:
            continue
        if pid is None:
            print(f"\n\n{'─'*96}\n未归类　{len(rows)} 条\n{'─'*96}")
        else:
            p = pats.get(pid, {})
            print(f"\n\n{'─'*96}")
            print(f"0{pid}  {p.get('move_name','?')}　{len(rows)} 条")
            print(f"      标准签名  {beats_str(p.get('beat_signature'))}")
            print(f"{'─'*96}")
        for a in sorted(rows, key=lambda x: -(by_id[x["video_id"]].plays
                                              if x["video_id"] in by_id else 0)):
            v = by_id.get(a["video_id"])
            if not v:
                continue
            print(f"\n  {v.plays:>9,}  {v.engagement_rate:>5.1%}  "
                  f"{v.duration:>3}s  @{v.author.username}")
            print(f"    节拍  {beats_str(a.get('beats'))}")
            print(f"    依据  {a.get('evidence','')[:82]}")


CSS = """
body{margin:0;padding:40px 32px 80px;font:15px/1.5 Inter,system-ui,sans-serif;
 color:#0E0E10;background:#fff}
.wrap{max-width:1180px;margin:0 auto}
h1{font-size:32px;font-weight:700;letter-spacing:-.02em;margin:0 0 4px}
.sub{color:#5C5C64;margin:0 0 32px}
h2{font-size:22px;margin:44px 0 4px;border-top:1px solid rgba(0,0,0,.1);padding-top:28px}
.sig{font-family:"Geist Mono",ui-monospace,monospace;font-size:12px;color:#0B7F7B;
 background:#E6FBFA;padding:6px 12px;border-radius:8px;display:inline-block;margin:6px 0 18px}
table{width:100%;border-collapse:collapse}
td{padding:12px 10px;border-bottom:1px solid rgba(0,0,0,.08);vertical-align:top}
.num{font-family:"Geist Mono",ui-monospace,monospace;font-variant-numeric:tabular-nums;
 text-align:right;white-space:nowrap;color:#5C5C64;font-size:13px}
.who{font-size:13px;color:#5C5C64;white-space:nowrap}
.beats{font-family:"Geist Mono",ui-monospace,monospace;font-size:12.5px}
.ev{font-size:12.5px;color:#6B6B75;margin-top:4px}
.off{background:#FFEEF1;border-radius:4px;padding:1px 4px}
.none h2{color:#6B6B75}
"""


def page(handle: str) -> None:
    brand, ranked, res = load(handle)
    by_id = {v.id: v for v in ranked}
    by_pat: dict = {}
    for a in res.get("assignments", []):
        by_pat.setdefault(a.get("pattern_id"), []).append(a)
    pats = {p["id"]: p for p in res.get("patterns", [])}

    def row(a) -> str:
        v = by_id.get(a["video_id"])
        if not v:
            return ""
        sig = pats.get(a.get("pattern_id"), {}).get("beat_signature") or []
        beats = a.get("beats") or []
        # 和标准签名不同的节拍标红，一眼看出谁是被硬塞进来的
        cells = []
        for i, b in enumerate(beats):
            same = i < len(sig) and b.split("(")[0] == sig[i].split("(")[0]
            cells.append(b if same or not sig else f'<span class="off">{H.escape(b)}</span>')
        return f"""<tr>
  <td class="num">{v.plays:,}<br>{v.engagement_rate:.1%}</td>
  <td class="who"><a href="{H.escape(v.url)}" target="_blank">@{H.escape(v.author.username)}</a><br>{v.duration}s</td>
  <td><div class="beats">{'  →  '.join(cells) or '—'}</div>
      <div class="ev">{H.escape(a.get('evidence',''))}</div></td>
</tr>"""

    blocks = []
    for pid in sorted([k for k in by_pat if k is not None]) + [None]:
        rows = by_pat.get(pid, [])
        if not rows:
            continue
        rows.sort(key=lambda x: -(by_id[x["video_id"]].plays
                                  if x["video_id"] in by_id else 0))
        if pid is None:
            head = f'<div class="none"><h2>未归类 · {len(rows)} 条</h2></div>'
        else:
            p = pats.get(pid, {})
            head = (f'<h2>0{pid}　{H.escape(p.get("move_name",""))}'
                    f'　<span class="sub">{len(rows)} 条</span></h2>'
                    f'<div class="sig">标准签名　'
                    f'{H.escape("  →  ".join(p.get("beat_signature") or []))}</div>')
        blocks.append(head + "<table>" + "".join(row(a) for a in rows) + "</table>")

    doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>归类核对 — {H.escape(brand.nickname)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Geist+Mono&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<h1>{H.escape(brand.nickname)} · 归类核对</h1>
<p class="sub">全部 {len(ranked)} 条。同组内节拍应高度一致；
<span class="off">标红</span>的是和标准签名对不上的节拍 —— 那些可能是被硬塞进来的。</p>
{''.join(blocks)}</div></body></html>"""

    out = FIX / f"labels_{handle}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"已生成 {out}")
    subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--html", action="store_true")
    args = ap.parse_args()
    h = args.handle.lstrip("@")
    page(h) if args.html else term(h)
