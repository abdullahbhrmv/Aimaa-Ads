import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'

import useAuthStore from './hooks/useAuth'
import AdminLayout from './components/AdminLayout'
import LoginPage from './pages/Login'
import AdminDashboard from './pages/AdminDashboard'
import ChannelModeration from './pages/ChannelModeration'
import CampaignReview from './pages/CampaignReview'
import UserManagement from './pages/UserManagement'
import RevenueReport from './pages/RevenueReport'
import CategoryManagement from './pages/CategoryManagement'
import SystemSettings from './pages/SystemSettings'
import PayoutManagement from './pages/PayoutManagement'

function ProtectedRoute({ children }) {
  const { user, isLoading } = useAuthStore()

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
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
    if (localStorage.getItem('admin_access_token')) {
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
        <Route
          path="/*"
          element={
            <ProtectedRoute>
              <AdminLayout>
                <Routes>
                  <Route path="/" element={<AdminDashboard />} />
                  <Route path="/channels" element={<ChannelModeration />} />
                  <Route path="/campaigns" element={<CampaignReview />} />
                  <Route path="/users" element={<UserManagement />} />
                  <Route path="/revenue" element={<RevenueReport />} />
                  <Route path="/categories" element={<CategoryManagement />} />
                  <Route path="/payouts" element={<PayoutManagement />} />
                  <Route path="/settings" element={<SystemSettings />} />
                </Routes>
              </AdminLayout>
            </ProtectedRoute>
          }
        />
      </Routes>
    </>
  )
}
