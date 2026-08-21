"""三个页面的 HTML 渲染。首页 / 进度页 / 结果页共用一套样式。

设计规则（都是踩过坑得出的）：
  · 洋红只用于 ≥24px 大字、CTA 实底、角标 —— 在白底上做小字对比度不够
  · 所有数字用等宽 + tabular-nums —— 这是专业感最廉价的来源
  · 晕染只在背景层，数据区域完全平面
  · PC 优先，靠 grid auto-fill 让手机自然降级，不写响应式布局
"""
from __future__ import annotations

import html as H
import json

from . import config as C

FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link href="https://api.fontshare.com/v2/css?f[]=satoshi@500,700,900&display=swap" rel="stylesheet">
"""

CSS = """
:root{
  --cyan:#00CFC8; --cyan-wash:#E6FBFA; --magenta:#FE2C55;
  --magenta-hover:#E62149; --magenta-wash:#FFEEF1;
  --bg:#fff; --sunken:#F6F6F7;
  --border:rgba(10,10,11,.10); --border-strong:rgba(10,10,11,.22);
  --text:#0E0E10; --text-2:#5C5C64; --text-3:#6B6B75; --data:#0B7F7B;
  --display:"Satoshi","General Sans",system-ui,sans-serif;
  --body:Inter,system-ui,sans-serif;
  --mono:"Geist Mono","JetBrains Mono",ui-monospace,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:15px/1.55 var(--body);-webkit-font-smoothing:antialiased}
a{color:inherit;text-decoration:none}
button{font:inherit;cursor:pointer}
.wrap{max-width:1180px;margin:0 auto;padding:0 24px}

/* 晕染：只在背景层，唯一的装饰 */
.bloom{position:fixed;inset:0;overflow:hidden;pointer-events:none;z-index:0}
.orb{position:absolute;border-radius:50%;filter:blur(130px)}
.orb-c{width:880px;height:880px;top:-320px;left:50%;margin-left:-620px;
  background:var(--cyan);opacity:.28}
.orb-m{width:820px;height:820px;top:-220px;left:50%;margin-left:-160px;
  background:var(--magenta);opacity:.18}

.topbar{position:relative;z-index:2;display:flex;align-items:center;
  justify-content:space-between;height:52px}
.wordmark{font-family:var(--mono);font-size:11px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--text-3)}
.wordmark:hover{color:var(--text-2)}
.count{font-family:var(--mono);font-size:13px;color:var(--data);
  font-variant-numeric:tabular-nums}

/* ── 首页 ─────────────────────────────────── */
.hero{position:relative;z-index:1;display:flex;flex-direction:column;
  align-items:center;text-align:center;padding:88px 0 72px}
h1{font-family:var(--display);font-size:52px;font-weight:900;
  letter-spacing:-.025em;line-height:1.06;margin:0}
.sub{max-width:560px;color:var(--text-2);margin:24px 0 0;text-wrap:pretty}
/* 七个门槛标签排一行。不设 max-width —— 正文限 560px 是为了阅读行长，
   而这排 pill 是扫视的，挤成两行反而更难扫。窗口不够时自然换行。 */
.gates{display:flex;flex-wrap:wrap;gap:6px;justify-content:center;margin:24px 0 0}
.gate{font-size:12px;padding:4px 11px;border-radius:999px;
  background:var(--sunken);color:var(--text-2)}
.gate .n{font-family:var(--mono);font-variant-numeric:tabular-nums}
form{margin-top:32px;width:480px;max-width:100%}
.row{display:flex;gap:12px}
.field{position:relative;flex:1}
input[type=text]{width:100%;height:48px;padding:0 44px 0 16px;
  font-family:var(--mono);font-size:15px;color:var(--text);background:#fff;
  border:1px solid var(--border);border-radius:10px;
  box-shadow:0 1px 2px rgba(10,10,11,.04);transition:border-color .12s,box-shadow .12s}
