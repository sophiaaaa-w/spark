"""把 brief 渲染成本地 HTML，用来肉眼核对帧图和口播对不对得上。

跑法：
    python3 scripts/preview.py @wavytalkofficial

零成本，只读本地文件。生成后自动用浏览器打开。

这一页也是 brief 结果页的雏形 —— 左右两栏的排版、逐字校验标记、
帧图和时间轴的对应关系，都是最终产品要有的。
"""
import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C                                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"

CSS = """
:root{
  --cyan:#00CFC8; --cyan-wash:#E6FBFA; --magenta:#FE2C55;
  --bg:#fff; --sunken:#F6F6F7; --border:rgba(10,10,11,.10);
  --text:#0E0E10; --text-2:#5C5C64; --text-3:#6B6B75; --data:#0B7F7B;
  --mono:"Geist Mono","JetBrains Mono",ui-monospace,monospace;
}
*{box-sizing:border-box}
body{margin:0;padding:48px 32px 96px;background:var(--bg);color:var(--text);
  font:16px/1.55 Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto}
.eyebrow{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text-3)}
h1{font-size:40px;font-weight:700;letter-spacing:-.02em;margin:.3em 0 .2em}
.sub{color:var(--text-2);margin:0 0 40px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:48px}
.stat{background:var(--sunken);border-radius:10px;padding:14px 18px;min-width:150px}
.stat b{display:block;font-family:var(--mono);font-size:26px;font-weight:500;
  font-variant-numeric:tabular-nums}
.stat span{font-size:12px;color:var(--text-3)}
.pat{border-top:1px solid var(--border);padding-top:32px;margin-top:48px}
.pat h2{font-size:28px;font-weight:700;letter-spacing:-.02em;margin:0 0 6px}
.num{font-family:var(--mono);color:var(--text-3);margin-right:10px}
.tags{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 18px}
.tag{font-size:12px;padding:3px 10px;border-radius:999px;background:var(--sunken);
  color:var(--text-2)}
.tag.warn{background:#FFEEF1;color:#A3122F}
.tag.good{background:var(--cyan-wash);color:var(--data)}
.metrics{font-family:var(--mono);font-size:13px;color:var(--text-2);
  font-variant-numeric:tabular-nums;margin-bottom:18px}
.metrics b{color:var(--data)}
.why{max-width:680px;color:var(--text-2);margin:0 0 24px}
.quotes{margin:0 0 32px;padding:0;list-style:none}
.quotes li{font-family:var(--mono);font-size:13px;color:var(--text-2);
  border-left:2px solid var(--border);padding:4px 0 4px 14px;margin-bottom:8px}
.src{font-family:var(--mono);font-size:12px;color:var(--text-3);margin-bottom:14px}
.src a{color:var(--data)}
.head{display:grid;grid-template-columns:96px 1fr 40%;gap:20px;
  font-family:var(--mono);font-size:11px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--text-3);padding-bottom:10px;border-bottom:1px solid var(--border)}
.seg{display:grid;grid-template-columns:96px 1fr 40%;gap:20px;
  padding:20px 0;border-bottom:1px solid var(--border);align-items:start}
.seg img{width:96px;border-radius:8px;display:block;background:var(--sunken)}
.t{font-family:var(--mono);font-size:12px;color:var(--text-3);margin-top:6px;
  font-variant-numeric:tabular-nums}
.label{font-family:var(--mono);font-size:11px;letter-spacing:.08em;color:var(--text-3)}
.vis{margin:4px 0 10px}
.vo{font-family:var(--mono);font-size:13px;color:var(--text-2);
  background:var(--sunken);padding:8px 12px;border-radius:8px}
.vo .ok{color:var(--data)} .vo .bad{color:var(--magenta);font-weight:500}
.right{border-left:2px solid var(--cyan);padding-left:16px}
.move{font-weight:500;color:var(--data);margin-bottom:4px}
.fn{font-size:14px;color:var(--text-2)}
.none{color:var(--text-3);font-style:italic}
"""


def esc(s) -> str:
    return html.escape(str(s or ""))


