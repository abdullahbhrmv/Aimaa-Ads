import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'

import useAuthStore from './hooks/useAuth'
import Layout from './components/Layout'
import LoginPage from './pages/Login'
import RegisterPage from './pages/Register'
import DashboardPage from './pages/Dashboard'
import CampaignsPage from './pages/Campaigns'
import CampaignCreatePage from './pages/CampaignCreate'
import CampaignEditPage from './pages/CampaignEdit'
import CampaignAnalyticsPage from './pages/CampaignAnalytics'
import ChannelExplorerPage from './pages/ChannelExplorer'
import SettingsPage from './pages/Settings'
import DepositPage from './pages/Deposit'

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuthStore()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!user) return <Navigate to="/login" />
  return children
}

export default function App() {
  const { fetchUser } = useAuthStore()

  useEffect(() => {
    if (localStorage.getItem('access_token')) {
      fetchUser()
    } else {
      useAuthStore.setState({ isLoading: false })
    }
  }, [])

  return (
    <>
      <Toaster position="top-right" />
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <Layout>
                <Routes>
                  <Route path="/" element={<DashboardPage />} />
                  <Route path="/campaigns" element={<CampaignsPage />} />
                  <Route path="/campaigns/new" element={<CampaignCreatePage />} />
                  <Route path="/campaigns/:id" element={<CampaignAnalyticsPage />} />
                  <Route path="/campaigns/:id/edit" element={<CampaignEditPage />} />
                  <Route path="/channels" element={<ChannelExplorerPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/deposit" element={<DepositPage />} />
                </Routes>
              </Layout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  )
}
