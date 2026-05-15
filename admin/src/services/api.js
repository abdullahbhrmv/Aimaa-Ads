import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Token refresh interceptor
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem('admin_refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post('/api/auth/refresh/', { refresh })
          localStorage.setItem('admin_access_token', data.access)
          error.config.headers.Authorization = `Bearer ${data.access}`
          return api(error.config)
        } catch {
          localStorage.removeItem('admin_access_token')
          localStorage.removeItem('admin_refresh_token')
          window.location.href = '/login'
        }
      }
    }
    return Promise.reject(error)
  }
)

// ─── Auth ───
export const authAPI = {
  login: (data) => api.post('/auth/login/', data),
  me: () => api.get('/auth/me/'),
}

// ─── Admin Platform ───
export const adminAPI = {
  stats: () => api.get('/admin-panel/stats/'),
  // Channels
  channels: (params) => api.get('/admin-panel/channels/', { params }),
  approveChannel: (id) => api.post(`/admin-panel/channels/${id}/approve/`),
  rejectChannel: (id) => api.post(`/admin-panel/channels/${id}/reject/`),
  // Campaigns
  campaigns: (params) => api.get('/admin-panel/campaigns/', { params }),
  approveCampaign: (id) => api.post(`/admin-panel/campaigns/${id}/approve/`),
  rejectCampaign: (id, data) => api.post(`/admin-panel/campaigns/${id}/reject/`, data),
  // Users
  users: (params) => api.get('/admin-panel/users/', { params }),
  // Revenue
  revenue: (params) => api.get('/admin-panel/revenue/', { params }),
  // Categories
  categories: () => api.get('/admin-panel/categories/'),
  createCategory: (data) => api.post('/admin-panel/categories/', data),
  updateCategory: (id, data) => api.patch(`/admin-panel/categories/${id}/`, data),
  deleteCategory: (id) => api.delete(`/admin-panel/categories/${id}/`),
  // Payouts
  payouts: (params) => api.get('/admin-panel/payouts/', { params }),
  approvePayout: (id) => api.post(`/admin-panel/payouts/${id}/approve/`),
  rejectPayout: (id) => api.post(`/admin-panel/payouts/${id}/reject/`),
}

export default api
