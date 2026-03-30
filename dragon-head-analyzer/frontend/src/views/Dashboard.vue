<template>
  <div class="dashboard">
    <div class="page-header">
      <h1>🐉 龙头战法看板</h1>
      <button class="btn btn-primary" @click="runScan" :disabled="scanning">
        {{ scanning ? '扫描中...' : '🔍 手动扫描' }}
      </button>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="card stat-card">
        <div class="stat-number up">{{ scanData.zt_pool_count || 0 }}</div>
        <div class="stat-label">今日涨停</div>
      </div>
      <div class="card stat-card">
        <div class="stat-number" style="color: #fa8c16">{{ scanData.lb_pool_count || 0 }}</div>
        <div class="stat-label">连板股</div>
      </div>
      <div class="card stat-card">
        <div class="stat-number" style="color: #52c41a">{{ scanData.zr_pool_count || 0 }}</div>
        <div class="stat-label">今日炸板</div>
      </div>
      <div class="card stat-card">
        <div class="stat-number" style="color: #722ed1">{{ candidates.length }}</div>
        <div class="stat-label">龙头候选</div>
      </div>
    </div>

    <!-- 龙头候选 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">👑 龙头候选</span>
        <span class="stat-label" v-if="scanData.date">扫描时间: {{ scanData.date }}</span>
      </div>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="candidates.length === 0" class="empty">暂无龙头候选数据，点击「手动扫描」获取</div>
      <table class="data-table" v-else>
        <thead>
          <tr>
            <th>排名</th>
            <th>代码</th>
            <th>名称</th>
            <th>连板</th>
            <th>等级</th>
            <th>封板评分</th>
            <th>涨跌幅</th>
            <th>封单额</th>
            <th>成交额</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(c, i) in candidates" :key="c['代码']">
            <td>{{ i + 1 }}</td>
            <td>{{ c['代码'] }}</td>
            <td>
              <router-link :to="`/stock/${c['代码']}`" class="stock-link">
                {{ c['名称'] }}
              </router-link>
            </td>
            <td>
              <span class="tag tag-red">{{ c['连板数'] || '-' }}板</span>
            </td>
            <td>
              <span :class="levelClass(c.level)">{{ c.level || '-' }}</span>
            </td>
            <td>
              <span class="tag tag-purple">{{ c.seal_score }}</span>
            </td>
            <td :class="pctClass(c['涨跌幅'])">
              {{ formatPct(c['涨跌幅']) }}
            </td>
            <td>{{ formatAmount(c['封单额']) }}</td>
            <td>{{ formatAmount(c['成交额']) }}</td>
            <td>
              <router-link :to="`/stock/${c['代码']}`" class="stock-link">详情</router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 信号列表 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">📡 交易信号</span>
      </div>
      <div v-if="signals.length === 0" class="empty">暂无信号</div>
      <table class="data-table" v-else>
        <thead>
          <tr>
            <th>时间</th>
            <th>类型</th>
            <th>代码</th>
            <th>名称</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in signals" :key="s.code + s.type + s.time">
            <td>{{ s.time }}</td>
            <td>
              <span :class="signalTagClass(s.type)">{{ s.type }}</span>
            </td>
            <td>{{ s.code }}</td>
            <td>
              <router-link :to="`/stock/${s.code}`" class="stock-link">{{ s.name }}</router-link>
            </td>
            <td>{{ s.detail }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'Dashboard',
  data() {
    return {
      scanData: {},
      candidates: [],
      signals: [],
      loading: false,
      scanning: false,
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    async loadData() {
      this.loading = true
      try {
        const res = await api.scan()
        if (res.data.success) {
          this.scanData = res.data.data
          this.candidates = res.data.data.candidates || []
          this.signals = res.data.data.signals || []
        }
      } catch (e) {
        console.error('加载数据失败:', e)
      }
      this.loading = false
    },
    async runScan() {
      this.scanning = true
      try {
        const res = await api.triggerScan()
        if (res.data.success) {
          this.scanData = res.data.data
          this.candidates = res.data.data.candidates || []
          this.signals = res.data.data.signals || []
        }
      } catch (e) {
        console.error('扫描失败:', e)
      }
      this.scanning = false
    },
    formatPct(val) {
      if (val == null) return '-'
      return (val > 0 ? '+' : '') + Number(val).toFixed(2) + '%'
    },
    formatAmount(val) {
      if (val == null) return '-'
      const v = Number(val)
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
      if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
      return v.toFixed(0)
    },
    pctClass(val) {
      if (val == null) return ''
      return val > 0 ? 'up' : val < 0 ? 'down' : ''
    },
    levelClass(level) {
      const map = {
        '妖王': 'level-yw',
        '总龙头': 'level-zlt',
        '分支龙头': 'level-fzl',
        '跟风龙头': 'level-gfl',
      }
      return map[level] || ''
    },
    signalTagClass(type) {
      const map = {
        '龙头确认': 'tag tag-red',
        '高位连板': 'tag tag-orange',
        '断板预警': 'tag tag-green',
      }
      return map[type] || 'tag tag-blue'
    },
  },
}
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
.page-header h1 {
  font-size: 24px;
  color: #1a1a2e;
}
.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.stat-card {
  text-align: center;
  padding: 24px;
}
</style>
