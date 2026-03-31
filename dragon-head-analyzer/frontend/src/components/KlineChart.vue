<template>
  <div class="kline-chart" ref="chartContainer">
    <div class="chart-toolbar">
      <button v-for="p in periods" :key="p.value"
        :class="['chart-btn', { active: period === p.value }]"
        @click="period = p.value; $emit('period-change', p.value)">
        {{ p.label }}
      </button>
    </div>
    <svg :viewBox="`0 0 ${width} ${height}`" class="chart-svg" @mousemove="onMouseMove" @mouseleave="hoverIdx = -1">
      <!-- 网格线 -->
      <g class="grid">
        <line v-for="i in 5" :key="'h'+i"
          :x1="paddingLeft" :x2="width - paddingRight"
          :y1="paddingTop + (chartHeight / 4) * (i - 1)" :y2="paddingTop + (chartHeight / 4) * (i - 1)"
          stroke="#f0f0f0" stroke-width="1" />
      </g>

      <!-- K线 -->
      <g class="candles">
        <template v-for="(d, i) in displayData" :key="i">
          <!-- 影线 -->
          <line
            :x1="getCandleX(i)" :x2="getCandleX(i)"
            :y1="priceToY(d.high)" :y2="priceToY(d.low)"
            :stroke="d.close >= d.open ? '#ff4d4f' : '#52c41a'"
            stroke-width="1" />
          <!-- 实体 -->
          <rect
            :x="getCandleX(i) - candleWidth / 2"
            :y="priceToY(Math.max(d.open, d.close))"
            :width="candleWidth"
            :height="Math.max(1, Math.abs(priceToY(d.open) - priceToY(d.close)))"
            :fill="d.close >= d.open ? '#ff4d4f' : '#52c41a'"
            :rx="1" />
        </template>
      </g>

      <!-- 成交量柱 -->
      <g class="volume-bars">
        <rect v-for="(d, i) in displayData" :key="'v'+i"
          :x="getCandleX(i) - candleWidth / 2"
          :y="volumeTop + volumeHeight - (d.volume / maxVolume * volumeHeight)"
          :width="candleWidth"
          :height="d.volume / maxVolume * volumeHeight"
          :fill="d.close >= d.open ? 'rgba(255,77,79,0.4)' : 'rgba(82,196,26,0.4)'" />
      </g>

      <!-- 价格轴 -->
      <g class="price-axis">
        <text v-for="i in 5" :key="'p'+i"
          :x="width - paddingRight + 4"
          :y="paddingTop + (chartHeight / 4) * (i - 1) + 4"
          fill="#999" font-size="11" text-anchor="start">
          {{ formatPrice(maxPrice - (priceRange / 4) * (i - 1)) }}
        </text>
      </g>

      <!-- 十字线 -->
      <g v-if="hoverIdx >= 0 && hoverIdx < displayData.length" class="crosshair">
        <line :x1="getCandleX(hoverIdx)" :x2="getCandleX(hoverIdx)"
          :y1="paddingTop" :y2="volumeTop + volumeHeight"
          stroke="#ddd" stroke-dasharray="3,3" />
        <line :x1="paddingLeft" :x2="width - paddingRight"
          :y1="mouseY" :y2="mouseY"
          stroke="#ddd" stroke-dasharray="3,3" />
      </g>
    </svg>

    <!-- 悬浮信息 -->
    <div class="tooltip" v-if="hoverIdx >= 0 && hoverIdx < displayData.length">
      <span class="tip-date">{{ displayData[hoverIdx].date }}</span>
      <span>开: {{ formatPrice(displayData[hoverIdx].open) }}</span>
      <span class="up">高: {{ formatPrice(displayData[hoverIdx].high) }}</span>
      <span class="down">低: {{ formatPrice(displayData[hoverIdx].low) }}</span>
      <span :class="displayData[hoverIdx].close >= displayData[hoverIdx].open ? 'up' : 'down'">
        收: {{ formatPrice(displayData[hoverIdx].close) }}
      </span>
      <span>量: {{ formatVol(displayData[hoverIdx].volume) }}</span>
    </div>
  </div>
