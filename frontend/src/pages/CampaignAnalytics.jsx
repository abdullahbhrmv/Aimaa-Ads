import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Eye, MousePointerClick, Wallet, Target, ArrowLeft, Pencil } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { campaignAPI, analyticsAPI } from '../services/api'

const statusStyles = {
  draft: 'bg-gray-100 text-gray-600',
  pending: 'bg-yellow-100 text-yellow-700',
  active: 'bg-emerald-100 text-emerald-700',
  paused: 'bg-orange-100 text-orange-700',
  completed: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-700',
}

const statusLabels = {
  draft: 'Taslak',
  pending: 'Kutilmoqda',
  active: 'Aktiv',
  paused: 'Pauza',
  completed: 'Tugallangan',
  rejected: 'Rad etilgan',
}

function StatCard({ icon: Icon, label, value, color }) {
  const colors = {
    brand: 'bg-brand-50 text-brand-600',
    green: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    purple: 'bg-purple-50 text-purple-600',
  }
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-2 mb-2">
        <div className={`p-1.5 rounded-lg ${colors[color]}`}>
          <Icon size={16} />
        </div>
        <span className="text-xs text-gray-500">{label}</span>
      </div>
      <p className="text-xl font-bold text-gray-900">{value}</p>
    </div>
  )
}

export default function CampaignAnalyticsPage() {
  const { id } = useParams()
  const [campaign, setCampaign] = useState(null)
  const [chartData, setChartData] = useState([])
  const [chartDays, setChartDays] = useState(7)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    campaignAPI.get(id)
      .then(({ data }) => setCampaign(data))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  useEffect(() => {
    analyticsAPI.campaign(id, chartDays)
      .then(({ data }) => {
        setChartData(data.map((d) => ({
          date: `${new Date(d.date).getDate()}/${new Date(d.date).getMonth() + 1}`,
          impressions: d.total_impressions || 0,
          clicks: d.total_clicks || 0,
          spent: parseFloat(d.total_spent || 0),
        })))
      })
      .catch(() => setChartData([]))
  }, [id, chartDays])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!campaign) {
    return <p className="text-gray-400">Kampaniya topilmadi</p>
  }

  const totalImpressions = campaign.ads?.reduce((s, a) => s + (a.impressions || 0), 0) || 0
  const totalClicks = campaign.ads?.reduce((s, a) => s + (a.clicks || 0), 0) || 0
  const ctr = totalImpressions > 0 ? ((totalClicks / totalImpressions) * 100).toFixed(2) : '0.00'

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div>
          <Link to="/campaigns" className="text-sm text-brand-600 hover:underline flex items-center gap-1 mb-2">
            <ArrowLeft size={14} /> Kampanyalar
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">{campaign.name}</h1>
            <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyles[campaign.status]}`}>
              {statusLabels[campaign.status]}
            </span>
          </div>
        </div>
        <Link
          to={`/campaigns/${id}/edit`}
          className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition"
        >
          <Pencil size={16} /> Tahrirlash
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard icon={Eye} label="Ko'rishlar" value={totalImpressions.toLocaleString()} color="purple" />
        <StatCard icon={MousePointerClick} label="Bosishlar" value={totalClicks.toLocaleString()} color="green" />
        <StatCard icon={Target} label="CTR" value={`${ctr}%`} color="brand" />
        <StatCard icon={Wallet} label="Sarflangan" value={`${Number(campaign.spent).toLocaleString()} UZS`} color="amber" />
      </div>

      {/* Budget Progress */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <div className="flex justify-between text-sm mb-2">
          <span className="text-gray-500">Budjet sarflanishi</span>
          <span className="font-medium text-gray-700">
            {Number(campaign.spent).toLocaleString()} / {Number(campaign.budget).toLocaleString()} UZS
          </span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-brand-600 h-2.5 rounded-full transition-all"
            style={{ width: `${Math.min((campaign.spent / campaign.budget) * 100, 100)}%` }}
          />
        </div>
      </div>

      {/* Chart */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-lg font-semibold text-gray-900">Kunlik ko'rsatkichlar</h2>
          <div className="flex items-center gap-2">
            {[7, 14, 30].map((d) => (
              <button key={d} onClick={() => setChartDays(d)}
                className={`px-3 py-1 rounded-lg text-sm font-medium transition ${
                  chartDays === d
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}>
                {d} kun
              </button>
            ))}
          </div>
        </div>

        {chartData.length === 0 ? (
          <div className="flex items-center justify-center h-[250px] text-gray-400 text-sm">
            Hali ma'lumot yo'q
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={chartData}>
              <defs>
                <linearGradient id="cImpr" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#338cff" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#338cff" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="cClick" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.15} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="date" tick={{ fontSize: 12, fill: '#9ca3af' }} />
              <YAxis tick={{ fontSize: 12, fill: '#9ca3af' }} />
              <Tooltip contentStyle={{ borderRadius: '12px', border: '1px solid #e5e7eb' }} />
              <Area type="monotone" dataKey="impressions" stroke="#338cff" strokeWidth={2}
                fill="url(#cImpr)" name="Ko'rishlar" />
              <Area type="monotone" dataKey="clicks" stroke="#10b981" strokeWidth={2}
                fill="url(#cClick)" name="Bosishlar" />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Ads list */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Reklamalar ({campaign.ads?.length || 0})</h2>
        <div className="space-y-3">
          {campaign.ads?.map((a) => (
            <div key={a.id} className="border border-gray-200 rounded-lg p-4 flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    a.ad_type === 'image' ? 'bg-purple-100 text-purple-700' :
                    a.ad_type === 'video' ? 'bg-blue-100 text-blue-700' :
                    'bg-gray-100 text-gray-700'
                  }`}>
                    {a.ad_type === 'image' ? 'Rasm' : a.ad_type === 'video' ? 'Video' : 'Matn'}
                  </span>
                </div>
                <p className="text-sm text-gray-700 line-clamp-2">{a.text_uz}</p>
              </div>
              <div className="text-right text-xs text-gray-500 ml-4">
                <p>{(a.impressions || 0).toLocaleString()} ko'rish</p>
                <p>{(a.clicks || 0).toLocaleString()} bosish</p>
                <p className="font-medium text-gray-700">CTR: {a.ctr || '0.00'}%</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
