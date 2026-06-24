<template>
  <el-container style="height: 100vh; background: #f5f7fa;">
    <!-- 侧边栏 -->
    <el-aside width="220px" style="background: #1d1e3c; color: white; overflow: hidden;">
      <div style="padding: 20px 16px; border-bottom: 1px solid rgba(255,255,255,0.1);">
        <h2 style="margin:0; font-size:16px; font-weight:600; color:#fff;">
          公交智能调度系统
        </h2>
        <p style="margin:6px 0 0; font-size:11px; opacity:0.6;">绿色排班 · 智能优化</p>
      </div>

      <el-menu
        :default-active="$route.path"
        router
        background-color="#1d1e3c"
        text-color="rgba(255,255,255,0.75)"
        active-text-color="#409EFF"
        style="border-right:none;"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataLine /></el-icon>总览仪表盘
        </el-menu-item>
        <el-menu-item index="/flow">
          <el-icon><TrendCharts /></el-icon>客流分析
        </el-menu-item>
        <el-menu-item index="/prediction">
          <el-icon><Cpu /></el-icon>客流预测
        </el-menu-item>
        <el-menu-item index="/optimization">
          <el-icon><Setting /></el-icon>排班优化
        </el-menu-item>
        <el-menu-item index="/carbon">
          <el-icon><Leaf /></el-icon>碳排放分析
        </el-menu-item>
        <el-menu-item index="/simulation">
          <el-icon><VideoPlay /></el-icon>仿真验证
        </el-menu-item>
      </el-menu>

      <div style="position:absolute; bottom:20px; left:0; right:0; padding:0 16px; font-size:10px; opacity:0.4; text-align:center;">
        2026 交通科技大赛参赛作品
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-main style="padding: 0; overflow-y: auto;">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { DataLine, TrendCharts, Cpu, Setting, Leaf, VideoPlay } from '@element-plus/icons-vue'
</script>

<style>
body { margin: 0; padding: 0; font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; }
* { box-sizing: border-box; }
</style>
