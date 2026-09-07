<template>
  <div class="conversation-sidebar">
    <!-- FILA 1: BUSCADOR -->
    <div class="conversation-search">
      <div class="search-box">
        <i class="ri-search-line search-icon" />
        <input
          v-model="searchPhone"
          type="text"
          placeholder="Buscar por nombre, teléfono o mensaje"
          class="search-input"
        >
        <button
          v-if="searchPhone"
          class="search-clear-btn"
          title="Limpiar búsqueda"
          @click="searchPhone = ''"
        >
          <i class="ri-close-line" />
        </button>
      </div>
    </div>

    <!-- Menú "más opciones" — teletransportado a <body> (igual que el menú de
         clic derecho): el sidebar recorta cualquier popover posicionado dentro,
         sin importar el z-index, así que se posiciona con coordenadas fijas. -->
    <Teleport to="body">
      <div
        v-if="showNewMenu"
        ref="newMenuRef"
        class="popover new-menu"
        :style="newMenuStyle"
      >
        <button
          class="menu-item"
          @click="showNewMenu = false; showCreateGroupDialog = true"
        >
          <i class="ri-team-line" /> Crear grupo
        </button>
        <button
          class="menu-item"
          @click="showNewMenu = false; manageCategoryOpen = 'oficina'"
        >
          <i class="ri-building-line" /> Gestionar Oficina
        </button>
        <button
          class="menu-item"
          @click="showNewMenu = false; manageCategoryOpen = 'transportista'"
        >
          <i class="ri-truck-line" /> Gestionar Transportistas
        </button>
        <button
          class="menu-item"
          @click="showNewMenu = false; manageCategoryOpen = 'campo'"
        >
          <i class="ri-tools-line" /> Gestionar Campo
        </button>
      </div>
    </Teleport>

    <ManageCategoryDialog
      v-if="manageCategoryOpen"
      :category="manageCategoryOpen"
      @close="manageCategoryOpen = null"
      @changed="loadConversations"
    />

    <!-- FILA 2: FILTROS (oculta dentro de Archivados — no aplican ahí) -->
    <div
      v-if="!showArchived"
      class="conversation-filters"
    >
      <!-- State filter tabs — su estado "activo" visual solo aplica fuera de
           Transportistas: son dos ejes distintos (Todas/Mías/No leídas filtran
           DENTRO de la vista actual; Transportistas ES la vista), pero mostrar
           "Todas" marcado a la vez que "Transportistas" confundía. -->
      <button
        v-for="tag in filterTabs"
        :key="tag"
        class="filter-tab transportistas-tab"
        :class="[{ active: activeFilters.includes(tag) && !showTransportistas && !showOficina && !showCampo }]"
        :title="tag"
        @click="toggleFilter(tag)"
      >
        {{ tag }}
        <span
          v-if="tag === 'Todas' && todasUnreadCount > 0"
          class="tab-badge"
        >{{ todasUnreadCount }}</span>
      </button>

      <!-- Advanced filters button -->
      <button
        ref="filterBtnRef"
        class="filter-btn"
        :title="activeFiltersCount > 0 ? `${activeFiltersCount} filtro(s) activo(s)` : 'Filtros avanzados'"
        @click="toggleFilterMenu"
      >
        <i class="ri-filter-line" />
        <span
          v-if="activeFiltersCount > 0"
          class="badge"
        >{{ activeFiltersCount }}</span>
      </button>

      <!-- Advanced filter menu (positioned absolutely) -->
      <div
        v-if="showFilterMenu"
        ref="filterMenuRef"
        class="filter-menu"
      >
        <div class="filter-group">
          <label class="group-title">Más filtros</label>
          <button
            v-for="tag in advancedFilterTags"
            :key="tag"
            class="menu-item"
            :class="[{ active: activeFilters.includes(tag) }]"
            @click="toggleFilter(tag)"
          >
            <i class="ri-checkbox-blank-circle-line" />
            {{ tag }}
          </button>
        </div>
        <div class="filter-group">
          <label class="group-title">Canal</label>
          <ChannelDropdown
            :active-channels="activeChannels"
            @update:active-channels="activeChannels = $event"
          />
        </div>
        <div
          v-if="activeFiltersCount > 0"
          class="filter-group"
        >
          <button
            class="menu-item clear-filters-item"
            @click="clearFilters"
          >
            <i class="ri-close-circle-line" />
            Limpiar filtros
          </button>
        </div>
      </div>
    </div>

    <!-- FILA 3: PARTICIONES (Transportistas/Oficina/Campo) — un contacto vive
         en una de estas categorías o en la bandeja normal, no es un filtro
         aditivo como Todas/Mías/No leídas, por eso van en su propia fila. -->
    <div
      v-if="!showArchived"
      class="conversation-categories"
    >
      <button
        class="filter-tab transportistas-tab"
        :class="[{ active: showTransportistas }]"
        title="Transportistas"
        @click="setCategoryView('transportistas')"
      >
        🚚 Transportistas
        <span
          v-if="transportistasUnreadCount > 0"
          class="tab-badge"
        >{{ transportistasUnreadCount }}</span>
      </button>

      <button
        class="filter-tab transportistas-tab"
        :class="[{ active: showOficina }]"
        title="Oficina"
        @click="setCategoryView('oficina')"
      >
        🏢 Oficina
        <span
          v-if="oficinaUnreadCount > 0"
          class="tab-badge"
        >{{ oficinaUnreadCount }}</span>
      </button>

      <button
        class="filter-tab transportistas-tab"
        :class="[{ active: showCampo }]"
        title="Campo"
        @click="setCategoryView('campo')"
      >
        🚛 Campo
        <span
          v-if="campoUnreadCount > 0"
          class="tab-badge"
        >{{ campoUnreadCount }}</span>
      </button>

      <button
        ref="newMenuAnchor"
        class="new-menu-btn categories-new-menu-btn"
        title="Más opciones"
        @click="toggleNewMenu"
      >
        <i class="ri-more-2-fill" />
      </button>
    </div>

    <!-- Entrada "Archivados" (estilo WhatsApp) -->
    <button
      v-if="!showArchived"
      class="archived-entry"
      @click="showArchived = true"
    >
      <i class="ri-archive-line" />
      <span class="archived-entry-label">Archivados</span>
      <span
        v-if="archivedCount > 0"
        class="archived-entry-count"
      >{{ archivedCount }}</span>
    </button>

    <!-- Cabecera al ver Archivados -->
    <div
      v-else
      class="archived-header"
    >
      <button
        class="archived-back-btn"
        @click="showArchived = false"
      >
        <i class="ri-arrow-left-line" />
      </button>
      <span>Archivados</span>
    </div>

    <!-- CONVERSATIONS LIST -->
    <div class="conversations-container">
      <!-- LOADING STATE -->
      <div
        v-if="loading"
        class="state-container"
      >
        <div
          v-for="i in 5"
          :key="`skeleton-${i}`"
          class="skeleton-item"
        >
          <div class="skeleton-avatar" />
          <div class="skeleton-content">
            <div class="skeleton-line" />
            <div class="skeleton-line short" />
          </div>
        </div>
      </div>

      <!-- ERROR STATE -->
      <div
        v-else-if="error"
        class="state-container"
      >
        <div class="empty-state">
          <i class="ri-error-warning-line error-icon" />
          <p class="error-title">
            No pudimos cargar las conversaciones
          </p>
          <button
            class="retry-btn"
            @click="loadConversations"
          >
            Reintentar
          </button>
        </div>
      </div>

      <!-- NÚMERO NUEVO: la búsqueda parece un teléfono y no hay coincidencias -->
      <div
        v-else-if="filteredConversations.length === 0 && looksLikeNewPhone"
        class="state-container"
      >
        <div class="empty-state">
          <i class="ri-add-circle-line empty-icon" />
          <p class="empty-title">
            No hay conversación con {{ newPhoneDigits }}
          </p>
          <p class="empty-text">
            Puedes iniciar una nueva conversación con este número
          </p>
          <input
            v-model="newContactName"
            type="text"
            placeholder="Nombre del contacto (opcional, si ya lo tienes guardado)"
            class="search-input"
            style="margin-bottom: 12px; max-width: 280px;"
          >
          <button
            class="clear-btn"
            :disabled="creatingConversation"
            @click="createNewConversation"
          >
            {{ creatingConversation ? 'Creando...' : `Crear conversación con ${newPhoneDigits}` }}
          </button>
          <p
            v-if="createError"
            class="empty-text"
            style="color: #d32f2f; margin-top: 8px;"
          >
            {{ createError }}
          </p>
        </div>
      </div>

      <!-- NO RESULTS STATE -->
      <div
        v-else-if="filteredConversations.length === 0 && hasActiveFilters"
        class="state-container"
      >
        <div class="empty-state">
          <i class="ri-inbox-line empty-icon" />
          <p class="empty-title">
            No encontramos conversaciones
          </p>
          <p class="empty-text">
            No hay conversaciones que coincidan con los filtros seleccionados
          </p>
          <button
            class="clear-btn"
            @click="clearFilters"
          >
            Limpiar filtros
          </button>
        </div>
      </div>

      <!-- EMPTY STATE -->
      <div
        v-else-if="filteredConversations.length === 0"
        class="state-container"
      >
        <div class="empty-state">
          <i class="ri-inbox-line empty-icon" />
          <p class="empty-title">
            {{ emptyStateTitle }}
          </p>
          <p class="empty-text">
            {{ emptyStateText }}
          </p>
        </div>
      </div>

      <!-- CONVERSATIONS -->
      <div
        v-for="conv in filteredConversations"
        :key="conv.id"
        class="conversation-item"
        :class="[{ active: conv.isGroup ? props.selectedGroupId === conv.groupId : props.selectedConversationId === conv.id }]"
        @click="conv.isGroup ? selectGroup(conv) : selectConversation(conv)"
        @contextmenu.prevent="!conv.isGroup && openContextMenu($event, conv)"
      >
        <div class="avatar">
          <div
            v-if="conv.isGroup"
            class="avatar-placeholder group-avatar"
          >
            <i class="ri-team-line" />
          </div>
          <img
            v-else-if="conv.avatar"
            :src="conv.avatar"
            :alt="conv.name"
          >
          <div
            v-else
            class="avatar-placeholder"
            :style="getAvatarStyle(conv.id)"
          >
            <span v-if="conv.name">{{ getInitials(conv.name) }}</span>
            <i
              v-else
              class="ri-account-circle-line"
            />
          </div>
        </div>
        <div class="content">
          <div class="header">
            <h4 class="name">
              {{ contactPrimary(conv) }}
            </h4>
            <span class="time">{{ formatTime(conv.lastActivity) }}</span>
            <button
              class="archive-toggle-btn"
              :title="conv.archived ? 'Desarchivar' : 'Archivar'"
              @click.stop="setArchived(conv, !conv.archived)"
            >
              <i :class="conv.archived ? 'ri-inbox-unarchive-line' : 'ri-archive-line'" />
            </button>
          </div>
          <p class="preview">
            {{ formatPreview(conv.preview) }}
          </p>
          <div class="badges">
            <span
              v-if="conv.estadoCotizacion === 'Por cotizar'"
              class="badge orange"
            >Por cotizar</span>
            <span
              v-if="conv.attentionMode === 'bot'"
              class="badge"
            >Bot</span>
            <span
              v-if="conv.attentionMode === 'advisor'"
              class="badge"
            >Asesor</span>
            <span
              v-if="conv.attentionMode === 'unassigned'"
              class="badge gray"
            >Sin asignar</span>
            <span
              v-if="conv.attentionMode === 'closed'"
              class="badge gray"
            >Cerrada</span>
            <span
              v-if="conv.unread > 0"
              class="badge-number"
            >{{ conv.unread }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Menú de clic derecho — teletransportado a <body> (igual que en los mensajes):
         .conversations-container tiene overflow-y:auto y recortaría el menú si se
         posicionara dentro, sin importar el z-index. -->
    <Teleport to="body">
      <div
        v-if="contextMenuFor"
        ref="contextMenuRef"
        class="context-menu"
        :style="contextMenuStyle"
        @click.stop
      >
        <button
          class="context-menu-item"
          @click="handleContextArchive"
        >
          <i :class="contextMenuFor.archived ? 'ri-inbox-unarchive-line' : 'ri-archive-line'" />
          {{ contextMenuFor.archived ? 'Desarchivar' : 'Archivar' }}
        </button>
        <button
          v-if="contextMenuFor.is_oficina"
          class="context-menu-item"
          @click="handleContextRemoveCategory('oficina')"
        >
          <i class="ri-close-circle-line" /> Quitar de Oficina
        </button>
        <button
          v-if="contextMenuFor.is_transportista"
          class="context-menu-item"
          @click="handleContextRemoveCategory('transportista')"
        >
          <i class="ri-close-circle-line" /> Quitar de Transportistas
        </button>
        <button
          v-if="contextMenuFor.is_campo"
          class="context-menu-item"
          @click="handleContextRemoveCategory('campo')"
        >
          <i class="ri-close-circle-line" /> Quitar de Campo
        </button>
      </div>
    </Teleport>

    <!-- Crear grupo -->
    <VDialog
      v-model="showCreateGroupDialog"
      max-width="420"
    >
      <VCard>
        <VCardTitle>Nuevo grupo</VCardTitle>
        <VCardText>
          <VTextField
            v-model="newGroupName"
            label="Nombre del grupo"
            autofocus
            @keydown.enter="createGroup"
          />
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn
            variant="text"
            @click="showCreateGroupDialog = false"
          >
            Cancelar
          </VBtn>
          <VBtn
            color="primary"
            :loading="creatingGroup"
            :disabled="!newGroupName.trim()"
            @click="createGroup"
          >
            Crear
          </VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { conversationService } from '@/services/conversationService'
import { groupsService } from '@/services/groupsService'
import ChannelDropdown from './components/ChannelDropdown.vue'
import ManageCategoryDialog from './components/ManageCategoryDialog.vue'

import { useConversationsStore } from '@/stores/conversationsStore'

const props = defineProps({
  selectedConversationId: {
    type: Number,
    default: null,
  },
  selectedGroupId: {
    type: Number,
    default: null,
  },
})

const emit = defineEmits(['conversation-selected', 'group-selected', 'update-count', 'update-view'])

const conversationsStore = useConversationsStore()

// Grupos internos: se mezclan como un contacto más en la lista principal (no
// son ConversacionWhatsApp, viven en su propio modelo apps/grupos_internos).
// Se refrescan por polling, igual de simple que el resto de la bandeja.
const groups = ref([])
let groupsPollTimer = null

const loadGroups = async () => {
  try {
    groups.value = await groupsService.listGroups()
  } catch (err) {
    console.error('[ConversationList] Failed to load groups:', err)
  }
}

const selectGroup = g => {
  emit('group-selected', { id: g.groupId ?? g.id })
}

// Crear grupo (menú de 3 puntos junto al buscador)
const showNewMenu = ref(false)
const newMenuAnchor = ref(null)
const newMenuRef = ref(null)
const newMenuStyle = ref({})
const showCreateGroupDialog = ref(false)
const manageCategoryOpen = ref(null) // null | 'oficina' | 'transportista' | 'campo'
const newGroupName = ref('')
const creatingGroup = ref(false)

const toggleNewMenu = () => {
  if (showNewMenu.value) {
    showNewMenu.value = false

    return
  }
  const rect = newMenuAnchor.value?.getBoundingClientRect()
  if (rect) {
    newMenuStyle.value = {
      position: 'fixed',
      top: `${rect.bottom + 4}px`,
      left: `${rect.right}px`,
      transform: 'translateX(-100%)',
    }
  }
  showNewMenu.value = true
}

const closeNewMenuIfOutside = event => {
  if (
    showNewMenu.value
    && !newMenuRef.value?.contains(event.target)
    && !newMenuAnchor.value?.contains(event.target)
  ) {
    showNewMenu.value = false
  }
}

const createGroup = async () => {
  const name = newGroupName.value.trim()
  if (!name) return
  creatingGroup.value = true
  try {
    const group = await groupsService.createGroup(name)
    newGroupName.value = ''
    showCreateGroupDialog.value = false
    await loadGroups()
    selectGroup(group)
  } finally {
    creatingGroup.value = false
  }
}
const loading = ref(false)
const error = ref(false)
const searchPhone = ref('')
const activeFilters = ref(['Todas'])
const activeChannels = ref(['Todos'])
const showFilterMenu = ref(false)
const filterBtnRef = ref(null)
const filterMenuRef = ref(null)

const closeFilterMenuIfOutside = event => {
  if (
    showFilterMenu.value
    && !filterMenuRef.value?.contains(event.target)
    && !filterBtnRef.value?.contains(event.target)
  ) {
    showFilterMenu.value = false
  }
}
const showArchived = ref(false)
const showTransportistas = ref(false)
const showOficina = ref(false)
const showCampo = ref(false)

// Transportistas/Oficina/Campo son mutuamente excluyentes entre sí (un
// contacto vive en una sola de estas particiones a la vez).
const setCategoryView = category => {
  showTransportistas.value = category === 'transportistas' ? !showTransportistas.value : false
  showOficina.value = category === 'oficina' ? !showOficina.value : false
  showCampo.value = category === 'campo' ? !showCampo.value : false
  // Entrar a una partición = "muéstrame TODOS los de esta categoría". Si quedaba
  // un filtro tipo "Bot"/"No leídas" activo de antes, escondía contactos de la
  // partición sin que se note (los tabs de filtro no se ven marcados aquí).
  if (showTransportistas.value || showOficina.value || showCampo.value) {
    activeFilters.value = ['Todas']
  }
}
const filterTabs = ['Todas', 'No leídas', 'Bot', 'Asesor']
const advancedFilterTags = ['Mías', 'Sin asignar', 'Cerradas']

const totalCount = computed(() => conversationsStore.conversations.filter(c => !c.archived).length)
const archivedCount = computed(() => conversationsStore.conversations.filter(c => c.archived).length)

// Suma de no leídos SOLO de transportistas — así el asesor ve, sin entrar a la
// pestaña, que hay algo nuevo esperando ahí (nunca se mezcla con el contador
// de la vista de clientes, que ya excluye transportistas por construcción).
const transportistasUnreadCount = computed(() =>
  conversationsStore.conversations
    .filter(conv => conv.is_transportista && !conv.archived)
    .reduce((sum, conv) => sum + (conv.unread || 0), 0)
)
const oficinaUnreadCount = computed(() =>
  conversationsStore.conversations
    .filter(conv => conv.is_oficina && !conv.archived)
    .reduce((sum, conv) => sum + (conv.unread || 0), 0)
)
const campoUnreadCount = computed(() =>
  conversationsStore.conversations
    .filter(conv => conv.is_campo && !conv.archived)
    .reduce((sum, conv) => sum + (conv.unread || 0), 0)
)
// "Todas" = bandeja normal de clientes (sin transportistas/oficina/campo, que
// tienen su propio badge). Se descuenta solo al abrir la conversación (ver
// ConversationPanel: updateConversationState(..., { unread: 0 })).
const todasUnreadCount = computed(() =>
  conversationsStore.conversations
    .filter(conv => !conv.archived && !conv.is_transportista && !conv.is_oficina && !conv.is_campo)
    .reduce((sum, conv) => sum + (conv.unread || 0), 0)
)

const activeFiltersCount = computed(() => {
  const count = activeFilters.value.filter(f => f !== 'Todas').length +
    activeChannels.value.filter(c => c !== 'Todos').length

  
  return count > 0 ? count : 0
})

const emptyStateTitle = computed(() => {
  if (showArchived.value) return 'No hay conversaciones archivadas'
  if (showTransportistas.value) return 'Aún no hay transportistas'
  if (showOficina.value) return 'Aún no hay contactos de Oficina'
  if (showCampo.value) return 'Aún no hay contactos de Campo'

  return 'Aún no hay conversaciones'
})

const emptyStateText = computed(() => {
  if (showArchived.value) return 'Las que archives aparecerán aquí'
  if (showTransportistas.value) return 'Aparecerán aquí cuando un transportista responda a una publicación'
  if (showOficina.value) return 'Marca un contacto como Oficina desde el menú de la conversación'
  if (showCampo.value) return 'Aparecen solo si el número coincide con un Conductor o Ayudante registrado y activo'

  return 'Las nuevas conversaciones aparecerán aquí'
})

// Número nuevo: la búsqueda son puros dígitos (con o sin +/espacios/guiones)
// y tiene largo de teléfono real — evita disparar el CTA con nombres cortos
// o texto que solo por casualidad tiene algún dígito.
const newPhoneDigits = computed(() => searchPhone.value.replace(/\D/g, ''))
const looksLikeNewPhone = computed(() => {
  const text = searchPhone.value.trim()
  if (!text) return false

  return newPhoneDigits.value.length >= 8 && /^[+\d\s()-]+$/.test(text)
})

const creatingConversation = ref(false)
const createError = ref('')
const newContactName = ref('')

const createNewConversation = async () => {
  createError.value = ''
  creatingConversation.value = true
  try {
    const data = await conversationService.createManualConversation(newPhoneDigits.value, newContactName.value)
    searchPhone.value = ''
    newContactName.value = ''
    await conversationsStore.loadInitial()
    const conv = conversationsStore.getConversation(data.conversation_id)
    if (conv) selectConversation(conv)
  } catch (error) {
    createError.value = error.message || 'No se pudo crear la conversación.'
  } finally {
    creatingConversation.value = false
  }
}

const hasActiveFilters = computed(() => {
  return searchPhone.value.trim() !== '' ||
    !activeFilters.value.includes('Todas') ||
    !activeChannels.value.includes('Todos')
})

// Grupos internos mezclados como un contacto más (tipo WhatsApp) — no son
// ConversacionWhatsApp, se adaptan a la misma forma para reusar la fila,
// el buscador y el archivado. Se distinguen por `isGroup` + `groupId`.
const mappedGroups = computed(() => groups.value.map(g => ({
  id: `group-${g.id}`,
  isGroup: true,
  groupId: g.id,
  name: g.name,
  archived: g.archived,
  is_transportista: false,
  is_oficina: false,
  is_campo: false,
  lastActivity: g.lastMessageAt,
  preview: g.lastMessagePreview
    ? (g.lastMessageAuthor ? `${g.lastMessageAuthor}: ${g.lastMessagePreview}` : g.lastMessagePreview)
    : `${g.memberCount} miembro${g.memberCount === 1 ? '' : 's'}`,
})))

const filteredConversations = computed(() => {
  const merged = [...conversationsStore.conversations, ...mappedGroups.value]
    .sort((a, b) => new Date(b.lastActivity || 0) - new Date(a.lastActivity || 0))

  // Archivadas, Transportistas, Oficina y Campo: particiones independientes
  // del resto de filtros (no son "Mías"/"No leídas" — son otro eje: dónde
  // vive la conversación, y quién es el contacto). Archivados manda primero
  // (una conversación archivada nunca se ve en ninguna otra vista).
  const inAnyCategoryView = showTransportistas.value || showOficina.value || showCampo.value
  let filtered = merged.filter(conv => {
    if (showArchived.value) return conv.archived
    if (conv.archived) return false
    if (conv.isGroup) return !inAnyCategoryView
    if (showTransportistas.value) return conv.is_transportista
    if (showOficina.value) return conv.is_oficina
    if (showCampo.value) return conv.is_campo

    return !conv.is_transportista && !conv.is_oficina && !conv.is_campo
  })

  if (searchPhone.value) {
    const query = searchPhone.value.toLowerCase().trim()
    // Buscar por número aunque el asesor escriba espacios/guiones/+: se compara
    // solo dígito contra dígito.
    const queryDigits = query.replace(/\D/g, '')

    filtered = filtered.filter(conv => {
      const name = (conv.profile_name || conv.name || '').toLowerCase()
      const phone = (conv.phone || '').toLowerCase()
      const phoneDigits = phone.replace(/\D/g, '')

      return name.includes(query) ||
        phone.includes(query) ||
        (queryDigits.length >= 3 && phoneDigits.includes(queryDigits)) ||
        (conv.preview && conv.preview.toLowerCase().includes(query)) ||
        (conv.resumen && conv.resumen.toLowerCase().includes(query))
    })
  }

  if (!activeFilters.value.includes('Todas')) {
    filtered = filtered.filter(conv => {
      // Los filtros Mías/No leídas/etc. son conceptos de conversación de
      // cliente (responsable, attentionMode) — un grupo siempre pasa.
      if (conv.isGroup) return true
      if (activeFilters.value.includes('Mías') && (!conv.responsable || !conv.responsable.id)) return false
      if (activeFilters.value.includes('No leídas') && conv.unread === 0) return false
      if (activeFilters.value.includes('Sin asignar') && conv.responsable && conv.responsable.id) return false
      if (activeFilters.value.includes('Bot') && conv.attentionMode !== 'bot') return false
      if (activeFilters.value.includes('Asesor') && conv.attentionMode !== 'advisor') return false
      if (activeFilters.value.includes('Cerradas') && conv.attentionMode !== 'closed') return false
      
      return true
    })
  }

  if (!activeChannels.value.includes('Todos')) {
    filtered = filtered.filter(conv => {
      if (conv.isGroup) return true
      const channelId = conv.channel?.id || conv.channel_id
      return activeChannels.value.includes(String(channelId))
    })
  }

  // Ensure conversations remain sorted by lastActivity (most recent first)
  // Backend already sorts, but preserve order in filtered results
  return filtered
})


const toggleFilterMenu = () => {
  showFilterMenu.value = !showFilterMenu.value
}

const toggleFilter = tag => {
  if (tag === 'Todas') {
    // "Todas" es la salida universal a la vista normal — el usuario espera
    // que lo saque de Transportistas/Oficina/Campo, no solo que limpie
    // Mías/No leídas.
    activeFilters.value = ['Todas']
    showTransportistas.value = false
    showOficina.value = false
    showCampo.value = false
  } else if (activeFilters.value.includes(tag)) {
    // Clic en el filtro ya activo → vuelve a "Todas".
    activeFilters.value = ['Todas']
  } else {
    // Selección única: un solo filtro a la vez, reemplaza al anterior.
    activeFilters.value = [tag]
  }

  // Close filter menu after selection
  showFilterMenu.value = false
}

const toggleChannel = channel => {
  if (channel === 'Todos') {
    activeChannels.value = ['Todos']
  } else {
    const index = activeChannels.value.indexOf(channel)
    if (index > -1) {
      activeChannels.value.splice(index, 1)
    } else {
      const todoIndex = activeChannels.value.indexOf('Todos')
      if (todoIndex > -1) {
        activeChannels.value.splice(todoIndex, 1)
      }
      activeChannels.value.push(channel)
    }
    if (activeChannels.value.length === 0) {
      activeChannels.value = ['Todos']
    }
  }
}

const clearFilters = () => {
  searchPhone.value = ''
  activeFilters.value = ['Todas']
  activeChannels.value = ['Todos']
}

// Clic en "Bandeja de entrada" del menú lateral estando ya en esta página: Vue
// Router no re-navega (misma ruta), así que sin esto el usuario queda atascado
// en la partición/filtro donde se haya quedado. NavItems.vue dispara este
// evento cuando detecta que ya estás en /atencion/bandeja-entrada.
const resetToTodas = () => {
  showArchived.value = false
  showTransportistas.value = false
  showOficina.value = false
  showCampo.value = false
  clearFilters()
}

const selectConversation = conv => {
  emit('conversation-selected', conv)
}

const formatTime = time => {
  if (!time) return ''
  const date = new Date(time)
  const now = new Date()

  // Get date at start of day (00:00:00)
  const dateAtMidnight = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const nowAtMidnight = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const diffDays = (nowAtMidnight - dateAtMidnight) / (1000 * 60 * 60 * 24)

  // Today: show time (HH:MM)
  if (diffDays < 1) {
    return date.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' })
  }

  // Yesterday: show "Ayer"
  if (diffDays < 2) return 'Ayer'

  // Last 7 days: show day name (Lun, Mar, etc)
  if (diffDays < 7) {
    const dayName = date.toLocaleDateString('es-ES', { weekday: 'short' })
    
    return dayName.charAt(0).toUpperCase() + dayName.slice(1)
  }

  // Older: show date (dd/mm)
  return date.toLocaleDateString('es-ES', { month: '2-digit', day: '2-digit' })
}

const getInitials = name => {
  if (!name) return ''
  
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)
}

