# 龙头战法分析系统 — 架构设计文档

> 版本: v0.3.0 | 更新: 2026-04-01

---

## 1. 项目定位

A 股短线「龙头战法」辅助分析系统。**纯规则驱动，不做预判，不提示风险**，机械执行预设规则：
- 从市场数据中识别涨停/连板/炸板股票
- 按规则筛选龙头候选、评级、生成入场/离场信号
- 通过 Web 看板展示分析结果

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户浏览器                                │
│                    Vue 3 SPA (Port 3000)                         │
└──────────────────────┬───────────────────────────────────────────┘
                       │ HTTP (REST API)
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Nginx / Vite Dev Server                        │
│              /api/* → proxy → http://localhost:8000              │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                   FastAPI Backend (Port 8000)                     │
│                                                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────────┐    │
│  │   Routers   │→ │   Analyzer   │→ │   DataFetcher        │    │
│  │  (API层)    │  │  (规则引擎)  │  │  (数据获取+缓存)     │    │
│  └─────────────┘  └──────────────┘  └──────────┬───────────┘    │
│        │                                         │                │
│        ▼                                         ▼                │
│  ┌─────────────┐                      ┌──────────────────┐       │
│  │   Logger    │                      │  External APIs   │       │
│  │  (日志服务) │                      │  akshare/efinance│       │
│  └─────────────┘                      │  /sina           │       │
│                                       └──────────────────┘       │
│  ┌─────────────┐                      ┌──────────────────┐       │
│  │  Scheduler  │                      │   DiskCache      │       │
│  │  (定时调度) │                      │  (JSON文件缓存)  │       │
│  └─────────────┘                      └──────────────────┘       │
└──────────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| 前端 | Vue 3 + Vite + Vue Router | SPA 单页应用，纯 SVG K 线图 |
| 后端 | FastAPI + Uvicorn | 异步 REST API |
| 数据源 | AKShare + efinance + 新浪 | 分层回退架构 |
| 调度 | APScheduler | 定时收盘扫描 |
| 缓存 | JSON 文件 (DiskCache) | 30 天自动清理 |
| 部署 | Docker + Nginx | 容器化一键部署 |

---

## 3. 目录结构

```
dragon-head-analyzer/
├── backend/                          # Python 后端
│   ├── Dockerfile                    # 容器构建
│   ├── requirements.txt              # Python 依赖
│   ├── logs/                         # 分析日志 (按日期)
│   │   └── 2026-03-31.log
│   ├── data_cache/                   # JSON 磁盘缓存 (运行时生成)
│   └── app/
│       ├── main.py                   # FastAPI 入口 + CORS + 日志配置
│       ├── core/
│       │   ├── config.py             # 规则参数 + 路径 + 调度配置
│       │   └── scheduler.py          # APScheduler 定时任务注册
│       ├── models/
│       │   └── schemas.py            # Pydantic 数据模型
│       ├── routers/
│       │   └── stocks.py             # API 路由 (所有 /api/* 端点)
│       └── services/
│           ├── data_fetcher.py       # 数据获取 (多源回退 + 缓存)
│           ├── analyzer.py           # 规则引擎 (11 步分析流水线)
│           ├── task_manager.py       # 任务管理 (8个内置任务 + 执行引擎)
│           └── logger.py             # 日志服务 (文件 + logging)
│
├── frontend/                         # Vue 3 前端
│   ├── Dockerfile                    # 容器构建 (Node + Nginx)
│   ├── nginx.conf                    # Nginx 配置 (SPA + API proxy)
│   ├── package.json                  # 依赖: vue, vue-router, axios
│   ├── vite.config.js                # Vite 配置 + dev proxy
│   ├── index.html                    # 入口 HTML
│   └── src/
│       ├── main.js                   # Vue app 初始化
│       ├── style.css                 # 全局样式 (卡片/表格/标签)
│       ├── App.vue                   # 根组件 (侧边栏导航)
│       ├── api/
│       │   └── index.js              # Axios 封装 + 拦截器
│       ├── router/
│       │   └── index.js              # 路由配置 (6 个页面)
│       ├── components/
│       │   ├── KlineChart.vue        # SVG 蜡烛图组件
│       │   └── HelloWorld.vue        # 占位组件 (未使用)
│       └── views/
│           ├── Dashboard.vue         # 主看板 (候选/信号/仓位)
│           ├── ZtPool.vue            # 涨停池/连板池/炸板池
│           ├── StockDetail.vue       # 个股详情 (K线+资金流)
│           ├── Boards.vue            # 板块排名
│           ├── Tasks.vue             # 任务中心 (调度+规则监听)
│           └── Logs.vue              # 分析日志查看
│
├── docker-compose.yml                # 一键编排
├── start-backend.sh / .bat           # 启动脚本
├── start-frontend.sh / .bat
├── start-all.bat / stop-all.bat
├── README.md                         # 用户文档
├── ARCHITECTURE.md                   # ← 本文档
└── LOGS.md                           # 开发日志
```

---

## 4. 模块设计

### 4.1 后端模块

#### `core/config.py` — 配置中心

所有规则参数集中管理，分为 7 组：

| 配置组 | 关键参数 | 说明 |
|---|---|---|
| 候选筛选 | `min_lianban_count=2` | 连板门槛 |
| 板块共振 | `min_board_follow_count`, `board_resonance_bonus` | 板块加分条件 |
| 封板评分 | `seal_order_ratio_threshold` (三级) | 封单额/流通市值 |
| 缩量板 | `shrink_volume_ratio=0.8` | 量比阈值 |
| 弱转强/分歧 | `weak_turn_strong_pct`, `consensus_turn_pct` | 形态判定阈值 |
| 卡位 | `compete_slot_*` | 同级竞争条件 |
| 离场 | `exit_*` | 断板/长阴/退潮 |
| 仓位 | `position_base/max/per_level` | 仓位管理 |
| K线形态 | `yi_zi_board_open_ratio`, `t_board_lower_shadow_pct` | 一字板/T字板 |
| 调度 | `close_analysis_hour/minute` | 收盘扫描时间 |

#### `core/scheduler.py` — 定时调度

```
APScheduler (BackgroundScheduler)
  └── job: close_analysis
       ├── trigger: CronTrigger (周一至周五 15:10)
       └── action: analyzer.scan_all() → logger.log_signal()
```

#### `services/data_fetcher.py` — 数据获取层

核心类：

```
DiskCache                          # JSON 文件缓存
  ├── get(key, ttl) → data|None    # 未过期返回
  ├── get_stale(key) → data|None   # 忽略 TTL (降级用)
  ├── set(key, data)               # 写入
  └── cleanup()                    # 清理 >30天 文件

SinaAPI                            # 新浪财经 HTTP 接口 (备用源)
  ├── get_realtime(codes)          # 实时行情
  └── get_kline(code, scale, len)  # K线

DataFetcher                        # 主数据获取器
  ├── get_zt_pool(date)            # 涨停池 [核心: EM only]
  ├── get_lb_pool(date)            # 连板池 [从涨停池筛选]
  ├── get_zr_pool(date)            # 炸板池 [核心: EM only]
  ├── get_realtime_quotes()        # 实时行情 [多源: EF→Sina]
  ├── get_minute_kline(code)       # 分钟K线 [多源: EM→Sina]
  ├── get_stock_history(code)      # 日线 [多源: EM→Sina]
  ├── get_board_list(type)         # 板块排名 [核心: EM only]
  ├── get_board_stocks(name)       # 板块成分股 [核心: EM only]
  ├── get_fund_flow_individual()   # 资金流向 [核心: EM only]
  ├── get_lhb_data(date)           # 龙虎榜 [核心: EM only]
  └── clear_cache(prefix)          # 缓存清理
```

#### `services/analyzer.py` — 规则引擎

`DragonHeadAnalyzer` 类，核心方法 `scan_all()` 执行 11 步流水线（见第 6 章流程图）：

| 步骤 | 方法 | 职责 |
|---|---|---|
| Step 1-3 | 内联 | 获取涨停池/连板池/炸板池 |
| Step 4 | `_fetch_board_data()` | 获取板块排名 |
| Step 5 | `_identify_candidates()` | 龙头候选识别 + 封板评分 + 板块共振 |
| Step 6 | `_detect_pattern_shifts()` | 弱转强 / 分歧转一致 |
| Step 7 | `_detect_compete_slots()` | 卡位判断 |
| Step 8 | `_detect_kline_patterns()` | K线形态（一字板/T字板） |
| Step 9 | `_generate_signals()` | 生成入场信号 |
| Step 10 | `_generate_exit_signals()` | 生成离场信号 |
| Step 11 | `_generate_position_suggestions()` | 仓位管理建议 |

#### `routers/stocks.py` — API 路由

所有端点统一格式 `{ success: bool, data: ... }`，统一 `try/except` 错误处理。

#### `services/logger.py` — 日志服务

双写：文件日志 (`logs/{date}.log`) + Python logging 模块。

---

### 4.2 前端模块

```
App.vue (根组件)
  ├── <nav class="sidebar">         # 固定侧边栏导航
  │   ├── 看板 (/)
  │   ├── 涨停池 (/zt-pool)
  │   ├── 板块 (/boards)
  │   └── 日志 (/logs)
  └── <router-view />               # 页面切换

路由表:
  /              → Dashboard.vue    # 主看板
  /zt-pool       → ZtPool.vue       # 涨停/连板/炸板池 (Tab切换)
  /stock/:code   → StockDetail.vue  # 个股详情
  /boards        → Boards.vue       # 板块排名
  /logs          → Logs.vue         # 日志查看

组件:
  KlineChart.vue                     # 纯 SVG 蜡烛图
  ├── 网格线 + K线实体 + 影线 + 成交量柱
  ├── 十字线追踪 (mousemove)
  └── 悬浮 OHLCV tooltip
```

---

## 4.3 任务系统 (`services/task_manager.py`)

任务系统分两大类，共 8 个内置任务：

### 调度类任务 (scheduled)

| 任务 ID | 名称 | 调度 | 说明 |
|---|---|---|---|
| `pre_market_scan` | 盘前集合竞价扫描 | 周一至周五 09:15 | 检测首板异动、高开信号 |
| `close_scan` | 收盘全量扫描 | 周一至周五 15:10 | 涨停池+龙头识别+信号+日志 |
| `weekend_review` | 周末复盘汇总 | 周六 10:00 | 本周信号统计 |

### 规则监听类任务 (rule_monitor)

| 任务 ID | 规则类型 | 调度 | 核心逻辑 |
|---|---|---|---|
| `emotion_monitor` | 情绪周期 | 每30分钟 | 涨停家数/晋级率/炸板率 → 冰点/退潮/修复/发酵/高潮 |
| `yijiner_scanner` | 一进二 | 09:25 | 首板→二板候选，排除烂板/左压，5-20亿成交额 |
| `seal_strength_monitor` | 封单强度 | 每15分钟 | 封单量:成交量比值，>5:1强势，<2:1预警 |
| `sector_resonance_monitor` | 板块共振 | 10/11/13/14点 | 板块涨幅前20%且≥2% |
| `breaking_board_alert` | 炸板预警 | 每5分钟 | 连板≥3标的不在涨停池 → 预警 |

### 情绪周期算法

```
基础分 50 分
  + 涨停家数评分 (-30 ~ +40)
      <20家: -30 (冰点)  |  20-30: -10  |  30-50: +15  |  50-80: +30  |  >80: +40
  + 晋级率评分 (-15 ~ +15)
      <10%: -15 (弱势)   |  >30%: +15 (强势)
  + 炸板率评分 (-15 ~ 0)
      >40%: -15 (退潮)   |  >25%: -5
  + 最高连板评分 (0 ~ +10)
      ≥7板: +10          |  ≥5板: +5

总分 0-100，阶段判定：
  冰点: 涨停<20家
  退潮: 炸板率>40%
  高潮: 得分≥75
  发酵: 得分≥55
  修复: 得分<55
```

### 一进二筛选规则（参考市场验证的高胜率策略）

```
输入：昨日涨停池中连板数=1 的首板股
过滤：
  ✗ 排除烂板: 封单额/流通市值 < 0.2%
  ✗ 排除过大/过小: 成交额不在 5-20 亿区间
  ✗ 排除市值极端: 流通市值不在 50-500 亿区间
通过：
  ✓ 集合竞价高开 1%-6%
  ✓ 封单额/流通市值 ≥ 0.5% (中封以上)
评分 = 10(首板基础) + 封单分(15/8/0) + 涨停分(10)
```

### 任务执行与存储

```
TaskManager
  ├── list_tasks()              # 列出所有任务
  ├── enable_task(id, bool)     # 启用/禁用
  ├── update_task_params(id)    # 更新规则参数
  ├── execute_task(id)          # 手动执行 → TaskResult
  ├── get_recent_results()      # 最近执行结果 (内存)
  └── get_results_by_date()     # 历史结果 (文件)

存储: task_results/{YYYY-MM-DD}.jsonl (JSON Lines)
每行一个 TaskResult:
  { task_id, name, executed_at, status, summary, data, alerts }
```

### API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tasks` | 列出所有任务 (分 scheduled/monitors) |
| GET | `/api/tasks/{task_id}` | 任务详情 |
| POST | `/api/tasks/{task_id}/execute` | 手动执行 |
| PUT | `/api/tasks/{task_id}/enable?enabled=true` | 启用/禁用 |
| PUT | `/api/tasks/{task_id}/params` | 更新规则参数 |
| GET | `/api/tasks/results/recent?limit=50&task_id=` | 最近结果 |
| GET | `/api/tasks/results/dates` | 有记录的日期 |
| GET | `/api/tasks/results/{date}` | 指定日期结果 |

---

## 5. 数据模型

### 5.1 Pydantic 模型 (`models/schemas.py`)

```python
StockCandidate     # 龙头候选
  ├── code, name, lianban, level
  ├── seal_score, pct_chg, seal_amount, circ_mv
  ├── board_bonus
  ├── patterns: [PatternShift]       # 弱转强/分歧转一致
  ├── compete_slot: CompeteSlot      # 卡位信息
  └── kline_patterns: [KlinePattern] # 一字板/T字板

TradeSignal        # 入场信号
  ├── time, code, name, type, detail
  ├── lianban, level, score
  └── severity

ExitSignal         # 离场信号
  ├── time, code, name, type, detail
  └── severity (high/medium)

PositionSuggestion # 仓位建议
  ├── code, name, level, lianban
  ├── suggested_position (百分比)
  └── reason

ScanResult         # 扫描结果 (顶层)
  ├── date, zt_pool_count, lb_pool_count, zr_pool_count
  ├── candidates: [StockCandidate]
  ├── signals: [TradeSignal]
  ├── exit_signals: [ExitSignal]
  └── position_suggestions: [PositionSuggestion]
```

### 5.2 API 响应格式

```json
// 成功
{ "success": true, "data": { ... } }

// 错误 (FastAPI HTTPException)
{ "detail": "错误信息" }
```

---

## 6. 核心流程图

### 6.1 全量扫描流程 (`scan_all`)

```
                    ┌─────────────┐
                    │  触发扫描   │
                    │ GET /scan   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ Step 1-3:   │
                    │ 获取三池数据 │
                    │ zt/lb/zr    │
                    └──────┬──────┘
                           │
              ┌─ 空? ──────┤
              │            │ 非空
              ▼            ▼
         返回空结果   ┌──────────────┐
                     │ Step 4:      │
                     │ 获取板块数据  │
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │ Step 5:      │
                     │ 龙头候选识别  │  遍历涨停池
                     │ 封板评分      │  连板≥2 → 候选
                     │ 板块共振加分  │  seal_score = 连板×10 + 封单分 + 涨幅分 + 板块分
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │ Step 6:      │
                     │ 弱转强/分歧   │  逐只获取历史K线
                     │ 转一致判定    │  前日涨幅<3% + 今日涨停 → 弱转强(+15分)
                     └──────┬───────┘                            前日振幅>5% + 今日涨停 → 分歧转一致(+12分)
                            │
                     ┌──────▼───────┐
                     │ Step 7:      │
                     │ 卡位判断      │  同连板数≥2只竞争
                     │              │  涨幅领先≥3% → 卡位成功
                     └──────┬───────┘
                            │
                     ┌──────▼───────┐
                     │ Step 8:      │
                     │ K线形态识别   │  一字板: 开≈收 + 涨停
                     │              │  T字板: 下影线>2% + 涨停
                     └──────┬───────┘
                            │
                ┌───────────┼───────────┐
                ▼           ▼           ▼
        ┌──────────┐ ┌───────────┐ ┌──────────┐
        │ Step 9:  │ │ Step 10:  │ │ Step 11: │
        │ 入场信号 │ │ 离场信号  │ │ 仓位建议 │
        └────┬─────┘ └─────┬─────┘ └────┬─────┘
             │             │            │
             └──────┬──────┘            │
                    │◄──────────────────┘
                    ▼
             ┌─────────────┐
             │ 返回 ScanResult │
             └─────────────┘
```

### 6.2 数据获取流程 (`DataFetcher`)

```
请求数据
  │
  ├─ 1. 检查内存/磁盘缓存 (TTL 未过期) ──→ 命中 → 返回
  │
  ├─ 2. 随机延迟 0.5~2s (反反爬)
  │
  ├─ 3. 调用主数据源 (akshare/efinance)
  │     │
  │     ├─ 成功 → 写缓存 → 返回
  │     │
  │     └─ 失败 ─┬─ [核心数据] → 返回过期缓存 (stale) → 仍无 → 返回空
  │              │
  │              └─ [通用数据] → 尝试备用源 (Sina)
  │                              │
  │                              ├─ 成功 → 写缓存 → 返回
  │                              └─ 失败 → 返回空 DataFrame
  │
  └─ 4. 30天自动清理过期缓存文件
```

### 6.3 龙头评级流程

```
涨停池股票
  │
  ├─ 连板数 < 2 → 跳过
  │
  └─ 连板数 ≥ 2 → 进入候选池
      │
      ├─ 计算封板评分:
      │   score = 连板数 × 10
      │          + 封单额占比分 (≥1%:15 / ≥0.5%:8 / ≥0.2%:3)
      │          + 涨幅分 (≥9.9%:10 / ≥5%:5)
      │          + 板块共振分 (+10, 前20%板块且涨幅≥2%)
      │          + 弱转强分 (+15, 可选)
      │          + 分歧转一致分 (+12, 可选)
      │
      └─ 评级:
          连板≥7 → 🩸 妖王
          连板5-6 → 👑 总龙头
          连板3-4 → 🔥 分支龙头
          连板2   → ⚡ 跟风龙头
```

### 6.4 离场信号判定

```
对每只候选股:
  │
  ├─ 断板检测:  前日在连板池 + 今日不在涨停池 → 断板预警
  │             (连板≥5 标记 high)
  │
  ├─ 放量长阴:  今日跌幅>7% AND 量比>1.8倍 → 放量长阴 (high)
  │
  └─ 板块退潮:  炸板数 ≥ 涨停数×50% → 板块退潮 (high)
```

### 6.5 仓位管理

```
根据等级分配基础仓位:
  妖王(7板+)   → 70%
  总龙头(5-6板) → 50%
  分支龙头(3-4) → 40%
  跟风(2板)     → 30%

信号加成:
  有弱转强/分歧转一致 → +10%

约束:
  单票最大仓位 ≤ 70%
```

---

## 7. 外部接口管理

### 7.1 SourceRegistry 自适应多源架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     SourceRegistry                               │
│                                                                  │
│  每类数据 → [Source₁, Source₂, Source₃, ...]                   │
│  每个 Source 持有:                                               │
│    · name         源名称                                        │
│    · fetch_fn     获取函数                                      │
│    · priority     基础优先级 (1-100)                            │
│    · health       健康分 (0-100, 动态)                          │
│    · consecutive_failures  连续失败计数                         │
│                                                                  │
│  有效优先级 = priority × (health / 100)                         │
│  按有效优先级排序，可用源优先尝试                                │
├─────────────────────────────────────────────────────────────────┤
│  故障转移规则:                                                   │
│    失败:   health -= 30                                         │
│    成功:   health += 10, consecutive_failures = 0               │
│    连续失败 ≥ 3次:                                              │
│      → priority *= 0.5 (降级)                                   │
│      → cooldown 5分钟 (暂不可用)                                │
│      → 同组其他源自动受益                                       │
│    定时恢复: 每10分钟 health += 5 (不超过100)                   │
├─────────────────────────────────────────────────────────────────┤
│  核心数据降级: 失败 → 过期缓存 (stale cache)                    │
│  通用数据降级: 源1失败 → 源2 → 源3 → 空                        │
└─────────────────────────────────────────────────────────────────┘
```

### 7.2 数据源对照表

| 数据类型 | 源1 (优先级100) | 源2 (优先级50) | 源3 (优先级25) | 降级策略 |
|---|---|---|---|---|
| 涨停池 | `ak.stock_zt_pool_em` | - | - | 过期缓存 |
| 炸板池 | `ak.stock_zt_pool_zbgc_em` | - | - | 过期缓存 |
| 连板池 | 从涨停池筛选 | - | - | 依赖涨停池 |
| 实时行情 | `ef.stock.get_realtime_quotes` | - | - | 返回空 |
| 分钟K线 | `ak.stock_zh_a_hist_min_em` | `SinaAPI.get_kline` | `TencentAPI.get_minute_kline` | 返回空 |
| 日线K线 | `ak.stock_zh_a_hist` | `SinaAPI.get_kline` | `TencentAPI.get_kline` | 返回空 |
| 板块排名 | `ak.stock_board_concept_name_em` | - | - | 过期缓存 |
| 板块成分 | `ak.stock_board_concept_cons_em` | - | - | 返回空 |
| 资金流向 | `ak.stock_individual_fund_flow` | - | - | 返回空 |
| 龙虎榜 | `ak.stock_lhb_detail_em` | - | - | 过期缓存 |

### 7.3 反反爬策略

```
每次外部请求前:
  1. 随机延迟: time.sleep(random.uniform(0.5, 2.0))
  2. UA 轮换: 4 个主流浏览器 UA 随机选择
  3. 请求头: Accept / Accept-Language 伪装
```

### 7.4 缓存 Key 设计

```
key 格式                    → 说明
─────────────────────────────────────────
zt_pool_{YYYYMMDD}         → 涨停池 (日粒度)
zr_pool_{YYYYMMDD}         → 炸板池 (日粒度)
realtime_quotes            → 实时行情 (10s TTL)
min_kline_{code}_{period}  → 分钟K线 (1h TTL)
hist_{code}_daily_{start}_{end} → 日线 (24h TTL)
board_{板块类型}           → 板块排名 (120s TTL)
board_cons_{板块名}        → 板块成分 (300s TTL)
fund_flow_{code}           → 资金流向 (300s TTL)
lhb_{YYYYMMDD}             → 龙虎榜 (24h TTL)
```

### 7.5 数据源管理 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/sources/status` | 所有数据源健康面板 (优先级/健康分/成功率) |
| POST | `/api/sources/reset?data_type=` | 手动重置数据源优先级 |

---

## 8. API 接口清单

| 方法 | 路径 | 说明 | 请求参数 |
|---|---|---|---|
| GET | `/` | 根路径，返回状态 | - |
| GET | `/api/health` | 健康检查 | - |
| GET | `/api/scan` | 全量扫描 | - |
| POST | `/api/scan/trigger` | 手动触发扫描 (写日志) | - |
| GET | `/api/zt-pool` | 涨停股池 | `?date=YYYYMMDD` |
| GET | `/api/lb-pool` | 连板股池 | `?date=YYYYMMDD` |
| GET | `/api/zr-pool` | 炸板股池 | `?date=YYYYMMDD` |
| GET | `/api/realtime` | 全市场实时行情 (≤200条) | - |
| GET | `/api/stock/{code}` | 个股详情 (分时+日线+资金流) | path: stock code |
| GET | `/api/boards` | 板块排名 (≤50条) | `?board_type=概念板块\|行业板块` |
| GET | `/api/logs` | 分析日志 | `?date=YYYY-MM-DD` |
| POST | `/api/cache/clear` | 清理缓存 | `?prefix=` |
| GET | `/api/cache/stats` | 缓存统计 | - |
| GET | `/api/tasks` | 任务列表 (scheduled/monitors) | - |
| GET | `/api/tasks/{task_id}` | 任务详情 | path: task_id |
| POST | `/api/tasks/{task_id}/execute` | 手动执行任务 | path: task_id |
| PUT | `/api/tasks/{task_id}/enable` | 启用/禁用 | `?enabled=true\|false` |
| PUT | `/api/tasks/{task_id}/params` | 更新规则参数 | body: JSON |
| GET | `/api/tasks/results/recent` | 最近执行结果 | `?limit=50&task_id=` |
| GET | `/api/tasks/results/dates` | 有记录的日期 | - |
| GET | `/api/tasks/results/{date}` | 指定日期结果 | path: date |
| GET | `/api/sources/status` | 数据源健康面板 | - |
| POST | `/api/sources/reset` | 重置数据源优先级 | `?data_type=` |

---

## 9. 持久化设计

### 9.1 无数据库架构

本系统**不使用数据库**，所有持久化基于文件系统：

```
backend/
├── logs/                              # 分析日志
│   ├── 2026-03-31.log                 # 按日期，纯文本追加
│   ├── 2026-04-01.log
│   └── app.log                        # 系统运行日志
│
└── data_cache/                        # JSON 缓存 (运行时生成)
    ├── a1b2c3d4e5f6.json              # MD5(key).json
    ├── f7e8d9c0b1a2.json
    └── ...
```

### 9.2 缓存文件格式

```json
{
  "key": "zt_pool_20260401",
  "timestamp": 1712016000.123,
  "data": [
    { "代码": "603538", "名称": "美诺华", "连板数": 5, ... },
    ...
  ]
}
```

### 9.3 日志文件格式

```
[2026-03-31 15:10:01] [定时任务] 开始盘后扫描
[2026-03-31 15:10:03] 涨停池共 62 只
[2026-03-31 15:10:03] 连板池共 12 只
[2026-03-31 15:10:04] 炸板池共 17 只
[2026-03-31 15:10:08] 龙头候选 12 只
[2026-03-31 15:10:15] SIGNAL | 龙头确认 | 603538 美诺华 | 5连板 | 总龙头 | 评分: 60
[2026-03-31 15:10:15] 扫描完成：候选 12 只，信号 13 条
```

---

## 10. 前端页面交互

### 10.1 页面数据流

```
Dashboard (/)
  ├── mounted → GET /api/scan → 渲染: 统计卡片 + 候选表 + 入场信号 + 离场信号 + 仓位建议
  ├── 点击「手动扫描」→ POST /api/scan/trigger → 刷新全部数据
  ├── 每 5 分钟自动刷新
  └── 点击候选名称 → /stock/:code

ZtPool (/zt-pool)
  ├── mounted → GET /api/zt-pool + /lb-pool + /zr-pool (并行)
  ├── Tab 切换: 涨停/连板/炸板
  ├── 日期选择器 → 按日期查询历史
  └── 点击名称 → /stock/:code

StockDetail (/stock/:code)
  ├── mounted → GET /api/stock/:code
  ├── 渲染: 日线K线图 + 5分钟K线图 + 分时数据表 + 日线数据表 + 资金流向表
  └── KlineChart 组件: SVG 蜡烛图 + 十字线追踪

Boards (/boards)
  ├── mounted → GET /api/boards
  └── Tab 切换: 概念板块/行业板块

Logs (/logs)
  ├── mounted → GET /api/logs
  └── 日期下拉 → 按日期查看历史日志
```

### 10.2 前端状态管理

无 Vuex/Pinia，每个组件自行管理状态。数据流：

```
API 调用 → axios response → 组件 data → 模板渲染
```

---

## 11. 部署架构

### 11.1 开发模式

```
终端1: cd backend && uvicorn app.main:app --reload --port 8000
终端2: cd frontend && npm run dev (Vite, port 3000)
Vite proxy: /api/* → http://localhost:8000
```

### 11.2 生产模式 (Docker)

```
docker-compose up -d

┌─────────────────────────────┐
│  frontend (Nginx, :3000)    │
│  ├── 静态文件: /usr/share/  │
│  └── proxy: /api/* → :8000  │
├─────────────────────────────┤
│  backend (Uvicorn, :8000)   │
│  └── volumes: logs/ + cache/ │
└─────────────────────────────┘
```

---

## 12. 配额与限制

| 项目 | 限制 | 说明 |
|---|---|---|
| 缓存 TTL (交易时段) | 60s | 9:00-16:00 |
| 缓存 TTL (盘后) | 300s | 非交易时段 |
| 缓存 TTL (周末) | 86400s | 周六日 |
| 缓存最大寿命 | 30 天 | 自动清理 |
| 实时行情返回上限 | 200 条 | `[:200]` |
| 板块排名返回上限 | 50 条 | `.head(50)` |
| 外部请求重试 | 3 次 | 指数退避 |
| 请求间延迟 | 0.5~2s | 随机，反反爬 |
| API 超时 (前端) | 30s | axios timeout |
| 定时扫描 | 周一至周五 15:10 | APScheduler Cron |
| 前端自动刷新 | 5 分钟 | Dashboard |
| 分钟K线缓存 | 1 小时 | TTL=3600s |
| 日线缓存 | 24 小时 | TTL=86400s |

---

## 13. 待完善 (Roadmap)

### 已完成 ✅

- [x] 任务中心 — 8 个内置任务（3 调度 + 5 规则监听）
- [x] 情绪周期监控 — 冰点/退潮/修复/发酵/高潮
- [x] 一进二候选筛选 — 参考高胜率量化策略
- [x] 封单强度/板块共振/炸板预警监控
- [x] Docker 部署支持

### 待开发 🔲

- [ ] 历史回测功能（用历史日期数据验证规则准确率）
- [ ] 更多 K 线形态（锤子线、吞没形态等）
- [ ] 单元测试（analyzer + task_manager 测试覆盖）
- [ ] 信号触发时精确的价格/时间记录
- [ ] 微信/企微推送通知（任务告警推送）
- [ ] 前端状态管理升级（Pinia）
- [ ] 数据库存储（如需历史数据长期查询）
- [ ] 集合竞价量能分析（竞价成交量 vs 昨日总量 5%-20%）
- [ ] 量化反制策略（识别量化操盘模式，调整打板时机）
