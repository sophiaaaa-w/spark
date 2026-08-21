"""生成一个本地网页，让人肉眼过一遍 50 条视频并给 hook 打标。

跑法：
    python3 scripts/label_hooks.py @wavytalkofficial

零成本。会自动打开浏览器。

页面上每条视频给出：模型看到的那两帧（0.5s / 2.5s）、开场原话、播放和互动率、
原视频链接、以及模型给的标签。

**支持多选** —— 数据模型本来就允许一条视频归入多个 hook 类型。
自己输入的新标签会自动加进快捷列表，供其余视频复用，词表边标边长出来。

打完点「复制全部」，粘回对话里即可。标注存在 localStorage，关掉页面不会丢。
"""
import argparse
import html as H
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"
FRAMES = ROOT / "data" / "frames"

# 讨论中确认的类型，模型没识别出来，先放进快捷列表
EXTRA_TYPES = ["Mid-action open"]

CSS = """
:root{--cy:#00CFC8;--cyw:#E6FBFA;--mg:#FE2C55;--bd:rgba(10,10,11,.1);
 --t2:#5C5C64;--t3:#6B6B75;--dt:#0B7F7B;--sk:#F6F6F7;
 --mono:"Geist Mono",ui-monospace,monospace}
*{box-sizing:border-box}
body{margin:0;padding:28px 24px 140px;background:#fff;color:#0E0E10;
 font:15px/1.5 Inter,system-ui,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:1240px;margin:0 auto}
h1{font-size:28px;font-weight:700;letter-spacing:-.02em;margin:0 0 4px}
.sub{color:var(--t2);margin:0 0 8px}
.bar{position:sticky;top:0;z-index:9;background:#fff;padding:14px 0;
 border-bottom:1px solid var(--bd);display:flex;gap:12px;align-items:center;
 margin-bottom:20px;flex-wrap:wrap}
.bar b{font-family:var(--mono);color:var(--dt)}
button{font:inherit;border:1px solid var(--bd);background:#fff;border-radius:8px;
 padding:7px 14px;cursor:pointer}
button:hover{border-color:#0E0E10}
button.pri{background:var(--mg);color:#fff;border-color:var(--mg)}
.card{display:grid;grid-template-columns:210px 1fr 360px;gap:18px;
 padding:18px 0;border-bottom:1px solid var(--bd);align-items:start}
.frames{display:flex;gap:6px}
.frames img{width:100px;border-radius:6px;background:var(--sk);display:block}
.cap{font-family:var(--mono);font-size:11px;color:var(--t3);margin-top:4px}
.meta{font-family:var(--mono);font-size:12.5px;color:var(--t2);
 font-variant-numeric:tabular-nums;margin-bottom:6px}
.meta a{color:var(--dt)}
.quote{font-family:var(--mono);font-size:12.5px;color:var(--t2);
 background:var(--sk);padding:7px 11px;border-radius:8px;margin-bottom:8px}
.ai{font-size:12.5px;color:var(--t3)}
.ai span{color:var(--dt)}
.chips{display:flex;flex-wrap:wrap;gap:5px;margin-bottom:7px}
.chip{font-size:11.5px;padding:3px 9px;border-radius:999px;border:1px solid var(--bd);
 background:#fff;cursor:pointer;color:var(--t2);user-select:none}
.chip:hover{border-color:var(--cy)}
.chip.on{background:var(--cyw);border-color:var(--cy);color:var(--dt);font-weight:500}
input[type=text]{width:100%;padding:7px 10px;border:1px solid var(--bd);
 border-radius:8px;font:inherit;font-size:13px}
input[type=text]:focus{outline:none;border-color:var(--cy);
 box-shadow:0 0 0 3px rgba(0,207,200,.22)}
.hint{font-size:11.5px;color:var(--t3);margin-top:4px}
.done{opacity:.5}
textarea{width:100%;height:300px;font-family:var(--mono);font-size:12px;
 border:1px solid var(--bd);border-radius:10px;padding:12px;margin-top:12px}
"""

