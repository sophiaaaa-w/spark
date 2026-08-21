"""生成结果页 —— 封面网格 + 筛选器。

跑法：
    python3 scripts/build_results.py @wavytalkofficial

零 API 成本。缺帧图的视频会自动补下载（需要 yt-dlp + ffmpeg）。

PC 优先，但用 grid auto-fit 让它在手机上自然降级成单列 —— 零额外成本。
"""
import argparse
import asyncio
import html as H
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, frames, funnel                # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
FR = ROOT / "data" / "frames"

CSS = """
:root{
  --cyan:#00CFC8; --cyan-wash:#E6FBFA; --magenta:#FE2C55;
  --bg:#fff; --sunken:#F6F6F7; --hover:rgba(10,10,11,.03);
  --border:rgba(10,10,11,.10); --border-strong:rgba(10,10,11,.22);
  --text:#0E0E10; --text-2:#5C5C64; --text-3:#6B6B75; --data:#0B7F7B;
  --font-display:"Satoshi","General Sans",system-ui,sans-serif;
  --font-body:Inter,system-ui,sans-serif;
  --mono:"Geist Mono","JetBrains Mono",ui-monospace,monospace;
  --radius:10px;
}
*{box-sizing:border-box}
body{margin:0;padding:0 24px 96px;background:var(--bg);color:var(--text);
  font:15px/1.55 var(--font-body);-webkit-font-smoothing:antialiased}
.wrap{max-width:1180px;margin:0 auto}
a{color:inherit;text-decoration:none}

.topbar{display:flex;align-items:center;justify-content:space-between;
  height:52px;border-bottom:1px solid var(--border);margin-bottom:36px}
.wordmark{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text-3)}
.wordmark:hover{color:var(--text-2)}

h1{font-family:var(--font-display);font-size:38px;font-weight:900;
  letter-spacing:-.025em;margin:0 0 2px;line-height:1.1}
.handle{font-family:var(--mono);font-size:13px;color:var(--text-3);margin:0 0 18px}
.count{font-family:var(--mono);font-size:13px;color:var(--data);
  font-variant-numeric:tabular-nums}
.yield{font-size:13.5px;color:var(--text-2);margin:0 0 12px}
.yield b{font-family:var(--mono);color:var(--text);font-weight:500;
  font-variant-numeric:tabular-nums}

.gates{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:28px}
.gate{font-size:12px;padding:4px 11px;border-radius:999px;
  background:var(--sunken);color:var(--text-2)}
.gate .n{font-family:var(--mono);font-variant-numeric:tabular-nums}

.filters{border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  padding:14px 0;margin-bottom:28px;display:flex;flex-wrap:wrap;gap:22px}
.fgroup{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.flabel{font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-3);margin-right:2px}
.f{font-size:12.5px;padding:4px 12px;border-radius:999px;cursor:pointer;
  border:1px solid var(--border);background:#fff;color:var(--text-2);
  transition:border-color .12s,background .12s,color .12s;user-select:none}
.f:hover{border-color:var(--border-strong)}
.f.on{background:var(--cyan-wash);border-color:var(--cyan);color:var(--data);
  font-weight:500}
.f .n{font-family:var(--mono);opacity:.65;margin-left:4px}

.shown{font-family:var(--mono);font-size:12.5px;color:var(--text-3);
  margin:0 0 16px;font-variant-numeric:tabular-nums}
.legend{font-family:var(--font-body);font-size:12.5px}
.legend::before{content:"■";color:var(--data);margin-right:5px}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));
  gap:20px}
.card{display:block;border-radius:var(--radius);overflow:hidden}
.card:hover .thumb{border-color:var(--border-strong)}
.card:hover .author{color:var(--text)}
.thumb{position:relative;aspect-ratio:9/16;border-radius:var(--radius);
  overflow:hidden;background:var(--sunken);border:1px solid var(--border);
  transition:border-color .12s}
.thumb img{width:100%;height:100%;object-fit:cover;display:block}
.noimg{display:grid;place-items:center;height:100%;font-family:var(--mono);
  font-size:11px;color:var(--text-3)}
.badge{position:absolute;top:8px;left:8px;background:var(--magenta);color:#fff;
  font-family:var(--mono);font-size:11px;font-weight:500;padding:3px 8px;
  border-radius:999px;font-variant-numeric:tabular-nums}
.dur{position:absolute;bottom:8px;right:8px;background:rgba(10,10,11,.72);
  color:#fff;font-family:var(--mono);font-size:11px;padding:2px 7px;
  border-radius:6px;font-variant-numeric:tabular-nums}

.stats{margin:10px 0 4px;font-family:var(--mono);font-size:12.5px;
  line-height:1.45;font-variant-numeric:tabular-nums;color:var(--text-2)}
.stats b{color:var(--text);font-weight:500}
.stats .er b{color:var(--data)}
.author{font-size:13px;color:var(--text-2);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;margin-bottom:2px}
.attrs{font-family:var(--mono);font-size:11.5px;color:var(--text-3);
  font-variant-numeric:tabular-nums}
.src{font-family:var(--mono);font-size:11px;color:var(--text-3);margin-top:6px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.src.mined{color:var(--data)}

.empty{padding:60px 0;text-align:center;color:var(--text-3)}

@media (max-width:640px){
  body{padding:0 16px 64px}
  h1{font-size:30px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
  .filters{gap:14px}
}
"""

