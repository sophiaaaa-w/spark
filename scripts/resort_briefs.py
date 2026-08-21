"""把已存的 brief 按新排序规则重排。

排序规则从「三项百分位加权」改成了「纯播放量降序」，但已经跑完的 brief 里
视频顺序是写死在 JSON 里的，不重排就还是旧顺序 —— 线上 demo 会继续显示
198k 排在 1.2M 上面。

跑法：
    python3 scripts/resort_briefs.py          # 预览
    python3 scripts/resort_briefs.py --yes    # 真改（同时处理 seed/）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config as C                                  # noqa: E402


def resort(path: Path, go: bool) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    vids = data.get("videos") or []
    if not vids:
        return

    before = [v["plays"] for v in vids]
    ordered = sorted(vids, key=lambda v: v["plays"], reverse=True)

    # 每账号上限在排序后重新施加，规则和 funnel.final_rank 一致
    used: dict[str, int] = {}
    kept = []
    for v in ordered:
        n = used.get(v["author"], 0)
        if n >= C.MAX_VIDEOS_PER_ACCOUNT:
            continue
        used[v["author"]] = n + 1
        kept.append(v)
        if len(kept) >= C.TOP_N:
            break

    after = [v["plays"] for v in kept]
    was_sorted = all(before[i] >= before[i + 1] for i in range(len(before) - 1))
    print(f"  {path.name:<22} {len(vids)} → {len(kept)} 条  "
          f"{'已经是降序' if was_sorted else '需要重排'}")
    if not was_sorted:
        print(f"     旧: {', '.join(f'{p:,}' for p in before[:5])} …")
        print(f"     新: {', '.join(f'{p:,}' for p in after[:5])} …")

    if go:
        data["videos"] = kept
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    go = "--yes" in sys.argv
    print(f"{'执行' if go else '预览'}模式\n")

    targets = sorted((C.DATA_DIR / "briefs").glob("*.json"))
    seed = ROOT / "seed"
    targets += [p for p in seed.glob("*.json") if p.name != "demo.json"]

    if not targets:
        sys.exit("没找到任何 brief")

    for p in targets:
        resort(p, go)

    print("\n" + ("完成。重启服务后生效。" if go else "确认后加 --yes 执行。"))


if __name__ == "__main__":
    main()
