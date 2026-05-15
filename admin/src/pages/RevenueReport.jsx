import { useEffect, useState } from 'react'
import { DollarSign, Download } from 'lucide-react'
import { adminAPI } from '../services/api'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import toast from 'react-hot-toast'

export default function RevenueReport() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [days, setDays] = useState(30)

  const fetchRevenue = () => {
    setLoading(true)
    adminAPI.revenue({ days })
      .then(({ data }) => setData(data))
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchRevenue() }, [days])

  const exportCSV = () => {
    if (!data?.chart) return
    const header = 'Sana,Daromad,Komissiya,Nashriyotchiga\n'
    const rows = data.chart.map((r) =>
      `${r.date},${r.total_spent},${r.commission},${r.publisher_payout}`
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `revenue_${days}d.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin h-8 w-8 border-4 border-brand-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  const d = data || {}

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <DollarSign size={24} /> Daromad hisoboti
          </h1>
          <p className="text-gray-500 mt-1">Platform daromadi va komissiya taqsimoti</p>
        </div>
        <button
          onClick={exportCSV}
          className="inline-flex items-center gap-2 bg-white border border-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 transition"
        >
          <Download size={16} />
          CSV yuklab olish
        </button>
      </div>

      {/* Period Selector */}
      <div className="flex gap-2 mb-6">
        {[7, 14, 30, 90].map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={`px-4 py-1.5 rounded-full text-sm font-medium transition ${
              days === d
                ? 'bg-brand-600 text-white'
                : 'bg-white text-gray-600 border border-gray-200 hover:bg-gray-50'
            }`}
          >
            {d} kun
          </button>
        ))}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500 mb-1">Umumiy sarflanma</p>
          <p className="text-2xl font-bold text-gray-900">
            {Number(d.total_spent || 0).toLocaleString()} UZS
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500 mb-1">Platform komissiyasi (30%)</p>
          <p className="text-2xl font-bold text-emerald-600">
            {Number(d.total_commission || 0).toLocaleString()} UZS
          </p>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-5">
          <p className="text-sm text-gray-500 mb-1">Nashriyotchilarga (70%)</p>
          <p className="text-2xl font-bold text-blue-600">
            {Number(d.total_publisher_payout || 0).toLocaleString()} UZS
          </p>
        </div>
      </div>

      {/* Chart */}
      {d.chart && d.chart.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Kunlik daromad</h2>
          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={d.chart}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`} />
                <Tooltip
                  formatter={(v, name) => [
                    `${Number(v).toLocaleString()} UZS`,
                    name === 'commission' ? 'Komissiya' : name === 'publisher_payout' ? 'Nashriyotchi' : 'Jami'
                  ]}
                />
                <Area type="monotone" dataKey="total_spent" stackId="1" stroke="#1a6cf5" fill="#bce0ff" name="total_spent" />
                <Area type="monotone" dataKey="commission" stackId="2" stroke="#10b981" fill="#d1fae5" name="commission" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  )
}
