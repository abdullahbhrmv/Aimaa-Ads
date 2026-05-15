import { useEffect, useState } from 'react'
import { Users, Radio, Megaphone, DollarSign, Clock, AlertCircle } from 'lucide-react'
import { adminAPI } from '../services/api'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

function StatCard({ icon: Icon, label, value, color }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${color}`}>
          <Icon size={20} className="text-white" />
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

export default function AdminDashboard() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    adminAPI.stats()
      .then(({ data }) => setStats(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  const s = stats || {}

  const revenueData = s.revenue_chart || []

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Platform umumiy ko'rinishi</p>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard icon={Users} label="Foydalanuvchilar" value={s.total_users || 0} color="bg-blue-500" />
        <StatCard icon={Radio} label="Kanallar" value={s.total_channels || 0} color="bg-emerald-500" />
        <StatCard icon={Megaphone} label="Kampanyalar" value={s.total_campaigns || 0} color="bg-purple-500" />
        <StatCard icon={DollarSign} label="Umumiy daromad"
          value={`${Number(s.total_revenue || 0).toLocaleString()} UZS`}
          color="bg-amber-500" />
      </div>

      {/* Pending Items */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-2 mb-4">
            <Clock size={18} className="text-yellow-500" />
            <h2 className="text-lg font-semibold text-gray-900">Kutilayotganlar</h2>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 flex items-center gap-2">
                <Radio size={16} /> Kanallar
              </span>
              <span className="bg-yellow-100 text-yellow-700 px-3 py-0.5 rounded-full text-sm font-medium">
                {s.pending_channels || 0}
              </span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600 flex items-center gap-2">
                <Megaphone size={16} /> Kampanyalar
              </span>
              <span className="bg-yellow-100 text-yellow-700 px-3 py-0.5 rounded-full text-sm font-medium">
                {s.pending_campaigns || 0}
              </span>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle size={18} className="text-blue-500" />
            <h2 className="text-lg font-semibold text-gray-900">Bugungi faoliyat</h2>
          </div>
          <div className="space-y-3">
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600">Yangi foydalanuvchilar</span>
              <span className="font-semibold text-gray-900">{s.today_users || 0}</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600">Aktiv kampanyalar</span>
              <span className="font-semibold text-gray-900">{s.active_campaigns || 0}</span>
            </div>
            <div className="flex items-center justify-between py-2">
              <span className="text-gray-600">Bugungi daromad</span>
              <span className="font-semibold text-gray-900">
                {Number(s.today_revenue || 0).toLocaleString()} UZS
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Revenue Chart */}
      {revenueData.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Daromad grafigi (oxirgi 30 kun)</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={revenueData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(v) => [`${Number(v).toLocaleString()} UZS`, 'Daromad']}
                  labelStyle={{ fontWeight: 600 }}
                />
                <Bar dataKey="revenue" fill="#1a6cf5" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
