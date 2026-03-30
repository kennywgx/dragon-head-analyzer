# 🐉 龙头战法分析系统

A股短线龙头识别与信号分析系统，纯规则驱动，不做预判。

## 架构

```
dragon-head-analyzer/
├── backend/                 # Python FastAPI 后端
│   ├── app/
│   │   ├── core/           # 配置 + 定时调度
│   │   ├── models/         # Pydantic 数据模型
│   │   ├── routers/        # API 路由
│   │   └── services/       # 数据获取 + 分析引擎 + 日志
│   └── logs/               # 分析日志 (按日期)
├── frontend/                # Vue 3 网页看板
│   └── src/
│       ├── api/            # API 封装
│       ├── views/          # 页面组件
│       └── router/         # 路由配置
└── start-backend.sh
└── start-frontend.sh
```

## 快速启动

### 1. 启动后端
```bash
cd dragon-head-analyzer/backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 启动前端
```bash
cd dragon-head-analyzer/frontend
npm install
npm run dev
```

访问 http://localhost:3000

### 一键启动
```bash
./start-backend.sh   # 终端1
./start-frontend.sh  # 终端2
```

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/scan` | GET | 全量扫描：涨停池 + 龙头识别 + 信号 |
| `/api/scan/trigger` | POST | 手动触发扫描（写日志） |
| `/api/zt-pool` | GET | 涨停股池 |
| `/api/lb-pool` | GET | 连板股池 |
| `/api/zr-pool` | GET | 炸板股池 |
| `/api/realtime` | GET | 全市场实时行情快照 |
| `/api/stock/{code}` | GET | 个股详情（分时+日线+资金流） |
| `/api/boards` | GET | 板块排名 |
| `/api/logs` | GET | 分析日志 |

## 龙头识别规则

1. **连板高度** ≥ 2板 进入候选池
2. **封板评分** = 连板数×10 + 封单额占比分 + 涨幅分
3. **等级划分**：
   - 🩸 妖王：7板+
   - 👑 总龙头：5-6板
   - 🔥 分支龙头：3-4板
   - ⚡ 跟风龙头：2板

## 定时任务

- 周一至周五 15:10 自动收盘扫描
- 结果写入 `logs/{date}.log`

## 数据源

- **AKShare**（主力）：涨停池、连板池、炸板池、板块、龙虎榜、分时、资金流
- **efinance**（补充）：实时行情快照