const formatPreview = text => {
  if (!text) return 'Conversación nueva'

  // Normalize common message types
  if (text.includes('Imagen') || text.match(/📷|Foto/i)) return '📷 Foto'
  if (text.includes('Audio') || text.match(/🎤|Audio/i)) return '🎤 Audio'
  if (text.includes('Documento') || text.match(/📄|Documento/i)) return '📄 Documento'
  if (text.includes('Ubicación') || text.match(/📍|Ubicación/i)) return '📍 Ubicación'
  
  return text
}

const getChannelIcon = channel => {
  const icons = {
    Todos: 'global-line',
    WhatsApp: 'whatsapp-line',
    Correo: 'mail-line',
    Instagram: 'instagram-line',
    Facebook: 'facebook-circle-line',
    'Chat web': 'chat-3-line',
    TikTok: 'tiktok-line',
    Otros: 'more-2-fill',
  }

  
  return icons[channel] || 'global-line'
}

const getAvatarStyle = contactId => {
  const colors = ['#FF6B9D', '#C44569', '#F8B500', '#56AB2F', '#0085CA', '#662E9B']
  const index = Math.abs(contactId % colors.length)
  
  return {
    backgroundColor: colors[index],
    color: '#fff',
  }
}

const formatPhone = phone => {
  if (!phone) return ''
  if (phone.startsWith('+')) {
    return phone.slice(0, 3) + ' ' + phone.slice(3)
  }

  return phone
}

