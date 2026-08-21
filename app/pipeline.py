"""端到端流水线：品牌名 → Top 50 达人视频。

用户只输入品牌名，其余全部推导。实测验证过：让用户输官号 handle 唯一多给的
信息是 author_id，而它对结果的贡献是 0 条（品牌自己发的视频在轮到官号过滤之前
就已被互动率等门槛挡掉）。既然输入什么都不影响结果，就用对用户最简单的。

阶段与耗时（实测 wavytalk）：

    recall1    4 路探路           ~2 min    $1.4
    mine       挖词（本地）        <1s       $0
    recall2    13 路扩量          ~5 min    $4.4
    filter     漏斗 + 排序（本地）  <1s       $0
    frames     下载 Top50 抽首帧    ~1 min    $0
                                  ~8 min    ~$5.8
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import config as C
from . import frames as F
from . import funnel, mining
from .apify import Apify
from .funnel import BrandRef, FunnelStats
from .models import Video, dedupe, parse_many

log = logging.getLogger(__name__)

# 各阶段占总进度的权重。实测比例，不必精确 —— 但召回占大头这件事必须体现，
# 否则进度条会在最长的那一段假装很快然后卡住。
STAGES = [
    ("recall1", "Searching TikTok", 22),
    ("mine", "Learning the brand's own hashtags", 3),
    ("recall2", "Searching the terms we just learned", 45),
    ("filter", "Filtering and ranking", 5),
    ("frames", "Grabbing cover frames", 25),
]


@dataclass(slots=True)
class Progress:
    stage: str = "queued"
    label: str = ""
    detail: str = ""
    pct: int = 0


@dataclass(slots=True)
class Result:
    brand: BrandRef
    videos: list[Video] = field(default_factory=list)
    sources: dict[str, str] = field(default_factory=dict)
    terms: list[str] = field(default_factory=list)
    stats: FunnelStats = field(default_factory=FunnelStats)
    raw_count: int = 0


def _source_map(raws: list[dict]) -> dict[str, str]:
    """记录每条视频是被哪个搜索词捞到的 —— 这是产品差异化的可见证明。"""
    out: dict[str, str] = {}
    for r in raws:
        vid = str(r.get("id") or "")
        if not vid or vid in out:
            continue
        if r.get("searchQuery"):
            out[vid] = f'"{r["searchQuery"]}"'
        else:
            h = r.get("searchHashtag")
            if h:
                out[vid] = "#" + (h if isinstance(h, str) else h.get("name", ""))
    return out


async def probe(brand_name: str, *, per_run: int = 20) -> int:
    """输入框失焦时的快速体检：搜 20 条，看能拿回几条。

    拿不到总量（TikTok 不暴露「这个标签下共有多少视频」），只能看填充率：
    要 20 给 20 = 素材充足；只给回 3 条 = 这个词搜不到东西。
    作用是在花掉 10 分钟之前拦住拼写错误和冷门品牌。
    """
    brand = BrandRef.from_brand_name(brand_name)
    items = await Apify().run(
        {"searchQueries": [brand.nickname], "resultsPerPage": per_run,
         "shouldDownloadSubtitles": False},
        label=f"probe:{brand_name}",
    )
    return len(items)


async def analyze(brand_name: str, *, on_progress=None,
                  dev: bool = False) -> Result:
    """跑完整条流水线。on_progress(Progress) 会被反复调用。"""
    brand = BrandRef.from_brand_name(brand_name)
    api = Apify()
    per_run = C.DEV_ITEMS_PER_RUN if dev else C.RECALL_ITEMS_PER_RUN
    per_run2 = C.DEV_ITEMS_PER_RUN if dev else C.RECALL2_ITEMS_PER_RUN
    base = 0

    def emit(stage: str, label: str, detail: str = "", frac: float = 0.0) -> None:
        w = dict((s, w) for s, _, w in STAGES).get(stage, 0)
        if on_progress:
            on_progress(Progress(stage, label, detail,
                                 min(99, int(base + w * frac))))

    # ---------------------------------------------------------------- 1 召回
    emit("recall1", "Searching TikTok", f'"{brand.nickname}" · #{brand.hashtag}')
    t0 = time.time()
    raws = await api.recall(nickname=brand.nickname, hashtag=brand.hashtag,
                            username=brand.hashtag, per_run=per_run)
    log.info("recall1 %d 条 %.0fs", len(raws), time.time() - t0)
    base += 22

    # ---------------------------------------------------------------- 2 挖词
    emit("mine", "Learning the brand's own hashtags")
    terms = mining.mine(raws, token=brand.hashtag, nickname=brand.nickname)
    picked = mining.pick(terms)

    # 挖词是纯字符串处理，真实耗时接近 0，而前端每 3 秒才轮询一次 ——
    # 不停一下的话这一步根本不会被采样到，用户永远看不见它。
    # 但它恰恰是整个产品最值得看的一步（"我们学会了品牌自己的说法"），
    # 所以这里让它在屏幕上驻留两拍：先报数量，再报具体挖到了什么。
    # 这不是假进度，阶段真实发生过，只是把它显示得够久到能读完。
    emit("mine", "Learning the brand's own hashtags",
         f"found {len(picked)} more ways creators tag it", 0.4)
    await asyncio.sleep(C.MINE_DWELL_S)
    sample = ", ".join(t.value for t in picked[:2])
    emit("mine", "Learning the brand's own hashtags", sample, 1.0)
    await asyncio.sleep(C.MINE_DWELL_S)
    base += 3

    # ---------------------------------------------------------------- 3 扩量
    payloads = mining.selected_payloads(terms, per_run=per_run2)
    done = {"n": 0}

    def tick(label: str, n: int) -> None:
        done["n"] += 1
        emit("recall2", "Searching the terms we just learned",
             f"{label} — {done['n']} of {len(payloads)}",
             done["n"] / max(len(payloads), 1))

    if payloads:
        emit("recall2", "Searching the terms we just learned",
             f"0 of {len(payloads)}")
        t0 = time.time()
        res = await api.run_batch(payloads, on_done=tick)
        for items in res.values():
            raws += items
        log.info("recall2 %.0fs，累计 %d 条", time.time() - t0, len(raws))
    base += 45

    # ---------------------------------------------------------------- 4 漏斗
    emit("filter", "Filtering and ranking")
    videos = dedupe(parse_many(raws))
    st = FunnelStats(recalled=len(raws))
    kept = funnel.hard_filter(videos, brand, window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=st)
    top = funnel.final_rank(kept)
    emit("filter", "Filtering and ranking",
         f"{len(top)} of {st.after_dedupe:,} cleared every bar", 1.0)
    base += 5

    # ---------------------------------------------------------------- 5 抽帧
    # CDN 封面链接带签名会过期，本地抽一帧才是可靠的封面。
    if top and not F.check_tools():
        def fprog(n: int, total: int, v, ok: bool) -> None:
            emit("frames", "Grabbing cover frames", f"{n} of {total}", n / total)
        emit("frames", "Grabbing cover frames", f"0 of {len(top)}")
        await F.build_hook_frames(top, on_progress=fprog)
    base += 25

    return Result(brand=brand, videos=top, sources=_source_map(raws),
                  terms=[t.value if t.kind == "keyword" else f"#{t.value}"
                         for t in picked],
                  stats=st, raw_count=len(raws))


def save(result: Result, path: Path) -> None:
    """把结果落盘，供结果页渲染和 demo 复用。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "brand": {"nickname": result.brand.nickname,
                  "hashtag": result.brand.hashtag},
        "stats": result.stats.as_dict(),
        "raw_count": result.raw_count,
        "terms": result.terms,
        "sources": result.sources,
        "videos": [{
            "id": v.id, "url": v.url, "caption": v.caption,
            "plays": v.plays, "likes": v.likes, "comments": v.comments,
            "shares": v.shares, "duration": v.duration,
            "engagement_rate": round(v.engagement_rate, 5),
            "plays_per_follower": round(v.plays_per_follower, 2),
            "has_subtitles": v.has_subtitles, "cover_url": v.cover_url,
            "author": v.author.username, "followers": v.author.followers,
        } for v in result.videos],
    }, ensure_ascii=False), encoding="utf-8")
