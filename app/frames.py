"""视频下载与关键帧抽取。

实测 Apify 的 mediaUrls 恒为空数组，所以只能用 yt-dlp 自己下。

两条设计原则：
  · 下载失败是常态，不是异常 —— TikTok 的直链有时效、部分视频 403 或地区限制。
    所以过量取样：想要 3 条就拿 8 条去试，成功即停，绝不因单条失败中断整个 job。
  · 场景检测单用会失效 —— 长镜头口播视频几乎不触发 scene change。
    所以「场景检测 ∪ 固定间隔」取并集，保证帧数下界。
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import config as C
from .models import Video

log = logging.getLogger(__name__)


@dataclass(slots=True)
class Frame:
    index: int          # 给模型引用的序号，从 0 开始
    t: float            # 在视频里的秒数
    path: Path
    url: str            # 前端用的相对路径


@dataclass(slots=True)
class Clip:
    video: Video
    path: Path
    frames: list[Frame]


def _have(binary: str) -> bool:
    return shutil.which(binary) is not None


def check_tools() -> list[str]:
    """返回缺失的外部依赖。"""
    return [b for b in ("yt-dlp", "ffmpeg", "ffprobe") if not _have(b)]


# ---------------------------------------------------------------- 下载

async def download(video: Video, out_dir: Path) -> Path | None:
    """下一条视频。失败返回 None，不抛异常。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{video.id}.mp4"
    if dest.exists() and dest.stat().st_size > 10_000:
        return dest

    for attempt in range(C.DOWNLOAD_RETRIES + 1):
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--quiet", "--no-warnings",
            "--format", "mp4/best",
            "--socket-timeout", str(C.DOWNLOAD_TIMEOUT_S),
            "-o", str(dest), video.url,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            log.info("下载超时 %s（第 %d 次）", video.id, attempt + 1)
            continue
        if proc.returncode == 0 and dest.exists() and dest.stat().st_size > 10_000:
            return dest
        log.info("下载失败 %s: %s", video.id, (err or b"")[:160].decode(errors="ignore"))
    return None


async def download_many(videos: list[Video], out_dir: Path, *,
                        need: int, on_done=None) -> list[tuple[Video, Path]]:
    """过量取样下载，成功 need 条即停。

    并发受限是因为 ffmpeg 和下载都吃资源，而部署环境是单实例。
    """
    sem = asyncio.Semaphore(C.DOWNLOAD_CONCURRENCY)
    got: list[tuple[Video, Path]] = []
    stop = asyncio.Event()

    async def one(v: Video) -> None:
        if stop.is_set():
            return
        async with sem:
            if stop.is_set():
                return
            path = await download(v, out_dir)
        if path:
            got.append((v, path))
            if on_done:
                on_done(v, True)
            if len(got) >= need:
                stop.set()
        elif on_done:
            on_done(v, False)

    await asyncio.gather(*(one(v) for v in videos))
    return got[:need]


# ---------------------------------------------------------------- 抽帧

