"""Spark — FastAPI 服务。

三个页面 + 三个接口：

    GET  /              首页：输入品牌名
    GET  /api/probe     输入框失焦时的快速体检（20 条）
    POST /api/jobs      启动分析，立即返回 job_id
    GET  /job/{id}      进度页（前端每 3 秒轮询）
    GET  /api/jobs/{id} 进度 JSON
    GET  /brief/{id}    结果页

全局同时只跑一个 job：单实例 + ffmpeg 吃 CPU，两三个并发会一起超时。
超出的排队，比让所有人一起失败体验好。
"""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import shutil
import time
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as C
from . import db, pipeline, render

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# httpx 在 INFO 级别会把每个请求的完整 URL 打出来。即便密钥已经改走请求头，
# 也不该让第三方库替我们决定什么东西进日志 —— 出问题时临时调回 INFO 即可。
logging.getLogger("httpx").setLevel(logging.WARNING)

log = logging.getLogger("spark")

app = FastAPI(title="Spark")
_lock = asyncio.Semaphore(C.MAX_CONCURRENT_JOBS)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    C.FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/frames", StaticFiles(directory=C.FRAMES_DIR), name="frames")

    # 缓存下来的 TikTok 封面。Apify 给的 cover_url 带签名，实测只有约两天有效期，
    # 而 demo 要挂在简历上几个月 —— 不本地化的话过两天点开全是裂图。
    covers = C.DATA_DIR / "covers"
    covers.mkdir(parents=True, exist_ok=True)

    _seed_demo(covers)

    app.mount("/covers", StaticFiles(directory=covers), name="covers")

    # 任务活在进程内存里，进程一死它们就没了，但库里还写着 running。
    # 不收尸的话：进度页永远转圈，而且防重复检查会被这些幽灵卡住，
    # 同一个品牌再也开不了新任务。
    with db.connect() as conn:
        n = conn.execute(
            "UPDATE jobs SET status='failed', error='server restarted'"
            " WHERE status IN ('queued','running')").rowcount
    if n:
        log.warning("清理了 %d 个上次进程没跑完的任务", n)
    log.info("Spark 启动，数据目录 %s", C.DATA_DIR)


def _seed_demo(covers_dir) -> None:
    """把 seed/ 里的示例报告导进来。

    Railway 上每次部署都是全新的文件系统，而 data/ 有 717MB（大头是下载的视频）
    不可能进仓库 —— 所以 demo 需要的那一份 brief 和 47 张封面单独放在 seed/。
    没有它线上首页就是空的，而 demo 是没有邀请码的访客唯一看得到的东西。

    幂等：已经有 demo 就直接返回。
    """
    seed = C.BASE_DIR / "seed"
    manifest = seed / "demo.json"
    if not manifest.exists():
        return

    m = json.loads(manifest.read_text(encoding="utf-8"))
    with db.connect() as conn:
        if conn.execute("SELECT 1 FROM briefs WHERE is_demo = 1").fetchone():
            return

    brief_src = seed / f"{m['job_id']}.json"
    if not brief_src.exists():
        log.warning("seed 里缺 %s，跳过", brief_src.name)
        return

    dst_dir = C.DATA_DIR / "briefs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(brief_src, dst_dir / brief_src.name)

    n = 0
    for jpg in (seed / "covers").glob("*.jpg"):
        target = covers_dir / jpg.name
        if not target.exists():
            shutil.copy2(jpg, target)
            n += 1

    stats = {"count": m.get("count", 0), "crawled": m.get("crawled", 0)}
    with db.connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO briefs"
            " (job_id, handle, brand, category, patterns_json, sources_json,"
            "  stats_json, is_demo) VALUES (?,?,?,?,?,?,?,1)",
            (m["job_id"], "", m["brand"], m.get("category", ""), "", "",
             json.dumps(stats)))
    log.info("导入示例报告 %s（%s），封面 %d 张",
             m["brand"], m["job_id"], n)


# ---------------------------------------------------------------- 数据访问

def _set(job_id: str, **cols) -> None:
    keys = ", ".join(f"{k} = ?" for k in cols)
    with db.connect() as conn:
        conn.execute(f"UPDATE jobs SET {keys} WHERE id = ?",
                     (*cols.values(), job_id))


def _get(job_id: str) -> dict | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def _brief_path(job_id: str):
    return C.DATA_DIR / "briefs" / f"{job_id}.json"


def _frame_exists(video_id: str) -> bool:
    return (C.FRAMES_DIR / f"{video_id}_h0.jpg").exists()


def _demos() -> list[dict]:
    """首页的 demo 卡片。is_demo 直接改库设置，不做管理界面。"""
    out = []
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT job_id, brand, category, stats_json FROM briefs"
            " WHERE is_demo = 1 ORDER BY rowid LIMIT ?",
            (C.MAX_DEMOS,)).fetchall()
    for r in rows:
        s = json.loads(r["stats_json"] or "{}")
        out.append({"job_id": r["job_id"], "brand": r["brand"],
                    "category": r["category"] or "",
                    "count": s.get("count", 0), "crawled": s.get("crawled", 0)})
    return out


# ---------------------------------------------------------------- 后台任务

