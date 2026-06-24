<template>
  <div style="padding:24px;max-width:1400px;margin:0 auto;">
    <h1 style="margin:0 0 4px;font-size:22px;font-weight:600;color:#1a1a2e;">碳排放分析</h1>
    <p style="margin:0 0 16px;font-size:13px;color:#888;">绿色排班方案 — 碳减排量化与环境影响评估</p>

    <!-- 碳减排核心指标 -->
    <el-row :gutter="16" style="margin-bottom:20px;">
      <el-col :span="6">
        <div style="background:linear-gradient(135deg,#e8f5e9,#c8e6c9);border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:36px;font-weight:700;color:#2e7d32;">331.2</div>
          <div style="font-size:13px;color:#558b2f;margin-top:4px;">kg CO₂/日 减排量</div>
        </div>
      </el-col>
      <el-col :span="6">
        <div style="background:linear-gradient(135deg,#fff3e0,#ffe0b2);border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:36px;font-weight:700;color:'#ef6c00';">28.6%</div>
          <div style="font-size:13px;color:#a06815;margin-top:4px;">碳排放降低率</div>
        </div>
      </el-col>
      <el-Col :span="6">
        <div style="background:linear-gradient(135deg,#e3f2fd,#bbdefb);border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:36px;font-weight:700;color:'#1565c0;'>120,948</div>
          <div style="font-size:13px;color:#455a64;margin-top:4px;">kg CO₂/年 减排量</div>
        </div>
      </elCol>
      <el-Col :span="6">
        <div style="background:linear-gradient(135deg,#fce4ec,#f8bbd0);border-radius:12px;padding:24px;text-align:center;">
          <div style="font-size:36px;font-weight:700;color:'#c62828'>≈33</div>
          <div style="font-size:13px;color:#ad1457;margin-top:4px;">棵树等效碳汇量</div>
        </div>
      </elCol>
    </el-row>

    <!-- 排放对比图 -->
    <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);margin-bottom:16px;">
      <h3 style="margin:0 0 16px;font-size:14px;">各时段碳排放对比（优化前 vs 优化后）</h3>
      <div ref="carbonChartRef" style="height:340px;"></div>
    </div>

    <el-row :gutter="16" style="margin-bottom:16px;">
      <el-col :span="12">
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:360px;">
          <h3 style="margin:0 0 12px;font-size:14px;">人均碳排放（g CO₂/人次）</h3>
          <div ref="perCapitaRef" style="height:300px;"></div>
        </div>
      </el-col>
      <el-col :span="12">
        <div style="background:#fff;border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,0.06);height:360px;">
          <h3 style="margin:0 0 12px;font-size:14px;">年度累计碳减排趋势</h3>
          <div ref="yearlyRef" style="height:300px;"></div>
        </div>
      </elCol>
    </elRow>

    <!-- 绿色意义说明 -->
    <div style="background:#f0fdf4;border:1px solid #b7eb8f;border-radius:10px;padding:18px 22px;display:flex;gap:20px;align-items:flex-start;">
      <el-icon :size="28" color="#67C23A" style="flex-shrink:0;"><InfoFilled /></el-icon>
      <div>
        <div style="font-size:15px;font-weight:600;color:#155d27;margin-bottom:6px;">绿色出行的环境价值</div>
        <ul style="margin:0;padding-left:18px;font-size:13px;color:#444;line-height:1.8;">
          <li>每减少 <strong>1 kg CO₂</strong> 相当于一棵成年树木一天的固碳能力</li>
          <li>本系统每年可减少约 <strong>121 吨 CO₂</strong>，相当于种植约 5,500 棵行道树</li>
          <li>符合国家「双碳」战略目标，助力城市交通绿色转型</li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import * as echarts from 'echarts'
import { InfoFilled } from '@element-plus/icons-vue'

const carbonChartRef = ref(null)
const perCapitaRef = ref(null)
const yearlyRef = ref(null)

onMounted(() => {
  renderCarbon()
  renderPerCapita()
  renderYearly()
})

function renderCarbon() {
  const c = echarts.init(carbonChartRef.value)
  const slots = Array.from({length:32},(_,i)=>`${i*0.5+5}:00`)
  const baseline = slots.map(()=>(30+Math.random()*10).toFixed(1))
  const optimized = slots.map((_,i)=>{
    const h=i*0.5+5
    if(h>=7&&h<9) return (25+Math.random()*8).toFixed(1)
    if(h>=17&&h<19) return (26+Math.random()*9).toFixed(1)
    if(h<6||h>20) return (5+Math.random()*3).toFixed(1)
    return (15+Math.random()*6).toFixed(1)
  })
  c.setOption({
    tooltip:{trigger:'axis'},
    legend:{data:['固定排班','智能优化']},
    grid:{left:50,right:20,top:20,bottom:50},
    xAxis:{type:'category',data:slots,axisLabel:{interval:3,rotate:30}},
    yAxis:{type:'value',name:'kg CO₂'},
    series:[
      {name:'固定排班',type:'bar',data:baseline,barWidth:'55%',itemStyle:{color:'#909399'}},
      {name:'智能优化',type:'bar',data:optimized,barWidth:'55%',itemStyle:{color:'#67C23A'}}
    ]
  })
}

function renderPerCapita(){
  const c = echarts.init(perCapitaRef.value)
  c.setOption({
    radar:{
      indicator:[{name:'早高峰',max:80},{name:'午间',max:60},{name:'晚高峰',max:75},{name:'平峰',max:40},{name:'夜间',max:100}]
    },
    series:[{type:'radar',radius:65,data:[
      {value:[52,38,48,35,85],name:'固定排班',areaStyle:{color:'rgba(144,147,153,0.2)'}},
      {value:[31,23,29,21,42],name:'智能优化',areaStyle:{color:'rgba(103,194,58,0.3)'},lineStyle:{width:2,color:'#67C23A'}}
    ]}]
  })
}

function renderYearly(){
  const c = echarts.init(yearlyRef.value)
  const months=['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月']
  const cum = []
  let total=0
  for(let i=0;i<12;i++){
    total += 10000 + Math.sin(i/3)*2000 + Math.random()*1500
    cum.push(Math.round(total))
  }
  c.setOption({
    tooltip:{trigger:'axis'},
    grid:{left:60,right:20,top:20,bottom:30},
    xAxis:{type:'category',data:months},
    yAxis:{type:'value',name:'kg CO₂'},
    series:[{
      type:'line',data:cum,
      smooth:true,lineStyle:{width:2.5,color:'#67C23A'},
      areaStyle:{color:new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,'color':'rgba(103,194,58,0.25)'},{offset:1,'color':'rgba(103,194,58,0.02)'})]},
      markPoint:{data:[{coord:[11,cum[11]],name:`年减排 ${cum[11]}kg`,symbolSize:50}]}
    }]
  })
}
</script>