</template>

<script>
export default {
  name: 'KlineChart',
  props: {
    data: { type: Array, default: () => [] },
    initialPeriod: { type: String, default: 'daily' },
  },
  emits: ['period-change'],
  data() {
    return {
      period: this.initialPeriod,
      periods: [
        { label: '日线', value: 'daily' },
        { label: '5分', value: '5min' },
      ],
      width: 700,
      height: 350,
      paddingTop: 20,
      paddingRight: 60,
      paddingBottom: 60,
      paddingLeft: 10,
      hoverIdx: -1,
      mouseY: 0,
    }
  },
  computed: {
    displayData() {
      return this.data.slice(-60).map(d => ({
        date: d['日期'] || d['时间'] || '',
        open: Number(d['开盘'] || 0),
        close: Number(d['收盘'] || 0),
        high: Number(d['最高'] || 0),
        low: Number(d['最低'] || 0),
        volume: Number(d['成交量'] || 0),
      }))
    },
    chartHeight() {
      return (this.height - this.paddingTop - this.paddingBottom) * 0.75
    },
    volumeHeight() {
      return (this.height - this.paddingTop - this.paddingBottom) * 0.2
    },
    volumeTop() {
      return this.paddingTop + this.chartHeight + 10
    },
    candleWidth() {
      const avail = this.width - this.paddingLeft - this.paddingRight
      return Math.max(2, Math.min(12, (avail / this.displayData.length) * 0.7))
    },
    maxPrice() {
      if (!this.displayData.length) return 100
      return Math.max(...this.displayData.map(d => d.high))
    },
    minPrice() {
      if (!this.displayData.length) return 0
      return Math.min(...this.displayData.map(d => d.low))
    },
    priceRange() {
      return this.maxPrice - this.minPrice || 1
    },
    maxVolume() {
      if (!this.displayData.length) return 1
      return Math.max(...this.displayData.map(d => d.volume)) || 1
    },
  },
  methods: {
    getCandleX(i) {
      const avail = this.width - this.paddingLeft - this.paddingRight
      const step = avail / Math.max(1, this.displayData.length)
      return this.paddingLeft + step * i + step / 2
    },
    priceToY(price) {
      const ratio = (price - this.minPrice) / this.priceRange
      return this.paddingTop + this.chartHeight * (1 - ratio)
    },
    formatPrice(v) {
      return Number(v).toFixed(2)
    },
    formatVol(v) {
      const n = Number(v)
      if (n >= 1e8) return (n / 1e8).toFixed(1) + '亿'
      if (n >= 1e4) return (n / 1e4).toFixed(1) + '万'
      return n.toFixed(0)
    },
    onMouseMove(e) {
      const rect = this.$refs.chartContainer?.querySelector('.chart-svg')?.getBoundingClientRect()
      if (!rect) return
      const x = (e.clientX - rect.left) / rect.width * this.width
      const y = (e.clientY - rect.top) / rect.height * this.height
      this.mouseY = y

      const avail = this.width - this.paddingLeft - this.paddingRight
      const step = avail / Math.max(1, this.displayData.length)
      const idx = Math.floor((x - this.paddingLeft) / step)
      this.hoverIdx = Math.max(0, Math.min(idx, this.displayData.length - 1))
    },
  },
}
</script>

<style scoped>
.kline-chart {
  position: relative;
}
.chart-toolbar {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.chart-btn {
  padding: 4px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
  background: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.chart-btn.active {
  background: #ff6b6b;
  color: #fff;
  border-color: #ff6b6b;
}
.chart-svg {
  width: 100%;
  height: auto;
  cursor: crosshair;
}
.tooltip {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #666;
  padding: 6px 0;
  flex-wrap: wrap;
}
.tip-date {
  font-weight: 600;
  color: #333;
}
.up { color: #ff4d4f; }
.down { color: #52c41a; }
</style>
