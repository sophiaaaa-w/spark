"""WebVTT 字幕的下载与解析。

实测发现 TikTok 自带 ASR 字幕（videoMeta.subtitleLinks），格式是标准 WebVTT
且带毫秒时间戳：

    WEBVTT

    00:00:00.260 --> 00:00:01.620
    Take your hair from this dry,

    00:00:01.621 --> 00:00:04.501
    dehydrated, and damaged into this.

覆盖率 71%。这让 Whisper 在 MVP 里完全不需要 —— 口播文字和时间轴对齐都免费拿到了。

⚠️ 下载链接带签名和过期时间。若实测发现过期很快，就必须在召回阶段立刻把字幕
   下载下来，不能等到流水线后面几步再取。
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass

import httpx

from .models import Video

log = logging.getLogger(__name__)

_TS = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[.,](\d{3})"
)


@dataclass(slots=True)
class Cue:
    start: float
    end: float
    text: str


def _seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_vtt(raw: str) -> list[Cue]:
    """解析 WebVTT。同一时间段的多行文本合成一句。"""
    cues: list[Cue] = []
    start = end = None
    buf: list[str] = []

    def flush() -> None:
        if start is not None and buf:
            text = " ".join(x.strip() for x in buf if x.strip())
            if text:
                cues.append(Cue(start, end or start, text))

    for line in raw.splitlines():
        m = _TS.search(line)
        if m:
            flush()
            buf = []
            start = _seconds(*m.groups()[:4])
            end = _seconds(*m.groups()[4:])
            continue
        if line.strip().upper().startswith("WEBVTT"):
            continue
        if not line.strip():
            flush()
            buf = []
            start = end = None
            continue
        if start is not None:
            buf.append(line)
    flush()
    return cues


def plain_text(cues: list[Cue]) -> str:
    return " ".join(c.text for c in cues)


def first_seconds(cues: list[Cue], seconds: float = 3.0) -> str:
    """开头几秒的口播 —— hook 分析最关键的部分。"""
    return " ".join(c.text for c in cues if c.start < seconds)


async def fetch_one(client: httpx.AsyncClient, video: Video) -> list[Cue]:
    sub = video.english_subtitle
    if sub is None:
        return []
    try:
        r = await client.get(sub.url, timeout=20)
        if r.status_code != 200:
            log.info("字幕 %s HTTP %s（链接可能已过期）", video.id, r.status_code)
            return []
        return parse_vtt(r.text)
    except Exception as exc:                      # noqa: BLE001
        log.info("字幕 %s 下载失败: %s", video.id, exc)
        return []


async def fetch_many(videos: list[Video], *,
                     concurrency: int = 8) -> dict[str, list[Cue]]:
    """批量下载字幕。失败的视频返回空列表，不抛异常。"""
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        async def one(v: Video) -> tuple[str, list[Cue]]:
            async with sem:
                return v.id, await fetch_one(client, v)

        pairs = await asyncio.gather(
            *(one(v) for v in videos if v.has_subtitles)
        )
    out = {vid: cues for vid, cues in pairs}
    got = sum(1 for c in out.values() if c)
    log.info("字幕：%d/%d 条成功解析", got, len(videos))
    return out
