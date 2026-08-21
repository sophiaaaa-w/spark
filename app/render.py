"""三个页面的 HTML 渲染：搜索页 / 加载页 / 结果页。

样式在 app/styles.css，由 design/ 下的三份设计稿合并生成 —— 改样式改那个文件，
不要往这里塞 CSS。这里只负责把数据填进结构。

服务端渲染，没有模板引擎：页面就三个，每个都是一段 f-string，
引入 Jinja 的收益不抵多一个依赖和一层间接。
"""
from __future__ import annotations

import html as H
from pathlib import Path

from . import config as C

CSS = (Path(__file__).resolve().parent / "styles.css").read_text(encoding="utf-8")

FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600'
    '&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">'
    '<link href="https://api.fontshare.com/v2/css?f[]=satoshi@500,700,900'
    '&display=swap" rel="stylesheet">'
)

GATES = [
    ("Last 30 days", None), ("10k+", " views"), ("3%+", " engagement"),
    ("10–90", " sec"), ("English", None), ("Video only", None),
    ("Creators only", None),
]

# 卡片上的图标。设计稿里是内联 SVG，这里提出来当常量 —— 47 张卡片每张 5 个，
# 写进循环会让模板不可读。
ICONS = {
    "views": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M1 6.5S3 2.8 6.5 2.8 12 6.5 12 6.5s-2 3.7-5.5 3.7S1 6.5 1 6.5z" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/><circle cx="6.5" cy="6.5" r="1.7" stroke="currentColor" stroke-width="1.2"/></svg>',
    "eng": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><path d="M1 7.6h2.2l1.5-4 2.2 6.4 1.4-2.9H12" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    "vo": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><rect x="4.8" y="1.4" width="3.4" height="6" rx="1.7" stroke="currentColor" stroke-width="1.2"/><path d="M2.9 6.3a3.6 3.6 0 007.2 0M6.5 9.9v1.7" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>{slash}</svg>',
    "vo_slash": '<path d="M2 11L11 2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>',
    "handle": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="6.5" cy="4.4" r="2.3" stroke="currentColor" stroke-width="1.2"/><path d="M2.2 11.4c.6-2.1 2.3-3.2 4.3-3.2s3.7 1.1 4.3 3.2" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
    "followers": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="5" cy="4.3" r="2.1" stroke="currentColor" stroke-width="1.2"/><path d="M1.2 11c.5-1.9 2-2.9 3.8-2.9S8.3 9.1 8.8 11" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M9 2.6a2.1 2.1 0 010 3.4M10.4 8.6c.7.5 1.2 1.3 1.4 2.4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
    "info": '<svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true"><circle cx="5.6" cy="5.6" r="4" stroke="currentColor" stroke-width="1.2"/><path d="M8.7 8.7l3 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
}

BLOOM = ('<div class="bloom{extra}" aria-hidden="true">'
         '<div class="bloom__orb bloom__orb--cyan"></div>'
         '<div class="bloom__orb bloom__orb--magenta"></div></div>')

# 两种顶栏结构不同，不能合成一个。
# 搜索页/加载页：header 本身限宽居中。
# 结果页：header 全宽吸顶（要一条通栏底边），内层 .topbar__inner 才限宽。
TOPBAR = '<header class="topbar"><a class="wordmark" href="/">Spark</a></header>'

TOPBAR_STICKY = (
    '<header class="topbar--sticky"><div class="topbar__inner">'
    '<a class="wordmark" href="/">Spark</a>'
    '<div class="count"><span id="count">{n}</span> videos</div>'
    '</div></header>')


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


def fan_bucket(f: int) -> str:
    if f >= 1_000_000:
        return "gt1m"
    if f >= 100_000:
        return "mid"
    return "lt100k"


def _gates() -> str:
    out = []
    for a, b in GATES:
        inner = f'<span class="num">{a}</span>{b}' if b else a
        out.append(f'<span class="th">{inner}</span>')
    return "".join(out)


# ---------------------------------------------------------------- 搜索页

