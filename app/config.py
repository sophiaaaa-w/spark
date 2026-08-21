"""所有阈值集中在这里，不要散到代码各处。

数字全部来自 2026-08-18 对 clockworks/tiktok-scraper 的实测（scripts/probe*.py）。
改任何一个之前先看看注释里的实测依据。
"""
import os
from pathlib import Path


def _load_env() -> None:
    """读 .env 到环境变量。

    自己实现而不是依赖 python-dotenv —— 这个项目会在不同的 Python 之间跳
    （系统 Python / Homebrew Python / 虚拟环境），而 Homebrew 的 Python 禁止
    全局装包（PEP 668）。少一个依赖就少一处会炸的地方，而这个功能只有十行。
    """
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_env()

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")   # 二期字幕兜底用，MVP 不需要

# 仓库根目录。seed/ 之类跟着代码走的东西用它定位，不受 DATA_DIR 影响。
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "outlier.db"
FRAMES_DIR = DATA_DIR / "frames"

# ---------------------------------------------------------------- Apify

ACTOR_TIKTOK = "clockworks~tiktok-scraper"
APIFY_BASE = "https://api.apify.com/v2"
APIFY_POLL_INTERVAL = 5          # 同步接口 300s 会超时，全部走异步 run + 轮询

# 实测：日期下界参数只在 profiles 上生效，searchQueries / hashtags 上被忽略
DATE_PARAM_WORKS_ON_PROFILE = True
DATE_PARAM_WORKS_ON_SEARCH = False

# ---------------------------------------------------------------- 召回
#
# 实测产出率 4.7%（150 条 → 7 条），且 254 条要跑 156 秒。
# 单个大 run 会吃掉整个时间预算，所以拆成多个并行 run。
# 不同查询词变体的结果集重叠更少，召回反而更全。

# ── 两段式召回 ──────────────────────────────────────────────────
#
# TikTok 不提供「某品牌全部相关视频」的接口。能拿的只有几个由 TikTok 自己按相关性
# 排好、且有上限的切片。实测 4 路各要 400 条：
#     #wavytalk            400/400  100%   ← 还有余量
#     kw @wavytalkofficial 303/400   76%
#     kw wavytalk          277/400   69%   ← 相关性榨干了
#     kw wavytalk review   195/400   49%
# 结论：关键词路再加数量没用，**要加变体**。各路重叠只有 10-30%，每加一路基本都是新视频。
#
# 所以改成两段：第一轮探路 + 从 caption/hashtag 里挖出品牌的实际词汇表，
# 第二轮用挖到的词扩量。@wavytalkofficial 第一轮就挖出了 #wavytalkthermalbrush(128)、
# #wavytalkhair(163)、#wavytalkpartner(20) 等一堆高量标签。

RECALL_PARALLEL_RUNS = 4
# 邀请码。空值 = 不设防，任何人都能触发真实抓取（本地开发时的默认状态）。
# 线上必须在 Railway 的环境变量里配一个，否则每个访客都在花你的钱。
INVITE_CODE = os.getenv("SPARK_INVITE_CODE", "").strip()

# 校验通过后种的 cookie，30 天。存的是码本身，服务端每次请求都重新比对 ——
# 安全性来自「服务端每次都查」，不是来自 cookie 本身。
# httpOnly 只是额外好处：页面 JS 读不到，不会被 XSS 偷走或从 devtools 里复制走。
INVITE_COOKIE = "spark_invite"
INVITE_COOKIE_MAX_AGE = 30 * 24 * 3600

# 首页最多展示几张 demo 卡片。超过 3–4 个品类反而稀释说服力 ——
# 要证明的是「不是给一个品牌写死的」，两三个不同品类就够了。
MAX_DEMOS = 4

# 挖词阶段在屏幕上的最短驻留（秒）。前端每 3 秒轮询一次，低于这个数
# 这一步就会被整个跳过 —— 而它是最值得被看见的一步。两拍共 7 秒，
# 占十分钟流程的 1%。
MINE_DWELL_S = 3.5

RECALL_ITEMS_PER_RUN = 200          # 第一轮：探路，4×200
RECALL2_ITEMS_PER_RUN = 200         # 第二轮：用挖到的词
RECALL2_MAX_QUERIES = 13
RECALL2_CONCURRENCY = 6             # 实测 4 路并行仍要 500s+，说明并行度受内存限制，
                                    # 一次开 13 个只会排队。限 6 路、分批跑更可控。
DEV_ITEMS_PER_RUN = 20              # 开发期压到这个数，一次几分钱

