# Spark

**[spark-production-bd06.up.railway.app](https://spark-production-bd06.up.railway.app)**

> 🇨🇳 中文在前，**English version below** ↓ &nbsp;·&nbsp;
> [Jump to English](#spark-english)

输入一个品牌名，十分钟后拿到这个品牌相关的、真正跑出成绩的达人视频——带封面、
数据和筛选器。

真实抓取是邀请制的（每跑一次都花真钱），但
**[一份跑好的报告](https://spark-production-bd06.up.railway.app/brief/baa8bf6bdae9)**
对所有人开放。

---

## 要解决的问题

TikTok 的搜索没有筛选器。没有时间范围、没有播放量下限、没有时长、没有"只看视频"。
做营销的人想研究达人怎么讲一个竞品，只能打开 App 搜品牌名，然后一直往下划——
划过几个月前的旧帖、图文轮播、外语视频、和只有 400 播放的内容。

以某个美发工具品牌（下称 **W\***，名字略去）为例，搜索面上大约有 **1,700 条**视频，其中值得看的大约
**47 条**。哪怕每条只花几秒判断，光是筛选就要三到五小时，真正的工作还没开始。

## Spark 做的事

举个真实例子。这是
**[美发工具品牌 W\* 那份跑好的报告](https://spark-production-bd06.up.railway.app/brief/baa8bf6bdae9)**
顶部的一行字（点进去能看到完整的 47 条）：

```
Crawled 1,702 videos · 47 cleared every bar · max 3 per creator
```

爬了 1,702 条，47 条过关。每一条都清了七道硬门槛：

- **近 30 天** —— 半年前的爆款对现在没有参考价值
- **播放 1 万以上**
- **互动率 3% 以上** —— 低于 1% 基本可以判定是买的量
- **时长 10–90 秒**
- **英文**
- **视频**，不要图文轮播
- **达人发的**，不要品牌官号自己发的

过关之后再排序、去重，并限制**每个达人最多 3 条**，免得一个高产账号占满整页。

---

## 两个关键机制

### 一、品牌的"自有词汇"是挖出来的，不是猜的

搜品牌名只能捞到一部分。达人会用品牌投放时铺的产品标签，也会在文案里
用自然语言写产品名——这两类词事先都不可能知道。

所以召回分两轮。第一轮搜品牌名和品牌标签；第二轮读回来的文案，把实际在用的
词提取出来，再搜一遍：

```
#wthermalbrush   #whair          #wairshape
#wsteam          #wpowerwave     #w5in1
"w blowout boost"     "w steam sesh"
```

**最终 47 条里有 29 条，只能通过 Spark 学到的词才找得到**，搜品牌名是搜不到的。
这就是它和你自己在 TikTok 里搜一遍的区别。

标签挖掘和自然语言产品名挖掘是两遍独立的处理，因为它们找到的是不同的东西。
产品名必须在**剥掉文案里的 hashtag 之后**再提取——否则
`#wthermalbrush` 会被读成"品牌名 + 产品名 thermalbrush"，
第二轮一半的预算会花在重新搜索已经找到的视频上。

### 二、排序用免费代理，但先验证过它够不够用

最初的设计按**账号基线倍数**排序——这条视频的播放量，除以该达人自己的播放中位数。
这是个诚实的指标：20 万播放对一个 200 万粉的账号和一个 2 万粉的账号意义完全不同。
但要算它，得为每个达人多抓约 20 条历史视频，成本高一个量级。

我先把它实现了，然后测试"播放量 ÷ 粉丝数"这个免费代理——每次 API 返回里本来就有——
是不是足够接近。

**秩相关系数 +0.78，Top20 重合 14/20。**

够用。于是删掉了整块历史抓取。卡片上的 ⚡ 角标现在的含义是"播放量达到粉丝数的 3 倍
以上"。计算真实基线的代码没有了，但那次让我敢删掉它的测量，正是这个项目每次跑
只要几美元而不是五十美元的原因。

---

## 漏斗到底砍掉了什么

美发工具品牌 W\* 那次的真实数字：

| 关卡 | 剩余 | 淘汰 |
|---|---:|---:|
| 17 次搜索召回 | 2,400 | |
| 去重 | 1,702 | −698 |
| 排除图文轮播 | 1,426 | −276 |
| 只留英文 | 1,026 | −400 |
| 时长 10–90 秒 | 783 | −243 |
| 近 30 天 | 338 | −445 |
| 播放 ≥ 1 万 | 108 | −230 |
| 互动率 ≥ 3% | 49 | −59 |
| 相关性 | 47 | −2 |

互动率这一关是一箭双雕。低于 1% 时，一条视频的播放量几乎可以确定是买来的——
付费放量会推高播放，但不会同比例带来点赞和评论。3% 这条线筛的是"看到的人真的
有反应"的视频。

---

## 架构

```
品牌名 → 4 路并行搜索 → 挖词 → 13 路并发再搜 → 去重/过滤/排序 → 抽封面帧 → 结果页
```

- **FastAPI + SQLite + 服务端渲染**，Docker 部署到 Railway
- **抓取全异步**：Apify 同步接口有 300 秒上限，全部走「启动 run → 轮询 → 取数据」，
  信号量限并发
- **失败隔离**：单次抓取异常降级为空列表，不中断整个任务
- **十分钟任务跑在后台**，状态机管理，进度按实测耗时加权，前端每 3 秒轮询
- **成本约束写进流程**：同品牌重复提交复用任务、邀请码服务端校验、
  20 条样本预探测（约 1% 成本）
- **阈值集中在 `config.py`**，每个都带实测依据

```
app/
  apify.py     异步 run、轮询、并发控制、失败隔离
  models.py    唯一接触原始 JSON 的文件，下游只看 dataclass
  mining.py    两阶段词汇挖掘
  funnel.py    硬门槛、相关性打分、排序
  pipeline.py  编排与进度回调
  render.py    三个页面
  main.py      路由、任务生命周期、邀请码校验
```

<br>

---
---

<br>

<a name="spark-english"></a>

# Spark <sub>(English)</sub>

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

For one hair-tool brand — call it **W\***, name withheld — the raw search surface is about **1,700
videos**. Roughly **47** of them are worth watching. At a few seconds each just
to judge, that's three to five hours of screening before the actual work starts.

## What Spark does

A real example — this line sits at the top of
**[the finished report for W\*, a hair-tool brand](https://spark-production-bd06.up.railway.app/brief/baa8bf6bdae9)**
(open it to see all 47):

```
Crawled 1,702 videos · 47 cleared every bar · max 3 per creator
```

1,702 crawled, 47 kept. Each one cleared seven hard gates:

- **Last 30 days** — a hit from six months ago tells you nothing about now
- **10k+ views**
- **3%+ engagement** — under 1% and the reach was almost certainly bought
- **10–90 seconds**
- **English**
- **Video**, not a photo slideshow
- **Posted by a creator**, not the brand's own account

What survives is then ranked, deduped, and capped at **three videos per creator**
so one prolific account can't own the page.

---

## Two things that make it work

### 1. The brand's own vocabulary is mined, not assumed

Searching the brand name finds a fraction of what exists. Creators tag videos with
product-specific hashtags the brand seeded, and write product names in plain
English. Neither is knowable in advance.

So recall runs in two stages. Stage one searches the brand name and hashtag.
Stage two reads the captions that came back, extracts the vocabulary actually in
use, and searches again:

```
#wthermalbrush   #whair          #wairshape
#wsteam          #wpowerwave     #w5in1
"w blowout boost"     "w steam sesh"
```

**29 of the 47 final results were reachable only through a term Spark learned** —
not by searching the brand. That's the difference between this and typing the
brand into TikTok yourself.

Hashtag mining and natural-language product-name mining are separate passes,
because they find different things. Product names must be extracted *after*
stripping hashtags from the caption — otherwise `#wthermalbrush` reads as
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

Real numbers from the W\* (hair tools) run:

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

## Architecture

```
brand name → 4 parallel searches → mine terms → 13 more searches
           → dedupe / filter / rank → cover frames → report page
```

- **FastAPI + SQLite + server-rendered HTML**, deployed to Railway via Docker
- **All crawling is async**: Apify's sync endpoint caps at 300s, so everything is
  start-run → poll → fetch, with a semaphore capping concurrency
- **Failure isolation**: a crawl that throws degrades to an empty list instead of
  killing the job
- **Ten-minute jobs run in the background** behind a state machine; progress is
  weighted by measured duration and polled every 3s
- **Cost constraints are built into the pipeline**: duplicate submissions reuse
  the in-flight job, live runs sit behind a server-side invite check, and a
  20-video probe screens a brand for ~1% of a full run
- **Every threshold lives in `config.py`** with the measurement behind it

```
app/
  apify.py     Async runs, polling, concurrency limits, failure isolation
  models.py    The only file that touches raw JSON; downstream sees dataclasses
  mining.py    Two-stage vocabulary extraction
  funnel.py    Hard gates, relevance scoring, ranking
  pipeline.py  Orchestration and progress callbacks
  render.py    Three pages
  main.py      Routes, job lifecycle, invite gate
```