INDEX_JS = r"""
const inp=document.getElementById('brand'),st=document.getElementById('status'),
      mark=document.getElementById('status-mark'),txt=document.getElementById('status-text'),
      sp=document.getElementById('spinner'),go=document.getElementById('go'),
      form=document.getElementById('search'),
      scrim=document.getElementById('scrim'),modal=document.getElementById('modal'),
      code=document.getElementById('code'),mrun=document.getElementById('mrun'),
      merr=document.getElementById('merr');
let last, lastProbed='';

function setStatus(kind,text,glyph){
  form.classList.toggle('search--thin',kind==='thin');
  st.className='status'+(kind?' status--'+kind:'');
  if(!kind){st.hidden=true;sp.hidden=true;return;}
  sp.hidden=(kind!=='checking');
  mark.textContent=glyph||''; txt.textContent=text; st.hidden=false;
}

// 失焦才探测，而且值没变就不重发 —— 每次探测都花钱
inp.addEventListener('blur',()=>{
  const v=inp.value.trim();
  if(!v){lastProbed='';setStatus('');return;}
  if(v===lastProbed)return;
  lastProbed=v;
  setStatus('checking','Searching TikTok for “'+v+'”','◐');
  fetch('/api/probe?brand='+encodeURIComponent(v)).then(r=>r.json())
    .then(d=>{
      // count 为 -1 表示探测本身失败（配额、网络、token）。
      // 不能显示成「0 videos」—— 那会让人去查拼写，而拼写没问题。
      if(d.count<0)setStatus('thin',"Couldn't reach TikTok just now. You can still try.",'⚠');
      else if(d.count>=10)setStatus('ok','Looks good — plenty to work with','✓');
      else setStatus('thin','Only '+d.count+' videos came back. Check the spelling?','⚠');
    }).catch(()=>setStatus('thin',"Couldn't reach TikTok just now. You can still try.",'⚠'));
});

function busy(on){
  if(on&&!go.style.width)go.style.width=go.offsetWidth+'px';
  go.disabled=on; go.textContent=on?'Starting…':'Start digging';
}
function openModal(){
  last=document.activeElement; scrim.hidden=false;
  requestAnimationFrame(()=>scrim.classList.add('is-open'));
  code.focus();
}
function closeModal(){
  scrim.classList.remove('is-open');
  setTimeout(()=>{scrim.hidden=true;},140);
  modal.classList.remove('modal--error'); merr.textContent='';
  if(last)last.focus();
}
function runBusy(on){
  mrun.disabled=on;
  mrun.innerHTML=on?'<span class="modal__spinner"></span>':'Run';
}
// 报错要报到看得见的地方。弹窗关着的时候 merr 是隐藏的，
// 往里写等于什么都没说。
function fail(msg){
  if(scrim.hidden)setStatus('thin',msg,'⚠');
  else merr.textContent=msg;
}
// 服务端是唯一的判断者。前端只管「收到 401 就弹窗」——
// 就算有人改烂这段 JS 或直接 curl，服务端照样拒绝。
function start(c){
  const body={brand:inp.value.trim()}; if(c)body.code=c;
  c?runBusy(true):busy(true);
  fetch('/api/jobs',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body)}).then(r=>r.json().then(d=>({s:r.status,d})))
    .then(({s,d})=>{
      if(s===200){location.href='/job/'+d.job_id;return;}
      busy(false); runBusy(false);
      if(s===401){
        if(scrim.hidden)openModal();
        else{modal.classList.add('modal--error');
             merr.textContent="That code isn’t right."; code.focus();}
        return;
      }
      fail((d&&d.error)||'Something went wrong.');
    }).catch(()=>{busy(false);runBusy(false);fail('Network error. Try again.');});
}
form.addEventListener('submit',e=>{e.preventDefault();
  if(inp.value.trim())start('');});
mrun.addEventListener('click',()=>{const c=code.value.trim();if(c)start(c);});
code.addEventListener('input',()=>{
  mrun.disabled=!code.value.trim();
  modal.classList.remove('modal--error'); merr.textContent='';});
code.addEventListener('keydown',e=>{
  if(e.key==='Enter'){e.preventDefault();
    const c=code.value.trim(); if(c)start(c);}});
scrim.addEventListener('mousedown',e=>{if(e.target===scrim)closeModal();});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&!scrim.hidden)closeModal();
  if(e.key==='Tab'&&!scrim.hidden){
    const f=[code,mrun,modal.querySelector('.modal__foot a')].filter(Boolean);
    if(e.shiftKey&&document.activeElement===f[0]){e.preventDefault();f[f.length-1].focus();}
    else if(!e.shiftKey&&document.activeElement===f[f.length-1]){e.preventDefault();f[0].focus();}
  }});
"""


