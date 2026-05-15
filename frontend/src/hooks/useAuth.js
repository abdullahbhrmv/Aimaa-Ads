import { create } from 'zustand'
import { authAPI } from '../services/api'

const useAuthStore = create((set) => ({
  user: null,
  isLoading: true,

  login: async (username, password) => {
    const { data } = await authAPI.login({ username, password })
    localStorage.setItem('access_token', data.access)
    localStorage.setItem('refresh_token', data.refresh)
    const { data: user } = await authAPI.me()
    set({ user })
  },

  register: async (formData) => {
    await authAPI.register(formData)
  },

  fetchUser: async () => {
    try {
      const { data } = await authAPI.me()
      set({ user: data, isLoading: false })
    } catch {
      set({ user: null, isLoading: false })
    }
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ user: null })
  },
}))

export default useAuthStore
