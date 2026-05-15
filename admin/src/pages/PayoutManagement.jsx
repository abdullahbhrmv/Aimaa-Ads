import { useEffect, useState } from 'react'
import { Banknote, Check, X } from 'lucide-react'
import { adminAPI } from '../services/api'
import DataTable from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import toast from 'react-hot-toast'

export default function PayoutManagement() {
  const [payouts, setPayouts] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [filter, setFilter] = useState('all')

  const fetchPayouts = (p = page) => {
    setLoading(true)
    const params = { page: p }
    if (filter !== 'all') params.status = filter
    adminAPI.payouts(params)
      .then(({ data }) => {
        setPayouts(data.results || [])
        setTotalPages(Math.ceil((data.count || 0) / 20))
      })
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchPayouts(1); setPage(1) }, [filter])

  const handleApprove = async (id) => {
    try {
      await adminAPI.approvePayout(id)
      toast.success("To'lov tasdiqlandi")
      fetchPayouts()
    } catch {
      toast.error('Xatolik')
    }
  }

  const handleReject = async (id) => {
    try {
      await adminAPI.rejectPayout(id)
      toast.success("To'lov rad etildi")
      fetchPayouts()
    } catch {
      toast.error('Xatolik')
    }
  }

  const columns = [
    {
      key: 'id',
      label: 'ID',
      render: (row) => `#${row.id}`,
    },
    {
      key: 'username',
      label: 'Foydalanuvchi',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900">{row.username}</p>
          {row.telegram_id && (
            <p className="text-xs text-gray-400">TG: {row.telegram_id}</p>
          )}
        </div>
      ),
    },
    {
      key: 'amount',
      label: 'Summa',
      render: (row) => (
        <span className="font-semibold">{Number(row.amount || 0).toLocaleString()} UZS</span>
      ),
    },
    {
      key: 'payment_method',
      label: 'Usul',
      render: (row) => row.payment_method || '—',
    },
    {
      key: 'status',
      label: 'Holat',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'created_at',
      label: 'Sana',
      render: (row) => row.created_at ? new Date(row.created_at).toLocaleDateString() : '—',
    },
    {
      key: 'actions',
      label: '',
      render: (row) => row.status === 'pending' ? (
        <div className="flex items-center gap-1">
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
        </div>
      ) : null,
    },
  ]

  const filters = [
    { value: 'all', label: 'Barchasi' },
    { value: 'pending', label: 'Kutilmoqda' },
    { value: 'completed', label: 'Bajarilgan' },
    { value: 'rejected', label: 'Rad etilgan' },
  ]

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Banknote size={24} /> To'lov so'rovlari
        </h1>
        <p className="text-gray-500 mt-1">Nashriyotchilarning pul yechib olish so'rovlari</p>
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
        data={payouts}
        page={page}
        totalPages={totalPages}
        onPageChange={(p) => { setPage(p); fetchPayouts(p) }}
        loading={loading}
      />
    </div>
  )
}