// La lista muestra UNA sola línea de identificación + el preview del mensaje. El
// teléfono / ID de WhatsApp vive en el panel de info de la derecha, no aquí (no
// saturar la lista). Nombre de perfil si identifica; si no, @username de
// WhatsApp; si no, el número; si no, el ID de WhatsApp.
const isNameUsable = conv => {
  if (conv.name_usable === false) return false
  if (conv.name_usable === true) return true

  return Boolean(conv.name || conv.profile_name) // compat: eventos viejos sin el flag
}

const contactPrimary = conv => {
  if (conv.isGroup) return conv.name
  if (isNameUsable(conv)) return conv.profile_name || conv.name
  if (!conv.phone) return 'Contacto sin identificar'

  return conv.phone_is_id ? conv.phone : formatPhone(conv.phone)
}

/** Archive/unarchive — CRM-only state, no confirmation (low-risk, reversible).
 * Removes the conversation from local view immediately; if it's the currently open
 * one, also tell the parent so it can clear the panel (matches WhatsApp: archiving
 * the open chat closes it). Live for other sessions via the conversation.updated
 * SSE event (archivada is a significant field — see signals.py). */
const setArchived = async (conv, archived) => {
  if (conv.isGroup) {
    try {
      const updated = await groupsService.setGroupArchived(conv.groupId, archived)
      const idx = groups.value.findIndex(g => g.id === conv.groupId)
      if (idx >= 0) groups.value[idx] = updated
      if (archived && props.selectedGroupId === conv.groupId) {
        emit('group-selected', null)
      }
    } catch (err) {
      console.error('[ConversationList] Failed to archive group:', err)
    }

    return
  }

  const action = archived ? 'archivar' : 'desarchivar'

  try {
    const response = await fetch(`/dashboard/whatsapp/conversaciones/${conv.id}/${action}/`, {
      method: 'POST',
      headers: { 'X-CSRFToken': conversationService.getCsrfToken() },
      credentials: 'include',
    })

    if (response.ok) {
      // updateConversationState does a plain shallow merge (no recomputed unread/
      // attentionMode defaults like upsertConversation) — needed here since this is
      // a PARTIAL patch and upsertConversation would otherwise reset unread to 0.
      conversationsStore.updateConversationState(conv.id, { archived })
      if (props.selectedConversationId === conv.id) {
        emit('conversation-selected', null)
      }
    }
  } catch (err) {
    console.error(`[ConversationList] Failed to ${action} conversation:`, err)
  }
}