input[type=text]::placeholder{color:var(--text-3)}
input[type=text]:hover{border-color:var(--border-strong)}
input[type=text]:focus{outline:none;border-color:var(--cyan);
  box-shadow:0 0 0 3px rgba(0,207,200,.28)}
.spin{position:absolute;top:50%;right:16px;width:14px;height:14px;margin-top:-7px;
  border:1.5px solid var(--border);border-top-color:var(--cyan);border-radius:50%;
  animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.go{height:48px;padding:0 24px;font-size:15px;font-weight:500;color:#fff;
  background:var(--magenta);border:0;border-radius:10px;transition:background .12s}
.go:hover{background:var(--magenta-hover)}
.go:disabled{opacity:.45;cursor:not-allowed}
.status{margin-top:12px;font-size:13px;text-align:left;min-height:20px;
  color:var(--text-3)}
.status.ok{color:var(--data)}
.status.warn{color:var(--magenta)}
.demos{margin-top:40px;width:480px;max-width:100%}
.demos p{margin:0 0 10px;font-size:13px;color:var(--text-2);text-align:left}
/* auto-fit：一张就铺满，多张就并排。demo 数量是数据决定的，不写死列数 */
.dgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.demo{display:flex;align-items:center;gap:10px;padding:14px 16px;text-align:left;
  background:var(--sunken);border:1px solid var(--border);border-radius:10px;
  transition:border-color .12s,background .12s}
.demo:hover{border-color:var(--cyan);background:var(--cyan-wash)}
.demo:hover .arrow{transform:translateX(3px);color:var(--text)}
.demo b{font-size:14px;font-weight:500;flex:none}
.demo span{font-family:var(--mono);font-size:11.5px;color:var(--text-2);
  font-variant-numeric:tabular-nums;flex:1;min-width:0;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.arrow{flex:none;color:var(--text-3);transition:transform .12s,color .12s}

/* ── 进度页 ───────────────────────────────── */
.load{position:relative;z-index:1;display:flex;flex-direction:column;
  align-items:center;text-align:center;padding:140px 0}
.load h2{font-family:var(--display);font-size:32px;font-weight:700;margin:0 0 40px}
.bar{width:480px;max-width:100%;height:4px;background:var(--sunken);
  border-radius:999px;overflow:hidden}
.bar i{display:block;height:100%;width:0;border-radius:999px;
  background:linear-gradient(90deg,var(--cyan),var(--magenta));
  transition:width .6s ease}
.pct{font-family:var(--mono);font-size:32px;font-weight:500;margin:20px 0 6px;
  font-variant-numeric:tabular-nums}
.stage{font-size:14px;color:var(--text-2);transition:opacity .15s;min-height:22px}
.note{margin-top:40px;font-size:13px;color:var(--text-3)}

/* ── 结果页 ───────────────────────────────── */
.head{position:relative;z-index:1;padding-top:28px}
.head h1{font-size:38px;letter-spacing:-.02em}
.meta{font-family:var(--mono);font-size:13px;color:var(--text-3);margin:2px 0 16px}
.yield{font-size:13.5px;color:var(--text-2);margin:0 0 12px}
.yield b{font-family:var(--mono);color:var(--text);font-weight:500;
  font-variant-numeric:tabular-nums}
.filters{border-top:1px solid var(--border);border-bottom:1px solid var(--border);
  padding:14px 0;margin:28px 0;display:flex;flex-wrap:wrap;gap:22px}
.fgroup{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.flabel{font-family:var(--mono);font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--text-3)}
.f{font-size:12.5px;padding:4px 12px;border-radius:999px;border:1px solid var(--border);
  background:#fff;color:var(--text-2);user-select:none;
  transition:border-color .12s,background .12s,color .12s}
.f:hover{border-color:var(--border-strong)}
.f.on{background:var(--cyan-wash);border-color:var(--cyan);color:var(--data);
  font-weight:500}
.f .n{font-family:var(--mono);opacity:.65;margin-left:4px}
/* ⓘ 来源说明。原来两行解释文字收敛成一个图标 + 浮层 */
.info{position:relative;margin-left:auto;align-self:center}
.ibtn{width:22px;height:22px;display:grid;place-items:center;border-radius:50%;
  border:1px solid var(--border);background:#fff;color:var(--text-3);
  font-family:var(--mono);font-size:11px;line-height:1;padding:0;
  transition:border-color .12s,color .12s}
.ibtn:hover,.ibtn[aria-expanded=true]{border-color:var(--cyan);color:var(--data)}
.pop{position:absolute;top:30px;right:0;width:330px;z-index:10;padding:16px;
  background:#fff;border:1px solid var(--border);border-radius:12px;
  box-shadow:0 12px 32px rgba(10,10,11,.13),0 2px 6px rgba(10,10,11,.05);
  font-size:12.5px;line-height:1.6;color:var(--text-2);text-align:left}
.pop[hidden]{display:none}
.pop h3{font-family:var(--body);font-size:12.5px;font-weight:600;color:var(--text);
  margin:0 0 10px}
.pop .terms{font-family:var(--mono);font-size:11.5px;color:var(--data);
  line-height:1.85;word-break:break-word}
.pop .rule{height:1px;background:var(--border);margin:12px 0}
.pop .legend::before{content:"■";color:var(--data);margin-right:6px}
.pop b{font-family:var(--mono);font-weight:500;color:var(--text);
  font-variant-numeric:tabular-nums}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(212px,1fr));
  gap:20px 20px;padding-bottom:96px}
