<template>
  <div class="tasks-page">
    <div class="page-header">
      <h1>⚙️ 任务中心</h1>
      <div class="header-actions">
        <button class="btn btn-primary" @click="loadTasks" :disabled="loading">
          {{ loading ? '加载中...' : '🔄 刷新' }}
        </button>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="errorMsg" class="error-toast" @click="errorMsg = ''">
      ⚠️ {{ errorMsg }}
      <span class="error-close">✕</span>
    </div>

    <!-- 最近执行结果 -->
    <div class="card" v-if="recentResults.length > 0">
      <div class="card-header">
        <span class="card-title">📋 最近执行</span>
      </div>
      <div class="result-list">
        <div v-for="r in recentResults.slice(-5).reverse()" :key="r.task_id + r.executed_at"
          :class="['result-item', 'status-' + r.status]">
          <span class="result-status">
            {{ r.status === 'success' ? '✅' : r.status === 'error' ? '❌' : '⏭️' }}
          </span>
          <span class="result-name">{{ r.name }}</span>
          <span class="result-summary">{{ r.summary }}</span>
          <span class="result-time">{{ formatTime(r.executed_at) }}</span>
          <span v-if="r.alerts && r.alerts.length" class="result-alerts">
            🔔 {{ r.alerts.length }}条告警
          </span>
        </div>
      </div>
    </div>

    <!-- 调度类任务 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">⏰ 调度任务</span>
        <span class="stat-label">定时自动执行</span>
      </div>
      <div v-if="scheduled.length === 0" class="empty">暂无调度任务</div>
      <div class="task-grid">
        <div v-for="task in scheduled" :key="task.task_id" :class="['task-card', { disabled: !task.enabled }]">
          <div class="task-header">
            <span class="task-name">{{ task.name }}</span>
            <label class="switch">
              <input type="checkbox" :checked="task.enabled" @change="toggleTask(task.task_id, !task.enabled)" />
              <span class="slider"></span>
            </label>
          </div>
          <p class="task-desc">{{ task.description }}</p>
          <div class="task-meta">
            <span class="tag tag-blue">{{ formatSchedule(task.schedule_expr) }}</span>
          </div>
          <div class="task-actions">
            <button class="btn btn-sm" @click="runTask(task.task_id)" :disabled="executing === task.task_id">
              {{ executing === task.task_id ? '执行中...' : '▶ 执行' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 规则监听类任务 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">📡 规则监听</span>
        <span class="stat-label">基于龙头战法规则的实时监控</span>
      </div>
      <div v-if="monitors.length === 0" class="empty">暂无监听任务</div>
      <div class="task-grid">
        <div v-for="task in monitors" :key="task.task_id" :class="['task-card', { disabled: !task.enabled }]">
          <div class="task-header">
            <span class="task-name">{{ task.name }}</span>
            <label class="switch">
              <input type="checkbox" :checked="task.enabled" @change="toggleTask(task.task_id, !task.enabled)" />
              <span class="slider"></span>
            </label>
          </div>
          <p class="task-desc">{{ task.description }}</p>

          <!-- 规则参数展示 -->
          <div class="task-params" v-if="task.rule_params && expandedTask === task.task_id">
            <div class="params-title">规则参数：</div>
            <div v-for="(val, key) in task.rule_params" :key="key" class="param-row">
              <span class="param-key">{{ key }}</span>
              <span class="param-val">{{ formatParamVal(val) }}</span>
            </div>
          </div>

          <div class="task-meta">
            <span class="tag tag-purple">{{ ruleTypeLabel(task.rule_type) }}</span>
            <span class="tag tag-blue">{{ formatSchedule(task.schedule_expr) }}</span>
            <button class="tag tag-gray" style="cursor:pointer;border:none;" @click="toggleExpand(task.task_id)">
              {{ expandedTask === task.task_id ? '收起参数' : '查看参数' }}
            </button>
          </div>
          <div class="task-actions">
            <button class="btn btn-sm" @click="runTask(task.task_id)" :disabled="executing === task.task_id">
              {{ executing === task.task_id ? '执行中...' : '▶ 执行' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 执行结果详情弹窗 -->
    <div v-if="showResult" class="modal-overlay" @click.self="showResult = null">
      <div class="modal">
        <div class="modal-header">
          <h3>{{ showResult.name }} — 执行结果</h3>
          <button class="modal-close" @click="showResult = null">✕</button>
        </div>
        <div class="modal-body">
          <div class="result-detail">
            <div><strong>状态：</strong>
              <span :class="'tag ' + (showResult.status === 'success' ? 'tag-green' : 'tag-red')">
                {{ showResult.status }}
              </span>
            </div>
            <div><strong>时间：</strong>{{ showResult.executed_at }}</div>
            <div><strong>摘要：</strong>{{ showResult.summary }}</div>
          </div>

          <!-- 告警列表 -->
          <div v-if="showResult.alerts && showResult.alerts.length" class="alert-section">
            <h4>🔔 告警 ({{ showResult.alerts.length }})</h4>
            <table class="data-table">
              <thead>
                <tr>
                  <th>类型</th>
                  <th>标的</th>
                  <th>详情</th>
                  <th>级别</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(a, i) in showResult.alerts" :key="i"
                  :class="a.severity === 'high' ? 'exit-high' : ''">
                  <td><span :class="'tag ' + (a.severity === 'high' ? 'tag-red' : 'tag-orange')">{{ a.type }}</span></td>
                  <td>{{ a.name }}</td>
                  <td>{{ a.detail }}</td>
                  <td>{{ a.severity === 'high' ? '⚠️ 高' : '中' }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 详细数据 -->
          <div v-if="showResult.data" class="data-section">
            <h4>📊 详细数据</h4>
            <pre class="data-json">{{ JSON.stringify(showResult.data, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- 最近执行记录 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">📜 执行记录</span>
        <div>
          <select v-model="filterTaskId" @change="loadRecentResults" class="filter-select">
            <option value="">全部任务</option>
            <option v-for="t in allTasks" :key="t.task_id" :value="t.task_id">{{ t.name }}</option>
          </select>
        </div>
      </div>
      <div v-if="recentResults.length === 0" class="empty">暂无执行记录</div>
      <table class="data-table" v-else>
        <thead>
          <tr>
            <th>时间</th>
            <th>任务</th>
            <th>状态</th>
            <th>摘要</th>
            <th>告警</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filteredResults.slice().reverse().slice(0, 30)" :key="r.task_id + r.executed_at">
            <td>{{ formatTime(r.executed_at) }}</td>
            <td>{{ r.name }}</td>
            <td>
              <span :class="'tag ' + (r.status === 'success' ? 'tag-green' : r.status === 'error' ? 'tag-red' : 'tag-gray')">
                {{ r.status === 'success' ? '✅' : r.status === 'error' ? '❌' : '⏭️' }} {{ r.status }}
              </span>
            </td>
            <td>{{ r.summary }}</td>
            <td>
              <span v-if="r.alerts && r.alerts.length" class="tag tag-red">{{ r.alerts.length }}条</span>
              <span v-else>-</span>
            </td>
            <td>
              <button class="btn btn-sm" @click="showResult = r">详情</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 数据源健康状态 -->
    <div class="card">
      <div class="card-header">
        <span class="card-title">🏥 数据源健康状态</span>
        <div>
          <button class="btn btn-sm" @click="resetSources" style="margin-right: 8px;">🔄 重置优先级</button>
          <button class="btn btn-sm" @click="loadSourceStatus">刷新</button>
        </div>
      </div>
      <div v-if="Object.keys(sourceStatus).length === 0" class="empty">暂无数据源信息</div>
      <div v-for="(sources, dataType) in sourceStatus" :key="dataType" class="source-group">
        <div class="source-group-title">{{ dataType }}</div>
        <table class="data-table source-table">
          <thead>
            <tr>
              <th>数据源</th>
              <th>优先级</th>
              <th>健康分</th>
              <th>有效优先级</th>
              <th>连续失败</th>
              <th>总调用</th>
              <th>成功率</th>
              <th>状态</th>
              <th>最后成功</th>
              <th>最后失败</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="s in sources" :key="s.name"
              :class="{ 'source-down': !s.available, 'source-warn': s.health < 50 && s.available }">
              <td><strong>{{ s.name }}</strong></td>
              <td>{{ s.priority }}</td>
              <td>
                <div class="health-bar">
                  <div class="health-fill" :style="{ width: s.health + '%', background: healthColor(s.health) }"></div>
                  <span class="health-text">{{ s.health }}</span>
                </div>
              </td>
              <td>{{ s.effective_priority }}</td>
              <td>
                <span :class="s.consecutive_failures >= 3 ? 'tag tag-red' : s.consecutive_failures > 0 ? 'tag tag-orange' : 'tag tag-green'">
                  {{ s.consecutive_failures }}
                </span>
              </td>
              <td>{{ s.total_calls }}</td>
              <td>{{ s.success_rate }}</td>
              <td>
                <span :class="s.available ? 'tag tag-green' : 'tag tag-red'">
                  {{ s.available ? '✅ 可用' : '❌ 不可用' }}
                </span>
              </td>
              <td>{{ s.last_success }}</td>
              <td>{{ s.last_failure }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script>
import api from '../api'

export default {
  name: 'Tasks',
  data() {
    return {
      scheduled: [],
      monitors: [],
      recentResults: [],
      allTasks: [],
      loading: false,
      executing: null,
      errorMsg: '',
      showResult: null,
      filterTaskId: '',
      expandedTask: null,
      sourceStatus: {},
    }
  },
  computed: {
    filteredResults() {
      if (!this.filterTaskId) return this.recentResults
      return this.recentResults.filter(r => r.task_id === this.filterTaskId)
    },
  },
  mounted() {
    this.loadTasks()
    this.loadRecentResults()
    this.loadSourceStatus()
  },
  methods: {
    async loadTasks() {
      this.loading = true
      this.errorMsg = ''
      try {
        const res = await api.getTasks()
        if (res.data.success) {
          this.scheduled = res.data.data.scheduled || []
          this.monitors = res.data.data.monitors || []
          this.allTasks = [...this.scheduled, ...this.monitors]
        }
      } catch (e) {
        this.errorMsg = '加载任务失败: ' + (e.response?.data?.detail || e.message)
      }
      this.loading = false
    },
    async loadRecentResults() {
      try {
        const res = await api.getTaskResults(this.filterTaskId || undefined)
        this.recentResults = res.data.data || []
      } catch (e) {
        console.error('加载结果失败:', e)
      }
    },
    async toggleTask(taskId, enabled) {
      try {
        await api.enableTask(taskId, enabled)
        await this.loadTasks()
      } catch (e) {
        this.errorMsg = '操作失败: ' + (e.response?.data?.detail || e.message)
      }
    },
    async runTask(taskId) {
      this.executing = taskId
      this.errorMsg = ''
      try {
        const res = await api.executeTask(taskId)
        if (res.data.success) {
          this.showResult = res.data.data
          await this.loadRecentResults()
        }
      } catch (e) {
        this.errorMsg = '执行失败: ' + (e.response?.data?.detail || e.message)
      }
      this.executing = null
    },
    toggleExpand(taskId) {
      this.expandedTask = this.expandedTask === taskId ? null : taskId
    },
    async loadSourceStatus() {
      try {
        const res = await api.getSourceStatus()
        this.sourceStatus = res.data.data || {}
      } catch (e) {
        console.error('加载数据源状态失败:', e)
      }
    },
    async resetSources() {
      try {
        await api.resetSources()
        await this.loadSourceStatus()
      } catch (e) {
        this.errorMsg = '重置失败: ' + (e.response?.data?.detail || e.message)
      }
    },
    healthColor(health) {
      if (health >= 70) return '#52c41a'
      if (health >= 40) return '#fa8c16'
      return '#ff4d4f'
    },
    formatTime(isoStr) {
      if (!isoStr) return '-'
      const d = new Date(isoStr)
      return d.toLocaleString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    },
    formatSchedule(expr) {
      if (!expr) return '-'
      const map = {
        '15 9 * * 1-5': '每个交易日 09:15',
        '10 15 * * 1-5': '每个交易日 15:10',
        '0 10 * * 6': '每周六 10:00',
        '*/30 9-15 * * 1-5': '交易日每30分钟',
        '25 9 * * 1-5': '每个交易日 09:25',
        '*/15 9-15 * * 1-5': '交易日每15分钟',
        '0 10,11,13,14 * * 1-5': '交易日整点(10/11/13/14)',
        '*/5 9-15 * * 1-5': '交易日每5分钟',
      }
      return map[expr] || expr
    },
    ruleTypeLabel(type) {
      const map = {
        emotion: '情绪周期',
        yijiner: '一进二',
        seal_strength: '封单强度',
        sector_resonance: '板块共振',
        breaking_board: '炸板预警',
      }
      return map[type] || type
    },
    formatParamVal(val) {
      if (typeof val === 'number') {
        if (val >= 1e8) return (val / 1e8) + '亿'
        return val
      }
      return String(val)
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
.page-header h1 { font-size: 24px; }

.error-toast {
  background: #fff1f0; border: 1px solid #ffa39e; color: #cf1322;
  padding: 12px 16px; border-radius: 6px; margin-bottom: 16px;
  cursor: pointer; display: flex; justify-content: space-between;
}
.error-close { font-size: 14px; opacity: 0.6; }

/* 结果列表 */
.result-list { display: flex; flex-direction: column; gap: 6px; }
.result-item {
  display: flex; align-items: center; gap: 12px; padding: 8px 12px;
  border-radius: 6px; font-size: 13px;
}
.result-item.status-success { background: #f6ffed; }
.result-item.status-error { background: #fff1f0; }
.result-item.status-skipped { background: #f5f5f5; }
.result-status { font-size: 16px; }
.result-name { font-weight: 600; min-width: 120px; }
.result-summary { flex: 1; color: #666; }
.result-time { color: #999; font-size: 12px; min-width: 60px; }
.result-alerts { color: #ff4d4f; font-size: 12px; font-weight: 600; }

/* 任务卡片网格 */
.task-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
.task-card {
  border: 1px solid #eee; border-radius: 8px; padding: 16px;
  background: #fff; transition: all 0.2s;
}
.task-card:hover { box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.task-card.disabled { opacity: 0.5; background: #fafafa; }
.task-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px;
}
.task-name { font-size: 15px; font-weight: 600; }
.task-desc { font-size: 13px; color: #888; margin-bottom: 10px; line-height: 1.5; }
.task-meta { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.task-actions { display: flex; gap: 8px; }

/* 参数展示 */
.task-params {
  background: #f8f9fc; border-radius: 6px; padding: 10px;
  margin-bottom: 10px; font-size: 12px;
}
.params-title { font-weight: 600; margin-bottom: 6px; color: #666; }
.param-row { display: flex; justify-content: space-between; padding: 2px 0; }
.param-key { color: #888; }
.param-val { font-weight: 600; }

/* 开关 */
.switch { position: relative; display: inline-block; width: 36px; height: 20px; }
.switch input { opacity: 0; width: 0; height: 0; }
.slider {
  position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0;
  background-color: #ccc; border-radius: 20px; transition: 0.3s;
}
.slider:before {
  position: absolute; content: ""; height: 16px; width: 16px;
  left: 2px; bottom: 2px; background: white; border-radius: 50%; transition: 0.3s;
}
input:checked + .slider { background-color: #52c41a; }
input:checked + .slider:before { transform: translateX(16px); }

/* 按钮 */
.btn-sm {
  padding: 4px 12px; font-size: 12px; border: 1px solid #ddd;
  border-radius: 4px; background: #fff; cursor: pointer;
  transition: all 0.2s;
}
.btn-sm:hover { background: #f5f5f5; }
.btn-sm:disabled { opacity: 0.5; cursor: not-allowed; }

/* 筛选下拉 */
.filter-select {
  padding: 6px 10px; border: 1px solid #ddd; border-radius: 6px;
  font-size: 13px; min-width: 150px;
}

/* 弹窗 */
.modal-overlay {
  position: fixed; top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.4); display: flex; justify-content: center;
  align-items: center; z-index: 1000;
}
.modal {
  background: #fff; border-radius: 10px; width: 90%; max-width: 700px;
  max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 24px rgba(0,0,0,0.15);
}
.modal-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; border-bottom: 1px solid #eee;
}
.modal-header h3 { font-size: 16px; margin: 0; }
.modal-close {
  background: none; border: none; font-size: 18px; cursor: pointer; color: #999;
}
.modal-body { padding: 20px; }
.result-detail { margin-bottom: 16px; line-height: 2; }
.alert-section, .data-section { margin-top: 16px; }
.alert-section h4, .data-section h4 { margin-bottom: 10px; }
.data-json {
  background: #1a1a2e; color: #a8e6cf; padding: 16px; border-radius: 6px;
  font-size: 12px; max-height: 300px; overflow-y: auto; white-space: pre-wrap;
}

.exit-high { background: #fff1f0 !important; }

/* 数据源健康 */
.source-group { margin-bottom: 16px; }
.source-group-title {
  font-weight: 600; font-size: 14px; margin-bottom: 8px;
  padding: 4px 0; color: #1a1a2e;
}
.source-table { font-size: 12px; }
.source-table td, .source-table th { padding: 6px 8px; }
.source-down { background: #fff1f0 !important; }
.source-warn { background: #fff7e6 !important; }
.health-bar {
  position: relative; background: #f0f0f0; border-radius: 8px;
  height: 16px; min-width: 60px; overflow: hidden;
}
.health-fill {
  height: 100%; border-radius: 8px; transition: width 0.5s, background 0.3s;
}
.health-text {
  position: absolute; top: 0; left: 0; right: 0; text-align: center;
  line-height: 16px; font-size: 10px; font-weight: 700; color: #333;
}
</style>