const contextMenuFor = ref(null)
const contextMenuStyle = ref({})
const contextMenuRef = ref(null)

const openContextMenu = (event, conv) => {
  contextMenuFor.value = conv
  contextMenuStyle.value = {
    position: 'fixed',
    top: `${event.clientY}px`,
    left: `${event.clientX}px`,
  }
}

const handleContextArchive = () => {
  if (!contextMenuFor.value) return
  setArchived(contextMenuFor.value, !contextMenuFor.value.archived)
  contextMenuFor.value = null
}

// Quitar de Oficina/Transportistas/Campo desde el clic derecho — al sacarlo,
// la conversación cae sola en "Todos" (misma partición client-side que ya
// usan las pestañas, ver filteredConversations). Los setters van envueltos en
// arrow: conversationService.setX usa `this` internamente y se perdería si se
// referencia el método suelto.
const CATEGORY_SETTERS = {
  oficina: { setter: (id, v) => conversationService.setOficina(id, v), field: 'is_oficina' },
  transportista: { setter: (id, v) => conversationService.setTransportista(id, v), field: 'is_transportista' },
  campo: { setter: (id, v) => conversationService.setCampo(id, v), field: 'is_campo' },
}

const handleContextRemoveCategory = async category => {
  const conv = contextMenuFor.value
  contextMenuFor.value = null
  if (!conv) return
  const { setter, field } = CATEGORY_SETTERS[category]
  try {
    await setter(conv.id, false)
    conversationsStore.updateConversationState(conv.id, { [field]: false })
    // Campo se auto-detecta por teléfono: si el número coincide con un
    // Conductor/Ayudante activo el backend lo vuelve a marcar en la próxima
    // recarga aunque el flag manual quede en false — recargar deja ver el
    // estado real en vez del optimista.
    await loadConversations()
  } catch (err) {
    console.error(`[ConversationList] Failed to remove from ${category}:`, err)
  }
}


