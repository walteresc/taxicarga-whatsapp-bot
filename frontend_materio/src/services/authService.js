const AUTH_BASE = '/dashboard/api/auth'

// Alias para conversationService que también usa /dashboard
export const DASHBOARD_BASE = '/dashboard'

export const authService = {
  // Login
  async login(username, password) {
    try {
      const response = await fetch(`${AUTH_BASE}/login/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
        body: JSON.stringify({ username, password }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.error || 'Login failed')
      }

      const data = await response.json()
      localStorage.setItem('user', JSON.stringify(data.user))
      return data
    } catch (error) {
      console.error('Login error:', error)
      throw error
    }
  },

  // Logout
  async logout() {
    try {
      await fetch(`${AUTH_BASE}/logout/`, {
        method: 'POST',
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })
      localStorage.removeItem('user')
      return { status: 'ok' }
    } catch (error) {
      console.error('Logout error:', error)
      throw error
    }
  },

  // Get current user
  async getUser() {
    try {
      const response = await fetch(`${AUTH_BASE}/user/`, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })

      if (!response.ok) throw new Error('Not authenticated')
      const data = await response.json()
      localStorage.setItem('user', JSON.stringify(data.user))
      return data.user
    } catch (error) {
      localStorage.removeItem('user')
      throw error
    }
  },

  // Check if authenticated
  async checkAuth() {
    try {
      const response = await fetch(`${AUTH_BASE}/check/`, {
        headers: {
          'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'include',
      })
      const data = await response.json()
      return data.authenticated
    } catch (error) {
      return false
    }
  },

  // Get stored user (from localStorage)
  getStoredUser() {
    const user = localStorage.getItem('user')
    return user ? JSON.parse(user) : null
  },
}
