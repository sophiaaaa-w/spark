"""漏斗：硬过滤 → relevance 打分 → 预筛账号 → 终排序。

实测漏斗（Color Wow，150 条）：
    原始 150 → 剔图文帖 66 → 只留英文 59 → 时长 44 → 近30天 15 → 播放>10k 7
产出率 4.7%。所有阈值在 config.py，不要在这里写死数字。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, fields
from datetime import datetime, timedelta, timezone

from . import config as C
from .models import Video

# 单个常见英文词的品牌名（Rhode / Hero / Rare / Glow / Wow…）光靠 caption 命中
# 会招来大量无关视频，必须同时有 hashtag 或 @提及。
_COMMON_WORD = re.compile(r"^[a-z]{3,10}$")


@dataclass(slots=True)
class BrandRef:
    """一次分析的品牌锚点。

    用户只输入品牌名，其余全部推导。实测验证过：让用户输官号 handle 唯一多给的
    信息是 author_id，而它对结果的贡献是 **0 条** —— 品牌官号自己发的 169 条
    视频，在轮到官号过滤之前就已经被互动率等门槛全部挡掉了。去掉 author_id
    重跑，结果一模一样（50 vs 50）。

    所以输入什么都不影响结果，那就用对用户最简单的：品牌名。
    """
    nickname: str          # 用户输入的品牌名，关键词搜索用（可编辑）
    hashtag: str           # 归一化后的标签，hashtag 搜索用（可编辑）
    username: str = ""     # 官号 handle，可选，仅用于日志和展示
    author_id: str = ""    # 已不参与过滤，保留字段避免旧数据报错

    @classmethod
    def from_brand_name(cls, name: str) -> "BrandRef":
        """品牌名 → 搜索词。两行都在 chip 里可编辑，猜错了用户能改。"""
        tag = re.sub(r"[^a-z0-9]", "", name.lower())
        return cls(nickname=name.strip(), hashtag=tag, username=tag)

    @property
    def token(self) -> str:
        """归一化的品牌 token，用于识别「多个官号」。

        一个品牌常有多个官方账号（Halara 有 halara_official / halara_shop /
        halaraus / halara.us.live / halara_mx），只剔除一个 ID 会漏掉其余的
        品牌方视角内容。

        优先用 nickname 而不是 username：@wavytalkofficial 的 username 归一化后是
        "wavytalkoff"，只能匹配到带 official 的那个号；而 nickname "WavyTalk" 归一化
        后是 "wavytalk"，能同时匹配 wavytalkofficial / wavytalk_us / wavytalkshop。

        但 nickname 太短时不能用 —— 品牌叫 "Hero" 会把 @heroine_makeup 一起误杀。
        """
        nick = re.sub(r"[^a-z0-9]", "", self.nickname.lower())
        if len(nick) >= 6:
            return nick[:12]
        return re.sub(r"[^a-z0-9]", "", self.username.lower())[:12]

    @property
    def nickname_is_common_word(self) -> bool:
        return bool(_COMMON_WORD.match(self.nickname.strip().lower()))


@dataclass(slots=True)
class FunnelStats:
    recalled: int = 0
    after_dedupe: int = 0
    after_slideshow: int = 0
    after_language: int = 0
    after_duration: int = 0
    after_window: int = 0
    after_plays: int = 0
    after_engagement: int = 0
    after_relevance: int = 0
    after_official: int = 0
    relax_level: int = 1

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


# ---------------------------------------------------------------- 官号识别

def is_official_account(v: Video, brand: BrandRef) -> bool:
    """按 token 前缀匹配剔除官号，不是只剔一个 ID。"""
    if brand.author_id and v.author.id == brand.author_id:
        return True
    username = re.sub(r"[^a-z0-9]", "", v.author.username.lower())
    return bool(brand.token) and username.startswith(brand.token)


# ---------------------------------------------------------------- relevance

def score_relevance(v: Video, brand: BrandRef) -> int:
    caption = v.caption.lower()
    tag = brand.hashtag.lstrip("#").lower()
    nick = brand.nickname.strip().lower()

    hit_hashtag = bool(tag) and any(tag == h or tag in h for h in v.hashtags)
    hit_mention = (
        (brand.author_id and brand.author_id in v.mention_ids)
        or brand.username.lower() in v.mention_names
        or f"@{brand.username.lower()}" in caption
    )
    hit_caption = bool(nick) and nick in caption

    # 单词品牌名：只在 caption 里出现不算数，必须有 hashtag 或 @提及兜底
    if brand.nickname_is_common_word and not (hit_hashtag or hit_mention):
        return 0

    score = 0
    if hit_hashtag:
        score += 3
    if hit_mention:
        score += 4          # 结构化字段，最可靠的硬信号
    if hit_caption:
        score += 2
    if any(w in caption for w in C.BUY_INTENT_WORDS):
        score += 2
    return score


# ---------------------------------------------------------------- 硬过滤

def hard_filter(videos: list[Video], brand: BrandRef, *,
                window_days: int, min_plays: int,
                stats: FunnelStats | None = None) -> list[Video]:
    st = stats or FunnelStats()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=window_days)).timestamp()

    st.after_dedupe = len(videos)

    cur = [v for v in videos if not v.is_slideshow and v.duration > 0]
    st.after_slideshow = len(cur)

    cur = [v for v in cur if v.language in C.ALLOWED_LANGUAGES]
    st.after_language = len(cur)

    cur = [v for v in cur if C.MIN_DURATION_S <= v.duration <= C.MAX_DURATION_S]
    st.after_duration = len(cur)

    cur = [v for v in cur if v.published_at >= cutoff]
    st.after_window = len(cur)

    cur = [v for v in cur if v.plays >= min_plays]
    st.after_plays = len(cur)

    # 挡买量视频。见 config.MIN_ENGAGEMENT_RATE 的完整推理。
    cur = [v for v in cur if v.engagement_rate >= C.MIN_ENGAGEMENT_RATE]
    st.after_engagement = len(cur)

    for v in cur:
        v.relevance = score_relevance(v, brand)
    cur = [v for v in cur if v.relevance >= C.MIN_RELEVANCE]
    st.after_relevance = len(cur)

    cur = [v for v in cur if not is_official_account(v, brand)]
    st.after_official = len(cur)

    return cur


def filter_with_relaxation(videos: list[Video], brand: BrandRef,
                           *, need: int = C.TOP_N) -> tuple[list[Video], FunnelStats]:
    """按放宽阶梯逐级重试，直到样本够用。

    先降播放门槛再扩时间窗 —— 降门槛保住内容新鲜度，扩时间做不到。
    TikTok 内容格式的有效期以周计，陈旧样本会稀释信号。
    """
    best: list[Video] = []
    best_stats = FunnelStats(recalled=len(videos))
    for level, (window, min_plays) in enumerate(C.RELAX_LADDER, start=1):
        trial = FunnelStats(recalled=len(videos))
        got = hard_filter(videos, brand, window_days=window,
                          min_plays=min_plays, stats=trial)
        trial.relax_level = level
        if len(got) > len(best):
            best, best_stats = got, trial
        if len(got) >= need:
            return got, trial
    return best, best_stats


# ---------------------------------------------------------------- 预筛 / 终排序

def prescreen_accounts(videos: list[Video],
                       limit: int = C.PRESCREEN_ACCOUNTS) -> list[str]:
    """选出最值得花钱算真实基线的账号。

    用 播放/粉丝数 单指标排序：这一步要猜「哪些账号可能出现基线异常」，
    而 播放/粉丝 是真实基线倍数最接近的免费代理。互动率衡量的是内容黏性，
    是另一件事，混进来只会模糊目标。

    每个账号取其最好的一条作为代表参与排序，但不丢弃该账号的其他视频。
    """
    best_by_author: dict[str, Video] = {}
    for v in videos:
        cur = best_by_author.get(v.author.username)
        if cur is None or v.plays_per_follower > cur.plays_per_follower:
            best_by_author[v.author.username] = v
    ranked = sorted(best_by_author.values(),
                    key=lambda v: v.plays_per_follower, reverse=True)
    return [v.author.username for v in ranked[:limit]]


def _percentiles(values: list[float]) -> list[float]:
    """把一组数转成 0-1 的百分位（同值取平均秩）。

    必须先转百分位再加权：播放量 1万-650万、互动率 1.5%-15%、播放/粉丝 0.1-500，
    量级差太远，直接加权会被播放量完全支配。
    """
    n = len(values)
    if n <= 1:
        return [1.0] * n
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[order[j + 1]] == values[order[i]]:
            j += 1
        rank = (i + j) / 2 / (n - 1)
        for k in range(i, j + 1):
            out[order[k]] = rank
        i = j + 1
    return out


def score_videos(videos: list[Video]) -> list[Video]:
    """给每条视频算加权得分，写进 v.score。

    权重在 config：播放 0.7 / 互动率 0.2 / 播放粉丝比 0.1。
    播放量占大头是刻意的 —— TikTok 的分发很严酷，大号内容不好照样没播放，
    所以播放量本身就是「有没有人爱看」的有效信号。
    """
    if not videos:
        return videos
    p_plays = _percentiles([float(v.plays) for v in videos])
    p_eng = _percentiles([v.engagement_rate for v in videos])
    p_ppf = _percentiles([v.plays_per_follower for v in videos])
    for i, v in enumerate(videos):
        v.score = round(
            C.SCORE_WEIGHT_PLAYS * p_plays[i]
            + C.SCORE_WEIGHT_ENGAGEMENT * p_eng[i]
            + C.SCORE_WEIGHT_PLAYS_PER_FOLLOWER * p_ppf[i],
            4,
        )
    return videos


def final_rank(videos: list[Video], *, top_n: int = C.TOP_N,
               per_account: int = C.MAX_VIDEOS_PER_ACCOUNT) -> list[Video]:
    """按加权得分降序，每账号最多 N 条。

    限制每账号条数是为了避免 pattern 归纳偏向某一个达人的个人风格 ——
    一个人贡献 8 条会让「共性」变成「他的习惯」。
    """
    scored = score_videos(list(videos))
    scored.sort(key=lambda v: v.score, reverse=True)

    used: dict[str, int] = {}
    out: list[Video] = []
    for v in scored:
        n = used.get(v.author.username, 0)
        if n >= per_account:
            continue
        used[v.author.username] = n + 1
        out.append(v)
        if len(out) >= top_n:
            break
    return out
