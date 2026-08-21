"""用已抓下来的 fixtures 离线验证漏斗 —— 零 API 成本。

跑法：
    python3 scripts/test_funnel.py

会打印漏斗每一级的存活数，应该和 probe3 实测的数字对得上（4.7% 左右）。
每次改过滤逻辑都跑一遍，比重新爬便宜得多。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import funnel                                   # noqa: E402
from app.funnel import BrandRef                          # noqa: E402
from app.models import dedupe, parse_many                # noqa: E402

FIX = Path(__file__).resolve().parent.parent / "fixtures"

# Color Wow 的三个字符串互相推导不出来，这正是 chip 存在的理由
BRAND = BrandRef(
    username="colorwow.hair",
    author_id="6735794023728677894",     # 从 detailedMentions 里实测拿到的
    nickname="Color Wow",
    hashtag="colorwow",
)


def load() -> list[dict]:
    raws: list[dict] = []
    for path in sorted(FIX.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:                                # noqa: BLE001
            continue
        if isinstance(data, list):
            raws.extend(data)
            print(f"  读入 {path.name}: {len(data)} 条")
    return raws


def main() -> None:
    print("=" * 62)
    print("离线漏斗验证（零成本）")
    print("=" * 62)

    raws = load()
    if not raws:
        sys.exit("fixtures 里没数据，先跑 scripts/probe_apify.py")

    videos = parse_many(raws)
    print(f"\n解析成功 {len(videos)}/{len(raws)} 条")

    deduped = dedupe(videos)
    print(f"去重后（含搬运去重）{len(deduped)} 条")

    kept, stats = funnel.filter_with_relaxation(deduped, BRAND)

    print("\n" + "=" * 62)
    print(f"漏斗（放宽等级 {stats.relax_level} / 共 {len(funnel.C.RELAX_LADDER)} 级）")
    print("=" * 62)
    base = max(stats.after_dedupe, 1)
    rows = [
        ("去重后", stats.after_dedupe),
        ("剔除图文帖", stats.after_slideshow),
        ("只留英文/未知", stats.after_language),
        ("时长 10-90s", stats.after_duration),
        ("时间窗内", stats.after_window),
        ("播放门槛", stats.after_plays),
        ("互动率 ≥1.5%", stats.after_engagement),
        ("relevance>=3", stats.after_relevance),
        ("剔除官号", stats.after_official),
    ]
    for name, n in rows:
        bar = "█" * int(34 * n / base)
        print(f"  {name:<16}{n:>5}  {bar}")
    print(f"\n  产出率 {len(kept)}/{base} = {len(kept)/base:.1%}")

    if not kept:
        print("\n  ⚠️  一条不剩。检查 BrandRef 是否填对，或阈值是否过严。")
        return

    top = funnel.final_rank(kept)
    print(f"\n终排序后 {len(top)} 条（播放降序，每账号最多 "
          f"{funnel.C.MAX_VIDEOS_PER_ACCOUNT} 条）")
    plays = [v.plays for v in top]
    print("  是否严格降序:", all(plays[i] >= plays[i + 1] for i in range(len(plays) - 1)))
    print(f"  涉及账号 {len({v.author.username for v in top})} 个")

    print("\n存活样本明细（按播放降序，前 12 条）")
    print(f"  {'播放':>9} {'互动率':>7} {'时长':>5} {'字幕':>4} {'相关':>4}  账号")
    for v in sorted(kept, key=lambda x: x.plays, reverse=True)[:12]:
        print(f"  {v.plays:>9,} {v.engagement_rate:>6.1%} {v.duration:>4}s "
              f"{'有' if v.has_subtitles else '无':>4} {v.relevance:>4}  @{v.author.username}")

    subs = sum(1 for v in kept if v.has_subtitles)
    print(f"\n  ★ 字幕覆盖率 {subs}/{len(kept)} = {subs/len(kept):.0%}"
          f"  —— 决定有多少条能当骨架视频")
    print(f"  ★ 涉及账号数 {len({v.author.username for v in kept})}")


if __name__ == "__main__":
    main()