.card{display:block}
.card:hover .thumb{border-color:var(--border-strong);
  box-shadow:0 6px 20px rgba(10,10,11,.14)}
.card:hover .thumb img{transform:scale(1.035)}
.card:hover .who{color:var(--text)}
.thumb{position:relative;aspect-ratio:9/16;border-radius:10px;overflow:hidden;
  background:var(--sunken);border:1px solid var(--border);transition:border-color .12s}
.thumb img{width:100%;height:100%;object-fit:cover;display:block;
  transition:transform .2s ease}
.noimg{display:grid;place-items:center;height:100%;font-family:var(--mono);
  font-size:11px;color:var(--text-3)}
.badge{position:absolute;top:8px;left:8px;background:var(--magenta);color:#fff;
  font-family:var(--mono);font-size:11px;font-weight:500;padding:3px 8px;
  border-radius:999px;font-variant-numeric:tabular-nums}
.dur{position:absolute;bottom:8px;right:8px;background:rgba(10,10,11,.72);color:#fff;
  font-family:var(--mono);font-size:11px;padding:2px 7px;border-radius:6px;
  font-variant-numeric:tabular-nums}
/* 卡片三行 = 三个信息层级：① 视频表现 ② 达人 ③ 来源 */
.perf{margin:11px 0 3px;font-family:var(--mono);font-size:12.5px;line-height:1.45;
  font-variant-numeric:tabular-nums;color:var(--text-2)}
.perf b{color:var(--text);font-weight:500}
.perf .er b{color:var(--data)}
.who{font-size:12.5px;color:var(--text-2);white-space:nowrap;overflow:hidden;
  text-overflow:ellipsis;transition:color .12s}
.who .fans{font-family:var(--mono);font-size:11.5px;color:var(--text-3);
  font-variant-numeric:tabular-nums}
