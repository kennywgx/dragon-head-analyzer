# 开发日志

## 2026-03-31 — 项目初始化

### 需求确认

- 用户需求：建立一个 A 股短线龙头战法分析系统，用于学习
- 核心原则：纯规则驱动，不做预判，不提示风险，机械执行规则
- 技术栈：Python (FastAPI) + Vue3 + AKShare/efinance

### 数据源调研

调研了以下免费 A 股数据源，最终选定 **AKShare（主力）+ efinance（补充）**：

| 库 | 注册 | 分钟线 | 实时 | 涨停池 | 龙虎榜 | 封单 |
|---|---|---|---|---|---|---|
| AKShare | 无需 | ✅ | ✅ | ✅ | ✅ | ✅ |
| efinance | 无需 | ✅ | ✅ | ❌ | ❌ | 有限 |
| BaoStock | 无需 | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tushare Pro | 需积分 | ✅ | ✅ | ✅ | ✅ | ❌ |

**结论：** AKShare 一家几乎覆盖龙头战法的全部需求（涨停池、连板、板块、龙虎榜、分时、资金流）。

### 项目结构搭建

```
dragon-head-analyzer/
├── backend/                    # Python FastAPI 后端
│   ├── app/
│   │   ├── core/              # config.py（规则参数）+ scheduler.py（定时调度）
│   │   ├── models/            # Pydantic 数据模型
│   │   ├── routers/           # stocks.py（API 路由）
│   │   └── services/          # data_fetcher.py + analyzer.py + logger.py
│   ├── logs/                  # 分析日志（按日期）
│   └── requirements.txt
├── frontend/                   # Vue 3 + Vite 前端
│   └── src/
│       ├── api/               # axios 封装
│       ├── components/        # KlineChart.vue（K线图组件）
│       ├── views/             # Dashboard / ZtPool / StockDetail / Boards / Logs
│       └── router/            # 路由配置
├── start-all.bat / .sh        # 一键启动
├── stop-all.bat               # 一键停止（Windows）
├── start-backend.bat / .sh
└── start-frontend.bat / .sh
```

### API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scan` | GET | 全量扫描：涨停池 + 龙头识别 + 信号 |
| `/api/scan/trigger` | POST | 手动触发扫描（写日志） |
| `/api/zt-pool` | GET | 涨停股池 |
| `/api/lb-pool` | GET | 连板股池（从涨停池筛选连板数>1） |
| `/api/zr-pool` | GET | 炸板股池 |
| `/api/realtime` | GET | 全市场实时行情快照 |
| `/api/stock/{code}` | GET | 个股详情（分时+日线+资金流） |
| `/api/boards` | GET | 板块排名 |
| `/api/logs` | GET | 分析日志 |

### 龙头识别规则 v1

当前实现的基础规则：

1. **候选筛选：** 涨停池中连板数 ≥ 2 的个股进入龙头候选池
2. **封板评分：** `连板数 × 10 + 封单额占比分(15/8/0) + 涨幅分(10/5/0)`
3. **等级划分：**
   - 妖王：7 板+
   - 总龙头：5-6 板
   - 分支龙头：3-4 板
   - 跟风龙头：2 板
4. **信号类型：** 龙头确认 / 高位连板（≥5板预警）

### 实测结果（2026-03-31 盘后数据）

| 指标 | 数据 |
|---|---|
| 涨停池 | 62 只 |
| 连板股 | 12 只 |
| 炸板 | 17 只 |
| 龙头候选 | 12 只 |
| 交易信号 | 13 条 |

**龙头排名：**
1. 美诺华 (603538) — 5 连板 | 总龙头 | 评分 60
2. 神剑股份 (002361) — 3 连板 | 分支龙头 | 评分 40
3. 双鹭药业 / 津药药业 / 联环药业等 10 只 — 2 连板跟风龙头

### 踩坑记录

1. **akshare API 变更：** `stock_zt_pool_lbg_em`（连板池）在新版不存在，改为从涨停池中筛选连板数 > 1
2. **Windows 中文乱码：** CMD 默认 GBK 编码，bat 脚本加 `chcp 65001 >nul` 切 UTF-8 代码页
3. **pip PEP 668：** 系统 Python 需要 `--break-system-packages` 或用 venv

---

## 2026-03-31（二轮）— 全面完善规则引擎 + K线可视化

### 新增功能

#### 1. 板块共振规则细化 ✅
- 获取板块排名数据，判断龙头所属板块是否处于强势（前20%且涨幅>2%）
- 板块共振加分 +10 分，体现在封板评分中
- 信号类型新增「板块共振」

#### 2. 封单额/流通市值精确阈值调整 ✅
- 三级评分体系：强封（≥1%）+15分 / 中封（≥0.5%）+8分 / 弱封（≥0.2%）+3分
- 新增 `seal_ratio_medium` 和 `seal_ratio_weak` 配置参数

