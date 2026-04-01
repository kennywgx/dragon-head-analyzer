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
}
