"""把某次分析标记成首页的 demo 卡片。

跑法：
    python3 scripts/mark_demo.py              # 列出所有已完成的分析
    python3 scripts/mark_demo.py <job_id>     # 标记成 demo
    python3 scripts/mark_demo.py <job_id> --cat "hair tools"
    python3 scripts/mark_demo.py <job_id> --off

--cat 是首页 example 列表里品牌名后面那个小字（"hair tools" / "skincare"）。
品类判断不了自动化 —— 靠 caption 猜会猜错，这种一个字的东西手填最省事。

首页最多显示 2 张 demo 卡片，它们直接打开已生成的结果，不触发新任务 ——
没有人会为一个没见过的东西等 10 分钟，这两张卡片是唯一的零成本入口。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db                                        # noqa: E402


def main() -> None:
    db.init()
    argv = sys.argv[1:]
    off = "--off" in argv
    cat = None
    if "--cat" in argv:
        i = argv.index("--cat")
        if i + 1 >= len(argv):
            sys.exit("--cat 后面要跟品类，比如 --cat \"hair tools\"")
        cat = argv[i + 1]
        del argv[i:i + 2]
    args = [a for a in argv if not a.startswith("--")]

    if not args:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT b.job_id, b.brand, b.is_demo, b.category, j.created_at,"
                " b.stats_json"
                " FROM briefs b LEFT JOIN jobs j ON j.id = b.job_id"
                " ORDER BY j.created_at DESC").fetchall()
        import json
        if not rows:
            print("还没有任何已完成的分析")
            return
        print(f"{'job_id':<14}{'brand':<18}{'videos':>7}  {'category':<14}demo")
        for r in rows:
            s = json.loads(r["stats_json"] or "{}")
            print(f"{r['job_id']:<14}{r['brand']:<18}{s.get('count',0):>7}"
                  f"  {(r['category'] or '—'):<14}{'✔' if r['is_demo'] else ''}")
        print("\n标记：python3 scripts/mark_demo.py <job_id>")
        return

    job_id = args[0]
    with db.connect() as conn:
        n = conn.execute("SELECT COUNT(*) FROM briefs WHERE job_id = ?",
                         (job_id,)).fetchone()[0]
        if not n:
            sys.exit(f"找不到 {job_id}")
        conn.execute("UPDATE briefs SET is_demo = ? WHERE job_id = ?",
                     (0 if off else 1, job_id))
        if cat is not None:
            conn.execute("UPDATE briefs SET category = ? WHERE job_id = ?",
                         (cat, job_id))
    print(f"{job_id} {'取消' if off else '设为'} demo"
          + (f"，品类 “{cat}”" if cat is not None else ""))


if __name__ == "__main__":
    main()
