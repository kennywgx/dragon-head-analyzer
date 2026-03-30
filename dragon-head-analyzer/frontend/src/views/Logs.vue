<template>
  <div class="logs-page">
    <div class="page-header">
      <h1>📝 分析日志</h1>
      <div class="header-actions">
        <select v-model="selectedDate" @change="loadLogs" class="date-select">
          <option v-for="d in dates" :key="d" :value="d">{{ d }}</option>
        </select>
        <button class="btn btn-primary" @click="loadLogs" :disabled="loading">
          {{ loading ? '加载中...' : '刷新' }}
        </button>
      </div>
    </div>

    <div class="card">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="!logContent" class="empty">暂无日志</div>
      <pre v-else class="log-content">{{ logContent }}</pre>
    </div>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'Logs',
  data() {
    return {
      dates: [],
      selectedDate: '',
      logContent: '',
      loading: false,
    }
  },
  mounted() {
    this.loadLogs()
  },
  methods: {
    async loadLogs() {
      this.loading = true
      try {
        const date = this.selectedDate || undefined
        const res = await api.getLogs(date)
        const data = res.data.data
        this.dates = data.dates || []
        this.logContent = data.content || ''
        if (!this.selectedDate && this.dates.length) {
          this.selectedDate = this.dates[0]
        }
      } catch (e) {
        console.error('加载日志失败:', e)
      }
      this.loading = false
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
.date-select {
  padding: 8px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  min-width: 140px;
}
.log-content {
  background: #1a1a2e;
  color: #a8e6cf;
  padding: 20px;
  border-radius: 6px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 600px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
