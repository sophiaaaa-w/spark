"""拿 fixtures 里的真实视频跑一次聚类，把结果用人能读的方式打印出来。

跑法：
    python3 scripts/test_cluster.py

成本：约 $0.05（一次 Sonnet 调用）。不爬任何数据。

这一步要你判断的问题只有一个：
    **这个结论，你拿到手能用吗？**
如果答案是「看着挺对但不知道怎么用」，就是没通过，要改 prompt。
"""
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import baseline, cluster, funnel, subtitles as subs   # noqa: E402
from app.funnel import BrandRef                                # noqa: E402
from app.models import dedupe, parse_many                      # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "fixtures"

BRAND = BrandRef(
    username="colorwow.hair",
    author_id="6735794023728677894",
    nickname="Color Wow",
    hashtag="colorwow",
)
BIO = "Color Wow Hair — professional haircare, home of Dream Coat and Money Masque."


def load_videos():
    raws = []
    for path in sorted(FIX.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except Exception:                                      # noqa: BLE001
            continue
        if isinstance(data, list):
            raws.extend(data)
    videos = dedupe(parse_many(raws))
    kept, stats = funnel.filter_with_relaxation(videos, BRAND)
    return kept, stats


def fake_baselines(videos):
    """fixtures 里没有账号历史，用 播放/粉丝 折算一个占位倍数。

    只为让聚类的输入完整。真实倍数要等流水线跑通后才有。
    """
    for v in videos:
        v.baseline = max(int(v.author.followers * 0.15), 1)
        v.baseline_multiple = round(v.plays / v.baseline, 2)
        v.baseline_confidence = "placeholder"
    return videos


def main() -> None:
    print("=" * 66)
    print("聚类测试 —— 真实视频，真实 Claude 调用")
    print("=" * 66)

    videos, stats = load_videos()
    print(f"\n漏斗产出 {len(videos)} 条（放宽等级 {stats.relax_level}）")
    if not videos:
        sys.exit("没有可用样本")

    videos = fake_baselines(videos)

    print("正在下载 WebVTT 字幕…")
    t0 = time.time()
    cues = asyncio.run(subs.fetch_many(videos))
    texts = {vid: subs.plain_text(c) for vid, c in cues.items() if c}
    print(f"  {len(texts)}/{len(videos)} 条拿到口播文字（{time.time()-t0:.0f}s）")
    if not texts:
        print("  ⚠️  一条都没拿到 —— 字幕链接大概率已过期。")
        print("     这本身是个重要发现：字幕必须在召回阶段立刻下载。")

    print("\n正在调用 Claude 聚类…")
    t0 = time.time()
    result = cluster.run(videos, texts, brand=BRAND.nickname, category_hint=BIO)
    print(f"  完成（{time.time()-t0:.0f}s）")

    # ---------------------------------------------------------------- 输出
    print("\n" + "=" * 66)
    print(f"识别品类：{result.get('category')}")
    print(f"归纳出 {len(result['patterns'])} 个 pattern"
          f"，{result['unclustered_count']} 条未归类")
    print("=" * 66)

    for p in result["patterns"]:
        marks = []
        if p.get("highest_lift"):
            marks.append("⚡ 少有人用但一用就爆")
        if p.get("thin_evidence"):
            marks.append("⚠ 样本支撑较薄")
        mark = ("   " + " · ".join(marks)) if marks else ""
        print(f"\n\n{'─' * 66}")
        print(f"0{p['rank']}  {p['move_name']}{mark}")
        print(f"{'─' * 66}")
        print(f"命中 {p['share_count']}/{p['share_total']} 条"
              f"   倍数中位数 {p.get('median_multiple')}×")
        print(f"\n为什么有效：\n  {p['why_it_works']}")
        print("\n真实原话：")
        for h in p.get("hook_examples", []):
            print(f"  · 「{h['quote']}」")

    if result.get("dropped_patterns"):
        print(f"\n\n{'·' * 66}")
        print("以下 pattern 被丢弃（支撑视频少于"
              f" {cluster.C.MIN_VIDEOS_PER_PATTERN} 条）")
        for p in result["dropped_patterns"]:
            print(f"  · {p['move_name']}  仅 {p['share_count']} 条")

    print(f"\n\n{'=' * 66}")
    print("逐条打标（看它的判断依据靠不靠谱）")
    print("=" * 66)
    by_id = {v.id: v for v in videos}
    for a in result.get("assignments", []):
        v = by_id.get(a["video_id"])
        if not v:
            continue
        pid = a.get("pattern_id")
        tag = f"0{pid}" if pid else "—"
        print(f"  {tag}  @{v.author.username:<20} {v.plays:>9,}  {a['evidence']}")

    out = ROOT / "fixtures" / "cluster_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n完整结果已存到 {out.name}")


if __name__ == "__main__":
    main()