def index_page(demos: list[dict]) -> str:
    demo_href = f'/brief/{H.escape(demos[0]["job_id"])}' if demos else "/"

    def ex(d: dict) -> str:
        cat = H.escape(d.get("category") or "")
        meta = f'{cat} · {d["count"]} videos' if cat else f'{d["count"]} videos'
        return (f'<a class="ex" href="/brief/{H.escape(d["job_id"])}">'
                f'<span class="ex__brand">{H.escape(d["brand"])}</span>'
                f'<span class="ex__cat">{meta}</span>'
                f'<span class="ex__arrow">→</span></a>')

    examples = (
        f'<section class="examples">'
        f'<p class="examples__label">See a finished report <span>— no wait</span></p>'
        f'<div class="examples__list">{"".join(ex(d) for d in demos)}</div>'
        f'</section>') if demos else ""

    body = f"""{BLOOM.format(extra="")}
<div class="scrim" id="scrim" hidden>
  <div class="modal" id="modal" role="dialog" aria-modal="true"
       aria-labelledby="modal-title">
    <h2 class="modal__title" id="modal-title">Live runs are invite-only during beta</h2>
    <p class="modal__body">Each run crawls ~<span class="num">1,700</span> videos
      across <span class="num">17</span> searches, so access is limited for now.</p>
    <div class="modal__row">
      <div class="modal__field">
        <input class="modal__input" id="code" type="text" placeholder="invite code"
               autocomplete="off" spellcheck="false" aria-describedby="merr">
      </div>
      <button class="modal__run" id="mrun" type="button" disabled>Run</button>
    </div>
    <p class="modal__error" id="merr" aria-live="polite"></p>
    <p class="modal__foot">No code?
      <a href="{demo_href}">See a finished report →</a></p>
  </div>
</div>
{TOPBAR}
<main class="page--hero">
  <h1 class="hero__title">Skip the scroll.<br>Watch the 3% that hit.</h1>
  <p class="hero__sub">TikTok's search filters suck — no date, no reach, no format.
    So researching a competitor's viral videos means digging through thousands
    first. Spark does the digging so you can just watch.</p>

  <div class="thresholds" aria-label="Thresholds already applied">{_gates()}</div>

  <form class="search" id="search">
    <div class="search__row">
      <div class="search__field">
        <input class="search__input" id="brand" type="text" placeholder="wavytalk"
               autocomplete="off" spellcheck="false">
        <span class="search__spinner" id="spinner" hidden></span>
      </div>
      <button class="search__submit" id="go" type="submit">Start digging</button>
    </div>
    <p class="status" id="status" hidden><span class="status__mark"
      id="status-mark"></span><span id="status-text"></span></p>
  </form>
  {examples}
</main>"""
    return _shell("Spark", body, INDEX_JS)


# ---------------------------------------------------------------- 加载页

JOB_JS = r"""
const ID=location.pathname.split('/').pop();
const fill=document.getElementById('fill'),bar=document.getElementById('bar'),
      pct=document.getElementById('pct'),lines=document.querySelectorAll('.stage__line');
let a=lines[0],b=lines[1],shown='';

// 服务端只发纯文本 —— 阶段文案里含用户输入的品牌名，走 innerHTML 就是 XSS。
// 数字的等宽样式因此放弃，值得。
function swap(text){
  if(text===shown)return; shown=text;
  b.textContent=text; b.classList.add('is-current'); a.classList.remove('is-current');
  const t=a; a=b; b=t;
}
function poll(){
  fetch('/api/jobs/'+ID).then(r=>r.json()).then(d=>{
    if(d.status==='done'){location.href='/brief/'+ID;return;}
    if(d.status==='failed'){swap('Something went wrong: '+(d.error||''));return;}
    const p=d.progress_pct||0;
    fill.style.width=p+'%'; bar.setAttribute('aria-valuenow',String(p));
    pct.textContent=p+'%';
    swap((d.stage_detail? d.stage+' — '+d.stage_detail : d.stage)||'');
    setTimeout(poll,3000);
  }).catch(()=>setTimeout(poll,5000));
}
// 标签页标题带进度，切走也能扫一眼
setInterval(()=>{document.title=(pct.textContent||'')+' · '+document.title.split(' · ').pop();},3000);
poll();
"""


