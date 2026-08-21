# Outlier

输入一个品牌的 TikTok handle，找出该品牌相关视频里**超出自己账号基线**的爆款，归纳出 1-3 个共性内容模式，产出一份用于找灵感的 brief。

核心机制是**账号基线倍数** `这条播放 ÷ 该达人平常的播放中位数`——播放量高只说明账号强，不说明内容强。

完整规格见 `outlier-prd-v3.md` 和 `outlier-design-brief.md`。

## 当前状态

骨架就位，流水线是桩函数。等 fixtures 确认 Apify 真实字段后填实现。

```
app/config.py     所有阈值集中在这里
app/db.py         SQLite schema
app/main.py       FastAPI 路由（流水线待实现）
scripts/probe_apify.py   字段探测，开工第一步
```

## 本地跑起来

```bash
cp .env.example .env      # 然后把三个 key 填进去
pip install -r requirements.txt
uvicorn app.main:app --reload
```

打开 http://localhost:8000/health 应该看到 `{"ok": true}`。

## 第一步：字段探测

```bash
python scripts/probe_apify.py @cerave
```

只抓 20 条，成本几分钱。**其中两项结果会决定方案要不要改**：

- profile 调用是否支持日期下界参数 → 决定基线抓取策略
- 自带字幕覆盖率 → 低于 50% 则聚类输入要改

## 部署到 Railway

1. `New Project → Deploy from GitHub repo`，选这个仓库
2. `Variables` 填 `APIFY_TOKEN` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `DATA_DIR=/data`
3. `Settings → Volumes` 挂一个 volume，**挂载路径 `/data`**

第 3 步不能省。Railway 默认文件系统重启即清空，不挂 Volume 会丢掉数据库和所有截图，而 brief 是永久链接。