# 挖词的门槛
MINE_MIN_HASHTAG_COUNT = 15
MINE_MIN_PRODUCT_COUNT = 5
# 地区/店铺类词，搜了是浪费钱
MINE_STOPWORDS = {"uk", "us", "usa", "mx", "eu", "de", "fr", "es", "it", "ca",
                  "au", "shop", "store", "official", "sale", "code", "link",
                  "and", "en", "la", "el", "products", "product"}

# ---------------------------------------------------------------- 硬过滤
#
# 实测 150 条的漏斗：
#   原始 150 → 剔图文帖 66 → 只留英文 59 → 时长 44 → 近30天 15 → 播放>10k 7

WINDOW_DAYS = 30
MIN_PLAYS = 10_000
MIN_DURATION_S = 10
MAX_DURATION_S = 90
MIN_RELEVANCE = 3
# 只留 en。原来放行 "un"（未判定）是为了保样本量，但实测那批全是纯 hashtag + emoji
# 的 caption —— TikTok 判不出语言，我们也判不出，其中确实混进了非英文语境的视频。
# 代价：过硬门槛从 55 条降到 48 条（-13%），靠多召回补回来。
ALLOWED_LANGUAGES = {"en"}

# 互动率下限 —— 用来挡「买了量的视频」。
#
# TikTok 公开接口只给总 playCount，没有付费/自然流量的拆分（那只在创作者后台和
# 广告后台里，外部拿不到）。所以只能反推：付费投放的观众是被推到面前的，不是主动
# 划到的，互动率会明显偏低。
#
# 实测 @wavytalkofficial 的 62 条候选，信号非常干净：
#   疑似买量  0.23% / 0.28% / 0.30% / 0.37% / 0.43% / 0.52% …（10 条里 9 条带广告标记）
#   正常爆款  3% ~ 10%
#   中间几乎没有过渡带
#
# 注意：不能直接按 isAd 剔除 —— 62 条里 45 条带广告标记，剔完只剩 16 条。
# 而且商业合作本身不是问题，达人收钱拍的内容一样有手法可学。要挡的是
# 「播放量不反映内容质量」的那些，不是「收了钱」的那些。
#
# 这条门槛还顺带解决了另一件事：互动率低的视频不管什么原因，都不是好老师。
#
# 行业基准是 ≥5% 合格 / ≥7% 较好 / ≥10% 优秀。但实测 @wavytalkofficial 的
# 2088 条唯一视频里，过完其他门槛的 122 条 ER 中位数只有 1.4%-3.9%，
# 5% 这条线意味着只有 20-30% 的内容合格，凑不满 Top 50（只剩 27 条）。
#
#   ≥5% → 27 条    ≥4% → 41 条    ≥3% → 53 条 ✅
#
# 定在 3% 的理由不是妥协，是目标变了：产品要挖的是**品牌给达人的 brief**，
# 而 brief 同样存在于执行得平庸的视频里 —— 甚至更明显，因为平庸的执行往往是
# 照抄 brief 而没加自己的东西。放宽门槛才看得到「brief 让大家这么拍但观众
# 不买账」这类结论。
#
# 防买量的功能不受影响：买量视频的特征是 0.2%-0.7%，3% 已是它的 4-15 倍。
#
# 互动率同时作为**输出维度**，每个 pattern 报自己的 ER 中位数：
#   占比高 + ER 高  →  brief 里的招，而且真的有用
#   占比高 + ER 低  →  brief 让大家这么拍，但观众不买账   ← 最有价值的一条
#   占比低 + ER 高  →  少有人做但一做就灵
MIN_ENGAGEMENT_RATE = 0.03

# 另外，实测互动率**不随播放量下降**（1000k+ 区间 ER 中位 3.9%，反而最高），
# 所以不需要按播放量分层设门槛。这也说明播放量本身是个好的质量信号。

RELAX_LADDER = [(30, 10_000), (30, 5_000), (30, 3_000), (60, 5_000)]

BUY_INTENT_WORDS = ["link in bio", "code", "% off", "tiktok shop", "🛒", "#ad"]

# ---------------------------------------------------------------- 排序
#
# ── 排序 ────────────────────────────────────────────────────────
#
# 原方案按「账号基线倍数」排序 —— 这条播放 ÷ 该达人平常的播放中位数。
# 它是诚实的指标，但要为每个达人多抓 20 条历史视频，成本高一个量级
# （实测 +$2.12/次、+167 秒）。
#
# 所以先实现，再测「播放 ÷ 粉丝数」这个免费代理够不够用：
#     秩相关 +0.780，Top20 重合 14/20 —— 够用。
# 于是删掉了历史抓取那一整块。⚡ 角标现在的含义是播放达到粉丝数 3 倍以上。
#
# 三个指标各转成百分位再加权 —— 播放量 1万-650万、互动率 1.5%-15%、
# 播放/粉丝 0.1-500，量级差太远，直接加权会被播放量完全支配。