def job_page(brand: str) -> str:
    body = f"""{BLOOM.format(extra=" bloom--drift")}
{TOPBAR}
<main class="loading">
  <h1 class="loading__title">Reading TikTok</h1>
  <div class="loading__meter">
    <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100"
         aria-valuenow="0" id="bar"><div class="bar__fill" id="fill"></div></div>
    <div class="pct" id="pct">0%</div>
  </div>
  <div class="stage" id="stage" aria-live="polite">
    <p class="stage__line is-current">Starting…</p>
    <p class="stage__line"></p>
  </div>
  <p class="loading__note">About 10 minutes. Go make coffee — just don't close
    this tab, it's the only way back.</p>
</main>"""
    return _shell(f"{brand} — Spark", body, JOB_JS)


# ---------------------------------------------------------------- 结果页

RESULT_JS = r"""
const picked={followers:'all',voiceover:'all'};
const grid=document.getElementById('grid'),empty=document.getElementById('empty'),
      count=document.getElementById('count');
function apply(){
  let n=0;
  document.querySelectorAll('.card').forEach(c=>{
    const ok=(picked.followers==='all'||c.dataset.fans===picked.followers)
          &&(picked.voiceover==='all'||c.dataset.speech===picked.voiceover);
    c.style.display=ok?'':'none'; if(ok)n++;
  });
  count.textContent=n;
  grid.hidden=n===0; empty.hidden=n!==0;
}
document.querySelectorAll('.fgroup').forEach(g=>{
  const key=g.getAttribute('data-group');
  g.querySelectorAll('.f').forEach(pill=>{
    pill.addEventListener('click',()=>{
      picked[key]=pill.getAttribute('data-value');
      g.querySelectorAll('.f').forEach(o=>{
        const on=o===pill;
        o.classList.toggle('on',on); o.setAttribute('aria-pressed',String(on));
      });
      apply();
    });
  });
});
const info=document.getElementById('info'),ibtn=document.getElementById('ibtn'),
      pop=document.getElementById('pop');
function setPop(open){pop.hidden=!open;ibtn.setAttribute('aria-expanded',String(open));}
ibtn.addEventListener('click',e=>{e.stopPropagation();setPop(pop.hidden);});
document.addEventListener('click',e=>{if(!pop.hidden&&!info.contains(e.target))setPop(false);});
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'&&!pop.hidden){setPop(false);ibtn.focus();}});
apply();
"""


def _card(v: dict, source: str, mined: bool, frame_exists) -> str:
    # 封面三级回退：自己抽的帧 → 本地缓存 → 远程 CDN。
    # 远程排最后 —— 它带签名、约两天过期，只能兜底不能当主力。
    if frame_exists(v["id"]):
        src = f'/frames/{v["id"]}_h0.jpg'
    elif v.get("cover_local"):
        src = v["cover_local"]
    elif v.get("cover_url"):
        src = v["cover_url"]
    else:
        src = ""
    img = (f'<img class="thumb__img" src="{H.escape(src)}" loading="lazy" alt="">'
           if src else '<img class="thumb__img" alt="">')

    over = v["plays_per_follower"]
    badge = (f'<div class="badge"><span class="badge__bolt">⚡</span>Views '
             f'<span>{over:.0f}</span>× followers</div>' if over >= 3 else "")

    has_vo = bool(v["has_subtitles"])
    vo_icon = ICONS["vo"].format(slash="" if has_vo else ICONS["vo_slash"])
    vo_cls = "m m--vo" + ("" if has_vo else " is-off")

    return f"""<a class="card" data-fans="{fan_bucket(v['followers'])}"
   data-speech="{'vo' if has_vo else 'novo'}"
   href="{H.escape(v['url'])}" target="_blank" rel="noopener">
  <div class="thumb">{img}{badge}<div class="dur">{v['duration']}s</div></div>
  <div class="perf metrics">
    <span class="m m--views" title="Views">{ICONS['views']}
      <span class="m__v">{human(v['plays'])}</span></span>
    <span class="m m--eng{' is-top' if mined.get('eng_top') else ''}" title="Engagement rate">{ICONS['eng']}
      <span class="m__v">{v['engagement_rate']*100:.1f}%</span></span>
    <span class="{vo_cls}" title="Voiceover">{vo_icon}
      <span class="m__v">{'VO' if has_vo else 'no VO'}</span></span>
  </div>
  <div class="who metrics">
    <span class="m m--handle" title="Creator">{ICONS['handle']}
      <span class="who__handle">@{H.escape(v['author'])}</span></span>
    <span class="m m--followers" title="Followers">{ICONS['followers']}
      <span class="m__v">{human(v['followers'])}</span></span>
  </div>
</a>"""