#### 3. 弱转强 / 分歧转一致判定 ✅
- **弱转强**：前日涨幅<3%（弱板），今日涨停 → 加分15，发出「弱转强」信号
- **分歧转一致**：前日振幅>5%（分歧板），今日涨停 → 加分12，发出「分歧转一致」信号
- 需要获取个股历史K线数据来计算前日涨跌幅和振幅

#### 4. 卡位介入规则 ✅
- 同连板数多只股票竞争时，涨幅领先>=3%的视为卡位成功
- 生成「卡位成功」信号，包含对手信息

#### 5. 离场信号完善 ✅
- **断板预警**：前日涨停/连板股今日未进涨停池（高连板断板标记 high 级别）
- **放量长阴**：跌幅>7%且量比>1.8倍（high 级别）
- **板块退潮**：炸板数>=涨停数的50%（high 级别）
- 离场信号独立展示在 Dashboard 中，高优先级标红

#### 6. 仓位管理规则 ✅
- 基础仓位：妖王70% / 总龙头50% / 分支龙头40% / 跟风30%
- 弱转强/分歧转一致信号额外 +10%
- 单票最大仓位 70%
- Dashboard 新增仓位建议表，带可视化进度条

#### 7. K线图表可视化 ✅
- 新增 `KlineChart.vue` 组件：纯 SVG 蜡烛图 + 成交量柱
- 支持十字线追踪悬浮，显示 OHLCV 数据
- StockDetail 页面新增 K 线图卡片（日线 + 5分钟线）
- 无需外部图表库依赖

### 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/core/config.py` | 新增板块共振、弱转强、卡位、离场、仓位等规则参数 |
| `backend/app/services/analyzer.py` | 全面重写：新增6个分析步骤，规则覆盖从7项扩展到11项 |
| `backend/app/models/schemas.py` | 新增 ExitSignal / PositionSuggestion 模型 |
| `frontend/src/components/KlineChart.vue` | 新建：SVG 蜡烛图组件 |
| `frontend/src/views/Dashboard.vue` | 新增离场信号、仓位建议展示，信号类型扩展 |
| `frontend/src/views/StockDetail.vue` | 集成 KlineChart 组件 |

### 待完善

- [ ] 微信机器人推送（需配置公众号/企业微信 webhook）
- [ ] 更多K线形态（锤子线、吞没形态等）
- [ ] 历史回测功能
- [ ] 信号触发的价格/时间精确记录

---

## 2026-04-01 — 数据源重构：多源回退 + 磁盘缓存 + 反反爬

### 问题

- `push2his.eastmoney.com` 接口从服务器环境无法访问，导致 akshare/efinance 多数接口超时或失败
- 需要找到可替代的数据获取方案，同时保持原有功能不变

### 解决方案

#### 1. 完全重写 `data_fetcher.py` ✅
采用三层架构：

```
请求层: akshare/efinance (优先) → 新浪/腾讯 (备用) → 返回空
   ↓
缓存层: DiskCache (JSON 文件, 本地持久化)
   ↓
工具层: polite_delay + UA 伪装 + 错误处理
```

#### 2. 本地磁盘缓存 (`DiskCache`) ✅
- 缓存目录：`backend/data_cache/`（自动创建）
- 格式：每个 key 对应一个 JSON 文件（MD5 命名）
- 包含 `data` + `timestamp` + `key`
- TTL 策略：
  - 涨停池/炸板池：交易时间 60s，盘后 300s，周末 24h
  - 实时行情：10s
  - 日线历史：24h（数据不会变）
  - 分时K线：1h
  - 板块数据：120s
  - 资金流向：300s
- 自动清理：启动时清理超过 30 天的缓存文件

#### 3. 新浪备用数据源 (`SinaStockAPI`) ✅
- 实时行情：`hq.sinajs.cn` 接口
- K线数据：`money.finance.sina.com.cn` 接口（支持 5/15/30/60/240 分钟）
- 当 akshare/efinance 失败时自动切换

#### 4. 反反爬措施 ✅
- **随机延迟**：每个请求之间随机 0.5-2s 延迟
- **UA 伪装**：4 个 User-Agent 轮换
- **Referer 设置**：模拟来自东方财富网站的请求
- **批量限制**：新浪行情单次最多 80 只股票

#### 5. 历史数据精简 ✅
- `get_stock_history()` 默认只取 30 天（参数 `days=30`）
- `get_stock_detail()` 日线从 `start_date="20250101"` 改为 `days=30`
- 大幅减少每次请求的数据量

#### 6. 新增缓存管理 API ✅
| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/cache/clear` | POST | 清理缓存（可指定前缀） |
| `/api/cache/stats` | GET | 查看缓存文件数和大小 |

### 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/services/data_fetcher.py` | 完全重写：DiskCache + SinaStockAPI + 多源回退 + 反反爬 |
| `backend/app/services/analyzer.py` | `get_stock_detail()` 改为默认 30 天 |
| `backend/app/routers/stocks.py` | 新增 `/api/cache/clear` 和 `/api/cache/stats` |
| `backend/requirements.txt` | 新增 `requests`、`numpy` |
