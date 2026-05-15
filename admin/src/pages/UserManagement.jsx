import { useEffect, useState } from 'react'
import { Users, Search } from 'lucide-react'
import { adminAPI } from '../services/api'
import DataTable from '../components/DataTable'
import toast from 'react-hot-toast'

export default function UserManagement() {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [roleFilter, setRoleFilter] = useState('all')
  const [search, setSearch] = useState('')

  const fetchUsers = (p = page) => {
    setLoading(true)
    const params = { page: p }
    if (roleFilter !== 'all') params.role = roleFilter
    if (search) params.search = search
    adminAPI.users(params)
      .then(({ data }) => {
        setUsers(data.results || [])
        setTotalPages(Math.ceil((data.count || 0) / 20))
      })
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchUsers(1); setPage(1) }, [roleFilter])

  const handleSearch = (e) => {
    e.preventDefault()
    fetchUsers(1)
    setPage(1)
  }

  const roleStyles = {
    admin: 'bg-purple-100 text-purple-700',
    advertiser: 'bg-blue-100 text-blue-700',
    publisher: 'bg-emerald-100 text-emerald-700',
  }

  const roleLabels = {
    admin: 'Admin',
    advertiser: 'Reklamchi',
    publisher: 'Nashriyotchi',
  }

  const columns = [
    {
      key: 'username',
      label: 'Foydalanuvchi',
      render: (row) => (
        <div>
          <p className="font-medium text-gray-900">{row.username}</p>
          <p className="text-xs text-gray-400">{row.email || '—'}</p>
        </div>
      ),
    },
    {
      key: 'role',
      label: 'Rol',
      render: (row) => (
        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${roleStyles[row.role] || 'bg-gray-100 text-gray-600'}`}>
          {roleLabels[row.role] || row.role}
        </span>
      ),
    },
    {
      key: 'company_name',
      label: 'Kompaniya',
      render: (row) => row.company_name || '—',
    },
    {
      key: 'balance',
      label: 'Balans',
      render: (row) => `${Number(row.balance || 0).toLocaleString()} UZS`,
    },
    {
      key: 'telegram_id',
      label: 'Telegram',
      render: (row) => row.telegram_id || '—',
    },
    {
      key: 'created_at',
      label: "Ro'yxatdan",
      render: (row) => row.created_at ? new Date(row.created_at).toLocaleDateString() : '—',
    },
  ]

  const roles = [
    { value: 'all', label: 'Barchasi' },
    { value: 'advertiser', label: 'Reklamchilar' },
    { value: 'publisher', label: 'Nashriyotchilar' },
    { value: 'admin', label: 'Adminlar' },
  ]

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Users size={24} /> Foydalanuvchilar
        </h1>
        <p className="text-gray-500 mt-1">Platformadagi barcha foydalanuvchilar</p>
      </div>

      <div className="flex items-center gap-4 mb-6">
        {/* Role Filters */}
        <div className="flex gap-2">
          {roles.map((r) => (
            <button
              key={r.value}
              onClick={() => setRoleFilter(r.value)}
              className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
                roleFilter === r.value
                  ? 'bg-brand-600 text-white'
                  : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex-1 max-w-xs ml-auto">
          <div className="relative">
            <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Qidirish..."
              className="w-full pl-9 pr-4 py-2 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-brand-500 outline-none"
            />
          </div>
        </form>
      </div>

      <DataTable
        columns={columns}
        data={users}
        page={page}
        totalPages={totalPages}
        onPageChange={(p) => { setPage(p); fetchUsers(p) }}
        loading={loading}
      />
    </div>
  )
}
