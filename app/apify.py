"""Apify 客户端。

两条实测结论决定了这里的写法：
  · 同步接口 run-sync-get-dataset-items 有 300s 上限，召回一定会超 → 全部走异步 run + 轮询
  · 单个 run 拿 254 条要 156 秒 → 召回拆成多个并行 run，总耗时不变
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import httpx

from . import config as C

log = logging.getLogger(__name__)


class ApifyError(RuntimeError):
    pass


class Apify:
    def __init__(self, token: str | None = None, actor: str | None = None) -> None:
        self.token = token or C.APIFY_TOKEN
        self.actor = actor or C.ACTOR_TIKTOK
        if not self.token:
            raise ApifyError("缺 APIFY_TOKEN，检查 .env")

    @property
    def auth(self) -> dict:
        """走 Authorization 头，不要用 ?token= 查询串。

        httpx 会把完整 URL 打进 INFO 日志，token 放查询串就等于每次请求都把
        密钥明文写进日志 —— 本地终端、Railway 的日志面板、任何日志收集服务
        全都留一份。已经因此泄露过一次。
        请求头不会被记录，这是唯一区别，但足够。
        """
        return {"Authorization": f"Bearer {self.token}"}

    # ---------------------------------------------------------------- 底层

    async def _start(self, client: httpx.AsyncClient, payload: dict) -> tuple[str, str]:
        r = await client.post(
            f"{C.APIFY_BASE}/acts/{self.actor}/runs",
            headers=self.auth,
            json=payload,
        )
        if r.status_code >= 400:
            raise ApifyError(f"启动 run 失败 HTTP {r.status_code}: {r.text[:300]}")
        d = r.json()["data"]
        return d["id"], d["defaultDatasetId"]

    async def _wait(self, client: httpx.AsyncClient, run_id: str, on_tick=None) -> str:
        while True:
            await asyncio.sleep(C.APIFY_POLL_INTERVAL)
            r = await client.get(
                f"{C.APIFY_BASE}/actor-runs/{run_id}", headers=self.auth
            )
            status = r.json()["data"]["status"]
            if on_tick:
                on_tick(status)
            if status in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                return status

    async def _items(self, client: httpx.AsyncClient, dataset_id: str) -> list[dict]:
        r = await client.get(
            f"{C.APIFY_BASE}/datasets/{dataset_id}/items", headers=self.auth
        )
        r.raise_for_status()
        return r.json()

    async def run(self, payload: dict, *, label: str = "run") -> list[dict]:
        """跑一个 actor run 并返回全部结果。失败返回空列表而不抛异常。

        单个 run 挂掉不该拖垮整个 job —— 并行召回里挂一路，其他三路照样用。
        """
        async with httpx.AsyncClient(timeout=900) as client:
            try:
                run_id, dataset_id = await self._start(client, payload)
                status = await self._wait(client, run_id)
                if status != "SUCCEEDED":
                    log.warning("apify %s 结束状态 %s", label, status)
                    return []
                items = await self._items(client, dataset_id)
                log.info("apify %s 拿到 %d 条", label, len(items))
                return items
            except Exception as exc:                       # noqa: BLE001
                log.warning("apify %s 失败: %s", label, exc)
                return []

    # ---------------------------------------------------------------- 业务调用

    async def resolve_profile(self, handle: str) -> dict | None:
        """解析 handle，拿 nickname / bio / 粉丝数。"""
        items = await self.run(
            {"profiles": [handle.lstrip("@")], "resultsPerPage": 1},
            label=f"resolve:{handle}",
        )
        if not items:
            return None
        return items[0].get("authorMeta") or None

    def _recall_payloads(self, *, nickname: str, hashtag: str,
                         username: str, per_run: int) -> list[tuple[str, dict]]:
        """四路并行召回。

        用不同查询词变体是为了让结果集重叠更少 —— 实测单一查询词产出率只有 4.7%，
        多变体既提高覆盖，又因为并行而不增加耗时。
        """
        return [
            ("keyword", {"searchQueries": [nickname], "resultsPerPage": per_run,
                         "shouldDownloadSubtitles": True}),
            ("keyword+review", {"searchQueries": [f"{nickname} review"],
                                "resultsPerPage": per_run,
                                "shouldDownloadSubtitles": True}),
            ("hashtag", {"hashtags": [hashtag.lstrip("#")], "resultsPerPage": per_run,
                         "shouldDownloadSubtitles": True}),
            ("mention", {"searchQueries": [f"@{username}"], "resultsPerPage": per_run,
                         "shouldDownloadSubtitles": True}),
        ]

    async def recall(self, *, nickname: str, hashtag: str, username: str,
                     per_run: int | None = None) -> list[dict]:
        per_run = per_run or C.RECALL_ITEMS_PER_RUN
        payloads = self._recall_payloads(
            nickname=nickname, hashtag=hashtag, username=username, per_run=per_run
        )
        results = await asyncio.gather(
            *(self.run(p, label=label) for label, p in payloads)
        )
        merged: list[dict] = []
        for items in results:
            merged.extend(items)
        log.info("召回合计 %d 条（去重前）", len(merged))
        return merged

    async def run_batch(self, payloads: list[tuple[str, dict]], *,
                        concurrency: int = C.RECALL2_CONCURRENCY,
                        on_done=None) -> dict[str, list[dict]]:
        """并发跑一批 run，限并发。返回 {label: items}。

        限并发是因为实测 4 路并行仍要 500s+ —— 并行度受 Apify 的内存配额限制，
        一次开 13 个不会更快，只会全部排队且难以观察进度。
        """
        sem = asyncio.Semaphore(concurrency)

        async def one(label: str, payload: dict) -> tuple[str, list[dict]]:
            async with sem:
                items = await self.run(payload, label=label)
                if on_done:
                    on_done(label, len(items))
                return label, items

        pairs = await asyncio.gather(*(one(l, p) for l, p in payloads))
        return dict(pairs)

    async def author_history(self, username: str, *, since_ts: int) -> list[dict]:
        """抓某账号的历史视频，用于算基线。

        实测：日期下界参数在 profiles 上生效（搜索上不生效），所以这里可以精确按
        日期抓 —— 慢更账号只回十几条，高频账号回够为止，两头都不浪费。
        """
        since = datetime.fromtimestamp(since_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        return await self.run(
            {
                "profiles": [username.lstrip("@")],
                "resultsPerPage": C.HISTORY_FETCH_MAX,
                "oldestPostDate": since,
            },
            label=f"history:{username}",
        )

    async def author_histories(self, usernames: list[str], *, since_ts: int,
                               concurrency: int = 6) -> dict[str, list[dict]]:
        """并发抓多个账号的历史。限并发，避免一次开几十个 run。"""
        sem = asyncio.Semaphore(concurrency)

        async def one(u: str) -> tuple[str, list[dict]]:
            async with sem:
                return u, await self.author_history(u, since_ts=since_ts)

        pairs = await asyncio.gather(*(one(u) for u in usernames))
        return dict(pairs)


def default_since_ts(days: int = C.BASELINE_WINDOW_DAYS + C.WINDOW_DAYS) -> int:
    """基线要回溯到「最早候选视频的 T − 90d」，最坏情况是 30 + 90 = 120 天前。"""
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
