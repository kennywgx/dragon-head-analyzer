import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api',
  timeout: 30000,
})

// 响应拦截器：统一错误处理
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const msg = error.response?.data?.detail || error.message || '请求失败'
    console.error(`[API] ${error.config?.url}: ${msg}`)
    return Promise.reject(error)
  }
)

export default {
  // 全量扫描
  scan() {
    return api.get('/scan')
  },
  // 手动触发扫描
  triggerScan() {
    return api.post('/scan/trigger')
  },
  // 涨停池
  getZtPool(date) {
    return api.get('/zt-pool', { params: { date } })
  },
  // 连板池
  getLbPool(date) {
    return api.get('/lb-pool', { params: { date } })
  },
  // 炸板池
  getZrPool(date) {
    return api.get('/zr-pool', { params: { date } })
  },
  // 实时行情
  getRealtime() {
    return api.get('/realtime')
  },
  // 个股详情
  getStockDetail(code) {
    return api.get(`/stock/${code}`)
  },
  // 板块列表
  getBoards(type = '概念板块') {
    return api.get('/boards', { params: { board_type: type } })
  },
  // 日志
  getLogs(date) {
    return api.get('/logs', { params: { date } })
  },
  // 健康检查
  health() {
    return api.get('/health')
  },

  // ==================== 任务管理 ====================
  // 任务列表
  getTasks() {
    return api.get('/tasks')
  },
  // 任务详情
  getTask(taskId) {
    return api.get(`/tasks/${taskId}`)
  },
  // 手动执行任务
  executeTask(taskId) {
    return api.post(`/tasks/${taskId}/execute`)
  },
  // 启用/禁用任务
  enableTask(taskId, enabled) {
    return api.put(`/tasks/${taskId}/enable`, null, { params: { enabled } })
  },
  // 更新任务参数
  updateTaskParams(taskId, params) {
    return api.put(`/tasks/${taskId}/params`, params)
  },
  // 最近执行结果
  getTaskResults(taskId, limit = 50) {
    return api.get('/tasks/results/recent', { params: { task_id: taskId, limit } })
  },
  // 有记录的日期
  getTaskResultDates() {
    return api.get('/tasks/results/dates')
  },
  // 指定日期结果
  getTaskResultsByDate(date) {
    return api.get(`/tasks/results/${date}`)
  },
}
