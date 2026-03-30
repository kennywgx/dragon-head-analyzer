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

### 定时任务

- 周一至周五 15:10 自动收盘扫描
- 结果写入 `backend/logs/{date}.log`

### 踩坑记录

1. **akshare API 变更：** `stock_zt_pool_lbg_em`（连板池）在新版不存在，改为从涨停池中筛选连板数 > 1
2. **Windows 中文乱码：** CMD 默认 GBK 编码，bat 脚本加 `chcp 65001 >nul` 切 UTF-8 代码页
3. **pip PEP 668：** 系统 Python 需要 `--break-system-packages` 或用 venv

### 待完善

- [ ] 板块共振规则细化（同板块跟涨几只？）
- [ ] 封单额/流通市值精确阈值调整
- [ ] 弱转强 / 分歧转一致判定逻辑
- [ ] 卡位介入规则
- [ ] 离场信号完善（断板 / 放量长阴 / 板块退潮）
- [ ] 仓位管理规则
- [ ] 微信机器人推送
- [ ] K 线图表可视化（当前仅表格）
