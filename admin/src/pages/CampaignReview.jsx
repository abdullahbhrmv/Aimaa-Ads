import { useEffect, useState } from 'react'
import { Megaphone, Check, X, Eye } from 'lucide-react'
import { adminAPI } from '../services/api'
import DataTable from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import toast from 'react-hot-toast'

export default function CampaignReview() {
  const [campaigns, setCampaigns] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [filter, setFilter] = useState('all')
  const [preview, setPreview] = useState(null)
  const [rejectModal, setRejectModal] = useState(null)
  const [rejectReason, setRejectReason] = useState('')
  const [customReason, setCustomReason] = useState('')

  const fetchCampaigns = (p = page) => {
    setLoading(true)
    const params = { page: p }
    if (filter !== 'all') params.status = filter
    adminAPI.campaigns(params)
      .then(({ data }) => {
        setCampaigns(data.results || [])
        setTotalPages(Math.ceil((data.count || 0) / 20))
      })
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchCampaigns(1); setPage(1) }, [filter])

  const handleApprove = async (id) => {
    try {
      await adminAPI.approveCampaign(id)
      toast.success('Kampaniya tasdiqlandi')
      fetchCampaigns()
      setPreview(null)
    } catch {
      toast.error('Xatolik')
    }
  }

  const handleReject = (id) => {
    setRejectModal(id)
    setRejectReason('')
    setCustomReason('')
  }

  const confirmReject = async () => {
    const finalReason = rejectReason === 'custom' ? customReason : rejectReason
    if (!finalReason.trim()) {
      toast.error('Red sebebini belirtin')
      return
    }

    try {
      await adminAPI.rejectCampaign(rejectModal, { reason: finalReason })
      toast.success('Kampaniya rad etildi')
      fetchCampaigns()
      setPreview(null)
      setRejectModal(null)
    } catch (err) {
      toast.error(err.response?.data?.error || 'Xatolik')
    }
  }

  const columns = [
    {
      key: 'name',
      label: 'Kampaniya',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900">{row.name}</p>
          <p className="text-xs text-gray-400">{row.billing_type?.toUpperCase()}</p>
        </div>
      ),
    },
    {
      key: 'owner',
      label: 'Reklamchi',
      render: (row) => row.owner_username || `ID: ${row.owner}`,
    },
    {
      key: 'budget',
      label: 'Budjet',
      render: (row) => `${Number(row.budget || 0).toLocaleString()} UZS`,
    },
    {
      key: 'bid_amount',
      label: 'CPM/CPC',
      render: (row) => `${Number(row.bid_amount || 0).toLocaleString()} UZS`,
    },
    {
      key: 'status',
      label: 'Holat',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'actions',
      label: '',
      render: (row) => (
        <div className="flex items-center gap-1">
          <button
            onClick={() => setPreview(row)}
            className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-500 transition"
            title="Ko'rish"
          >
            <Eye size={18} />
          </button>
          {row.status === 'pending' && (
            <>
              <button
                onClick={() => handleApprove(row.id)}
                className="p-1.5 rounded-lg hover:bg-emerald-50 text-emerald-500 transition"
                title="Tasdiqlash"
              >
                <Check size={18} />
              </button>
              <button
                onClick={() => handleReject(row.id)}
                className="p-1.5 rounded-lg hover:bg-red-50 text-red-500 transition"
                title="Rad etish"
              >
                <X size={18} />
              </button>
            </>
          )}
        </div>
      ),
    },
  ]

  const filters = [
    { value: 'all', label: 'Barchasi' },
    { value: 'pending', label: 'Kutilmoqda' },
    { value: 'active', label: 'Aktiv' },
    { value: 'paused', label: 'Pauza' },
    { value: 'completed', label: 'Tugallangan' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Megaphone size={24} /> Kampanya tekshiruvi
          </h1>
          <p className="text-gray-500 mt-1">Reklama kampanyalarini ko'rib chiqish</p>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 mb-6">
        {filters.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              filter === f.value
                ? 'bg-brand-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      <DataTable
        columns={columns}
        data={campaigns}
        page={page}
        totalPages={totalPages}
        onPageChange={(p) => { setPage(p); fetchCampaigns(p) }}
        loading={loading}
      />

      {/* Preview Modal */}
      {preview && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setPreview(null)}>
          <div className="bg-white rounded-2xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">{preview.name}</h3>
              <button onClick={() => setPreview(null)} className="p-1 hover:bg-gray-100 rounded-lg transition">
                <X size={20} />
              </button>
            </div>

            <div className="space-y-3 text-sm">
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">Holat</span>
                <StatusBadge status={preview.status} />
              </div>
              {preview.status === 'rejected' && preview.rejection_reason && (
                <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                  <p className="text-xs text-red-500 font-medium mb-1">Red etilish sababi:</p>
                  <p className="text-sm text-red-700">{preview.rejection_reason}</p>
                </div>
              )}
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">Reklamchi</span>
                <span className="text-gray-900">{preview.owner_username || `ID: ${preview.owner}`}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">Budjet</span>
                <span className="font-semibold">{Number(preview.budget || 0).toLocaleString()} UZS</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">Sarflangan</span>
                <span>{Number(preview.spent || 0).toLocaleString()} UZS</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">CPM/CPC</span>
                <span>{Number(preview.bid_amount || 0).toLocaleString()} UZS</span>
              </div>
              <div className="flex justify-between py-2 border-b border-gray-100">
                <span className="text-gray-500">Billing turi</span>
                <span className="uppercase">{preview.billing_type}</span>
              </div>

              {/* Ads */}
              {preview.ads && preview.ads.length > 0 && (
                <div className="mt-4">
                  <p className="font-medium text-gray-700 mb-2">Reklamalar:</p>
                  {preview.ads.map((ad, i) => (
                    <div key={i} className="bg-gray-50 rounded-lg p-4 mb-2">
                      {ad.image && <img src={ad.image} alt="" className="max-h-40 rounded-lg mb-2 object-contain" />}
                      <p className="text-sm whitespace-pre-wrap">{ad.text_uz}</p>
                      {ad.button_text && (
                        <div className="mt-2">
                          <span className="inline-block bg-brand-600 text-white text-xs px-3 py-1 rounded-lg">
                            {ad.button_text}
                          </span>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {preview.status === 'pending' && (
              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => handleReject(preview.id)}
                  className="flex-1 border border-red-300 text-red-600 py-2 rounded-lg font-medium hover:bg-red-50 transition"
                >
                  Rad etish
                </button>
                <button
                  onClick={() => handleApprove(preview.id)}
                  className="flex-1 bg-emerald-600 text-white py-2 rounded-lg font-medium hover:bg-emerald-700 transition"
                >
                  Tasdiqlash
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Reject Modal */}
      {rejectModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setRejectModal(null)}>
          <div className="bg-white rounded-2xl p-6 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Kampaniyani rad etish</h3>

            <div className="space-y-3">
              <label className="block">
                <span className="text-sm font-medium text-gray-700 mb-2 block">Red sebebini tanlang:</span>
                <select
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
                >
                  <option value="">Sebebni tanlang...</option>
                  <option value="Kontent nomuvofiq yoki chalg'ituvchi">Kontent nomuvofiq yoki chalg'ituvchi</option>
                  <option value="Reklama matni aniq emas">Reklama matni aniq emas</option>
                  <option value="Nishon mezonlari mos emas">Nishon mezonlari mos emas</option>
                  <option value="Budjet juda past">Budjet juda past</option>
                  <option value="Rasm sifati yetarli emas">Rasm sifati yetarli emas</option>
                  <option value="custom">Boshqa sabab (yozing)...</option>
                </select>
              </label>

              {rejectReason === 'custom' && (
                <label className="block">
                  <span className="text-sm font-medium text-gray-700 mb-2 block">Sabab yozing:</span>
                  <textarea
                    value={customReason}
                    onChange={(e) => setCustomReason(e.target.value)}
                    rows={3}
                    placeholder="Red etish sababini kiriting..."
                    className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none resize-none"
                  />
                </label>
              )}
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setRejectModal(null)}
                className="flex-1 border border-gray-300 text-gray-600 py-2 rounded-lg font-medium hover:bg-gray-50 transition"
              >
                Bekor qilish
              </button>
              <button
                onClick={confirmReject}
                className="flex-1 bg-red-600 text-white py-2 rounded-lg font-medium hover:bg-red-700 transition"
              >
                Rad etish
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