def seg_html(s: dict) -> str:
    img = s.get("frame_url") or ""
    name = img.rsplit("/", 1)[-1] if img else ""
    src = f"../data/frames/{name}" if name else ""
    thumb = (f'<img src="{esc(src)}" alt="frame">' if name
             else '<div class="none">无帧图</div>')

    vo = s.get("vo") or ""
    ver = s.get("vo_verified")
    if vo:
        mark = ('<span class="ok">✓ 逐字</span>' if ver
                else '<span class="bad">⚠ 非逐字，模型可能润色过</span>')
        vo_html = f'<div class="vo">「{esc(vo)}」 {mark}</div>'
    else:
        vo_html = '<div class="vo none">这一段没有口播</div>'

    return f"""<div class="seg">
  <div>{thumb}<div class="t">{s.get('frame_t', 0):.1f}s · frame {s.get('frame_index')}</div></div>
  <div>
    <div class="label">{esc(s.get('label'))} · {s.get('t_start',0):.0f}–{s.get('t_end',0):.0f}s</div>
    <div class="vis">{esc(s.get('visual'))}</div>
    {vo_html}
  </div>
  <div class="right">
    <div class="move">{esc(s.get('move_name'))}</div>
    <div class="fn">{esc(s.get('function'))}</div>
  </div>
</div>"""


def pattern_html(p: dict, category: str) -> str:
    tags = []
    if p.get("highest_lift"):
        tags.append('<span class="tag good">⚡ 少有人做但一做就灵</span>')
    if p.get("underperforms"):
        tags.append('<span class="tag warn">⚠ 大家都在拍但传播最差</span>')
    if p.get("thin_evidence"):
        tags.append('<span class="tag">样本支撑较薄</span>')

    quotes = "".join(f"<li>「{esc(h.get('quote'))}」</li>"
                     for h in p.get("hook_examples", []))

    tl = p.get("timeline")
    if not tl:
        body = '<p class="none">这个 pattern 没能生成时间轴（骨架视频下载失败）</p>'
    else:
        unver = len(tl.get("vo_unverified") or [])
        warn = (f'<p class="tag warn">⚠ 有 {unver} 段口播不是逐字原话</p>'
                if unver else "")
        body = (
            f'<div class="src">Structure from '
            f'<a href="{esc(tl.get("skeleton_video_url"))}" target="_blank">'
            f'@{esc(tl.get("skeleton_author"))} 的这条视频 ↗</a>'
            f' · 点开可逐帧核对</div>{warn}'
            f'<div class="head"><div>帧</div><div>What they did</div>'
            f'<div>The move · in {esc(category)}</div></div>'
            + "".join(seg_html(s) for s in tl.get("segments", []))
        )

    return f"""<section class="pat">
  <h2><span class="num">0{p.get('rank')}</span>{esc(p.get('move_name'))}</h2>
  <div class="tags">{''.join(tags)}</div>
  <div class="metrics">占比 <b>{p.get('share_count')}/{p.get('share_total')}</b>
    　　互动率中位 <b>{(p.get('median_engagement') or 0)*100:.1f}%</b>
    　　播放中位 <b>{p.get('median_plays', 0):,}</b></div>
  <p class="why">{esc(p.get('why_it_works'))}</p>
  <ul class="quotes">{quotes}</ul>
  {body}
</section>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    path = FIX / f"brief_{handle}.json"
    if not path.exists():
        path = FIX / f"result_{handle}.json"
    if not path.exists():
        sys.exit(f"找不到 brief_{handle}.json，先跑 run_timeline.py")

    data = json.loads(path.read_text())
    brand = json.loads((FIX / f"brand_{handle}.json").read_text())
    cat = data.get("category", "")
    pats = data.get("patterns", [])
    total = pats[0]["share_total"] if pats else 0

    doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>Outlier — {esc(brand['nickname'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<div class="eyebrow">Outlier · 预览</div>
<h1>{esc(brand['nickname'])}</h1>
<p class="sub">@{esc(handle)} · {esc(cat)} · TikTok 近 30 天</p>
<div class="stats">
  <div class="stat"><b>{total}</b><span>分析的视频</span></div>
  <div class="stat"><b>{len(pats)}</b><span>识别出的 pattern</span></div>
  <div class="stat"><b>{data.get('unclustered_count', 0)}</b><span>未归类</span></div>
</div>
{''.join(pattern_html(p, cat) for p in pats)}
</div></body></html>"""

    out = FIX / f"preview_{handle}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"已生成 {out}")
    subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()