.src{font-family:var(--mono);font-size:11px;color:var(--text-3);margin-top:7px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.src.mined{color:var(--data)}
.empty{padding:60px 0;text-align:center;color:var(--text-3)}

@media (max-width:640px){
  .wrap{padding:0 16px}
  h1{font-size:34px}
  .head h1{font-size:28px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:14px}
  form,.demos,.bar{width:100%}
  .filters{gap:14px}
}
"""

GATES = ["Last 30 days", "10k+ views", "3%+ engagement", "10–90 sec",
         "English", "Video only", "Creators only"]

BLOOM = ('<div class="bloom" aria-hidden="true"><div class="orb orb-c"></div>'
         '<div class="orb orb-m"></div></div>')


def _shell(title: str, body: str, script: str = "") -> str:
    return (f'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{H.escape(title)}</title>{FONTS}<style>{CSS}</style></head>'
            f'<body>{body}{f"<script>{script}</script>" if script else ""}'
            f'</body></html>')


def human(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n/1000:.0f}k"
    return str(n)


def fan_bucket(f: int) -> tuple[str, str]:
    if f >= 1_000_000:
        return "1m", "1M+"
    if f >= 100_000:
        return "100k", "100k–1M"
    return "sub100k", "<100k"


# ---------------------------------------------------------------- 首页

INDEX_JS = r"""
const inp=document.getElementById('brand'),st=document.getElementById('status'),
      sp=document.getElementById('spin'),go=document.getElementById('go');
let timer;
inp.addEventListener('blur',()=>{
  const v=inp.value.trim(); clearTimeout(timer);
  if(!v){st.textContent='';st.className='status';return;}
  sp.style.display='block'; st.textContent=''; st.className='status';
  fetch('/api/probe?brand='+encodeURIComponent(v))
    .then(r=>r.json()).then(d=>{
      sp.style.display='none';
      if(d.count>=10){st.textContent='✓ Looks good — plenty of videos to work with';
        st.className='status ok';}
      else{st.textContent='⚠ Barely any videos found. Check the spelling?';
        st.className='status warn';}
    }).catch(()=>{sp.style.display='none';});
});
document.getElementById('f').addEventListener('submit',e=>{
  e.preventDefault();
  const v=inp.value.trim(); if(!v)return;
  // 先钉住当前宽度再换文案，否则 'Start digging' → 'Starting…' 会让按钮缩一下
  go.style.width=go.offsetWidth+'px';
  go.disabled=true; go.textContent='Starting…';
  fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({brand:v})}).then(r=>r.json())
    .then(d=>{location.href='/job/'+d.job_id;});
});
"""


def index_page(demos: list[dict]) -> str:
    gates = "".join(f'<span class="gate">{g}</span>' for g in GATES)
    def dcard(d: dict) -> str:
        meta = (f'{H.escape(d["category"])} · {d["count"]} videos'
                if d.get("category") else f'{d["count"]} videos')
        return (f'<a class="demo" href="/brief/{H.escape(d["job_id"])}">'
                f'<b>{H.escape(d["brand"].upper())}</b>'
                f'<span>{meta}</span><span class="arrow">→</span></a>')

    # 文案随数量变。只有一份时说 "a finished report"，多份才用复数 ——
    # 一张卡片配 "Examples" 会让人以为还有别的没加载出来。
    label = ("See a finished report — no wait" if len(demos) == 1
             else "Or see one already made")
    demos_html = (f'<div class="demos"><p>{label}</p>'
                  f'<div class="dgrid">{"".join(dcard(d) for d in demos)}</div>'
                  f'</div>') if demos else ""
    body = f"""{BLOOM}<div class="wrap"><header class="topbar">
  <a class="wordmark" href="/">Spark</a></header>
<main class="hero">
  <h1>Skip the scroll.<br>Watch the 3% that hit.</h1>
  <p class="sub">TikTok's search filters suck — no date, no reach, no format.
    So researching a competitor's viral videos means digging through thousands
    first. Spark does the digging so you can just watch.</p>
  <div class="gates">{gates}</div>
  <form id="f">
    <div class="row">
      <div class="field">
        <input type="text" id="brand" placeholder="wavy talk"
               autocomplete="off" spellcheck="false">
        <span class="spin" id="spin" style="display:none"></span>
      </div>
      <button class="go" id="go" type="submit">Start digging</button>
    </div>
    <div class="status" id="status"></div>
  </form>
  {demos_html}