def result_page(data: dict, *, frame_exists) -> str:
    brand = data["brand"]
    vids = data["videos"]
    src = data.get("sources", {})
    plain = {brand["nickname"].lower(), brand["hashtag"].lower()}

    # 互动率前 15% 上色。排序只编码了播放量，互动率完全没被编码 ——
    # 实测播放量前 10 里只有 3 条互动率也在前 10，两个维度基本独立。
    ers = sorted((v["engagement_rate"] for v in vids), reverse=True)
    cut = ers[max(0, -(-len(ers) * 15 // 100) - 1)] if ers else 1.0

    fans = {"lt100k": 0, "mid": 0, "gt1m": 0}
    speech = {"vo": 0, "novo": 0}
    for v in vids:
        fans[fan_bucket(v["followers"])] += 1
        speech["vo" if v["has_subtitles"] else "novo"] += 1
    n_mined = sum(1 for v in vids
                  if src.get(v["id"], "").strip('"#').lower() not in plain)

    def pill(key, val, label, n):
        on = " on" if val == "all" else ""
        return (f'<button class="f{on}" type="button" data-value="{val}"'
                f' aria-pressed="{str(val == "all").lower()}">{label} '
                f'<span class="f__n">{n}</span></button>')

    terms = " · ".join(H.escape(t) for t in (data.get("terms") or []))
    cards = "".join(
        _card(v, src.get(v["id"], ""),
              {"eng_top": v["engagement_rate"] >= cut}, frame_exists)
        for v in vids)

    body = f"""{TOPBAR_STICKY.format(n=len(vids))}
<main class="page--report">
  <h1 class="brand">{H.escape(brand['nickname'])}</h1>
  <p class="yield">Crawled <span class="num">{data['stats'].get('after_dedupe', 0):,}</span>
    videos · <span class="num">{len(vids)}</span> cleared every bar ·
    max <span class="num">{C.MAX_VIDEOS_PER_ACCOUNT}</span> per creator</p>

  <p class="sourcenote">
    <span class="info" id="info">
      <button class="ibtn" id="ibtn" type="button" aria-expanded="false"
              aria-controls="pop">{ICONS['info']}
        <span class="num">{n_mined}</span> found only by a tag Spark learned</button>
      <span class="pop" id="pop" role="dialog"
            aria-label="How Spark found these" hidden>
        <span class="pop__title">How Spark found these</span>
        <span class="pop__label">Searched
          <span class="num">{len(data.get('terms') or [])}</span> terms</span>
        <span class="pop__terms">{terms}</span>
        <span class="pop__note"><strong>{n_mined} of {len(vids)}</strong> were found
          only through a tag or product name Spark learned — not by searching
          the brand.</span>
      </span>
    </span>
  </p>

  <div class="thresholds" aria-label="Thresholds already applied">{_gates()}</div>

  <div class="filters">
    <div class="filters__groups">
      <div class="fgroup" data-group="followers">
        <div class="fgroup__label">Followers</div>
        <div class="fgroup__pills">
          {pill('followers', 'all', 'All', len(vids))}
          {pill('followers', 'lt100k', '&lt;100k', fans['lt100k'])}
          {pill('followers', 'mid', '100k–1M', fans['mid'])}
          {pill('followers', 'gt1m', '1M+', fans['gt1m'])}
        </div>
      </div>
      <div class="fgroup" data-group="voiceover">
        <div class="fgroup__label">Voiceover</div>
        <div class="fgroup__pills">
          {pill('voiceover', 'all', 'All', len(vids))}
          {pill('voiceover', 'vo', 'Has VO', speech['vo'])}
          {pill('voiceover', 'novo', 'No VO', speech['novo'])}
        </div>
      </div>
    </div>
  </div>

  <div class="grid" id="grid">{cards}</div>

  <div class="empty" id="empty" hidden>
    <p class="empty__title">Nothing clears both filters</p>
    <p class="empty__body">Loosen one of them to see videos again.</p>
  </div>
</main>"""
    return _shell(f"{brand['nickname']} — Spark", body, RESULT_JS)