JS = r"""
const KEY='outlier_hooks_'+HANDLE, TKEY=KEY+'_types';
const store=JSON.parse(localStorage.getItem(KEY)||'{}');
let TYPES=JSON.parse(localStorage.getItem(TKEY)||'null')||BASE_TYPES.slice();

const save=()=>{localStorage.setItem(KEY,JSON.stringify(store));
                localStorage.setItem(TKEY,JSON.stringify(TYPES));};
const labels=id=>store[id]||[];

function renderChips(card){
  const id=card.dataset.id, sel=labels(id);
  card.querySelector('.chips').innerHTML=TYPES.map(t=>
    `<span class="chip${sel.includes(t)?' on':''}" data-v="${t.replace(/"/g,'&quot;')}">${t}</span>`
  ).join('');
  card.querySelectorAll('.chip').forEach(c=>c.onclick=()=>toggle(id,c.dataset.v));
  card.classList.toggle('done', sel.length>0);
}
function renderAll(){document.querySelectorAll('.card').forEach(renderChips);count();}

function toggle(id,v){
  const cur=labels(id), i=cur.indexOf(v);
  if(i>=0) cur.splice(i,1); else cur.push(v);
  if(cur.length) store[id]=cur; else delete store[id];
  save(); renderChips(document.getElementById('c_'+id)); count();
}
function addCustom(inp){
  const v=inp.value.trim(); if(!v) return;
  if(!TYPES.includes(v)) TYPES.push(v);          // 新标签进入全局快捷列表
  const id=inp.closest('.card').dataset.id;
  if(!labels(id).includes(v)) (store[id]=labels(id)).push(v);
  inp.value=''; save(); renderAll();
}
function count(){
  document.getElementById('n').textContent=Object.keys(store).length;
  document.getElementById('nt').textContent=TYPES.length;
}
document.addEventListener('DOMContentLoaded',()=>{
  document.querySelectorAll('.card input').forEach(i=>
    i.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();addCustom(i);}});
  renderAll();
});
function dump(){
  const rows=IDS.map(id=>{
    const m=META[id], mine=labels(id);
    return (mine.length?mine.join(' + '):'（未标）')+'\t'+m.plays+'\t'+m.er
           +'\t'+m.ai+'\t@'+m.author;
  });
  const ta=document.getElementById('out');
  ta.style.display='block';
  ta.value='我的标注\t播放\tER\t模型标注\t账号\n'+rows.join('\n')
    +'\n\n用到的类型：\n'+TYPES.map(t=>{
      const n=IDS.filter(i=>labels(i).includes(t)).length;
      return '  '+n+'\t'+t;
    }).filter(l=>!l.startsWith('  0\t')).join('\n');
  ta.select(); try{document.execCommand('copy')}catch(e){}
}
function clearAll(){
  if(!confirm('清空全部标注和自建类型？')) return;
  localStorage.removeItem(KEY); localStorage.removeItem(TKEY); location.reload();
}
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    path = FIX / f"breakdown_{handle}.json"
    if not path.exists():
        sys.exit(f"找不到 {path.name}，先跑 run_breakdown.py @{handle}")
    data = json.loads(path.read_text())
    built, raw = data["built"], data["raw"]
    brand = json.loads((FIX / f"brand_{handle}.json").read_text())

    opening = {r["video_id"]: r.get("hook_quote", "") for r in raw.get("videos", [])}
    base_types = [t["name"] for t in built.get("hooks", [])] + EXTRA_TYPES

    cards, ids, meta = [], [], {}
    for r in built["index"]:
        vid = r["video_id"]
        ids.append(vid)
        meta[vid] = {"plays": f"{r['plays']:,}", "author": r["author"],
                     "er": f"{r['engagement_rate']:.1%}",
                     "ai": (r["hook"] or ["—"])[0]}
        imgs = "".join(
            f'<img src="../data/frames/{vid}_h{i}.jpg" alt="">' for i in (0, 1)
            if (FRAMES / f"{vid}_h{i}.jpg").exists())
        q = opening.get(vid, "")
        cards.append(f"""<div class="card" id="c_{vid}" data-id="{vid}">
  <div><div class="frames">{imgs or '<div class="cap">无帧图</div>'}</div>
    <div class="cap">0.5s　/　2.5s</div></div>
  <div>
    <div class="meta">{r['plays']:,} 播放　·　{r['engagement_rate']:.1%}　·
      {r['duration']}s　·　<a href="{H.escape(r['url'])}" target="_blank">
      @{H.escape(r['author'])} 看原视频 ↗</a></div>
    {f'<div class="quote">「{H.escape(q)}」</div>' if q else
     '<div class="quote" style="color:#6B6B75">无口播</div>'}
    <div class="ai">模型标注　<span>{H.escape((r['hook'] or ['—'])[0])}</span></div>
  </div>
  <div><div class="chips"></div>
    <input type="text" placeholder="新类型，回车加入…">
    <div class="hint">可多选。新类型会自动加进上面的快捷列表</div></div>
</div>""")

    doc = f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>Hook 打标 — {H.escape(brand['nickname'])}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700&family=Geist+Mono&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body><div class="wrap">
<h1>{H.escape(brand['nickname'])} · Hook 打标</h1>
<p class="sub">左边两帧就是模型看到的画面（0.5s 和 2.5s）。可多选；
自己输入的新类型会加进快捷列表供其余视频复用。标注自动保存。</p>
<div class="bar">
  已标 <b id="n">0</b> / {len(ids)}　·　类型 <b id="nt">0</b> 个
  <button class="pri" onclick="dump()">复制全部</button>
  <button onclick="clearAll()">清空</button>
</div>
{''.join(cards)}
<textarea id="out" style="display:none" readonly></textarea>
</div>
<script>
const HANDLE={json.dumps(handle)};
const IDS={json.dumps(ids)};
const META={json.dumps(meta, ensure_ascii=False)};
const BASE_TYPES={json.dumps(base_types, ensure_ascii=False)};
{JS}
</script></body></html>"""

    out = FIX / f"hooks_{handle}.html"
    out.write_text(doc, encoding="utf-8")
    print(f"已生成 {out}")
    subprocess.run(["open", str(out)], check=False)


if __name__ == "__main__":
    main()
