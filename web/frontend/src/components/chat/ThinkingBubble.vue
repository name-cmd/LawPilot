<script setup lang="ts">
// 思考气泡：三个圆点呼吸动画（沿用旧版体验）
const dots = [0, 1, 2]
</script>

<template>
  <div class="flex items-center gap-1.5 px-1 py-2">
    <span
      v-for="i in dots"
      :key="i"
      class="h-1.5 w-1.5 rounded-full bg-brand-400 animate-breathe"
      :style="{ animationDelay: `${i * 0.2}s` }"
    />
  </div>
</template>
