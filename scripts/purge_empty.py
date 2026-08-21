"""删掉 0 条结果的废分析记录。

失败的跑（401、品牌太冷）也会写进库和 data/briefs，留着只会让 mark_demo
的列表越来越脏，也容易误标。

跑法：
    python3 scripts/purge_empty.py          # 先看会删什么
    python3 scripts/purge_empty.py --yes    # 真删
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config as C                                  # noqa: E402
from app import db                                           # noqa: E402


def main() -> None:
    go = "--yes" in sys.argv
    db.init()

    with db.connect() as conn:
        rows = conn.execute(
            "SELECT job_id, brand, is_demo, stats_json FROM briefs").fetchall()

    doomed = []
    for r in rows:
        n = json.loads(r["stats_json"] or "{}").get("count", 0)
        if n == 0:
            doomed.append((r["job_id"], r["brand"], bool(r["is_demo"])))

    if not doomed:
        print("没有 0 条结果的记录，干净。")
        return

    print(f"{'job_id':<14}{'brand':<18}")
    for jid, brand, is_demo in doomed:
        flag = "  ⚠ 这条被标成 demo 了，跳过" if is_demo else ""
        print(f"{jid:<14}{brand:<18}{flag}")

    doomed = [d for d in doomed if not d[2]]
    if not doomed:
        print("\n剩下的都是 demo，不动。")
        return

    if not go:
        print(f"\n共 {len(doomed)} 条。确认无误后加 --yes 真删。")
        return

    for jid, _, _ in doomed:
        with db.connect() as conn:
            conn.execute("DELETE FROM briefs WHERE job_id = ?", (jid,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (jid,))
        p = C.DATA_DIR / "briefs" / f"{jid}.json"
        if p.exists():
            p.unlink()
    print(f"\n删了 {len(doomed)} 条。")


if __name__ == "__main__":
    main()
