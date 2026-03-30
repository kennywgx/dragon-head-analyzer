<template>
  <div class="zt-pool">
    <div class="page-header">
      <h1>🔥 涨停股池</h1>
      <div class="header-actions">
        <input type="date" v-model="dateStr" @change="loadData" class="date-input" />
        <button class="btn btn-primary" @click="loadData" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="tab-bar">
      <button :class="['tab', { active: tab === 'zt' }]" @click="tab = 'zt'; loadData()">
        涨停 ({{ ztData.length }})
      </button>
      <button :class="['tab', { active: tab === 'lb' }]" @click="tab = 'lb'; loadData()">
        连板 ({{ lbData.length }})
      </button>
      <button :class="['tab', { active: tab === 'zr' }]" @click="tab = 'zr'; loadData()">
        炸板 ({{ zrData.length }})
      </button>
    </div>

    <div class="card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="currentData.length === 0" class="empty">暂无数据</div>
      <table class="data-table" v-else>
        <thead>
          <tr>
            <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in currentData" :key="row['代码']">
            <td v-for="col in columns" :key="col.key">
              <template v-if="col.key === '名称'">
                <router-link :to="`/stock/${row['代码']}`" class="stock-link">
                  {{ row[col.key] }}
                </router-link>
              </template>
              <template v-else-if="col.key === '涨跌幅'">
                <span :class="Number(row[col.key]) > 0 ? 'up' : Number(row[col.key]) < 0 ? 'down' : ''">
                  {{ formatPct(row[col.key]) }}
                </span>
              </template>
              <template v-else-if="col.key === '连板数'">
                <span class="tag tag-red" v-if="row[col.key]">{{ row[col.key] }}板</span>
                <span v-else>-</span>
              </template>
              <template v-else>
                {{ formatCell(row[col.key], col.key) }}
              </template>
            </td>
            <td>
              <router-link :to="`/stock/${row['代码']}`" class="stock-link">详情</router-link>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'ZtPool',
  data() {
    return {
      tab: 'zt',
      dateStr: '',
      ztData: [],
      lbData: [],
      zrData: [],
      loading: false,
    }
  },
  computed: {
    currentData() {
      if (this.tab === 'zt') return this.ztData
      if (this.tab === 'lb') return this.lbData
      return this.zrData
    },
    columns() {
      const base = [
        { key: '代码', label: '代码' },
        { key: '名称', label: '名称' },
        { key: '涨跌幅', label: '涨跌幅' },
        { key: '成交额', label: '成交额' },
      ]
      if (this.tab === 'zt') {
        return [
          ...base.slice(0, 3),
          { key: '连板数', label: '连板' },
          ...base.slice(3),
          { key: '封单额', label: '封单额' },
          { key: '流通市值', label: '流通市值' },
        ]
      }
      if (this.tab === 'lb') {
        return [
          ...base.slice(0, 3),
          { key: '连板数', label: '连板' },
          ...base.slice(3),
        ]
      }
      return base
    },
  },
  mounted() {
    this.loadData()
  },
  methods: {
    async loadData() {
      this.loading = true
      const date = this.dateStr ? this.dateStr.replace(/-/g, '') : undefined
      try {
        const [ztRes, lbRes, zrRes] = await Promise.all([
          api.getZtPool(date),
          api.getLbPool(date),
          api.getZrPool(date),
        ])
        this.ztData = ztRes.data.data || []
        this.lbData = lbRes.data.data || []
        this.zrData = zrRes.data.data || []
      } catch (e) {
        console.error('加载失败:', e)
      }
      this.loading = false
    },
    formatPct(val) {
      if (val == null) return '-'
      return (val > 0 ? '+' : '') + Number(val).toFixed(2) + '%'
    },
    formatCell(val, key) {
      if (val == null) return '-'
      if (['成交额', '封单额', '流通市值'].includes(key)) {
        const v = Number(val)
        if (v >= 1e8) return (v / 1e8).toFixed(2) + '亿'
        if (v >= 1e4) return (v / 1e4).toFixed(2) + '万'
        return v.toFixed(0)
      }
      return val
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
.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.date-input {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
}
.tab-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
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