</main></div>"""
    return _shell("Spark", body, INDEX_JS)


# ---------------------------------------------------------------- 进度页

JOB_JS = r"""
const ID=location.pathname.split('/').pop();
const bar=document.querySelector('.bar i'),pct=document.getElementById('pct'),
      stage=document.getElementById('stage');
function poll(){
  fetch('/api/jobs/'+ID).then(r=>r.json()).then(d=>{
    if(d.status==='done'){location.href='/brief/'+ID;return;}
    if(d.status==='failed'){stage.textContent='Something went wrong: '+(d.error||'');
      return;}
    bar.style.width=(d.progress_pct||0)+'%';
    pct.textContent=(d.progress_pct||0)+'%';
    const txt=(d.stage_detail? d.stage+' — '+d.stage_detail : d.stage)||'';
    if(stage.textContent!==txt){
      stage.style.opacity=0;
      setTimeout(()=>{stage.textContent=txt;stage.style.opacity=1;},150);
    }
    setTimeout(poll,3000);
  }).catch(()=>setTimeout(poll,5000));
}
poll();
"""


def job_page(brand: str) -> str:
    body = f"""{BLOOM}<div class="wrap"><header class="topbar">
  <a class="wordmark" href="/">Spark</a></header>
<main class="load">
  <h2>Reading TikTok</h2>
  <div class="bar"><i></i></div>
  <div class="pct" id="pct">0%</div>
  <div class="stage" id="stage">Starting…</div>
  <p class="note">This takes about 10 minutes. You can close this tab —
    the link stays live.</p>
</main></div>"""
    return _shell(f"{brand} — Spark", body, JOB_JS)


# ---------------------------------------------------------------- 结果页

RESULT_JS = r"""
const state={fans:'all',speech:'all'};
function apply(){
  let n=0;
  document.querySelectorAll('.card').forEach(c=>{
    const ok=(state.fans==='all'||c.dataset.fans===state.fans)
          &&(state.speech==='all'||c.dataset.speech===state.speech);
    c.style.display=ok?'':'none'; if(ok)n++;
  });
  document.getElementById('shown').textContent=n;
  document.getElementById('empty').style.display=n?'none':'block';
}
document.querySelectorAll('.f').forEach(f=>f.onclick=()=>{
  const k=f.dataset.k; state[k]=f.dataset.v;
  document.querySelectorAll('.f[data-k="'+k+'"]').forEach(x=>
    x.classList.toggle('on',x.dataset.v===state[k]));
  apply();
});
apply();

const ib=document.getElementById('ibtn'),pop=document.getElementById('pop');
function setPop(open){pop.hidden=!open;ib.setAttribute('aria-expanded',open);}
ib.onclick=e=>{e.stopPropagation();setPop(pop.hidden);};
pop.onclick=e=>e.stopPropagation();
document.addEventListener('click',()=>setPop(false));
document.addEventListener('keydown',e=>{if(e.key==='Escape')setPop(false);});
"""


def _card(v: dict, source: str, plain: set[str], frame_exists) -> str:
    fkey, _ = fan_bucket(v["followers"])
    speech = "yes" if v["has_subtitles"] else "no"
    # 封面三级回退：自己抽的帧 → 缓存到本地的封面 → 远程 CDN 地址。
    # 远程那条永远排最后 —— 它带签名、约两天过期，只能当兜底不能当主力。
    if frame_exists(v["id"]):
        img = f'<img src="/frames/{v["id"]}_h0.jpg" loading="lazy" alt="">'
    elif v.get("cover_local"):
        img = f'<img src="{H.escape(v["cover_local"])}" loading="lazy" alt="">'
    elif v.get("cover_url"):
        img = f'<img src="{H.escape(v["cover_url"])}" loading="lazy" alt="">'
    else:
        img = '<div class="noimg">no cover</div>'

    over = v["plays_per_follower"]
    badge = (f'<div class="badge">⚡ Views {over:.0f}× followers</div>'
             if over >= 3 else "")
    cls = "src" if source.strip('"#').lower() in plain else "src mined"

    return f"""<a class="card" data-fans="{fkey}" data-speech="{speech}"
   href="{H.escape(v['url'])}" target="_blank" rel="noopener">
  <div class="thumb">{img}{badge}<div class="dur">{v['duration']}s</div></div>
  <div class="perf"><b>{human(v['plays'])}</b> views ·
    <span class="er"><b>{v['engagement_rate']:.1%}</b></span> engagement ·
    {'Has VO' if v['has_subtitles'] else 'No VO'}</div>
  <div class="who">@{H.escape(v['author'])} ·
    <span class="fans">{human(v['followers'])} followers</span></div>
  <div class="{cls}">{H.escape(source)}</div>
