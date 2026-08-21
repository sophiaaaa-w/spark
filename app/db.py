"""SQLite schema。

只有两张表：任务状态和已完成的报告。报告正文写在 DATA_DIR/briefs/*.json，
库里只存索引字段 —— 结果是一个几十上百 KB 的嵌套结构，塞进关系表除了
增加序列化开销没有任何好处，没有一个查询需要按视频维度过滤。
"""
import sqlite3

from .config import DATA_DIR, DB_PATH, FRAMES_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id            TEXT PRIMARY KEY,
  handle        TEXT,
  brand         TEXT,
  status        TEXT,            -- queued|running|done|partial|failed
  stage         TEXT,
  stage_detail  TEXT,
  progress_pct  INTEGER DEFAULT 0,
  created_at    INTEGER,
  error         TEXT,
  hidden        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS briefs (
  job_id        TEXT PRIMARY KEY,
  handle        TEXT,
  brand         TEXT,
  category      TEXT,            -- 首页 demo 卡片上那行小字，手工填
  patterns_json TEXT,
  sources_json  TEXT,
  stats_json    TEXT,            -- {"count": 47, "crawled": 1702}
  is_demo       INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(SCHEMA)
