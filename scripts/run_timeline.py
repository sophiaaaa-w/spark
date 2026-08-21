"""为每个 pattern 挑骨架视频、下载抽帧、生成左右两栏时间轴。

跑法：
    python3 scripts/run_timeline.py @wavytalkofficial

依赖 run_cluster.py 的 result_*.json。
成本：约 $0.3 Claude（每 pattern 一次 Opus 多模态调用），下载抽帧不花 API 钱。

需要本机装好 yt-dlp 和 ffmpeg：
    brew install yt-dlp ffmpeg
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C, frames, funnel, timeline      # noqa: E402
from app import subtitles as subs                          # noqa: E402
from app.funnel import BrandRef, FunnelStats               # noqa: E402
from app.models import dedupe, parse_many                  # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("handle")
    args = ap.parse_args()
    handle = args.handle.lstrip("@")

    missing = frames.check_tools()
    if missing:
        sys.exit(f"缺少外部依赖 {', '.join(missing)}\n"
                 f"装一下：brew install {' '.join(missing)}")

    rpath = FIX / f"result_{handle}.json"
    bpath = FIX / f"brand_{handle}.json"
    if not rpath.exists():
        sys.exit(f"找不到 {rpath.name}，先跑 run_cluster.py @{handle}")
    result = json.loads(rpath.read_text())
    d = json.loads(bpath.read_text())
    brand = BrandRef(**{k: d[k] for k in
                        ("username", "author_id", "nickname", "hashtag")})

    raws = []
    for name in (f"recall_{handle}.json", f"recall2_{handle}.json"):
        p = FIX / name
        if p.exists():
            raws += json.loads(p.read_text())
    kept = funnel.hard_filter(dedupe(parse_many(raws)), brand,
                              window_days=C.WINDOW_DAYS,
                              min_plays=C.MIN_PLAYS, stats=FunnelStats())
    ranked = funnel.final_rank(kept)
    by_id = {v.id: v for v in ranked}

    print("=" * 74)
    print(f"生成时间轴　{brand.nickname}　{len(result['patterns'])} 个 pattern")
    print("=" * 74)

    print("\n下载字幕…")
    cues = asyncio.run(subs.fetch_many(ranked))

    for p in result["patterns"]:
        members = [by_id[i] for i in p.get("member_ids", []) if i in by_id]
        if not members:
            continue
        skeleton, has_speech = timeline.pick_skeleton(members, cues)

        print(f"\n{'─' * 74}")
        print(f"0{p['rank']}  {p['move_name']}")
        print(f"{'─' * 74}")
        print(f"  骨架视频 @{skeleton.author.username}　"
              f"{skeleton.plays:,} 播放　{skeleton.duration}s　"
              f"{'有口播' if has_speech else '⚠ 全组无口播，只出画面'}")

        # 过量取样：骨架优先，同组其他视频作为备选
        candidates = [skeleton] + [m for m in members if m.id != skeleton.id]
        print(f"  下载中（候选 {len(candidates[:C.DOWNLOAD_OVERSAMPLE])} 条，要 1 条）…")
        t0 = time.time()
        clips = asyncio.run(frames.build_clips(
            candidates[:C.DOWNLOAD_OVERSAMPLE], need=1,
            on_download=lambda v, ok: print(
                f"    {'✓' if ok else '✗'} @{v.author.username}"),
        ))
        if not clips:
            print("  ✗ 全部下载失败，跳过这个 pattern")
            p["timeline"] = None
            continue
        clip = clips[0]
        print(f"  抽出 {len(clip.frames)} 帧（{time.time()-t0:.0f}s）")

        print("  调用 Claude 拆解…")
        t0 = time.time()
        try:
            tl = timeline.run(clip, cues.get(clip.video.id, []),
                              pattern=p, category=result.get("category", ""))
        except Exception as exc:                          # noqa: BLE001
            print(f"  ✗ 失败：{exc}")
            p["timeline"] = None
            continue
        p["timeline"] = tl
        print(f"  完成（{time.time()-t0:.0f}s）\n")

        print(f"  Structure from @{tl['skeleton_author']}'s video")
        print(f"  {'':>13}{'WHAT THEY DID':<44}THE MOVE")
        for s in tl["segments"]:
            print(f"\n  {s['t_start']:>4.0f}-{s['t_end']:<4.0f} {s['label']:<8}"
                  f"[frame {s.get('frame_index')}]")
            print(f"      画面  {s['visual'][:64]}")
            if s.get("vo"):
                mark = {True: "✓", False: "⚠ 非逐字"}.get(s.get("vo_verified"), "")
                print(f"      口播  「{s['vo'][:60]}」 {mark}")
            print(f"      → {s['move_name']}")
            print(f"        {s['function']}")

        if tl.get("vo_unverified"):
            print(f"\n  ⚠️ 有 {len(tl['vo_unverified'])} 段口播不是逐字原话："
                  f"{tl['vo_unverified'][:2]}")

    out = FIX / f"brief_{handle}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n{'=' * 74}")
    print(f"完整 brief 已存 fixtures/brief_{handle}.json")
    print(f"帧图在 {C.FRAMES_DIR}")


if __name__ == "__main__":
    main()
