# Spark

**[spark-production-bd06.up.railway.app](https://spark-production-bd06.up.railway.app)**

Type a brand name. Ten minutes later you get the creator videos about that brand
that actually performed — with covers, metrics, and filters.

Live runs are invite-only (each one costs real money), but
**[a finished report](https://spark-production-bd06.up.railway.app/brief/baa8bf6bdae9)**
is open to anyone.

---

## The problem

TikTok's search has no filters. No date range, no view floor, no duration, no
"video only." If you're a marketer researching how creators talk about a
competitor, you open the app, search the brand, and scroll — through months-old
posts, photo slideshows, foreign-language clips, and videos with 400 views.

For WavyTalk (a hair-tool brand), the raw search surface is about **1,700
videos**. Roughly **47** of them are worth watching. At a few seconds each just
to judge, that's three to five hours of screening before the actual work starts.

## What Spark does

```
Crawled 1,702 videos · 47 cleared every bar · max 3 per creator
```

Every result has cleared seven hard gates — last 30 days, 10k+ views, 3%+
engagement, 10–90 seconds, English, video not slideshow, creator not brand
account — then ranked, deduped, and capped at three videos per creator so one
prolific account can't own the page.

---

## Two things that make it work

### 1. The brand's own vocabulary is mined, not assumed

Searching `wavytalk` finds a fraction of what exists. Creators tag videos with
product-specific hashtags the brand seeded, and write product names in plain
English. Neither is knowable in advance.

So recall runs in two stages. Stage one searches the brand name and hashtag.
Stage two reads the captions that came back, extracts the vocabulary actually in
use, and searches again:

```
#wavytalkthermalbrush   #wavytalkhair    #wavytalkairshape
#wavytalksteam          #wavytalkpowerwave   #wavytalk5in1
"wavytalk blowout boost"    "wavytalk steam sesh"
```

**29 of the 47 final results were reachable only through a term Spark learned** —
not by searching the brand. That's the difference between this and typing the
brand into TikTok yourself.

Hashtag mining and natural-language product-name mining are separate passes,
because they find different things. Product names must be extracted *after*
stripping hashtags from the caption — otherwise `#wavytalkthermalbrush` reads as
"brand + product `thermalbrush`" and half the second-stage budget gets spent
re-searching videos already found.

### 2. Ranking uses a free proxy, validated against the expensive one

The original design ranked by *account baseline multiple* — this video's views
divided by that creator's own median. It's the honest metric: 200k views means
something different for a 2M-follower account than a 20k one. But computing it
means crawling ~20 historical videos per creator, which multiplies cost by an
order of magnitude.

I built it, then tested whether `views ÷ followers` — free, already in every API
response — was close enough.

**Spearman rank correlation: +0.78. Top-20 overlap: 14/20.**

Close enough. The baseline crawl was removed, and the ⚡ badge on a card now
means views reached 3× the creator's follower count. The code that computed the
real baseline is gone; the measurement that justified deleting it is the reason
this project costs a few dollars per run instead of fifty.

---

## What the funnel actually removes

Real numbers from the WavyTalk run:

| Gate | Remaining | Cut |
|---|---:|---:|
| Recalled across 17 searches | 2,400 | |
| Deduped | 1,702 | −698 |
| Photo slideshows removed | 1,426 | −276 |
| English only | 1,026 | −400 |
| 10–90 seconds | 783 | −243 |
| Last 30 days | 338 | −445 |
| 10k+ views | 108 | −230 |
| 3%+ engagement | 49 | −59 |
| Relevance | 47 | −2 |

Engagement rate does double duty here. Below ~1%, a video's reach was almost
certainly bought — paid amplification inflates views without moving likes or
comments. The 3% floor filters for videos whose audience actually reacted.

---

## Not every brand works, and that's a finding

Six brands, same pipeline:

| Brand | Crawled | Passed | Rate |
|---|---:|---:|---:|
| Nike | 1,771 | 50 | 2.8% |
| WavyTalk | 1,702 | 47 | 2.8% |
| CeraVe | 1,371 | 25 | 1.8% |
| Momcozy | 2,451 | 29 | 1.2% |
| Nello | 2,097 | 5 | 0.2% |
| Dr Dent | 873 | 2 | 0.2% |

Two distinct failure modes, and they need different tests:

**Not enough volume.** Dr Dent's creator content is mostly older than 30 days,
and 86% of what remained had under 10k views. The brand isn't running an active
creator program. The funnel reports this correctly — there was nothing to find.

**Volume without relevance.** Momcozy returned 29 videos, all genuinely tagged
with the brand. But nearly half were emotional motherhood content with brand
hashtags appended — the video itself has nothing to do with the product:

> *"Baby, you danced terribly and I loved every second."* — 2.3M views,
> `#momcozy #momcozylife #breastpump`

Useless if you're studying how to make content about a breast pump. The pattern
is categorical: products that must be demonstrated on camera (hair tools,
appliances) yield demonstration content. Products attached to an identity
(motherhood) yield identity content with the tag stapled on.

A cheap proxy separates them — strip hashtags from the caption, then check
whether the brand name still appears in the prose. WavyTalk scores 85%,
Momcozy 59%.

### Screening a brand for 30 seconds instead of 10 minutes

```
$ python3 scripts/probe_stats.py "mellow sleep" --show

品牌            回条  播放中位数  ≥10k  近30天  英文  正文提品牌   判断
mellow sleep     20     14,200    45%    20%   75%       50%   ✗ 产量不行
WavyTalk 参照           44,800    66%    37%   67%       85%   → 47 条
```

Twenty videos, about 1% of a full run's cost.

My first design for this was wrong, and the data showed it. I planned to run the
20 sample videos through the real filters and count survivors — but the pass
rate is 1–3%, so 20 samples yield an expected 0.03–0.55 survivors. Both good and
bad brands score zero. Rare events carry no signal at n=20.

Measuring *distributions* does: a median and a proportion are stable on 20
samples. That's what the tool reports now.

---

## Build

```
FastAPI · SQLite · server-rendered HTML · Apify TikTok actor · Docker · Railway
```

No frontend framework, no template engine, no ORM. Pages are Python f-strings;
filtering is 40 lines of vanilla JS. A ten-minute job runs in a background task
with an in-process state machine, and the page polls every three seconds.

```
app/
  apify.py     API client. Async run + poll — the sync endpoint caps at 300s
               and recall always exceeds it.
  models.py    The only file that touches raw Apify JSON. Everything downstream
               sees normalized dataclasses.
  mining.py    Two-stage vocabulary extraction.
  funnel.py    Hard gates, relevance scoring, percentile ranking.
  pipeline.py  Orchestration with progress callbacks.
  render.py    Three pages, one stylesheet.
  main.py      Routes, job lifecycle, invite gate.

scripts/
  probe_stats.py   Screen a brand before spending on it.
  cache_covers.py  Apify cover URLs expire in ~48h. Demos need permanent ones.
  mark_demo.py     Pick which report the homepage links to.
```

Every threshold lives in `config.py`, each with the measurement behind it in a
comment. `WINDOW_DAYS`, `MIN_PLAYS`, `MIN_ENGAGEMENT_RATE`,
`MAX_VIDEOS_PER_ACCOUNT` — none of them are round numbers picked by feel.

### A few decisions worth naming

**Brand name as the only input.** The original design asked for the official
TikTok handle. Testing showed the handle's only unique contribution was an
`author_id` used to exclude the brand's own posts — and that exclusion removed
**zero** videos, because the brand's 169 posts had already failed other gates.
Running without it returned an identical result set. One less thing to explain,
one less thing to get wrong.

**Recall saturates.** A third recall round added 484 unique videos and **2**
qualifying ones — 0.4% marginal yield against a 2.3% average. The binding
constraint on reaching 50 was the per-creator cap, not recall volume.

**The invite gate is server-side.** The repo is public, so the code lives in an
environment variable and `/api/jobs` checks it on every request. A front-end
check would be decoration — the endpoint is one `curl` away from anyone reading
the page source.

---

## Running it

```bash
cp .env.example .env      # add APIFY_TOKEN
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Leave `SPARK_INVITE_CODE` empty locally and the gate is open.

```bash
python3 scripts/probe_stats.py "brand name" --show   # ~1% of a run's cost
```

Deploys to Railway from the Dockerfile. `seed/` carries one finished report so a
fresh instance has something to show.
