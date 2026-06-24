<template>
  <div style="padding:24px;max-width:1400px;margin:0 auto;">
    <h1 style="margin:0 0 4px;font-size:22px;font-weight:600;color:#1a1a2e;">客流分析</h1>
    <p style="margin:0 0 20px;font-size:13px;color:#888;">多维度公交客流数据可视化分析</p>

    <!-- 按小时客流分布 -->
    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:16px;">
      <h3 style="margin:0 0 16px;font-size:14px;">按小时客流分布曲线</h3>
      <div ref="hourlyChartRef" style="height:320px;"></div>
    </div>

    <!-- 站点客流热力图 -->
    <el-row :gutter="16" style="margin-bottom:16px;">
      <el-col :span="12">
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:400px;">
          <h3 style="margin:0 0 12px;font-size:14px;">站点×时段 客流热力图</h3>
          <div ref="heatMapRef" style="height:340px;"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:400px;">
          <h3 style="margin:0 0 12px;font-size:14px;">各站点累计客流（柱状）</h3>
          <div ref="stopBarRef" style="height:340px;"></div>
        </div>
      </el-col>
    </el-row>

    <!-- 数据统计卡片 -->
    <el-row :gutter="16">
      <el-col :span="6" v-for="(s,i) in stats" :key="i">
        <div style="background:#fff;border-radius:10px;padding:18px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,0.04);">
          <div style="font-size:24px;font-weight:700;color:s.color">{{s.val}}</div>
          <div style="font-size:12px;color:#999;margin-top:4px;">{{s.label}}</div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'

const hourlyChartRef = ref(null)
const heatMapRef = ref(null)
const stopBarRef = ref(null)

const stats = ref([
  { label: '总记录数', val: '57,600', color: '#409EFF' },
  { label: '日均客流', val: '23,805', color: '#67C23A' },
  { label: '工作日均值', val: '45.4 人/窗', color: '#E6A23C' },
  { label: '周末均值', val: '17.0 人/窗', color: '#F56C6C' },
])

onMounted(() => {
  renderHourly()
  renderHeatMap()
  renderStopBar()
})

function renderHourly() {
  const c = echarts.init(hourlyChartRef.value)
  const hours = Array.from({length:17},(_,i)=>`${i+5}:00`)
  const workday = [5,8,25,42,68,85,72,55,38,28,22,15,8,5,3,2,1]
  const weekend = [2,4,12,22,35,48,52,45,38,32,25,18,12,6,3,2,1]
  c.setOption({
    tooltip:{trigger:'axis'},legend:{data:['工作日','周末']},
    grid:{left:50,right:20,top:30,bottom:30},
    xAxis:{type:'category',data:hours},
    yAxis:{type:'value',name:'客流量(百人)'},
    series:[
      {name:'工作日',type:'line',data:workday,smooth:true,lineStyle:{width:2.5,color:'#409EFF'},areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:'rgba(64,158,255,0.25)'},{offset:1,color:'rgba(64,158,255,0.02)'}])}},
      {name:'周末',type:'line',data:weekend,smooth:true,lineStyle:{width:2.5,color:'#67C23A',type:'dashed'}}
    ]
  })
}

function renderHeatMap() {
  const c = echarts.init(heatMapRef.value)
  const hours=['5-7','7-9','9-11','11-13','13-15','15-17','17-19','19-21']
  const data=[]
  for(let i=0;i<8;i++) for(let j=0;j<10;j++)
    data.push([j,i,Math.round(Math.exp(-((i-1.5)**2+(j-5)**2)/8)*90+Math.random()*15])
  c.setOption({
    tooltip:{position:'top'},
    grid:{left:60,right:15,top:10,bottom:45},
    xAxis:{type:'category',data:Array.from({length:10},(_,i)=>`S${i+1}`),splitArea:{show:true}},
    yAxis:{type:'category',data:hours,splitArea:{show:true}},
    visualMap:{min:0,max:120,calculable:true,orient:'horizontal',left:'center',bottom:0,textStyle:{fontSize:11}},
    series:[{type:'heatmap',data:data,itemStyle:{borderRadius:2}}]
  })
}

function renderStopBar() {
  const c = echarts.init(stopBarRef.value)
  c.setOption({
    grid:{left:60,right:15,top:10,bottom:30},
    xAxis:{type:'value'},
    yAxis:{type:'category',data:Array.from({length:20},(_,i)=>`站点${i+1}`).reverse(),inverse:true},
    series:[{type:'bar',data:Array.from({length:20},()=>Math.round(Math.random()*3000+1500)).reverse(),barWidth:'65%',itemStyle:{color:(p)=>new echarts.graphic.LinearGradient(0,0,1,0,[{offset:0,color:'#409EFF'},{offset:1,color:p.value>2500?'#f56c6c':'#79bbff'}]),borderRadius:[0,3,3,0]}}]
  })
}
</script>
