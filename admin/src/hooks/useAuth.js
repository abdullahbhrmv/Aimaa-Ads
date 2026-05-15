import { create } from 'zustand'
import { authAPI } from '../services/api'

const useAuthStore = create((set) => ({
  user: null,
  isLoading: true,

  login: async (username, password) => {
    const { data } = await authAPI.login({ username, password })
    localStorage.setItem('admin_access_token', data.access)
    localStorage.setItem('admin_refresh_token', data.refresh)
    const { data: user } = await authAPI.me()
    if (user.role !== 'admin') {
      localStorage.removeItem('admin_access_token')
      localStorage.removeItem('admin_refresh_token')
      throw new Error('Admin huquqi yo\'q')
    }
    set({ user })
  },

  fetchUser: async () => {
    try {
      const { data } = await authAPI.me()
      if (data.role !== 'admin') {
        localStorage.removeItem('admin_access_token')
        localStorage.removeItem('admin_refresh_token')
        set({ user: null, isLoading: false })
        return
      }
      set({ user: data, isLoading: false })
    } catch {
      set({ user: null, isLoading: false })
    }
  },

  logout: () => {
    localStorage.removeItem('admin_access_token')
    localStorage.removeItem('admin_refresh_token')
    set({ user: null })
  },
}))

export default useAuthStore
