"""基线算法的单元测试 —— 纯计算，零 API 成本。

跑法：
    python3 scripts/test_baseline.py

三个坑各有一个用例。任何一个 FAIL 都说明基线倍数会算错，
而基线倍数是整个产品的核心判据，错了产品就没意义。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.baseline import HistoryPoint, compute_baseline   # noqa: E402
from app.models import Author, Video                      # noqa: E402

DAY = 86400
NOW = time.time()

passed = failed = 0


def check(name: str, got, want) -> None:
    global passed, failed
    ok = got == want
    if ok:
        passed += 1
        print(f"  ✅ {name}")
    else:
        failed += 1
        print(f"  ❌ {name}\n       期望 {want}，实际 {got}")


def fake_video(*, plays: int, days_ago: float) -> Video:
    return Video(
        id="target", url="", caption="", language="en",
        published_at=int(NOW - days_ago * DAY),
        duration=30, cover_url="", is_slideshow=False, is_ad=False,
        plays=plays, likes=0, comments=0, shares=0, saves=0,
        hashtags=[], mention_ids=[], mention_names=[], subtitles=[],
        author=Author(id="a", username="a", nickname="A",
                      followers=10_000, bio="", verified=False),
    )


def hist(*pairs: tuple[float, int]) -> list[HistoryPoint]:
    """(days_ago, plays) —— days_ago 越大越早。"""
    return [HistoryPoint(int(NOW - d * DAY), p) for d, p in pairs]


print("=" * 62)
print("基线算法测试")
print("=" * 62)

# ── 坑 1：只用目标视频之前的视频 ──────────────────────────────
# 目标发布于 20 天前。之后（10-19 天前）的视频吃了爆款红利，播放很高。
# 若把它们算进分母，中位数会被抬高，倍数被低估。
print("\n坑 1  只能用 T 之前的视频做分母")
target = fake_video(plays=500_000, days_ago=20)
before = [(30, 20_000), (40, 21_000), (50, 19_000), (60, 22_000), (70, 20_500)]
after = [(10, 300_000), (12, 280_000), (14, 310_000)]
baseline, conf = compute_baseline(target, hist(*before, *after), now=NOW)
check("分母只用之前的 5 条（中位 20,500）", baseline, 20_500)
check("置信度 high", conf, "high")

# ── 坑 2：按时间窗切，不按条数切 ──────────────────────────────
# 半年前的视频播放很低（账号还小）。90 天窗口应该把它们排除掉。
print("\n坑 2  按时间窗切，半年前的低播放数据不该进分母")
target = fake_video(plays=500_000, days_ago=10)
recent = [(20, 50_000), (30, 52_000), (40, 48_000), (50, 51_000), (60, 49_000)]
ancient = [(200, 800), (220, 900), (240, 700), (260, 850), (280, 750)]
baseline, _ = compute_baseline(target, hist(*recent, *ancient), now=NOW)
check("分母是近 90 天的中位数（50,000）", baseline, 50_000)

# ── 坑 3：排除 7 天内的新视频 ────────────────────────────────
# 3 天前发的视频播放量还在涨，只有 800，会把中位数拉低。
print("\n坑 3  发布不足 7 天的视频播放未收敛，要排除")
target = fake_video(plays=500_000, days_ago=1)
mature = [(20, 20_000), (30, 21_000), (40, 19_000), (50, 22_000), (60, 20_500)]
fresh = [(2, 800), (3, 900), (4, 700)]
baseline, _ = compute_baseline(target, hist(*mature, *fresh), now=NOW)
check("新视频不进分母（中位仍是 20,500）", baseline, 20_500)

# ── 目标视频本身要排除 ───────────────────────────────────────
print("\n目标视频本身不能进分母（自证）")
target = fake_video(plays=500_000, days_ago=20)
with_self = [(20, 500_000), (30, 20_000), (40, 21_000),
             (50, 19_000), (60, 22_000), (70, 20_500)]
baseline, _ = compute_baseline(target, hist(*with_self), now=NOW)
check("500,000 那条被剔除", baseline, 20_500)

# ── 样本不足 ────────────────────────────────────────────────
print("\n样本不足时的行为")
target = fake_video(plays=500_000, days_ago=10)
baseline, conf = compute_baseline(target, hist((20, 1000), (30, 1100)), now=NOW)
check("少于 5 条 → 返回 None", baseline, None)
check("置信度 none（该账号应被剔除）", conf, "none")

# ── 超高频发布者：全部历史都晚于 T ────────────────────────────
# 日发数条的账号，抓 80 条只覆盖最近半个月，全部晚于 30 天前的目标视频。
# 但这些视频本身是成熟的（>7 天），可以退化使用，只是要标低置信度。
print("\n超高频发布者：抓到的全部晚于 T → 退化 + 标低置信度")
target = fake_video(plays=500_000, days_ago=30)
all_after = [(8, 10_000), (10, 11_000), (12, 9_000),
             (14, 12_000), (16, 10_500), (18, 10_200)]
baseline, conf = compute_baseline(target, hist(*all_after), now=NOW)
check("退化用全部历史（中位 10,350）", baseline, 10_350)
check("置信度 low（页面上要标注）", conf, "low")

# ── 滤完一条不剩 → 宁可剔除，不用未收敛数据造假倍数 ─────────────
# 这是个有意的取舍：用还在涨的播放量做分母会低估分母、虚高倍数，
# 凭空造出假爆款。这个方向的错误比漏掉一个候选更糟。
print("\n全部历史都在 7 天内 → 剔除该账号，不退化")
target = fake_video(plays=500_000, days_ago=30)
all_fresh = [(1, 10_000), (2, 11_000), (3, 9_000),
             (4, 12_000), (5, 10_500), (6, 10_200)]
baseline, conf = compute_baseline(target, hist(*all_fresh), now=NOW)
check("返回 None 而不是用未收敛数据", baseline, None)
check("置信度 none", conf, "none")

# ── 倍数计算 ────────────────────────────────────────────────
print("\n倍数计算")
target = fake_video(plays=456_000, days_ago=20)
base = [(30, 20_000), (40, 21_000), (50, 19_000), (60, 22_000), (70, 20_000)]
baseline, _ = compute_baseline(target, hist(*base), now=NOW)
check("456,000 ÷ 20,000 = 22.8×", round(target.plays / baseline, 1), 22.8)

print("\n" + "=" * 62)
print(f"{passed} 通过 · {failed} 失败")
print("=" * 62)
sys.exit(1 if failed else 0)