def _scene_times(path: Path, threshold: float) -> list[float]:
    """用 ffmpeg 的场景检测找切镜时刻。"""
    cmd = ["ffmpeg", "-hide_banner", "-i", str(path),
           "-filter:v", f"select='gt(scene,{threshold})',showinfo",
           "-f", "null", "-"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception:                                    # noqa: BLE001
        return []
    out: list[float] = []
    for line in (r.stderr or "").splitlines():
        if "pts_time:" in line:
            try:
                out.append(float(line.split("pts_time:")[1].split()[0]))
            except (IndexError, ValueError):
                continue
    return out


def plan_timestamps(duration: float, scenes: list[float]) -> list[float]:
    """决定抽哪些时刻。

    前 3 秒固定密集抽（hook 最重要，必须看清），3 秒后场景检测 + 固定间隔兜底。
    单用场景检测的话，长镜头口播视频可能一帧都不触发。
    """
    times: set[float] = set()
    t = 0.0
    while t < min(C.HOOK_DENSE_UNTIL_S, duration):
        times.add(round(t, 2))
        t += C.HOOK_FRAME_INTERVAL_S

    times.update(round(s, 2) for s in scenes if s >= C.HOOK_DENSE_UNTIL_S)

    t = C.HOOK_DENSE_UNTIL_S
    while t < duration:
        times.add(round(t, 2))
        t += C.FALLBACK_FRAME_INTERVAL_S

    ordered = sorted(x for x in times if 0 <= x < duration)
    if len(ordered) <= C.FRAMES_MAX:
        return ordered
    # 超了就按时间均匀取样，保证首尾都在
    step = (len(ordered) - 1) / (C.FRAMES_MAX - 1)
    return [ordered[round(i * step)] for i in range(C.FRAMES_MAX)]


def extract(path: Path, video: Video, out_dir: Path) -> list[Frame]:
    """抽帧。分辨率保留 720p 宽边，模型要看清画面细节。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    duration = float(video.duration or 0)
    if duration <= 0:
        return []

    times = plan_timestamps(duration, _scene_times(path, C.SCENE_THRESHOLD))
    frames: list[Frame] = []
    for i, t in enumerate(times):
        dest = out_dir / f"{video.id}_{i:02d}.jpg"
        if not dest.exists():
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                   "-ss", str(t), "-i", str(path), "-frames:v", "1",
                   "-vf", f"scale={C.FRAME_WIDTH}:-2", "-q:v", "3",
                   "-y", str(dest)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            except Exception:                            # noqa: BLE001
                continue
        if dest.exists() and dest.stat().st_size > 1000:
            frames.append(Frame(index=len(frames), t=t, path=dest,
                                url=f"/frames/{dest.name}"))
    return frames


def extract_hook_frames(path: Path, video: Video, out_dir: Path) -> list[Frame]:
    """只抽前几秒的 2 帧，供 hook 分类用。

    比 extract() 便宜得多：2 帧而不是 12 帧，480px 而不是 720px。
    因为这里只需要看清「屏幕上是什么」，不需要细节。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Frame] = []
    for i, t in enumerate(C.HOOK_FRAME_TIMES):
        if t >= max(video.duration, 1):
            continue
        dest = out_dir / f"{video.id}_h{i}.jpg"
        if not dest.exists():
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
                   "-ss", str(t), "-i", str(path), "-frames:v", "1",
                   "-vf", f"scale={C.HOOK_FRAME_WIDTH}:-2", "-q:v", "4",
                   "-y", str(dest)]
            try:
                subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            except Exception:                            # noqa: BLE001
                continue
        if dest.exists() and dest.stat().st_size > 800:
            frames.append(Frame(index=len(frames), t=t, path=dest,
                                url=f"/frames/{dest.name}"))
    return frames


async def build_hook_frames(videos: list[Video], *, work_dir: Path | None = None,
                            on_progress=None) -> dict[str, list[Frame]]:
    """给一批视频各抽前几秒的 2 帧。下载失败的跳过，不中断。"""
    work_dir = work_dir or C.DATA_DIR
    vdir, fdir = work_dir / "videos", C.FRAMES_DIR
    sem = asyncio.Semaphore(C.DOWNLOAD_CONCURRENCY)
    out: dict[str, list[Frame]] = {}
    done = {"n": 0}

    async def one(v: Video) -> None:
        async with sem:
            path = await download(v, vdir)
        done["n"] += 1
        if path:
            fr = extract_hook_frames(path, v, fdir)
            if fr:
                out[v.id] = fr
        if on_progress:
            on_progress(done["n"], len(videos), v, bool(path))

    await asyncio.gather(*(one(v) for v in videos))
    return out


async def build_clips(videos: list[Video], *, need: int,
                      work_dir: Path | None = None,
                      on_download=None) -> list[Clip]:
    """下载 + 抽帧，返回成功的那些。"""
    work_dir = work_dir or C.DATA_DIR
    vdir = work_dir / "videos"
    fdir = C.FRAMES_DIR

    pairs = await download_many(videos, vdir, need=need, on_done=on_download)
    clips: list[Clip] = []
    for v, path in pairs:
        frames = extract(path, v, fdir)
        if frames:
            clips.append(Clip(video=v, path=path, frames=frames))
        else:
            log.info("抽帧失败 %s", v.id)
    return clips
