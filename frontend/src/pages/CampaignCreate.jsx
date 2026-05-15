import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { campaignAPI, channelAPI, adAPI } from '../services/api'
import { ImagePlus, Type, X } from 'lucide-react'
import toast from 'react-hot-toast'

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-red-500 text-xs mt-1">{msg}</p>
}

export default function CampaignCreatePage() {
  const navigate = useNavigate()
  const [step, setStep] = useState(1)
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState({})
  const fileRef = useRef(null)

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
    end_date: '',
  })

  const [ad, setAd] = useState({
    ad_type: 'text',
    text_uz: '',
    text_ru: '',
    button_text: '',
    button_url: '',
  })

  const [mediaFile, setMediaFile] = useState(null)
  const [mediaPreview, setMediaPreview] = useState(null)

  useEffect(() => {
    channelAPI.categories().then(({ data }) => setCategories(data.results || data || []))
  }, [])

  const updateCampaign = (field) => (e) => {
    setCampaign({ ...campaign, [field]: e.target.value })
    setErrors((prev) => ({ ...prev, [field]: null }))
  }

  const updateAd = (field) => (e) => {
    setAd({ ...ad, [field]: e.target.value })
    setErrors((prev) => ({ ...prev, [field]: null }))
  }

  const toggleCategory = (id) => {
    const cats = campaign.target_categories.includes(id)
      ? campaign.target_categories.filter((c) => c !== id)
      : [...campaign.target_categories, id]
    setCampaign({ ...campaign, target_categories: cats })
  }

  const toggleLang = (lang) => {
    const langs = campaign.target_languages.includes(lang)
      ? campaign.target_languages.filter((l) => l !== lang)
      : [...campaign.target_languages, lang]
    setCampaign({ ...campaign, target_languages: langs })
  }

  const handleFileChange = (e) => {
    const file = e.target.files?.[0]
    if (!file) return

    if (!file.type.startsWith('image/')) {
      toast.error('Faqat rasm fayllarini tanlang')
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      toast.error("Fayl hajmi 10MB dan oshmasligi kerak")
      return
    }

    setMediaFile(file)
    setMediaPreview(URL.createObjectURL(file))
  }

  const clearMedia = () => {
    setMediaFile(null)
    setMediaPreview(null)
    if (fileRef.current) fileRef.current.value = ''
  }

  const handleAdTypeChange = (type) => {
    setAd({ ...ad, ad_type: type })
    clearMedia()
  }

  // Step 1 validation
  const validateStep1 = () => {
    const errs = {}
    if (!campaign.name.trim()) errs.name = 'Kampaniya nomi majburiy'
    if (!campaign.budget || Number(campaign.budget) <= 0) errs.budget = "Budjet 0 dan katta bo'lishi kerak"
    if (!campaign.bid_amount || Number(campaign.bid_amount) < 5000) errs.bid_amount = "CPM kamida 5,000 UZS bo'lishi kerak"
    if (campaign.start_date) {
      const start = new Date(campaign.start_date)
      const now = new Date()
      now.setHours(0, 0, 0, 0)
      if (start < now) errs.start_date = "Boshlanish sanasi o'tmishda bo'lishi mumkin emas"
    }
    if (campaign.end_date && campaign.start_date) {
      const start = new Date(campaign.start_date)
      const end = new Date(campaign.end_date)
      if (end <= start) errs.end_date = "Tugash sanasi boshlanish sanasidan keyin bo'lishi kerak"
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  // Step 2 validation
  const validateStep2 = () => {
    const errs = {}
    if (!ad.text_uz.trim()) errs.text_uz = "O'zbekcha matn majburiy"
    if (ad.button_url && !/^https?:\/\/.+/.test(ad.button_url)) errs.button_url = "URL https:// bilan boshlanishi kerak"
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const goToStep2 = () => {
    if (validateStep1()) setStep(2)
  }

  const handleSubmit = async () => {
    if (!validateStep2()) return
    setLoading(true)
    try {
      const { data: created } = await campaignAPI.create({
        ...campaign,
        budget: Number(campaign.budget),
        daily_budget: Number(campaign.daily_budget) || 0,
        bid_amount: Number(campaign.bid_amount),
        start_date: campaign.start_date || null,
        end_date: campaign.end_date || null,
      })

      if (mediaFile) {
        const formData = new FormData()
        formData.append('campaign', created.id)
        formData.append('ad_type', ad.ad_type)
        formData.append('text_uz', ad.text_uz)
        if (ad.text_ru) formData.append('text_ru', ad.text_ru)
        if (ad.button_text) formData.append('button_text', ad.button_text)
        if (ad.button_url) formData.append('button_url', ad.button_url)
        formData.append('image', mediaFile)
        await adAPI.create(formData)
      } else {
        await adAPI.create({ ...ad, campaign: created.id })
      }

      toast.success('Kampaniya yaratildi!')
      navigate('/campaigns')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Xatolik yuz berdi')
    } finally {
      setLoading(false)
    }
  }

  const adTypes = [
    { value: 'text', icon: Type, label: 'Matn' },
    { value: 'image', icon: ImagePlus, label: 'Rasm + Matn' },
  ]

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Yangi kampaniya</h1>
      <p className="text-gray-500 mb-8">
        {step === 1 ? 'Kampaniya sozlamalari' : 'Reklama kreativi'}
      </p>

      {/* Progress */}
      <div className="flex items-center gap-3 mb-8">
        {[1, 2].map((s) => (
          <div key={s} className="flex items-center gap-2">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
              step >= s ? 'bg-brand-600 text-white' : 'bg-gray-200 text-gray-500'
            }`}>
              {s}
            </div>
            <span className={`text-sm ${step >= s ? 'text-gray-900' : 'text-gray-400'}`}>
              {s === 1 ? 'Sozlamalar' : 'Kreativ'}
            </span>
            {s < 2 && <div className="w-16 h-0.5 bg-gray-200 mx-2" />}
          </div>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-5">
        {step === 1 ? (
          <>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Kampaniya nomi</label>
              <input type="text" value={campaign.name} onChange={updateCampaign('name')}
                placeholder="Masalan: Yangi yil aksiyasi"
                className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.name ? 'border-red-400' : 'border-gray-300'}`} />
              <FieldError msg={errors.name} />
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
                  placeholder="1000000"
                  className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.budget ? 'border-red-400' : 'border-gray-300'}`} />
                <FieldError msg={errors.budget} />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">CPM taklif (UZS)</label>
                <input type="number" value={campaign.bid_amount} onChange={updateCampaign('bid_amount')}
                  placeholder="5000"
                  className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.bid_amount ? 'border-red-400' : 'border-gray-300'}`} />
                <FieldError msg={errors.bid_amount} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Kunlik budjet (ixtiyoriy)</label>
                <input type="number" value={campaign.daily_budget} onChange={updateCampaign('daily_budget')}
                  placeholder="100000"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Boshlanish sanasi <span className="text-gray-400 text-xs">(ixtiyoriy)</span>
                </label>
                <input type="date" value={campaign.start_date} onChange={updateCampaign('start_date')}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.start_date ? 'border-red-400' : 'border-gray-300'}`} />
                <FieldError msg={errors.start_date} />
                <p className="text-xs text-gray-400 mt-1">Bo'sh qolsa darhol boshlanadi</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Tugash sanasi <span className="text-gray-400 text-xs">(ixtiyoriy)</span>
                </label>
                <input type="date" value={campaign.end_date} onChange={updateCampaign('end_date')}
                  className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.end_date ? 'border-red-400' : 'border-gray-300'}`} />
                <FieldError msg={errors.end_date} />
                <p className="text-xs text-gray-400 mt-1">Bo'sh qolsa budjet tugaguncha davom etadi</p>
              </div>
            </div>

            <button onClick={goToStep2}
              className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition">
              Keyingisi →
            </button>
          </>
        ) : (
          <>
            {/* Ad Type Selector */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Reklama turi</label>
              <div className="flex gap-2">
                {adTypes.map(({ value, icon: Icon, label }) => (
                  <button key={value} type="button"
                    onClick={() => handleAdTypeChange(value)}
                    className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm border transition ${
                      ad.ad_type === value
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-gray-300 text-gray-600 hover:border-gray-400'
                    }`}>
                    <Icon size={16} />
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Image Upload */}
            {ad.ad_type === 'image' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Rasm yuklash (ixtiyoriy)
                </label>
                {!mediaFile ? (
                  <label className={`flex flex-col items-center justify-center w-full h-40 border-2 border-dashed rounded-lg cursor-pointer hover:bg-gray-50 transition ${errors.media ? 'border-red-400' : 'border-gray-300'}`}>
                    <div className="flex flex-col items-center text-gray-400">
                      <ImagePlus size={32} />
                      <p className="mt-2 text-sm">Rasm tanlang yoki shu yerga tashlang</p>
                      <p className="text-xs mt-1">PNG, JPG - Maks. 10MB</p>
                    </div>
                    <input ref={fileRef} type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="hidden" />
                  </label>
                ) : (
                  <div className="relative border border-gray-200 rounded-lg p-3">
                    <button onClick={clearMedia}
                      className="absolute top-2 right-2 p-1 bg-red-100 rounded-full text-red-500 hover:bg-red-200 transition">
                      <X size={14} />
                    </button>
                    <img src={mediaPreview} alt="Preview" className="max-h-48 rounded-lg object-contain mx-auto" />
                  </div>
                )}
                <FieldError msg={errors.media} />
              </div>
            )}

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reklama matni (O'zbekcha)</label>
              <textarea value={ad.text_uz} onChange={updateAd('text_uz')} rows={4}
                placeholder="Telegram kanalingizda reklama matni..."
                className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none resize-none ${errors.text_uz ? 'border-red-400' : 'border-gray-300'}`} />
              <FieldError msg={errors.text_uz} />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Reklama matni (Ruscha, ixtiyoriy)</label>
              <textarea value={ad.text_ru} onChange={updateAd('text_ru')} rows={4}
                placeholder="Текст рекламы на русском..."
                className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none resize-none" />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tugma matni</label>
                <input type="text" value={ad.button_text} onChange={updateAd('button_text')}
                  placeholder="Batafsil →"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Tugma havolasi</label>
                <input type="url" value={ad.button_url} onChange={updateAd('button_url')}
                  placeholder="https://..."
                  className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.button_url ? 'border-red-400' : 'border-gray-300'}`} />
                <FieldError msg={errors.button_url} />
              </div>
            </div>

            {/* Preview */}
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
              <p className="text-xs text-gray-400 mb-2">Ko'rinishi:</p>
              <div className="bg-white rounded-lg p-4 shadow-sm">
                {mediaPreview && (
                  <img src={mediaPreview} alt="Preview" className="max-h-48 rounded-lg object-contain mb-3" />
                )}
                {mediaFile && ad.ad_type === 'video' && (
                  <div className="flex items-center gap-2 text-sm text-gray-500 mb-3 bg-gray-50 p-3 rounded-lg">
                    <Film size={16} />
                    <span>{mediaFile.name}</span>
                  </div>
                )}
                <p className="text-sm whitespace-pre-wrap">{ad.text_uz || 'Reklama matni...'}</p>
                {ad.button_text && (
                  <div className="mt-3">
                    <span className="inline-block bg-brand-600 text-white text-sm px-4 py-1.5 rounded-lg">
                      {ad.button_text}
                    </span>
                  </div>
                )}
                {/* TODO: SystemSettings API hazır olunca platform_bot_username buradan çekilsin (config-driven). */}
                <p className="text-xs text-gray-400 mt-3 italic">Reklama | @aimaa_ads_bot</p>
              </div>
            </div>

            <div className="flex gap-3">
              <button onClick={() => setStep(1)}
                className="flex-1 border border-gray-300 text-gray-700 py-2.5 rounded-lg font-medium hover:bg-gray-50 transition">
                ← Orqaga
              </button>
              <button onClick={handleSubmit} disabled={loading}
                className="flex-1 bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition">
                {loading ? 'Yaratilmoqda...' : 'Kampaniya yaratish'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
