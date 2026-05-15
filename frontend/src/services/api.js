import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Token interceptor
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Token yenileme interceptor
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (error.response?.status === 401) {
      const refresh = localStorage.getItem('refresh_token')
      if (refresh) {
        try {
          const { data } = await axios.post('/api/auth/refresh/', { refresh })
          localStorage.setItem('access_token', data.access)
          error.config.headers.Authorization = `Bearer ${data.access}`
          return api(error.config)
        } catch {
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
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
  register: (data) => api.post('/auth/register/', data),
  me: () => api.get('/auth/me/'),
}

// ─── Dashboard ───
export const dashboardAPI = {
  stats: () => api.get('/dashboard/stats/'),
  chart: (days = 7) => api.get(`/dashboard/chart/?days=${days}`),
}

// ─── Kampanyalar ───
export const campaignAPI = {
  list: (params) => api.get('/ads/campaigns/', { params }),
  get: (id) => api.get(`/ads/campaigns/${id}/`),
  create: (data) => api.post('/ads/campaigns/', data),
  update: (id, data) => api.patch(`/ads/campaigns/${id}/`, data),
  delete: (id) => api.delete(`/ads/campaigns/${id}/`),
  activate: (id) => api.post(`/ads/campaigns/${id}/activate/`),
  pause: (id) => api.post(`/ads/campaigns/${id}/pause/`),
  resume: (id) => api.post(`/ads/campaigns/${id}/resume/`),
}

// ─── Reklamlar ───
export const adAPI = {
  list: (params) => api.get('/ads/creatives/', { params }),
  create: (data) => {
    if (data instanceof FormData) {
      return api.post('/ads/creatives/', data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }
    return api.post('/ads/creatives/', data)
  },
  update: (id, data) => {
    if (data instanceof FormData) {
      return api.patch(`/ads/creatives/${id}/`, data, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    }
    return api.patch(`/ads/creatives/${id}/`, data)
  },
  delete: (id) => api.delete(`/ads/creatives/${id}/`),
}

// ─── Kanallar ───
export const channelAPI = {
  list: (params) => api.get('/channels/', { params }),
  categories: () => api.get('/channels/categories/'),
}

// ─── Analitik ───
export const analyticsAPI = {
  campaign: (id, days = 7) => api.get(`/analytics/campaign/${id}/?days=${days}`),
}

export default api
