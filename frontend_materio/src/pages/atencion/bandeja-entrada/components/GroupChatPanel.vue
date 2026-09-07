<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

import { groupsService } from '@/services/groupsService'
import { useAuthStore } from '@/stores/authStore'

const props = defineProps({
  groupId: { type: [Number, String], required: true },
})
const emit = defineEmits(['group-updated'])

const auth = useAuthStore()

const group = ref(null)
const messages = ref([])
const loadingMessages = ref(false)
const messageText = ref('')
const sending = ref(false)
const fileInput = ref(null)
const messagesEnd = ref(null)
const sendError = ref('')

const showMembersDialog = ref(false)
const availableUsers = ref([])
const addingUserId = ref(null)

const showRenameDialog = ref(false)
const renameValue = ref('')
const renaming = ref(false)

let pollTimer = null

const scrollToBottom = () => {
  nextTick(() => messagesEnd.value?.scrollIntoView({ block: 'end' }))
}

const loadGroup = async () => {
  group.value = await groupsService.getGroup(props.groupId)
  emit('group-updated', group.value)
}

const loadMessages = async (initial = false) => {
  if (initial) {
    loadingMessages.value = true
    messages.value = []
  }
  try {
    const afterId = initial ? undefined : messages.value.at(-1)?.id
    const data = await groupsService.listMessages(props.groupId, afterId)
    if (data.length) {
      messages.value = initial ? data : [...messages.value, ...data]
      scrollToBottom()
    }
  } finally {
    if (initial) loadingMessages.value = false
  }
}

const startPolling = () => {
  stopPolling()
  pollTimer = setInterval(() => loadMessages(false), 4000)
}
const stopPolling = () => { if (pollTimer) clearInterval(pollTimer) }

const init = async () => {
  stopPolling()
  await loadGroup()
  await loadMessages(true)
  startPolling()
}

onMounted(init)
onUnmounted(stopPolling)
watch(() => props.groupId, init)

const sendText = async () => {
  const text = messageText.value.trim()
  if (!text) return
  sendError.value = ''
  sending.value = true
  try {
    const msg = await groupsService.sendText(props.groupId, text)
    messages.value.push(msg)
    messageText.value = ''
    scrollToBottom()
  } catch (e) {
    sendError.value = e.message || 'No se pudo enviar el mensaje.'
  } finally {
    sending.value = false
  }
}

const sendFile = async (file, type) => {
  if (!file) return
  sendError.value = ''
  sending.value = true
  try {
    const msg = await groupsService.sendMedia(props.groupId, file, type)
    messages.value.push(msg)
    scrollToBottom()
  } catch (e) {
    sendError.value = e.message || 'No se pudo enviar el archivo.'
  } finally {
    sending.value = false
  }
}

const triggerFile = () => fileInput.value?.click()
const onFileSelected = event => {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  let type = 'documento'
  if (file.type.startsWith('image/')) type = 'imagen'
  else if (file.type.startsWith('video/')) type = 'video'
  else if (file.type.startsWith('audio/')) type = 'audio'
  sendFile(file, type)
}

const handlePaste = event => {
  const items = event.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type?.startsWith('image/')) {
      const file = item.getAsFile()
      if (file) {
        event.preventDefault()
        sendFile(file, 'imagen')
      }
      return
    }
  }
}

const openMembers = async () => {
  showMembersDialog.value = true
  availableUsers.value = await groupsService.listAvailableUsers()
}

const openRename = () => {
  renameValue.value = group.value?.name || ''
  showRenameDialog.value = true
}

const saveRename = async () => {
  const name = renameValue.value.trim()
  if (!name) return
  renaming.value = true
  try {
    await groupsService.renameGroup(props.groupId, name)
    showRenameDialog.value = false
    await loadGroup()
  } finally {
    renaming.value = false
  }
}

const memberIds = computed(() => new Set((group.value?.members || []).map(m => m.id)))

const addMember = async userId => {
  addingUserId.value = userId
  try {
    await groupsService.addMember(props.groupId, userId)
    await loadGroup()
  } finally {
    addingUserId.value = null
  }
}

const removeMember = async userId => {
  await groupsService.removeMember(props.groupId, userId)
  await loadGroup()
}

const fmtTime = iso => new Date(iso).toLocaleTimeString('es-PE', { hour: '2-digit', minute: '2-digit' })
</script>

