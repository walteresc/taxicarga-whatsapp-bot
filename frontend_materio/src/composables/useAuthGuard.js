import { useRouter } from 'vue-router'
import { authService } from '@/services/authService'

export const useAuthGuard = () => {
  const router = useRouter()

  const checkAuth = async () => {
    try {
      const isAuthenticated = await authService.checkAuth()
      if (!isAuthenticated) {
        router.push('/login')
        return false
      }
      return true
    } catch (error) {
      console.error('Auth check error:', error)
      router.push('/login')
      return false
    }
  }

  const logout = async () => {
    try {
      await authService.logout()
      router.push('/login')
    } catch (error) {
      console.error('Logout error:', error)
      router.push('/login')
    }
  }

  return {
    checkAuth,
    logout,
  }
}
