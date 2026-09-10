<script setup>
import AgentChat from '@/components/AgentChat.vue'
import DefaultLayoutWithVerticalNav from './components/DefaultLayoutWithVerticalNav.vue'
</script>

<template>
  <DefaultLayoutWithVerticalNav>
    <RouterView />
  </DefaultLayoutWithVerticalNav>
  <AgentChat />
</template>

<style lang="scss">
// As we are using `layouts` plugin we need its styles to be imported
@use "@layouts/styles/default-layout";
</style>