SCORE_WEIGHT_PLAYS = 0.7
SCORE_WEIGHT_ENGAGEMENT = 0.2
SCORE_WEIGHT_PLAYS_PER_FOLLOWER = 0.1

TOP_N = 50
# 每个达人最多贡献几条。目的是防止单个人的风格主导整个样本。
# 定 3 而不是 2：实测 50 条来自 40 个账号，平均 1.25 条，cap 3 意味着
# 单人最高占比 6%，依然是很紧的约束，而 cap 2 会白白砍掉 2 条合格素材。
MAX_VIDEOS_PER_ACCOUNT = 3
PRESCREEN_ACCOUNTS = 50          # 已不用（基线砍掉后没有预筛环节），保留避免旧脚本报错

# ---------------------------------------------------------------- 聚类

MAX_PATTERNS = 3
# 下限 3 条：2 条相似可能是巧合，3 条共用一个具体动作才算信号。
# 原来定的 5 条是按 30 条输入设计的，实测 14 条输入时要求 5 条等于要求占 36%，
# 几乎不可能达到，结果把模型正确归纳出的 pattern 全丢了。
MIN_VIDEOS_PER_PATTERN = 3
# 占比低于这个数就标注「样本支撑较薄」，让用户自己判断，而不是我替他砍掉
THIN_EVIDENCE_SHARE = 0.15
HIGHEST_LIFT_MARGIN = 1.30       # 效果要比第二名高 30% 才打标记

# 「大家都在拍」和「少有人做」的分界。用占比而不是排名 —— 三个 pattern 时
# 排名第二可能只占 12%，那不叫大家都在拍。
HIGH_SHARE_RATIO = 0.25          # 占比 ≥25% 才算「大家都在拍」
LOW_SHARE_RATIO = 0.20           # 占比 ≤20% 才算「少有人做」

# ---------------------------------------------------------------- 样例与抽帧

EXEMPLARS_PER_PATTERN = 3        # 组内基线倍数前 50% 里，播放量最高的 3 条
DOWNLOAD_OVERSAMPLE = 8          # 下载失败是常态
DOWNLOAD_CONCURRENCY = 4
DOWNLOAD_TIMEOUT_S = 30
DOWNLOAD_RETRIES = 2
FRAMES_MAX = 12
FRAME_WIDTH = 720

# hook 分析用的抽帧：前 3 秒抽 2 张。
# 实测教训：只喂文字的话，没口播的视频会被判成「无 hook」—— 而样本里有近一半
# 没有字幕。一条 160 万播放的视频当然有钩子，只是钩子全在画面里。
# 分辨率比时间轴那边低，因为只需要看清「屏幕上是什么」，不需要细节，能省一半 token。
HOOK_FRAME_TIMES = (0.5, 2.5)
HOOK_FRAME_WIDTH = 480
HOOK_DENSE_UNTIL_S = 3.0
HOOK_FRAME_INTERVAL_S = 0.5
SCENE_THRESHOLD = 0.3
FALLBACK_FRAME_INTERVAL_S = 3.0

# 骨架视频必须有 WebVTT 字幕：砍掉屏幕字之后，没口播的视频左栏会空一半
SKELETON_REQUIRES_SUBTITLES = True

# ---------------------------------------------------------------- Claude

MODEL_CLUSTER = "claude-sonnet-5"
MODEL_PATTERN = "claude-opus-5"
MODEL_TRANSLATE = "claude-sonnet-5"
TIMELINE_MIN_SEGMENTS = 4
TIMELINE_MAX_SEGMENTS = 6
FUNCTION_MAX_WORDS = 25

# ---------------------------------------------------------------- 运行

MAX_CONCURRENT_JOBS = 1          # 单实例 + ffmpeg，超出排队
POLL_INTERVAL_S = 3              # 前端轮询

# 各阶段的进度条权重在 pipeline.py 的 STAGES 里，按实测耗时分配，不是平均分。

# ---------------------------------------------------------------- 字段路径
#
# 实测确认的嵌套位置。归一化统一在 models.py 里做，别处不要碰原始 JSON。
#   videoMeta.duration / coverUrl / subtitleLinks
#   authorMeta.id / name / nickName / fans / signature
#   mediaUrls 实测恒为空数组 —— 视频必须用 yt-dlp 自己下
