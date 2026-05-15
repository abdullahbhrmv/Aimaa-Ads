import { useState } from 'react'
import { User, Phone, Building2, Mail, Globe } from 'lucide-react'
import useAuthStore from '../hooks/useAuth'
import { authAPI } from '../services/api'
import toast from 'react-hot-toast'

export default function SettingsPage() {
  const { user, fetchUser } = useAuthStore()
  const [form, setForm] = useState({
    company_name: user?.company_name || '',
    phone: user?.phone || '',
    email: user?.email || '',
    language: user?.language || 'uz',
  })
  const [saving, setSaving] = useState(false)

  const update = (field) => (e) => setForm({ ...form, [field]: e.target.value })

  const handleSave = async () => {
    setSaving(true)
    try {
      await authAPI.me().then(() => {}) // ensure token is valid
      const api = (await import('../services/api')).default
      await api.patch('/auth/me/', form)
      await fetchUser()
      toast.success("Sozlamalar saqlandi!")
    } catch {
      toast.error('Xatolik yuz berdi')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Sozlamalar</h1>
        <p className="text-gray-500 mt-1">Hisobingiz sozlamalari</p>
      </div>

      {/* Profile */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5 mb-6">
        <h2 className="text-lg font-semibold text-gray-900">Profil</h2>

        <div className="flex items-center gap-4 p-4 bg-gray-50 rounded-lg">
          <div className="w-12 h-12 rounded-full bg-brand-100 flex items-center justify-center">
            <span className="text-lg font-bold text-brand-700">
              {user?.username?.[0]?.toUpperCase()}
            </span>
          </div>
          <div>
            <p className="font-semibold text-gray-900">{user?.username}</p>
            <p className="text-sm text-gray-500 capitalize">{user?.role}</p>
          </div>
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
            <Building2 size={14} /> Kompaniya nomi
          </label>
          <input type="text" value={form.company_name} onChange={update('company_name')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
            <Mail size={14} /> Email
          </label>
          <input type="email" value={form.email} onChange={update('email')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
            <Phone size={14} /> Telefon
          </label>
          <input type="tel" value={form.phone} onChange={update('phone')} placeholder="+998 90 123 45 67"
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
        </div>

        <div>
          <label className="flex items-center gap-2 text-sm font-medium text-gray-700 mb-1">
            <Globe size={14} /> Til
          </label>
          <select value={form.language} onChange={update('language')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none">
            <option value="uz">🇺🇿 O'zbekcha</option>
            <option value="ru">🇷🇺 Русский</option>
          </select>
        </div>

        <button onClick={handleSave} disabled={saving}
          className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition">
          {saving ? 'Saqlanmoqda...' : 'Saqlash'}
        </button>
      </div>

      {/* Account Info */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Hisob ma'lumotlari</h2>
        <div className="space-y-3 text-sm">
          <div className="flex justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">Balans</span>
            <span className="font-semibold text-gray-900">
              {Number(user?.balance || 0).toLocaleString()} UZS
            </span>
          </div>
          <div className="flex justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">Rol</span>
            <span className="capitalize text-gray-700">{user?.role}</span>
          </div>
          <div className="flex justify-between py-2 border-b border-gray-100">
            <span className="text-gray-500">Telegram ID</span>
            <span className="text-gray-700">{user?.telegram_id || '—'}</span>
          </div>
          <div className="flex justify-between py-2">
            <span className="text-gray-500">Ro'yxatdan o'tgan</span>
            <span className="text-gray-700">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
