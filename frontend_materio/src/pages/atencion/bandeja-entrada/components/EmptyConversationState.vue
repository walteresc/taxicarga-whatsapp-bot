<template>
  <div class="empty-state">
    <i class="ri-mail-open-line empty-icon"></i>
    <h3>Selecciona una conversación</h3>
    <p>Elige una conversación de la lista para revisar mensajes y responder</p>
  </div>
</template>

<script setup>
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  grid-column: 1 / -1;
  grid-row: 1 / -1;
  gap: 16px;
  color: #999;
  padding: 40px 20px;
}

.empty-icon {
  font-size: 64px;
  color: #ddd;
  opacity: 0.5;
}

h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: #333;
}

p {
  margin: 0;
  font-size: 13px;
  color: #999;
  text-align: center;
}
</style>
