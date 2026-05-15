import { useState } from 'react'
import { Settings, Save } from 'lucide-react'
import toast from 'react-hot-toast'

export default function SystemSettings() {
  const [settings, setSettings] = useState({
    commission_rate: 30,
    min_payout: 100000,
    min_subscribers: 500,
    min_cpm: 5000,
    max_ad_duration_hours: 48,
    platform_bot_username: 'aimaa_ads_bot',
  })
  const [saving, setSaving] = useState(false)

  const update = (field) => (e) => {
    const value = e.target.type === 'number' ? Number(e.target.value) : e.target.value
    setSettings({ ...settings, [field]: value })
  }

  const handleSave = async () => {
    setSaving(true)
    // TODO: Save to backend when endpoint is ready
    setTimeout(() => {
      setSaving(false)
      toast.success('Sozlamalar saqlandi!')
    }, 500)
  }

  return (
    <div className="max-w-2xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <Settings size={24} /> Tizim sozlamalari
        </h1>
        <p className="text-gray-500 mt-1">Platform parametrlari</p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
        {/* Commission */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Komissiya foizi (%)
          </label>
          <input
            type="number"
            value={settings.commission_rate}
            onChange={update('commission_rate')}
            min={0}
            max={100}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <p className="text-xs text-gray-400 mt-1">
            Reklamchidan olingan summadan platformaga tushadigan foiz
          </p>
        </div>

        {/* Min Payout */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Minimal chiqarish summasi (UZS)
          </label>
          <input
            type="number"
            value={settings.min_payout}
            onChange={update('min_payout')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <p className="text-xs text-gray-400 mt-1">
            Nashriyotchi pul chiqarishi uchun minimal balans
          </p>
        </div>

        {/* Min Subscribers */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Minimal obunachi soni
          </label>
          <input
            type="number"
            value={settings.min_subscribers}
            onChange={update('min_subscribers')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <p className="text-xs text-gray-400 mt-1">
            Kanal qo'shish uchun minimal obunachi soni
          </p>
        </div>

        {/* Min CPM */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Minimal CPM (UZS)
          </label>
          <input
            type="number"
            value={settings.min_cpm}
            onChange={update('min_cpm')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <p className="text-xs text-gray-400 mt-1">
            Reklamchi belgilashi mumkin bo'lgan minimal CPM narx
          </p>
        </div>

        {/* Max Ad Duration */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Maksimal reklama muddati (soat)
          </label>
          <input
            type="number"
            value={settings.max_ad_duration_hours}
            onChange={update('max_ad_duration_hours')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
        </div>

        {/* Bot Username */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Bot username
          </label>
          <div className="flex">
            <span className="inline-flex items-center px-3 bg-gray-50 border border-r-0 border-gray-300 rounded-l-lg text-gray-500 text-sm">
              @
            </span>
            <input
              type="text"
              value={settings.platform_bot_username}
              onChange={update('platform_bot_username')}
              className="flex-1 px-4 py-2.5 border border-gray-300 rounded-r-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full inline-flex items-center justify-center gap-2 bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition"
        >
          <Save size={18} />
          {saving ? 'Saqlanmoqda...' : 'Saqlash'}
        </button>
      </div>
    </div>
  )
}