JS = r"""
const state={fans:'all',speech:'all'};
function apply(){
  let n=0;
  document.querySelectorAll('.card').forEach(c=>{
    const ok=(state.fans==='all'||c.dataset.fans===state.fans)
          && (state.speech==='all'||c.dataset.speech===state.speech);
    c.style.display=ok?'':'none';
    if(ok)n++;
  });
  document.getElementById('shown').textContent=n;
  document.getElementById('empty').style.display=n?'none':'block';
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.f').forEach(f=>f.onclick=()=>{
    const k=f.dataset.k;
    state[k]=f.dataset.v;
    document.querySelectorAll(`.f[data-k="${k}"]`).forEach(x=>
      x.classList.toggle('on',x.dataset.v===state[k]));
    apply();
  });
  apply();
});
"""


def fan_bucket(f: int) -> tuple[str, str]:
    if f >= 1_000_000:
        return "1m", "1M+"
    if f >= 100_000:
        return "100k", "100k–1M"
    return "sub100k", "<100k"


def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1000:.0f}k"
    return str(n)


def load(handle: str):
    d = json.loads((FIX / f"brand_{handle}.json").read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})
    raws = []
    for n in (f"recall_{handle}.json", f"recall2_{handle}.json",
              f"recall3_{handle}.json"):
        p = FIX / n
        if p.exists():
            raws += json.loads(p.read_text())

    src = {}
    for r in raws:
        vid = str(r.get("id") or "")
        if not vid or vid in src:
            continue
        if r.get("searchQuery"):
            src[vid] = f'"{r["searchQuery"]}"'
        else:
            h = r.get("searchHashtag")
            if h:
                src[vid] = "#" + (h if isinstance(h, str) else h.get("name", ""))

    st = FunnelStats(recalled=len(raws))
    kept = funnel.hard_filter(dedupe(parse_many(raws)), brand,
                              window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=st)
    return brand, funnel.final_rank(kept), src, st