<template>
  <div class="group-chat-panel">
    <template v-if="group">
      <div class="chat-header">
        <div>
          <div class="text-subtitle-1 font-weight-bold">
            <i class="ri-team-line" /> {{ group.name }}
            <button
              v-if="group.canManage"
              class="rename-btn"
              title="Editar nombre"
              @click="openRename"
            >
              <i class="ri-pencil-line" />
            </button>
          </div>
          <div class="text-caption text-medium-emphasis">
            {{ (group.members || []).map(m => m.name).join(', ') }}
          </div>
        </div>
        <VBtn
          v-if="group.canManage"
          variant="tonal"
          size="small"
          prepend-icon="ri-group-line"
          @click="openMembers"
        >
          Miembros
        </VBtn>
      </div>

      <div class="chat-messages">
        <VProgressLinear
          v-if="loadingMessages"
          indeterminate
        />
        <div
          v-for="m in messages"
          :key="m.id"
          class="message-row"
          :class="{ mine: m.authorId === auth.user?.id }"
        >
          <div class="message-bubble">
            <div class="message-author">
              {{ m.authorName }}
            </div>
            <p
              v-if="m.type === 'texto'"
              class="message-text"
            >
              {{ m.text }}
            </p>
            <img
              v-else-if="m.type === 'imagen'"
              :src="m.fileUrl"
              class="message-image"
              :alt="m.fileName"
            >
            <audio
              v-else-if="m.type === 'audio'"
              :src="m.fileUrl"
              controls
            />
            <video
              v-else-if="m.type === 'video'"
              :src="m.fileUrl"
              controls
              class="message-image"
            />
            <a
              v-else
              :href="m.fileUrl"
              target="_blank"
              rel="noopener"
              class="message-file"
            >
              <i class="ri-file-text-line" /> {{ m.fileName }}
            </a>
            <div class="message-time">
              {{ fmtTime(m.createdAt) }}
            </div>
          </div>
        </div>
        <div ref="messagesEnd" />
      </div>

      <div class="chat-composer">
        <p
          v-if="sendError"
          class="text-caption text-error px-2"
        >
          {{ sendError }}
        </p>
        <div class="composer-row">
          <VBtn
            icon="ri-attachment-line"
            variant="text"
            :disabled="sending"
            @click="triggerFile"
          />
          <input
            ref="fileInput"
            type="file"
            hidden
            @change="onFileSelected"
          >
          <textarea
            v-model="messageText"
            placeholder="Escribe un mensaje al grupo..."
            class="message-textarea"
            rows="1"
            :disabled="sending"
            @keydown.enter.exact.prevent="sendText"
            @paste="handlePaste"
          />
          <VBtn
            icon="ri-send-plane-2-line"
            color="primary"
            :loading="sending"
            @click="sendText"
          />
        </div>
      </div>
    </template>

    <VDialog
      v-model="showMembersDialog"
      max-width="480"
    >
      <VCard v-if="group">
        <VCardTitle>Miembros de {{ group.name }}</VCardTitle>
        <VCardText style="max-height: 60vh; overflow-y: auto;">
          <div
            v-for="u in availableUsers"
            :key="u.id"
            class="member-row"
          >
            <span>{{ u.name }}</span>
            <VBtn
              v-if="memberIds.has(u.id)"
              size="small"
              variant="tonal"
              color="error"
              @click="removeMember(u.id)"
            >
              Quitar
            </VBtn>
            <VBtn
              v-else
              size="small"
              variant="tonal"
              :loading="addingUserId === u.id"
              @click="addMember(u.id)"
            >
              Agregar
            </VBtn>
          </div>
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="text"
            @click="showMembersDialog = false"
          >
            Cerrar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>

    <!-- Editar nombre del grupo -->
    <VDialog
      v-model="showRenameDialog"
      max-width="420"
    >
      <VCard>
        <VCardTitle>Editar nombre del grupo</VCardTitle>
        <VCardText>
          <VTextField
            v-model="renameValue"
            label="Nombre del grupo"
            autofocus
            @keydown.enter="saveRename"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="text"
            @click="showRenameDialog = false"
          >
            Cancelar
          </VBtn>
          <VBtn
            color="primary"
            :loading="renaming"
            :disabled="!renameValue.trim()"
            @click="saveRename"
          >
            Guardar
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.group-chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.rename-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 13px;
  opacity: 0.6;
  vertical-align: middle;
  margin-left: 2px;
}

.rename-btn:hover {
  opacity: 1;
  background: rgba(var(--v-theme-on-surface), 0.08);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.message-row {
  display: flex;
}

.message-row.mine {
  justify-content: flex-end;
}

.message-bubble {
  max-width: 60%;
  background: rgba(var(--v-theme-on-surface), 0.06);
  border-radius: 10px;
  padding: 8px 12px;
}

.message-row.mine .message-bubble {
  background: rgba(var(--v-theme-primary), 0.15);
}

.message-author {
  font-size: 0.7rem;
  font-weight: 700;
  opacity: 0.7;
}

.message-text {
  margin: 2px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.message-image {
  max-width: 260px;
  border-radius: 6px;
  margin-top: 4px;
}

.message-file {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.message-time {
  font-size: 0.65rem;
  opacity: 0.6;
  text-align: right;
  margin-top: 2px;
}

.chat-composer {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  padding: 8px;
}

.composer-row {
  display: flex;
  align-items: flex-end;
  gap: 4px;
}

.message-textarea {
  flex: 1;
  resize: none;
  border: none;
  outline: none;
  background: transparent;
  font-family: inherit;
  font-size: 0.9rem;
  padding: 8px;
  max-height: 120px;
}

.member-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}
</style>