// mousedown + capture (same pattern used for the message menu/other popovers in
// this app): closes on any click outside — including right-clicking a DIFFERENT
// row, which should move the menu, not leave two open.
const closeContextMenuIfOutside = event => {
  if (contextMenuFor.value && !contextMenuRef.value?.contains(event.target)) {
    contextMenuFor.value = null
  }
}

const loadConversations = async () => {
  loading.value = true
  error.value = false
  try {
    await conversationsStore.loadInitial()
  } catch (err) {
    console.error('Error loading conversations:', err)
    error.value = true
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  // Load initial conversations from store
  // useWhatsAppRealtime already handles SSE updates to conversationsStore
  await loadConversations()
  document.addEventListener('mousedown', closeContextMenuIfOutside, true)
  document.addEventListener('mousedown', closeNewMenuIfOutside, true)
  document.addEventListener('mousedown', closeFilterMenuIfOutside, true)
  window.addEventListener('bandeja:reset-view', resetToTodas)

  await loadGroups()
  groupsPollTimer = setInterval(loadGroups, 5000)
})

onUnmounted(() => {
  // Cleanup: store handles its own lifecycle
  document.removeEventListener('mousedown', closeContextMenuIfOutside, true)
  document.removeEventListener('mousedown', closeNewMenuIfOutside, true)
  document.removeEventListener('mousedown', closeFilterMenuIfOutside, true)
  window.removeEventListener('bandeja:reset-view', resetToTodas)
  if (groupsPollTimer) clearInterval(groupsPollTimer)
})

