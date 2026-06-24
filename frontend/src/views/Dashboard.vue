<template>
  <div style="padding: 24px; max-width: 1400px; margin: 0 auto;">
    <!-- 标题 -->
    <div style="margin-bottom: 24px;">
      <h1 style="margin: 0 0 4px; font-size: 22px; font-weight:600; color:#1a1a2e;">总览仪表盘</h1>
      <p style="margin:0; font-size:13px; color:#888;">基于客流预测的绿色排班方案 · 实时数据监控</p>
    </div>

    <!-- 核心指标卡片 -->
    <el-row :gutter="16" style="margin-bottom: 20px;">
      <el-col :span="6" v-for="(card, i) in kpiCards" :key="i">
        <div :style="{ background: card.bg, borderRadius: '12px', padding: '20px', color: '#fff' }">
          <div style="font-size:12px; opacity:0.8; margin-bottom:6px;">{{ card.title }}</div>
          <div style="font-size:28px; font-weight:700;">{{ card.value }}</div>
          <div style="font-size:12px; opacity:0.7; margin-top:4px;" :style="{ color: card.trendUp ? '#67c23a' : '#f56c6c' }">
            {{ card.trend }}
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="16">
      <el-col :span="16" style="margin-bottom: 16px;">
        <div style="background:#fff; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <h3 style="margin:0 0 16px; font-size:14px; font-weight:500; color:#333;">客流趋势（近30日）</h3>
          <div ref="trendChartRef" style="height:300px;"></div>
        </div>
      </el-col>
      <el-col :span="8" style="margin-bottom: 16px;">
        <div style="background:#fff; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <h3 style="margin:0 0 16px; font-size:14px; font-weight:500; color:#333;">站点客流排名 TOP10</h3>
          <div ref="stopRankRef" style="height:300px;"></div>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :span="8">
        <div style="background:#fff; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <h3 style="margin:0 0 16px; font-size:14px; font-weight:500; color:#333;">工作日 vs 周末对比</h3>
          <div ref="compareChartRef" style="height:250px;"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div style="background:#fff; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <h3 style="margin:0 0 16px; font-size:14px; font-weight:500; color:#333;">时段分布热力</h3>
          <div ref="heatMapRef" style="height:250px;"></div>
        </div>
      </el-col>
      <el-col :span="8">
        <div style="background:#fff; border-radius:12px; padding:20px; box-shadow: 0 1px 3px rgba(0,0,0,0.06);">
          <h3 style="margin:0 0 16px; font-size:14px; font-weight:500; color:#333;">模型性能概览</h3>
          <div ref="modelRadarRef" style="height:250px;"></div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import { apiGet } from '../api'

const trendChartRef = ref(null)
const stopRankRef = ref(null)
const compareChartRef = ref(null)
const heatMapRef = ref(null)
const modelRadarRef = ref(null)

const kpiCards = ref([
  { title: '日均客流量', value: '23,805 人次', trend: '较上周 +3.2%', bg: '#409EFF', trendUp: true },
  { title: '优化后碳排放', value: '820.8 kg/日', trend: '较基准 -28.6%', bg: '#67C23A', trendUp: true },
  { title: '平均等待时间', value: '0.63 分钟', trend: '较基准 -91.0%', bg: '#E6A23C', trendUp: true },
  { title: 'LSTM 预测精度 (MAPE)', value: '13.72%', trend: '优于 XGBoost 4.06%', bg: '#F56C6C', trendUp: false },
])

onMounted(() => {
  renderTrendChart()
  renderStopRankChart()
  renderCompareChart()
  renderHeatMap()
  renderModelRadar()
})

function renderTrendChart() {
  const chart = echarts.init(trendChartRef.value)
  const days = Array.from({length: 30}, (_, i) => `${i+1}日`)
  const flowData = days.map((_, i) => Math.round(22000 + Math.sin(i/5) * 4000 + Math.random() * 2000))
  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: 'category', data: days, axisLabel: { interval: 4 } },
    yAxis: { type: 'value', name: '人次' },
    series: [{
      type: 'line',
      data: flowData,
      smooth: true,
      areaStyle: { color: new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(64,158,255,0.3)'},{offset:1,color:'rgba(64,158,255,0.02)'}]) },
      lineStyle: { width: 2.5, color: '#409EFF' },
      itemStyle: { color: '#409EFF' },
    }]
  })
}

function renderStopRankChart() {
  const chart = echarts.init(stopRankRef.value)
  const stops = Array.from({length: 10}, (_, i) => `站点 ${i+1}号`)
  chart.setOption({
    grid: { left: 80, right: 20, top: 10, bottom: 30 },
    xAxis: { type: 'value', name: '人次' },
    yAxis: { type: 'category', data: stops.reverse(), inverse: true },
    series: [{
      type: 'bar',
      data: [4520, 3980, 3650, 3420, 3100, 2890, 2650, 2400, 2180, 1950].reverse(),
      barWidth: '60%',
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'#409EFF'},{offset:1,color:'#79bbff'}]),
        borderRadius: [0, 4, 4, 0],
      }
    }]
  })
}

function renderCompareChart() {
  const chart = echarts.init(compareChartRef.value)
  chart.setOption({
    legend: { data: ['工作日', '周末'], bottom: 0 },
    radar: { indicator: [
      { name: '早高峰', max: 100 }, { name: '午间', max: 100 }, { name: '晚高峰', max: 100 }, { name: '夜间', max: 100 }
    ]},
    series: [{ type: 'radar', data: [{value:[85,55,78,15],name:'工作日'},{value:[42,48,52,8],name:'周末'}] }]
  })
}

function renderHeatMap() {
  const chart = echarts.init(heatMapRef.value)
  const hours = ['5-6','6-7','7-8','8-9','9-10','10-11','11-12','12-13']
  const data = []
  for (let i=0;i<8;i++) for(let j=0;j<5;j++)
    data.push([j,i,Math.round(Math.random()*80+10)])
  chart.setOption({
    tooltip:{position:'top'},
    grid:{left:70,right:20,top:20,bottom:50},
    xAxis:{type:'category',data:['站点1','站点2','站点3','站点4','站点5'],splitArea:{show:true}},
    yAxis:{type:'category',data:hours.splitArea:{show:true}},
    visualMap:{min:0,max:100,calculable:true,orient:'horizontal',left:'center',bottom:0},
    series:[{type:'heatmap',data:data,label:{show:false},emphasis:{itemStyle:{shadowBlur:10,shadowColor:'rgba(0,0,0,0.5)'}}}]
  })
}

function renderModelRadar() {
  const chart = echarts.init(modelRadarRef.value)
  chart.setOption({
    legend:{bottom:0,data:['LSTM','XGBoost']},
    radar:{indicator:[
      {name:'MAE',max:10},{name:'RMSE',max:15},{name:'MAPE%',max:25}
    ],shape:'circle'},
    series:[{type:'radar',data:[
      {value:[4.78,7.42,13.72],name:'LSTM',areaStyle:{color:'rgba(64,158,255,0.2)'}},
      {value:[5.28,8.10,17.78],name:'XGBoost',areaStyle:{color:'rgba(103,194,58,0.2)'}}
    ]}]
  })
}
</script>