async def _run(job_id: str, brand: str, dev: bool) -> None:
    async with _lock:
        _set(job_id, status="running", stage="starting", progress_pct=0)

        def on_progress(p: pipeline.Progress) -> None:
            _set(job_id, stage=p.label, stage_detail=p.detail,
                 progress_pct=p.pct)

        try:
            result = await pipeline.analyze(brand, on_progress=on_progress,
                                            dev=dev)
        except Exception as exc:                          # noqa: BLE001
            log.exception("job %s 失败", job_id)
            _set(job_id, status="failed", error=str(exc)[:400])
            return

        path = _brief_path(job_id)
        pipeline.save(result, path)
        stats = {"count": len(result.videos),
                 "crawled": result.stats.after_dedupe}
        with db.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO briefs"
                " (job_id, handle, brand, category, patterns_json, sources_json,"
                "  stats_json, is_demo) VALUES (?,?,?,?,?,?,?,0)",
                (job_id, result.brand.hashtag, result.brand.nickname, "",
                 "", json.dumps(result.sources), json.dumps(stats)))
        _set(job_id, status="done", stage="done", progress_pct=100)
        log.info("job %s 完成，%d 条", job_id, len(result.videos))


# ---------------------------------------------------------------- 路由

@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return render.index_page(_demos())


@app.get("/api/probe")
async def api_probe(brand: str) -> JSONResponse:
    if not brand.strip():
        return JSONResponse({"count": 0})
    try:
        n = await pipeline.probe(brand)
    except Exception as exc:                              # noqa: BLE001
        log.warning("probe 失败: %s", exc)
        return JSONResponse({"count": -1})
    return JSONResponse({"count": n})


def _invited(request: Request, code: str) -> bool:
    """这次请求有没有资格花钱。

    判断放在服务端，因为前端拦不住任何人 —— `/api/jobs` 这个地址就写在页面
    代码里，谁都能直接 curl 过来，绕开弹窗、绕开 localStorage、绕开整个前端。
    唯一有意义的位置是真正花钱的那个函数前面。

    没配 INVITE_CODE 就是不设防，方便本地开发。
    """
    if not C.INVITE_CODE:
        return True
    if code and secrets.compare_digest(code, C.INVITE_CODE):
        return True
    cookie = request.cookies.get(C.INVITE_COOKIE, "")
    return bool(cookie) and secrets.compare_digest(cookie, C.INVITE_CODE)


@app.post("/api/jobs")
async def create_job(request: Request, bg: BackgroundTasks) -> JSONResponse:
    payload = await request.json()
    brand = (payload.get("brand") or "").strip()
    if not brand:
        raise HTTPException(400, "brand is required")
    dev = bool(payload.get("dev"))

    code = (payload.get("code") or "").strip()
    if not _invited(request, code):
        # 401 而不是 403：前端靠这个状态码决定弹窗，也靠它区分「码错了」和
        # 「还没输码」。一分钱不花。
        return JSONResponse({"error": "invite required",
                             "tried": bool(code)}, status_code=401)

    # 同一品牌已经在跑或在排队，就把那个 job 还回去，不再开新的。
    # MAX_CONCURRENT_JOBS=1 只保证不并行，不保证不重复 —— 排队的那个照样会跑、
    # 照样花钱。手滑多点一次 Analyze、或者 curl 多敲一次回车就会双倍付费，
    # 已经发生过一次。
    with db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM jobs WHERE lower(brand) = lower(?)"
            " AND status IN ('queued','running')"
            " ORDER BY created_at DESC LIMIT 1", (brand,)).fetchone()
    if row:
        log.info("%s 已有进行中的任务 %s，直接复用", brand, row["id"])
        return JSONResponse({"job_id": row["id"], "reused": True})

    job_id = uuid.uuid4().hex[:12]
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, handle, brand, status, stage, progress_pct,"
            " created_at) VALUES (?,?,?,'queued','queued',0,?)",
            (job_id, "", brand, int(time.time())))
    bg.add_task(_run, job_id, brand, dev)

    resp = JSONResponse({"job_id": job_id})
    if C.INVITE_CODE and code:
        # 输对过一次就记住这个浏览器，之后不再弹窗。
        # 它不认设备 —— 只是一张「这个浏览器输对过」的条子，谁输对谁都有。
        resp.set_cookie(C.INVITE_COOKIE, C.INVITE_CODE,
                        max_age=C.INVITE_COOKIE_MAX_AGE,
                        httponly=True, samesite="lax",
                        secure=request.url.scheme == "https")
    return resp


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    row = _get(job_id)
    if not row:
        raise HTTPException(404, "job not found")
    return JSONResponse({k: row[k] for k in
                         ("status", "stage", "stage_detail", "progress_pct",
                          "error", "brand")})


@app.get("/job/{job_id}", response_class=HTMLResponse)
def job_page(job_id: str) -> str:
    row = _get(job_id)
    if not row:
        raise HTTPException(404, "job not found")
    if row["status"] == "done":
        return HTMLResponse(status_code=302, content="",
                            headers={"Location": f"/brief/{job_id}"})
    return render.job_page(row["brand"])


@app.get("/brief/{job_id}", response_class=HTMLResponse)
def brief_page(job_id: str) -> str:
    path = _brief_path(job_id)
    if not path.exists():
        raise HTTPException(404, "brief not found")
    return render.result_page(json.loads(path.read_text()),
                              frame_exists=_frame_exists)


@app.get("/health")
def health() -> dict:
    return {"ok": True}
