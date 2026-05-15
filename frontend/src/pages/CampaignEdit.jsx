import { useState, useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { campaignAPI, channelAPI, adAPI } from '../services/api'
import { Trash2, ImagePlus } from 'lucide-react'
import toast from 'react-hot-toast'

export default function CampaignEditPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  const [campaign, setCampaign] = useState({
    name: '',
    target_categories: [],
    target_languages: ['uz'],
    min_subscribers: 0,
    billing_type: 'cpm',
    budget: '',
    daily_budget: '',
    bid_amount: '',
    start_date: '',
  })

  const [ads, setAds] = useState([])
  const [editingAd, setEditingAd] = useState(null)

  useEffect(() => {
    Promise.all([
      campaignAPI.get(id),
      channelAPI.categories(),
    ]).then(([campRes, catRes]) => {
      const c = campRes.data
      setCampaign({
        name: c.name,
        target_categories: c.target_categories || [],
        target_languages: c.target_languages || ['uz'],
        min_subscribers: c.min_subscribers || 0,
        billing_type: c.billing_type,
        budget: c.budget,
        daily_budget: c.daily_budget || '',
        bid_amount: c.bid_amount,
        start_date: c.start_date || '',
      })
      setAds(c.ads || [])
      setCategories(catRes.data.results || catRes.data || [])
    }).catch(() => {
      toast.error('Kampaniya topilmadi')
      navigate('/campaigns')
    }).finally(() => setLoading(false))
  }, [id])

  const updateCampaign = (field) => (e) =>
    setCampaign({ ...campaign, [field]: e.target.value })

  const toggleCategory = (catId) => {
    const cats = campaign.target_categories.includes(catId)
      ? campaign.target_categories.filter((c) => c !== catId)
      : [...campaign.target_categories, catId]
    setCampaign({ ...campaign, target_categories: cats })
  }

  const toggleLang = (lang) => {
    const langs = campaign.target_languages.includes(lang)
      ? campaign.target_languages.filter((l) => l !== lang)
      : [...campaign.target_languages, lang]
    setCampaign({ ...campaign, target_languages: langs })
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await campaignAPI.update(id, {
        name: campaign.name,
        target_categories: campaign.target_categories,
        target_languages: campaign.target_languages,
        min_subscribers: Number(campaign.min_subscribers),
        billing_type: campaign.billing_type,
        budget: Number(campaign.budget),
        daily_budget: Number(campaign.daily_budget) || 0,
        bid_amount: Number(campaign.bid_amount),
      })
      toast.success('Kampaniya yangilandi!')
      navigate('/campaigns')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Xatolik yuz berdi')
    } finally {
      setSaving(false)
    }
  }

  const handleUpdateAd = async (adId, data) => {
    try {
      await adAPI.update(adId, data)
      toast.success('Reklama yangilandi')
      setEditingAd(null)
      // Refresh
      const { data: c } = await campaignAPI.get(id)
      setAds(c.ads || [])
    } catch {
      toast.error('Xatolik')
    }
  }

  const handleDeleteAd = async (adId) => {
    if (!confirm("Bu reklamani o'chirmoqchimisiz?")) return
    try {
      await adAPI.delete(adId)
      setAds(ads.filter((a) => a.id !== adId))
      toast.success("Reklama o'chirildi")
    } catch {
      toast.error('Xatolik')
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
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Kampaniyani tahrirlash</h1>
      <p className="text-gray-500 mb-8">Kampaniya sozlamalarini o'zgartiring</p>

      {/* Kampanya sozlamalari */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5 mb-6">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Kampaniya nomi</label>
          <input type="text" value={campaign.name} onChange={updateCampaign('name')}
            className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Kategoriyalar</label>
          <div className="flex flex-wrap gap-2">
            {categories.map((cat) => (
              <button key={cat.id} type="button"
                onClick={() => toggleCategory(cat.id)}
                className={`px-3 py-1.5 rounded-full text-sm border transition ${
                  campaign.target_categories.includes(cat.id)
                    ? 'border-brand-500 bg-brand-50 text-brand-700'
                    : 'border-gray-300 text-gray-600 hover:border-gray-400'
                }`}>
                {cat.icon} {cat.name_uz}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-2">Tillar</label>
          <div className="flex gap-3">
            {[['uz', "🇺🇿 O'zbekcha"], ['ru', '🇷🇺 Русский']].map(([code, label]) => (
              <button key={code} type="button"
                onClick={() => toggleLang(code)}
                className={`px-4 py-2 rounded-lg text-sm border transition ${
                  campaign.target_languages.includes(code)
                    ? 'border-brand-500 bg-brand-50 text-brand-700'
                    : 'border-gray-300 text-gray-600'
                }`}>
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Umumiy budjet (UZS)</label>
            <input type="number" value={campaign.budget} onChange={updateCampaign('budget')}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">CPM taklif (UZS)</label>
            <input type="number" value={campaign.bid_amount} onChange={updateCampaign('bid_amount')}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
          </div>
        </div>

        <button onClick={handleSave} disabled={saving || !campaign.name}
          className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition">
          {saving ? 'Saqlanmoqda...' : 'Saqlash'}
        </button>
      </div>

      {/* Reklamalar */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Reklamalar</h2>

        {ads.length === 0 ? (
          <p className="text-gray-400 text-sm">Hali reklama yo'q</p>
        ) : (
          <div className="space-y-4">
            {ads.map((a) => (
              <div key={a.id} className="border border-gray-200 rounded-lg p-4">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                      a.ad_type === 'image' ? 'bg-purple-100 text-purple-700' :
                      a.ad_type === 'video' ? 'bg-blue-100 text-blue-700' :
                      'bg-gray-100 text-gray-700'
                    }`}>
                      {a.ad_type === 'image' ? 'Rasm' : a.ad_type === 'video' ? 'Video' : 'Matn'}
                    </span>
                    <span className="text-xs text-gray-400">
                      {a.impressions} ko'rish, {a.clicks} bosish
                    </span>
                  </div>
                  <button onClick={() => handleDeleteAd(a.id)}
                    className="p-1 hover:bg-red-50 rounded text-red-400 hover:text-red-600 transition">
                    <Trash2 size={16} />
                  </button>
                </div>
                <p className="text-sm text-gray-700 whitespace-pre-wrap line-clamp-3">{a.text_uz}</p>
                {a.button_text && (
                  <span className="inline-block mt-2 text-xs bg-brand-100 text-brand-700 px-3 py-1 rounded-lg">
                    {a.button_text}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
