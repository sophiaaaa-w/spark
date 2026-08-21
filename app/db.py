"""SQLite schema（PRD 第六节）。所有数据放在 DATA_DIR，Railway 上必须挂 Volume。"""
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
  category      TEXT,
  patterns_json TEXT,
  sources_json  TEXT,
  stats_json    TEXT,
  is_demo       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS brief_translations (
  job_id        TEXT,
  lang          TEXT,
  patterns_json TEXT,
  PRIMARY KEY (job_id, lang)
);

-- 缓存原始序列而非单个中位数：同一账号的不同目标视频，时间窗不同，分母也不同
CREATE TABLE IF NOT EXISTS author_videos (
  author_id     TEXT,
  video_id      TEXT,
  published_at  INTEGER,
  plays         INTEGER,
  PRIMARY KEY (author_id, video_id)
);

CREATE TABLE IF NOT EXISTS author_meta (
  author_id         TEXT PRIMARY KEY,
  username          TEXT,
  follower_count    INTEGER,
  fetched_count     INTEGER,
  oldest_fetched_at INTEGER,
  updated_at        INTEGER
);

CREATE INDEX IF NOT EXISTS idx_author_videos_author ON author_videos(author_id);
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