</a>"""


def result_page(data: dict, *, frame_exists) -> str:
    brand = data["brand"]
    vids = data["videos"]
    src = data.get("sources", {})
    plain = {brand["nickname"].lower(), brand["hashtag"].lower()}

    fans, speech = {}, {"yes": 0, "no": 0}
    for v in vids:
        k, _ = fan_bucket(v["followers"])
        fans[k] = fans.get(k, 0) + 1
        speech["yes" if v["has_subtitles"] else "no"] += 1
    mined = sum(1 for v in vids
                if src.get(v["id"], "").strip('"#').lower() not in plain)

    def fbtn(k, val, label, n):
        on = " on" if val == "all" else ""
        return (f'<span class="f{on}" data-k="{k}" data-v="{val}">{label}'
                f'<span class="n">{n}</span></span>')

    terms = data.get("terms") or []
    all_terms = " · ".join(H.escape(t) for t in terms)

    body = f"""<div class="wrap"><header class="topbar">
  <a class="wordmark" href="/">Spark</a>
  <span class="count"><span id="shown">{len(vids)}</span> videos</span></header>
<div class="head">
  <h1>{H.escape(brand['nickname'].upper())}</h1>
  <p class="yield">Crawled <b>{data['stats'].get('after_dedupe', 0):,}</b> videos ·
    <b>{len(vids)}</b> cleared every bar ·
    max <b>{C.MAX_VIDEOS_PER_ACCOUNT}</b> per creator</p>
  <div class="gates" style="justify-content:flex-start;max-width:none">
    {''.join(f'<span class="gate">{g}</span>' for g in GATES)}</div>
  <div class="filters">
    <div class="fgroup"><span class="flabel">Followers</span>
      {fbtn('fans','all','All',len(vids))}
      {fbtn('fans','sub100k','&lt;100k',fans.get('sub100k',0))}
      {fbtn('fans','100k','100k–1M',fans.get('100k',0))}
      {fbtn('fans','1m','1M+',fans.get('1m',0))}</div>
    <div class="fgroup"><span class="flabel">Voiceover</span>
      {fbtn('speech','all','All',len(vids))}
      {fbtn('speech','yes','Has VO',speech['yes'])}
      {fbtn('speech','no','No VO',speech['no'])}</div>
    <div class="info">
      <button class="ibtn" id="ibtn" aria-expanded="false"
              aria-label="How Spark found these">i</button>
      <div class="pop" id="pop" hidden>
        <h3>How Spark found these</h3>
        Searched {len(terms)} terms:
        <div class="terms">{all_terms}</div>
        <div class="rule"></div>
        <span class="legend"><b>{mined} of {len(vids)}</b> were found only through
        a tag or product name Spark learned — not by searching the brand.</span>
      </div>
    </div>
  </div>
</div>
<div class="grid">{''.join(_card(v, src.get(v['id'], ''), plain, frame_exists)
                            for v in vids)}</div>
<div class="empty" id="empty" style="display:none">No videos match those filters</div>
</div>"""
    return _shell(f"{brand['nickname']} — Spark", body, RESULT_JS)
