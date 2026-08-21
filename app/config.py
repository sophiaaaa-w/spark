"""所有阈值集中在这里，不要散到代码各处。

数字全部来自对 clockworks~tiktok-scraper 的实测。改任何一个之前先看注释里的依据 ——
没有一个是凭感觉取的整数。
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

# ---------------------------------------------------------------- 凭证与路径

APIFY_TOKEN = os.getenv("APIFY_TOKEN", "")

# 邀请码。空值 = 不设防，本地开发时的默认状态。
# 线上必须配，否则每个访客都在花你的钱。校验在服务端 —— 仓库是公开的，
# 前端的检查只是装饰，那个接口一条 curl 就能绕过去。
INVITE_CODE = os.getenv("SPARK_INVITE_CODE", "").strip()
INVITE_COOKIE = "spark_invite"
INVITE_COOKIE_MAX_AGE = 30 * 24 * 3600

# 仓库根目录。seed/ 之类跟着代码走的东西用它定位，不受 DATA_DIR 影响。
BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = Path(os.getenv("DATA_DIR", "./data"))
DB_PATH = DATA_DIR / "outlier.db"
FRAMES_DIR = DATA_DIR / "frames"

# ---------------------------------------------------------------- Apify

ACTOR_TIKTOK = "clockworks~tiktok-scraper"
APIFY_BASE = "https://api.apify.com/v2"
APIFY_POLL_INTERVAL = 5          # 同步接口 300s 会超时，全部走异步 run + 轮询

# ---------------------------------------------------------------- 两段式召回
#
# TikTok 不提供「某品牌全部相关视频」的接口。能拿的只有几个由 TikTok 自己按
# 相关性排好、且有上限的切片。实测 4 路各要 400 条：
#     #brand              400/400  100%   ← 还有余量
#     kw @brandofficial   303/400   76%
#     kw brand            277/400   69%   ← 相关性榨干了
#     kw brand review     195/400   49%
# 结论：关键词路再加数量没用，**要加变体**。各路重叠只有 10-30%。
#
# 所以分两段：第一轮探路 + 从 caption/hashtag 里挖出品牌的实际词汇表，
# 第二轮用挖到的词扩量。

RECALL_ITEMS_PER_RUN = 200          # 第一轮：4 路并行探路
RECALL2_ITEMS_PER_RUN = 200         # 第二轮：用挖到的词
RECALL2_MAX_QUERIES = 13
RECALL2_CONCURRENCY = 6             # 实测 4 路并行仍要 500s+，说明并行度受 Apify
                                    # 内存配额限制，一次开 13 个只会排队
DEV_ITEMS_PER_RUN = 20              # 开发期压到这个数，一次几分钱

# 挖词门槛
MINE_MIN_HASHTAG_COUNT = 15
MINE_MIN_PRODUCT_COUNT = 5
# 地区/店铺类词，搜了是浪费钱
MINE_STOPWORDS = {"uk", "us", "usa", "mx", "eu", "de", "fr", "es", "it", "ca",
                  "au", "shop", "store", "official", "sale", "code", "link",
                  "and", "en", "la", "el", "products", "product"}

# ---------------------------------------------------------------- 硬过滤

WINDOW_DAYS = 30
MIN_PLAYS = 10_000
MIN_DURATION_S = 10
MAX_DURATION_S = 90
MIN_RELEVANCE = 3

# 只留 en。原来放行 "un"（未判定）是为了保样本量，但实测那批全是纯 hashtag +
# emoji 的 caption —— TikTok 判不出语言，我们也判不出，其中确实混进了非英文视频。
# 代价：过关数从 55 降到 48（-13%），靠多召回补回来。
ALLOWED_LANGUAGES = {"en"}

# 互动率下限 —— 用来挡「买了量的视频」。
#
# TikTok 公开接口只给总 playCount，没有付费/自然流量的拆分。所以只能反推：
# 付费投放的观众是被推到面前的，不是主动划到的，互动率会明显偏低。
#
# 实测某品牌 62 条候选，信号非常干净：
#   疑似买量  0.23% / 0.28% / 0.30% / 0.37% / 0.43% / 0.52% …
#   正常爆款  3% ~ 10%
#   中间几乎没有过渡带
#
# 不能直接按 isAd 剔除 —— 62 条里 45 条带广告标记，剔完只剩 16 条。而且商业合作
# 本身不是问题，达人收钱拍的内容一样有手法可学。要挡的是「播放量不反映内容质量」
# 的那些，不是「收了钱」的那些。
#
# 行业基准是 ≥5% 合格，但实测过完其他门槛的样本 ER 中位数只有 1.4%-3.9%：
#   ≥5% → 27 条    ≥4% → 41 条    ≥3% → 53 条 ✅
# 定在 3% 不影响防买量功能：买量视频的特征是 0.2%-0.7%，3% 已是它的 4-15 倍。
MIN_ENGAGEMENT_RATE = 0.03

# 实测互动率**不随播放量下降**（100 万以上区间 ER 中位 3.9%，反而最高），
# 所以不需要按播放量分层设门槛。这也说明播放量本身是个好的质量信号。

# 冷门品牌兜底：按 (天数, 播放下限) 逐级放宽，直到凑够结果
RELAX_LADDER = [(30, 10_000), (30, 5_000), (30, 3_000), (60, 5_000)]

BUY_INTENT_WORDS = ["link in bio", "code", "% off", "tiktok shop", "🛒", "#ad"]

# ---------------------------------------------------------------- 排序
#
# 纯播放量降序。曾经用三项百分位加权（播放/互动率/播放粉丝比），换掉的原因是
# 加权排序在页面上看不出规律 —— 用户扫到 198k 排在 1.2M 上面只会以为是 bug，
# 而排序规则又解释不了（总不能在页面上写一行公式）。
#
# 代价是互动率不再影响顺序，所以卡片上给本组互动率前 15% 的那档上色：
# 排序编码不了的维度，用颜色补。

TOP_N = 50

# 每个达人最多贡献几条，防止单人风格主导整个样本。
# 定 3 而不是 2：实测 50 条来自 40 个账号，平均 1.25 条，cap 3 意味着单人最高
# 占比 6%，依然是很紧的约束，而 cap 2 会白白砍掉 2 条合格素材。
MAX_VIDEOS_PER_ACCOUNT = 3

# ---------------------------------------------------------------- 封面抽帧

DOWNLOAD_CONCURRENCY = 4
DOWNLOAD_TIMEOUT_S = 30
DOWNLOAD_RETRIES = 2             # 下载失败是常态
FRAMES_MAX = 12
FRAME_WIDTH = 720
SCENE_THRESHOLD = 0.3
FALLBACK_FRAME_INTERVAL_S = 3.0

# 前 3 秒抽 2 张。实测教训：只喂文字的话，没口播的视频会被判成「无 hook」——
# 而样本里近一半没有字幕。一条 160 万播放的视频当然有钩子，只是钩子全在画面里。
HOOK_FRAME_TIMES = (0.5, 2.5)
HOOK_FRAME_WIDTH = 480
HOOK_DENSE_UNTIL_S = 3.0
HOOK_FRAME_INTERVAL_S = 0.5

# ---------------------------------------------------------------- 运行

MAX_CONCURRENT_JOBS = 1          # 单实例 + ffmpeg，超出排队

# 首页最多展示几张示例卡片
MAX_DEMOS = 4

# 挖词阶段在屏幕上的最短驻留（秒）。前端每 3 秒轮询一次，低于这个数这一步
# 根本不会被采样到 —— 而它是最值得被看见的一步。两拍共 7 秒，占全程的 1%。
MINE_DWELL_S = 3.5

# 各阶段的进度条权重在 pipeline.py 的 STAGES 里，按实测耗时分配，不是平均分。

# ---------------------------------------------------------------- 字段路径
#
# 实测确认的嵌套位置。归一化统一在 models.py 里做，别处不要碰原始 JSON。
#   videoMeta.duration / coverUrl / subtitleLinks
#   authorMeta.id / name / nickName / fans / signature
#   mediaUrls 实测恒为空数组 —— 视频必须用 yt-dlp 自己下