// Emit count update whenever filtered results change
watch(() => filteredConversations.value.length, newCount => {
  emit('update-count', newCount)
})

// Vista actual — la cabecera la usa para el título y para mostrar el control del
// bot que corresponde (clientes vs transportistas). Prioridad: archivados manda,
// luego transportistas, luego la bandeja normal de clientes.
const currentViewName = computed(() => {
  if (showArchived.value) return 'archived'
  if (showTransportistas.value) return 'transportistas'
  if (showOficina.value) return 'oficina'
  if (showCampo.value) return 'campo'

  return 'inbox'
})

watch(currentViewName, v => emit('update-view', v), { immediate: true })
</script>

<style scoped>
.conversation-sidebar {
  /* flex, not grid: the number of top-level rows here varies (filtros y la fila de
     Archivados/cabecera son v-if) — a fixed grid-template-rows count breaks (and
     overlaps rows) the moment the number of children doesn't match its track count,
     which is exactly what happened when the Archivados row was added. Flex just
     stacks whatever is actually rendered, in order, no track count to keep in sync. */
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #fff;
  border-right: 1px solid #e0e0e0;
  width: 350px;
  min-height: 0;
  overflow: visible;
}

/* FILA 1: BUSCADOR */
.conversation-search {
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.search-box {
  position: relative;
  flex: 1;
  min-width: 0;
}

.search-icon {
  position: absolute;
  left: 8px;
  top: 50%;
  transform: translateY(-50%);
  color: #999;
  font-size: 16px;
  pointer-events: none;
}

.search-input {
  width: 100%;
  padding: 6px 32px 6px 32px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  font-size: 12px;
  height: 42px;
  background: #fff;
  transition: border-color 0.2s;
}

.search-clear-btn {
  position: absolute;
  right: 4px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: #999;
  font-size: 14px;
  cursor: pointer;
}

.search-clear-btn:hover {
  background: #f0f0f0;
  color: #666;
}

.search-input:focus {
  outline: none;
  border-color: var(--v-primary-base, #ff6b3d);
}

.search-input::placeholder {
  color: #ccc;
}

/* FILA 2: FILTROS */
.conversation-filters {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px 4px;
  min-height: auto;
  flex-shrink: 0;
  position: relative;
  z-index: 100;
}

/* FILA 3: PARTICIONES (Transportistas/Oficina/Campo) */
.conversation-categories {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px 8px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.08);
  flex-wrap: wrap;
}

.filter-tab {
  padding: 4px 10px;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 16px;
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
  min-width: fit-content;
}

.transportistas-tab {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--v-error-base, #f87171);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.filter-tab:hover {
  border-color: #999;
  background: #f9f9f9;
}

.filter-tab.active {
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border-color: var(--v-primary-base, #ff6b3d);
}

.filter-btn {
  position: relative;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid #ddd;
  background: #fff;
  border-radius: 4px;
  color: #666;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
}

.filter-btn:hover {
  border-color: #999;
  background: #f9f9f9;
}

.filter-btn .badge {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  font-size: 9px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
}

.filter-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: 10000;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 180px;
}

.new-menu-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: #666;
  font-size: 18px;
}

