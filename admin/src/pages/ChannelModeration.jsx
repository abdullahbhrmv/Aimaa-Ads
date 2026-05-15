import { useEffect, useState } from 'react'
import { Radio, Check, X, ExternalLink } from 'lucide-react'
import { adminAPI } from '../services/api'
import DataTable from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import toast from 'react-hot-toast'

export default function ChannelModeration() {
  const [channels, setChannels] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [filter, setFilter] = useState('all')

  const fetchChannels = (p = page) => {
    setLoading(true)
    const params = { page: p }
    if (filter !== 'all') params.status = filter
    adminAPI.channels(params)
      .then(({ data }) => {
        setChannels(data.results || [])
        setTotalPages(Math.ceil((data.count || 0) / 20))
      })
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchChannels(1); setPage(1) }, [filter])

  const handleApprove = async (id) => {
    try {
      await adminAPI.approveChannel(id)
      toast.success('Kanal tasdiqlandi')
      fetchChannels()
    } catch {
      toast.error('Xatolik')
    }
  }

  const handleReject = async (id) => {
    try {
      await adminAPI.rejectChannel(id)
      toast.success('Kanal rad etildi')
      fetchChannels()
    } catch {
      toast.error('Xatolik')
    }
  }

  const columns = [
    {
      key: 'name',
      label: 'Kanal',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900">{row.name}</p>
          <p className="text-xs text-gray-400">@{row.username || row.chat_id}</p>
        </div>
      ),
    },
    {
      key: 'subscriber_count',
      label: 'Obunachi',
      render: (row) => (
        <span className="font-medium">{(row.subscriber_count || 0).toLocaleString()}</span>
      ),
    },
    {
      key: 'category',
      label: 'Kategoriya',
      render: (row) => row.category_name || '—',
    },
    {
      key: 'owner',
      label: 'Egasi',
      render: (row) => row.owner_username || `ID: ${row.owner}`,
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
          {row.username && (
            <a
              href={`https://t.me/${row.username}`}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 transition"
              title="Telegramda ochish"
            >
              <ExternalLink size={16} />
            </a>
          )}
        </div>
      ),
    },
  ]

  const filters = [
    { value: 'all', label: 'Barchasi' },
    { value: 'pending', label: 'Kutilmoqda' },
    { value: 'approved', label: 'Tasdiqlangan' },
    { value: 'rejected', label: 'Rad etilgan' },
  ]

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <Radio size={24} /> Kanal moderatsiyasi
          </h1>
          <p className="text-gray-500 mt-1">Telegram kanallarini tekshirish va tasdiqlash</p>
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
        data={channels}
        page={page}
        totalPages={totalPages}
        onPageChange={(p) => { setPage(p); fetchChannels(p) }}
        loading={loading}
      />
    </div>
  )
}
