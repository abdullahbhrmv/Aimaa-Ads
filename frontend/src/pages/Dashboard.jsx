import { useEffect, useState } from 'react'
import { BarChart3, Eye, MousePointerClick, Wallet, TrendingUp } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { dashboardAPI } from '../services/api'

function StatCard({ icon: Icon, label, value, color = 'brand' }) {
  const colors = {
    brand: 'bg-brand-50 text-brand-600',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${colors[color]}`}>
          <Icon size={20} />
        </div>
        <span className="text-sm text-gray-500">{label}</span>
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

const DAY_LABELS = {
  0: 'Yak', 1: 'Dush', 2: 'Sesh', 3: 'Chor', 4: 'Pay', 5: 'Jum', 6: 'Shan',
}

function formatChartDate(dateStr) {
  const d = new Date(dateStr)
  return `${d.getDate()}/${d.getMonth() + 1}`
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [chartData, setChartData] = useState([])
  const [chartDays, setChartDays] = useState(7)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    dashboardAPI.stats()
      .then(({ data }) => setStats(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    dashboardAPI.chart(chartDays)
      .then(({ data }) => {
        setChartData(
          data.map((d) => ({
            date: formatChartDate(d.date),
            impressions: d.impressions || 0,
            clicks: d.clicks || 0,
          }))
        )
      })
      .catch(() => setChartData([]))
  }, [chartDays])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="text-gray-500 mt-1">Kampanyalaringiz umumiy ko'rinishi</p>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={BarChart3}
          label="Aktiv kampanyalar"
          value={stats?.active_campaigns || 0}
          color="brand"
        />
        <StatCard
          icon={Eye}
          label="Jami ko'rishlar"
          value={(stats?.total_impressions || 0).toLocaleString()}
          color="purple"
        />
        <StatCard
          icon={MousePointerClick}
          label="Jami bosishlar"
          value={(stats?.total_clicks || 0).toLocaleString()}
          color="green"
        />
        <StatCard
          icon={Wallet}
          label="Sarflangan"
          value={`${(stats?.total_spent || 0).toLocaleString()} UZS`}
          color="amber"
        />
      </div>

      {/* Chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Ko'rsatkichlar</h2>
            <p className="text-sm text-gray-500">Ko'rishlar va bosishlar</p>
          </div>
          <div className="flex items-center gap-2">
            {[7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => setChartDays(d)}
                className={`px-3 py-1 rounded-lg text-sm font-medium transition ${
                  chartDays === d
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {d} kun
              </button>
            ))}
          </div>
        </div>

        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[300px] text-gray-400 text-sm">
            Hali ma'lumot yo'q
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="colorImpressions" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#338cff" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#338cff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="colorClicks" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 12, fill: '#9ca3af' }} />
              <Tooltip
                contentStyle={{
                  borderRadius: '12px',
                  border: '1px solid #e5e7eb',
                  boxShadow: '0 4px 6px -1px rgba(0,0,0,0.05)',
                }}
              />
              <Area
                type="monotone"
                dataKey="impressions"
                stroke="#338cff"
                strokeWidth={2}
                fill="url(#colorImpressions)"
                name="Ko'rishlar"
              />
              <Area
                type="monotone"
                dataKey="clicks"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#colorClicks)"
                name="Bosishlar"
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