.new-menu-btn:hover {
  background: #f0f0f0;
}

.categories-new-menu-btn {
  margin-left: auto;
}

.clear-filters-item {
  color: #d32f2f;
}

/* Posición real la da :style (fixed, calculada del botón) — Teleported a
   <body> para no quedar recortado por el overflow del sidebar. */
.new-menu {
  z-index: 10000;
  background: white;
  border: 1px solid #ddd;
  border-radius: 4px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 180px;
  padding: 4px;
}

.filter-group {
  padding: 8px 0;
}

.group-title {
  display: block;
  padding: 6px 12px;
  font-size: 10px;
  font-weight: 600;
  color: #999;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 12px;
  border: none;
  background: none;
  font-size: 11px;
  color: #333;
  text-align: left;
  cursor: pointer;
  transition: background 0.2s;
}

.menu-item:hover {
  background: #f5f5f5;
}

.menu-item.active {
  color: var(--v-primary-base, #ff6b3d);
  font-weight: 600;
}

.menu-item i {
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s;
}

.menu-item.active i {
  opacity: 1;
}


.conversations-container {
  flex: 1 1 auto;
  overflow-y: auto;
  overflow-x: hidden;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.state-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
}

.skeleton-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.skeleton-avatar {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  flex-shrink: 0;
}

.skeleton-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skeleton-line {
  height: 8px;
  background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
  background-size: 200% 100%;
  animation: loading 1.5s infinite;
  border-radius: 2px;
  width: 100%;
}

.skeleton-line.short {
  width: 70%;
}

@keyframes loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.empty-state {
  text-align: center;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: center;
}

.empty-icon,
.error-icon {
  font-size: 48px;
  color: #ddd;
}

.error-icon {
  color: #f87171;
}

.empty-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #333;
}

