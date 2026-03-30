<template>
  <div class="boards">
    <div class="page-header">
      <h1>📂 板块排名</h1>
      <div class="header-actions">
        <div class="tab-bar">
          <button :class="['tab', { active: boardType === '概念板块' }]"
            @click="boardType = '概念板块'; loadData()">概念板块</button>
          <button :class="['tab', { active: boardType === '行业板块' }]"
            @click="boardType = '行业板块'; loadData()">行业板块</button>
        </div>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="boards.length === 0" class="empty">暂无数据</div>
      <table class="data-table" v-else>
        <thead>
          <tr>
            <th>排名</th>
            <th>板块名称</th>
            <th>涨跌幅</th>
            <th>领涨股</th>
            <th>换手率</th>
            <th>上涨家数</th>
            <th>下跌家数</th>
            <th>成交额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(b, i) in boards" :key="b['板块名称'] || i">
            <td>{{ i + 1 }}</td>
            <td>{{ b['板块名称'] }}</td>
            <td :class="Number(b['涨跌幅']) > 0 ? 'up' : 'down'">
              {{ formatPct(b['涨跌幅']) }}
            </td>
            <td>{{ b['领涨股票'] || '-' }}</td>
            <td>{{ formatPct(b['换手率']) }}</td>
            <td class="up">{{ b['上涨家数'] || 0 }}</td>
            <td class="down">{{ b['下跌家数'] || 0 }}</td>
            <td>{{ formatAmount(b['总成交额']) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'Boards',
  data() {
    return {
      boardType: '概念板块',
      boards: [],
      loading: false,
    }
  },
  mounted() {
    this.loadData()
  },
  methods: {
    async loadData() {
      this.loading = true
      try {
        const res = await api.getBoards(this.boardType)
        this.boards = res.data.data || []
      } catch (e) {
        console.error('加载失败:', e)
      }
      this.loading = false
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
}
.tab-bar {
  display: flex;
  gap: 8px;
}
.tab {
  padding: 8px 20px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 14px;
  transition: all 0.2s;
}
.tab.active {
  background: #ff6b6b;
  color: #fff;
  border-color: #ff6b6b;
}
</style>
