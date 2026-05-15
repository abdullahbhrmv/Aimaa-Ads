import { useEffect, useState } from 'react'
import { Search, Users, Eye, Filter } from 'lucide-react'
import { channelAPI } from '../services/api'

export default function ChannelExplorerPage() {
  const [channels, setChannels] = useState([])
  const [categories, setCategories] = useState([])
  const [filters, setFilters] = useState({ category: '', language: '', search: '' })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      channelAPI.list(),
      channelAPI.categories(),
    ]).then(([chRes, catRes]) => {
      setChannels(chRes.data.results || chRes.data || [])
      setCategories(catRes.data.results || catRes.data || [])
    }).finally(() => setLoading(false))
  }, [])

  const filtered = channels.filter((ch) => {
    if (filters.category && ch.category !== Number(filters.category)) return false
    if (filters.language && ch.language !== filters.language) return false
    if (filters.search && !ch.title.toLowerCase().includes(filters.search.toLowerCase())) return false
    return true
  })

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Kanallar</h1>
        <p className="text-gray-500 mt-1">Reklama joylash uchun mavjud Telegram kanallar</p>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 mb-6 flex flex-wrap gap-4 items-center">
        <div className="flex items-center gap-2 flex-1 min-w-[200px]">
          <Search size={18} className="text-gray-400" />
          <input
            type="text"
            placeholder="Kanal qidirish..."
            value={filters.search}
            onChange={(e) => setFilters({ ...filters, search: e.target.value })}
            className="w-full py-2 outline-none text-sm"
          />
        </div>

        <select
          value={filters.category}
          onChange={(e) => setFilters({ ...filters, category: e.target.value })}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Barcha kategoriyalar</option>
          {categories.map((cat) => (
            <option key={cat.id} value={cat.id}>{cat.icon} {cat.name_uz}</option>
          ))}
        </select>

        <select
          value={filters.language}
          onChange={(e) => setFilters({ ...filters, language: e.target.value })}
          className="px-3 py-2 border border-gray-300 rounded-lg text-sm outline-none focus:ring-2 focus:ring-brand-500"
        >
          <option value="">Barcha tillar</option>
          <option value="uz">🇺🇿 O'zbekcha</option>
          <option value="ru">🇷🇺 Русский</option>
          <option value="mixed">🌐 Aralash</option>
        </select>
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Filter size={32} className="text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">Kanallar topilmadi</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((ch) => (
            <div key={ch.id} className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <h3 className="font-semibold text-gray-900">{ch.title}</h3>
                  {ch.username && (
                    <a
                      href={`https://t.me/${ch.username}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-brand-600 hover:underline"
                    >
                      @{ch.username}
                    </a>
                  )}
                </div>
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-1 rounded-full">
                  {ch.category_name}
                </span>
              </div>

              <div className="flex items-center gap-4 text-sm text-gray-500">
                <span className="flex items-center gap-1">
                  <Users size={14} />
                  {(ch.subscriber_count || 0).toLocaleString()}
                </span>
                <span className="flex items-center gap-1">
                  <Eye size={14} />
                  ~{(ch.avg_views || 0).toLocaleString()}
                </span>
              </div>

              <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  CPM: {Number(ch.min_cpm || 0).toLocaleString()} UZS
                </span>
                <span className="text-xs text-gray-400">
                  {ch.language === 'uz' ? "🇺🇿" : ch.language === 'ru' ? '🇷🇺' : '🌐'}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
