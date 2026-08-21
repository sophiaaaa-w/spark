"""把 Apify 返回的原始记录归一化成干净对象。

存在的理由：真实字段嵌套很深且命名反直觉（粉丝数叫 fans、时长在 videoMeta 里、
mediaUrls 恒为空）。全项目只有这一个文件碰原始 JSON，别处一律用 Video / Author。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def _ts(iso: str | None) -> int:
    if not iso:
        return 0
    try:
        return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


@dataclass(slots=True)
class Author:
    id: str
    username: str          # authorMeta.name，即 @ 后面那串
    nickname: str          # authorMeta.nickName，显示名
    followers: int         # authorMeta.fans —— 注意不叫 followers
    bio: str
    verified: bool

    @classmethod
    def parse(cls, raw: dict) -> "Author":
        a = raw.get("authorMeta") or {}
        return cls(
            id=str(a.get("id") or ""),
            username=(a.get("name") or "").lower(),
            nickname=a.get("nickName") or "",
            followers=int(a.get("fans") or 0),
            bio=a.get("signature") or "",
            verified=bool(a.get("verified")),
        )


@dataclass(slots=True)
class Subtitle:
    language: str
    url: str
    source: str            # "ASR" = TikTok 自己做的口播语音识别，正是我们要的


@dataclass(slots=True)
class Video:
    id: str
    url: str               # webVideoUrl，yt-dlp 用这个下载
    caption: str
    language: str          # textLanguage，"un" = 未判定
    published_at: int
    duration: int          # 秒，videoMeta.duration
    cover_url: str
    is_slideshow: bool     # 图文轮播帖，实测占召回量的一半以上
    is_ad: bool

    plays: int
    likes: int
    comments: int
    shares: int
    saves: int

    hashtags: list[str]
    mention_ids: list[str]     # detailedMentions[].id —— 结构化，不用正则猜
    mention_names: list[str]
    subtitles: list[Subtitle]

    author: Author

    # 流水线后续阶段填充
    relevance: int = 0
    score: float = 0.0                     # 加权得分，见 funnel.score_videos
    pattern_id: int | None = None
    # 以下三个只在「深度模式」用（需要抓账号历史），MVP 不填
    baseline: int | None = field(default=None)
    baseline_multiple: float | None = field(default=None)
    baseline_confidence: str = "unknown"   # high | low | unknown

    @classmethod
    def parse(cls, raw: dict) -> "Video":
        vm = raw.get("videoMeta") or {}
        return cls(
            id=str(raw.get("id") or ""),
            url=raw.get("webVideoUrl") or "",
            caption=raw.get("text") or "",
            language=raw.get("textLanguage") or "un",
            published_at=_ts(raw.get("createTimeISO")),
            duration=int(vm.get("duration") or 0),
            cover_url=vm.get("coverUrl") or "",
            is_slideshow=bool(raw.get("isSlideshow")),
            is_ad=bool(raw.get("isAd") or raw.get("isSponsored")),
            plays=int(raw.get("playCount") or 0),
            likes=int(raw.get("diggCount") or 0),
            comments=int(raw.get("commentCount") or 0),
            shares=int(raw.get("shareCount") or 0),
            saves=int(raw.get("collectCount") or 0),
            # hashtags 里可能有 {"name": ""} 这种空壳，要滤掉
            hashtags=[
                (h.get("name") or "").lower()
                for h in (raw.get("hashtags") or [])
                if isinstance(h, dict) and (h.get("name") or "").strip()
            ],
            mention_ids=[
                str(m.get("id")) for m in (raw.get("detailedMentions") or [])
                if isinstance(m, dict) and m.get("id")
            ],
            mention_names=[
                (m.get("name") or "").lower()
                for m in (raw.get("detailedMentions") or [])
                if isinstance(m, dict) and m.get("name")
            ],
            subtitles=[
                Subtitle(
                    language=s.get("language") or "",
                    url=s.get("downloadLink") or "",
                    source=s.get("source") or "",
                )
                for s in (vm.get("subtitleLinks") or [])
                if isinstance(s, dict) and s.get("downloadLink")
            ],
            author=Author.parse(raw),
        )

    # ---------------------------------------------------------------- 派生属性

    @property
    def engagement_rate(self) -> float:
        """(赞 + 评 + 转) / 播放。saves 有返回但不计入，保持定义稳定。"""
        if not self.plays:
            return 0.0
        return (self.likes + self.comments + self.shares) / self.plays

    @property
    def plays_per_follower(self) -> float:
        """预筛用的免费代理指标 —— 真实基线倍数最接近的廉价近似。"""
        if not self.author.followers:
            return 0.0
        return self.plays / self.author.followers

    @property
    def age_days(self) -> float:
        if not self.published_at:
            return 1e9
        return (datetime.now(timezone.utc).timestamp() - self.published_at) / 86400

    @property
    def english_subtitle(self) -> Subtitle | None:
        for s in self.subtitles:
            if s.language.lower().startswith("en"):
                return s
        return None

    @property
    def has_subtitles(self) -> bool:
        return self.english_subtitle is not None


def parse_many(raws: list[dict]) -> list[Video]:
    out: list[Video] = []
    for raw in raws:
        if not isinstance(raw, dict):
            continue
        try:
            v = Video.parse(raw)
        except Exception:                     # noqa: BLE001 单条脏数据不该中断整批
            continue
        if v.id:
            out.append(v)
    return out


def dedupe(videos: list[Video]) -> list[Video]:
    """按 video id 去重；顺带做搬运号粗略去重。

    搬运是常态：同一条内容被多个账号发，会让某个 pattern 的占比虚高。
    用 caption 前 50 字符 + 时长 做指纹，同指纹只留播放最高的一条。
    """
    by_id: dict[str, Video] = {}
    for v in videos:
        if v.id not in by_id:
            by_id[v.id] = v

    by_fingerprint: dict[tuple, Video] = {}
    for v in by_id.values():
        head = v.caption[:50].strip().lower()
        if not head:                          # 无 caption 的不参与搬运判定
            by_fingerprint[("__id__", v.id)] = v
            continue
        fp = (head, v.duration)
        keep = by_fingerprint.get(fp)
        if keep is None or v.plays > keep.plays:
            by_fingerprint[fp] = v
    return list(by_fingerprint.values())