.empty-text {
  margin: 0;
  font-size: 12px;
  color: #999;
}

.retry-btn,
.clear-btn {
  padding: 6px 16px;
  background: var(--v-primary-base, #ff6b3d);
  color: white;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}

.retry-btn:hover,
.clear-btn:hover {
  opacity: 0.9;
}

.conversation-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background 0.15s;
  min-height: 88px;
  border-left: 3px solid transparent;
}

.conversation-item:hover {
  background: #fafafa;
}

.conversation-item.active {
  background: #fffaf5;
  border-left-color: var(--v-primary-base, #ff6b3d);
}

.avatar {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  width: 100%;
  height: 100%;
  background: #e0e0e0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 16px;
  color: #fff;
  text-transform: uppercase;
}

.avatar-placeholder.group-avatar {
  background: #6d5dfc;
}

.avatar-placeholder i {
  font-size: 24px;
  color: #999;
}

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 6px;
}

.archive-toggle-btn {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  background: transparent;
  color: #999;
  border-radius: 50%;
  cursor: pointer;
  font-size: 13px;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
}

.conversation-item:hover .archive-toggle-btn {
  opacity: 1;
}

.archive-toggle-btn:hover {
  background: #eee;
  color: #555;
}

.archived-entry {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  flex-shrink: 0;
  padding: 10px 16px;
  border: none;
  border-bottom: 1px solid #e0e0e0;
  background: #fff;
  cursor: pointer;
  font-size: 13px;
  color: #333;
  text-align: left;
}

.archived-entry:hover {
  background: #f5f5f5;
}

.archived-entry i {
  font-size: 18px;
  color: #667781;
}

.archived-entry-label {
  flex: 1;
  font-weight: 500;
}

.archived-entry-count {
  font-size: 12px;
  color: #667781;
}

.archived-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
  padding: 10px 16px;
  border-bottom: 1px solid #e0e0e0;
  font-weight: 600;
  font-size: 14px;
}

.archived-back-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 18px;
  color: #333;
  padding: 4px;
}

.context-menu {
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 6px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  min-width: 160px;
  z-index: 20000;
  overflow: hidden;
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 14px;
  border: none;
  background: transparent;
  color: #333;
  font-size: 13px;
  cursor: pointer;
  text-align: left;
}

.context-menu-item:hover {
  background: #f5f5f5;
}

.context-menu-item i {
  font-size: 14px;
}

.name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #333;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.time {
  font-size: 11px;
  color: #999;
  flex-shrink: 0;
  white-space: nowrap;
}

.preview {
  margin: 0;
  font-size: 13px;
  color: #666;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.2;
}

.badges {
  display: flex;
  gap: 4px;
  align-items: center;
  flex-wrap: wrap;
}

.badge {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  background: #e8eaf6;
  color: var(--v-primary-base, #ff6b3d);
  white-space: nowrap;
}

.badge.orange {
  background: #ffe8d6;
  color: var(--v-primary-base, #ff6b3d);
}

.badge.gray {
  background: #f0f0f0;
  color: #666;
}

.badge-number {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--v-error-base, #f87171);
  color: white;
  font-size: 10px;
  font-weight: 600;
}
</style>