def card(v, src: dict, brand: BrandRef) -> str:
    fkey, flabel = fan_bucket(v.author.followers)
    speech = "yes" if v.has_subtitles else "no"

    local = FR / f"{v.id}_h0.jpg"
    if local.exists():
        img = f'<img src="../data/frames/{local.name}" loading="lazy" alt="">'
    elif v.cover_url:
        img = f'<img src="{H.escape(v.cover_url)}" loading="lazy" alt="">'
    else:
        img = '<div class="noimg">无封面</div>'

    # 「播放量是该达人粉丝数的 N 倍」= 这条视频冲出了他自己的受众圈。
    # 措辞必须是主谓宾，"40× followers" 会被读成「粉丝多 40 倍」。
    over = v.plays_per_follower
    badge = (f'<div class="badge">⚡ Views {over:.0f}× followers</div>'
             if over >= 3 else "")

    # 搜品牌名就能找到的 vs 靠挖词才找到的 —— 后者是产品差异化的证明
    s = src.get(v.id, "")
    plain = {brand.nickname.lower(), f"@{brand.username.lower()}",
             brand.hashtag.lstrip("#").lower()}
    cls = "src" if s.strip('"#').lower() in plain else "src mined"

    return f"""<a class="card" data-fans="{fkey}" data-speech="{speech}"
   href="{H.escape(v.url)}" target="_blank" rel="noopener">
  <div class="thumb">{img}{badge}<div class="dur">{v.duration}s</div></div>
  <div class="stats"><b>{human(v.plays)}</b> views ·
    <span class="er"><b>{v.engagement_rate:.1%}</b></span> engagement</div>
  <div class="author">@{H.escape(v.author.username)}</div>
  <div class="attrs">{human(v.author.followers)} followers ·
    {'Has VO' if v.has_subtitles else 'No VO'}</div>
  <div class="{cls}">{H.escape(s)}</div>
</a>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    ap.add_argument("--no-fill", action="store_true", help="不补下载缺失的封面")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    brand, top, src, st = load(handle)
    print(f"Top {len(top)} 条")

    missing = [v for v in top if not (FR / f"{v.id}_h0.jpg").exists()]
    if missing and not args.no_fill and not frames.check_tools():
        print(f"补下载 {len(missing)} 条缺失封面…")
        asyncio.run(frames.build_hook_frames(missing))
    elif missing:
        print(f"⚠️  {len(missing)} 条缺本地封面，将用 CDN 链接（可能已过期）")

    fans = {}
    speech = {"yes": 0, "no": 0}
    for v in top:
        k, _ = fan_bucket(v.author.followers)
        fans[k] = fans.get(k, 0) + 1
        speech["yes" if v.has_subtitles else "no"] += 1

    gates = ["Last 30 days", "10k+ views", "3%+ engagement", "10–90 sec",
             "English", "Video only", "Creators only"]

    # 有多少条是靠挖词才找到的 —— 产品差异化的直接证据
    plain = {brand.nickname.lower(), f"@{brand.username.lower()}",
             brand.hashtag.lstrip("#").lower()}
    mined_n = sum(1 for v in top
                  if src.get(v.id, "").strip('"#').lower() not in plain)

    def fbtn(k, v, label, n=None):
        cnt = f'<span class="n">{n}</span>' if n is not None else ""
        on = " on" if v == "all" else ""
        return (f'<span class="f{on}" data-k="{k}" data-v="{v}">'
                f'{label}{cnt}</span>')

    doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{H.escape(brand.nickname)} — Spark</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@500,700,900&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">

<header class="topbar">
  <a class="wordmark" href="/">Spark</a>
  <span class="count">{len(top)} videos</span>
</header>

<h1>{H.escape(brand.nickname)}</h1>
<p class="handle">@{H.escape(brand.username)} · last 30 days</p>
<p class="yield">Crawled <b>{st.after_dedupe:,}</b> videos ·
  <b>{len(top)}</b> cleared every bar ·
  max <b>{C.MAX_VIDEOS_PER_ACCOUNT}</b> per creator</p>

<div class="gates">{''.join(f'<span class="gate">{g}</span>' for g in gates)}</div>

<div class="filters">
  <div class="fgroup"><span class="flabel">Followers</span>
    {fbtn('fans','all','All',len(top))}
    {fbtn('fans','sub100k','&lt;100k',fans.get('sub100k',0))}
    {fbtn('fans','100k','100k–1M',fans.get('100k',0))}
    {fbtn('fans','1m','1M+',fans.get('1m',0))}
  </div>
  <div class="fgroup"><span class="flabel">Voiceover</span>
    {fbtn('speech','all','All',len(top))}
    {fbtn('speech','yes','Has VO',speech['yes'])}
    {fbtn('speech','no','No VO',speech['no'])}
  </div>
</div>

<p class="shown"><span id="shown">{len(top)}</span> shown ·
  <span class="legend">green source = found only through a mined
  hashtag or product name, not by searching the brand
  ({mined_n} of {len(top)})</span></p>
<div class="grid">{''.join(card(v, src, brand) for v in top)}</div>
<div class="empty" id="empty" style="display:none">没有符合条件的视频</div>

</div><script>{JS}</script></body></html>"""

    out = FIX / f"results_{handle}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"已生成 {out}")
    subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()
