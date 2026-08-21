"""账号基线倍数。

    基线倍数 = 这条视频播放量 ÷ 该达人「在发这条之前」平常的播放中位数

分子免费（搜索结果里就有），分母要额外爬账号历史 —— 这是整个流水线最贵的一步，
所以只对预筛出来的 30 个账号做。

三条约束，每条都对应一个会导致结论错误的偏差：

坑 1  只能用目标视频「发布之前」的视频做分母。
      达人靠这条爆了之后，后续视频吃算法红利、播放普遍偏高，算进分母会抬高分母
      → 倍数被低估 → 真正的爆款反而被漏掉。

坑 2  按时间窗切，不按条数切。
      日更账号 40 条覆盖 40 天，周更账号 40 条覆盖 9 个月。后者把半年前的低播放
      数据算进来 → 分母偏低 → 倍数虚高。

坑 3  排除目标视频本身，以及发布不足 7 天的视频。
      前者是自证；后者播放量还在涨，没到终值，会拉低分母。
"""
from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass

from . import config as C
from . import db
from .models import Video, parse_many

log = logging.getLogger(__name__)


@dataclass(slots=True)
class HistoryPoint:
    published_at: int
    plays: int


# ---------------------------------------------------------------- 缓存

def cache_read(author_id: str) -> list[HistoryPoint] | None:
    """读缓存。返回 None 表示没有或已过期，需要重新抓。

    缓存的是原始序列而不是单个中位数 —— 同一账号的不同目标视频时间窗不同，
    分母也不同，存一个数就没法复用了。
    """
    ttl = C.AUTHOR_CACHE_TTL_DAYS * 86400
    with db.connect() as conn:
        meta = conn.execute(
            "SELECT updated_at FROM author_meta WHERE author_id = ?", (author_id,)
        ).fetchone()
        if meta is None or (time.time() - (meta["updated_at"] or 0)) > ttl:
            return None
        rows = conn.execute(
            "SELECT published_at, plays FROM author_videos WHERE author_id = ?",
            (author_id,),
        ).fetchall()
    if not rows:
        return None
    return [HistoryPoint(r["published_at"], r["plays"]) for r in rows]


def cache_write(author_id: str, username: str, followers: int,
                points: list[HistoryPoint]) -> None:
    now = int(time.time())
    oldest = min((p.published_at for p in points), default=0)
    with db.connect() as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO author_videos"
            " (author_id, video_id, published_at, plays) VALUES (?,?,?,?)",
            [(author_id, f"{author_id}:{p.published_at}", p.published_at, p.plays)
             for p in points],
        )
        conn.execute(
            "INSERT OR REPLACE INTO author_meta"
            " (author_id, username, follower_count, fetched_count,"
            "  oldest_fetched_at, updated_at) VALUES (?,?,?,?,?,?)",
            (author_id, username, followers, len(points), oldest, now),
        )


def history_from_raw(raws: list[dict]) -> list[HistoryPoint]:
    return [
        HistoryPoint(v.published_at, v.plays)
        for v in parse_many(raws)
        if v.published_at and v.plays
    ]


# ---------------------------------------------------------------- 核心算法

def compute_baseline(target: Video, history: list[HistoryPoint],
                     *, now: float | None = None) -> tuple[int | None, str]:
    """算单条视频的分母。返回 (中位播放, 置信度)。

    置信度：
      high  —— 在 [T-90d, T) 窗口内拿到 ≥5 条样本，最可信
      low   —— 窗口内不够，退化用了全部历史（超高频发布者会走到这里）
      none  —— 连退化都不够 5 条，该账号应被剔除
    """
    now = now or time.time()
    T = target.published_at
    recent_cut = now - C.BASELINE_EXCLUDE_RECENT_DAYS * 86400

    def usable(p: HistoryPoint) -> bool:
        # 排除目标视频本身（按时间戳近似匹配，历史里没有 video_id）
        if abs(p.published_at - T) < 2:
            return False
        # 排除播放量未收敛的新视频
        return p.published_at <= recent_cut

    pool = [p for p in history if usable(p)]

    for window in (C.BASELINE_WINDOW_DAYS, C.BASELINE_WINDOW_FALLBACK_DAYS):
        lo = T - window * 86400
        sample = [p.plays for p in pool if lo <= p.published_at < T]
        if len(sample) >= C.BASELINE_MIN_SAMPLE:
            return int(statistics.median(sample)), "high"

    # 兜底：抓到的全部都晚于 T（超高频发布者），用全部历史算，但标低置信度。
    # 宁可标注也不要静默给一个错的数字。
    fallback = [p.plays for p in pool]
    if len(fallback) >= C.BASELINE_MIN_SAMPLE:
        return int(statistics.median(fallback)), "low"

    return None, "none"


def apply_baselines(videos: list[Video],
                    histories: dict[str, list[HistoryPoint]]) -> list[Video]:
    """给候选视频填上基线倍数。算不出来的直接剔除。

    histories 的 key 是 username（预筛结果就是 username 列表）。
    """
    out: list[Video] = []
    dropped_no_history = 0
    dropped_thin = 0

    for v in videos:
        hist = histories.get(v.author.username)
        if not hist:
            dropped_no_history += 1
            continue
        baseline, conf = compute_baseline(v, hist)
        if baseline is None or baseline <= 0:
            dropped_thin += 1
            continue
        v.baseline = baseline
        v.baseline_multiple = round(v.plays / baseline, 2)
        v.baseline_confidence = conf
        out.append(v)

    log.info(
        "基线计算：%d 条成功，%d 条无历史，%d 条样本不足（<%d 条，中位数无意义）",
        len(out), dropped_no_history, dropped_thin, C.BASELINE_MIN_SAMPLE,
    )
    return out


def earliest_candidate_ts(videos: list[Video]) -> int:
    """抓历史要回溯到多深：最早候选视频的 T 再往前 90 天。"""
    if not videos:
        return int(time.time())
    earliest = min(v.published_at for v in videos if v.published_at)
    return int(earliest - C.BASELINE_WINDOW_DAYS * 86400)
