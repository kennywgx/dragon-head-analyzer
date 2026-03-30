<template>
  <div class="stock-detail">
    <div class="page-header">
      <h1>📈 个股详情 - {{ $route.params.code }}</h1>
      <button class="btn btn-primary" @click="loadData" :disabled="loading">
        {{ loading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>
    <template v-else>
      <!-- 分时K线 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">⏰ 5分钟K线（近48根）</span>
        </div>
        <div v-if="detail.minute_kline && detail.minute_kline.length" class="kline-list">
          <table class="data-table">
            <thead>
              <tr>
                <th>时间</th>
                <th>开盘</th>
                <th>收盘</th>
                <th>最高</th>
                <th>最低</th>
                <th>成交量</th>
                <th>成交额</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in detail.minute_kline.slice(-20)" :key="k['时间']">
                <td>{{ k['时间'] }}</td>
                <td>{{ k['开盘'] }}</td>
                <td :class="k['收盘'] >= k['开盘'] ? 'up' : 'down'">{{ k['收盘'] }}</td>
                <td>{{ k['最高'] }}</td>
                <td>{{ k['最低'] }}</td>
                <td>{{ formatVol(k['成交量']) }}</td>
                <td>{{ formatAmount(k['成交额']) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">暂无分时数据</div>
      </div>

      <!-- 日线 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">📅 日线（近60日）</span>
        </div>
        <div v-if="detail.daily_kline && detail.daily_kline.length" class="kline-list">
          <table class="data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>开盘</th>
                <th>收盘</th>
                <th>最高</th>
                <th>最低</th>
                <th>涨跌幅</th>
                <th>成交量</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="k in detail.daily_kline.slice(-20)" :key="k['日期']">
                <td>{{ k['日期'] }}</td>
                <td>{{ k['开盘'] }}</td>
                <td :class="k['收盘'] >= k['开盘'] ? 'up' : 'down'">{{ k['收盘'] }}</td>
                <td>{{ k['最高'] }}</td>
                <td>{{ k['最低'] }}</td>
                <td :class="Number(k['涨跌幅']) > 0 ? 'up' : 'down'">
                  {{ formatPct(k['涨跌幅']) }}
                </td>
                <td>{{ formatVol(k['成交量']) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">暂无日线数据</div>
      </div>

      <!-- 资金流向 -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">💰 资金流向（近5日）</span>
        </div>
        <div v-if="detail.fund_flow && detail.fund_flow.length">
          <table class="data-table">
            <thead>
              <tr>
                <th>日期</th>
                <th>主力净流入</th>
                <th>小单净流入</th>
                <th>中单净流入</th>
                <th>大单净流入</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="f in detail.fund_flow" :key="f['日期']">
                <td>{{ f['日期'] }}</td>
                <td :class="Number(f['主力净流入-净额']) > 0 ? 'up' : 'down'">
                  {{ formatAmount(f['主力净流入-净额']) }}
                </td>
                <td>{{ formatAmount(f['小单净流入-净额']) }}</td>
                <td>{{ formatAmount(f['中单净流入-净额']) }}</td>
                <td>{{ formatAmount(f['大单净流入-净额']) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-else class="empty">暂无资金流向数据</div>
      </div>
    </template>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'StockDetail',
  data() {
    return {
      detail: {},
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
        const code = this.$route.params.code
        const res = await api.getStockDetail(code)
        this.detail = res.data.data || {}
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
      if (Math.abs(v) >= 1e8) return (v / 1e8).toFixed(2) + '亿'
      if (Math.abs(v) >= 1e4) return (v / 1e4).toFixed(2) + '万'
      return v.toFixed(0)
    },
    formatVol(val) {
      if (val == null) return '-'
      const v = Number(val)
      if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿手'
      if (v >= 1e4) return (v / 1e4).toFixed(2) + '万手'
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
.kline-list {
  max-height: 400px;
  overflow-y: auto;
}
</style>
