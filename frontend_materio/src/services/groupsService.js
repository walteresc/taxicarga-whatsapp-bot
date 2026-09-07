// Chat de equipo interno (grupos de personal, no clientes). API v2, inglés
// canónico. 100% interno — nunca sale por WhatsApp, así que los adjuntos se
// suben directo a nuestro servidor (no a YCloud).
import { apiClient } from './apiClient'

const getCsrfToken = () => {
  const name = 'csrftoken'
  const cookie = document.cookie.split('; ').find(row => row.startsWith(`${name}=`))

  return cookie ? decodeURIComponent(cookie.split('=').slice(1).join('=')) : ''
}

export const groupsService = {
  listGroups: () => apiClient.get('groups/'),
  createGroup: name => apiClient.post('groups/', { name }),
  getGroup: id => apiClient.get(`groups/${id}/`),
  renameGroup: (id, name) => apiClient.patch(`groups/${id}/`, { name }),
  setGroupActive: (id, active) => apiClient.patch(`groups/${id}/`, { active }),
  setGroupArchived: (id, archived) => apiClient.patch(`groups/${id}/`, { archived }),

  listAvailableUsers: () => apiClient.get('groups/users'),
  addMember: (groupId, userId) => apiClient.post(`groups/${groupId}/members`, { userId }),
  removeMember: (groupId, userId) => apiClient.delete(`groups/${groupId}/members/${userId}`),

  listMessages: (groupId, afterId) => apiClient.get(`groups/${groupId}/messages`, afterId ? { afterId } : undefined),
  sendText: (groupId, text) => apiClient.post(`groups/${groupId}/messages`, { text }),

  async sendMedia(groupId, file, type) {
    const formData = new FormData()

    formData.append('file', file)
    formData.append('type', type)

    const response = await fetch(`/api/v2/groups/${groupId}/messages/media`, {
      method: 'POST',
      headers: { 'X-CSRFToken': getCsrfToken() },
      credentials: 'include',
      body: formData,
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`)

    return data
  },
}
