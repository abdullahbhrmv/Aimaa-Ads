import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, Play, Pause, Eye, MousePointerClick, Pencil } from 'lucide-react'
import { campaignAPI } from '../services/api'
import toast from 'react-hot-toast'

const statusStyles = {
  draft: 'bg-gray-100 text-gray-600',
  pending: 'bg-yellow-100 text-yellow-700',
  approved: 'bg-green-100 text-green-700',
  active: 'bg-emerald-100 text-emerald-700',
  paused: 'bg-orange-100 text-orange-700',
  completed: 'bg-blue-100 text-blue-700',
  rejected: 'bg-red-100 text-red-700',
}

const statusLabels = {
  draft: 'Taslak',
  pending: 'Kutilmoqda',
  approved: 'Tasdiqlangan',
  active: 'Aktiv',
  paused: 'Pauza',
  completed: 'Tugallangan',
  rejected: 'Rad etilgan',
}

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchCampaigns = () => {
    campaignAPI.list()
      .then(({ data }) => setCampaigns(data.results || []))
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchCampaigns() }, [])

  const handleActivate = async (id) => {
    try {
      await campaignAPI.activate(id)
      toast.success('Kampaniya aktivlashtirildi')
      fetchCampaigns()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Xatolik')
    }
  }

  const handlePause = async (id) => {
    try {
      await campaignAPI.pause(id)
      toast.success("Kampaniya to'xtatildi")
      fetchCampaigns()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Xatolik')
    }
  }

  const handleResume = async (id) => {
    try {
      await campaignAPI.resume(id)
      toast.success("Kampaniya davom ettirildi")
      fetchCampaigns()
    } catch (err) {
      toast.error(err.response?.data?.error || 'Xatolik')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Kampanyalar</h1>
          <p className="text-gray-500 mt-1">Barcha reklama kampanyalaringiz</p>
        </div>
        <Link
          to="/campaigns/new"
          className="inline-flex items-center gap-2 bg-brand-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-brand-700 transition"
        >
          <Plus size={18} />
          Yangi kampaniya
        </Link>
      </div>

      {campaigns.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <p className="text-gray-400 mb-4">Hali kampaniyalar yo'q</p>
          <Link
            to="/campaigns/new"
            className="text-brand-600 font-medium hover:underline"
          >
            Birinchi kampaniyangizni yarating →
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {campaigns.map((c) => (
            <div
              key={c.id}
              className="bg-white rounded-xl border border-gray-200 p-5 flex items-center justify-between hover:shadow-sm transition"
            >
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                  <Link to={`/campaigns/${c.id}`}
                    className="font-semibold text-gray-900 hover:text-brand-600 transition-colors">
                    {c.name}
                  </Link>
                  <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${statusStyles[c.status]}`}>
                    {statusLabels[c.status]}
                  </span>
                </div>
                {c.status === 'rejected' && c.rejection_reason && (
                  <div className="mb-2 text-sm text-red-600 bg-red-50 px-3 py-1.5 rounded-lg inline-block">
                    ❌ Red etildi: {c.rejection_reason}
                  </div>
                )}
                <div className="flex items-center gap-6 text-sm text-gray-500">
                  <span className="flex items-center gap-1">
                    <Eye size={14} /> {(c.total_impressions || 0).toLocaleString()}
                  </span>
                  <span className="flex items-center gap-1">
                    <MousePointerClick size={14} /> {(c.total_clicks || 0).toLocaleString()}
                  </span>
                  <span>
                    Budjet: {Number(c.budget).toLocaleString()} UZS
                  </span>
                  <span>
                    Sarflangan: {Number(c.spent).toLocaleString()} UZS
                  </span>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <Link to={`/campaigns/${c.id}/edit`}
                  className="p-2 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition"
                  title="Tahrirlash">
                  <Pencil size={18} />
                </Link>
                {c.status === 'active' && (
                  <button
                    onClick={() => handlePause(c.id)}
                    className="p-2 rounded-lg hover:bg-orange-50 text-orange-500 transition"
                    title="To'xtatish"
                  >
                    <Pause size={18} />
                  </button>
                )}
                {c.status === 'paused' && (
                  <button
                    onClick={() => handleResume(c.id)}
                    className="p-2 rounded-lg hover:bg-emerald-50 text-emerald-500 transition"
                    title="Davom ettirish"
                  >
                    <Play size={18} />
                  </button>
                )}
                {c.status === 'approved' && (
                  <button
                    onClick={() => handleActivate(c.id)}
                    className="p-2 rounded-lg hover:bg-emerald-50 text-emerald-500 transition"
                    title="Aktivlashtirish"
                  >
                    <Play size={18} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
