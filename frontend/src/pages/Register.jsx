import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import useAuthStore from '../hooks/useAuth'
import toast from 'react-hot-toast'

function FieldError({ msg }) {
  if (!msg) return null
  return <p className="text-red-500 text-xs mt-1">{msg}</p>
}

export default function RegisterPage() {
  const [form, setForm] = useState({
    username: '', email: '', password: '',
    company_name: '', phone: '', role: 'advertiser',
  })
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(false)
  const { register, login } = useAuthStore()
  const navigate = useNavigate()

  const update = (field) => (e) => {
    setForm({ ...form, [field]: e.target.value })
    setErrors((prev) => ({ ...prev, [field]: null }))
  }

  const validate = () => {
    const errs = {}
    if (!form.username.trim()) errs.username = 'Login majburiy'
    if (form.username.length < 3) errs.username = "Login kamida 3 ta belgidan iborat bo'lishi kerak"
    if (!form.email.trim()) errs.email = 'Email majburiy'
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errs.email = "Email formati noto'g'ri"
    if (!form.password) errs.password = 'Parol majburiy'
    if (form.password.length < 8) errs.password = "Parol kamida 8 ta belgidan iborat bo'lishi kerak"
    if (form.phone && !/^\+998\d{9}$/.test(form.phone.replace(/\s/g, ''))) {
      errs.phone = "Telefon raqam +998XXXXXXXXX formatida bo'lishi kerak"
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!validate()) return
    setLoading(true)
    try {
      await register(form)
      await login(form.username, form.password)
      toast.success("Muvaffaqiyatli ro'yxatdan o'tdingiz!")
      navigate('/')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const serverErrors = {}
        Object.entries(data).forEach(([key, val]) => {
          serverErrors[key] = Array.isArray(val) ? val[0] : val
        })
        setErrors(serverErrors)
      } else {
        toast.error(data?.detail || 'Xatolik yuz berdi')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-brand-50 to-brand-100 py-12">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-brand-700">
            Aimaa<span className="text-accent-500">Ads</span>
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-2xl shadow-lg p-8 space-y-4">
          <h2 className="text-xl font-semibold text-gray-800">Ro'yxatdan o'tish</h2>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Login</label>
            <input type="text" value={form.username} onChange={update('username')}
              className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.username ? 'border-red-400' : 'border-gray-300'}`} />
            <FieldError msg={errors.username} />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input type="email" value={form.email} onChange={update('email')}
              className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.email ? 'border-red-400' : 'border-gray-300'}`} />
            <FieldError msg={errors.email} />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Kompaniya nomi</label>
            <input type="text" value={form.company_name} onChange={update('company_name')}
              className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none" />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Telefon</label>
            <input type="tel" value={form.phone} onChange={update('phone')} placeholder="+998 90 123 45 67"
              className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.phone ? 'border-red-400' : 'border-gray-300'}`} />
            <FieldError msg={errors.phone} />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Parol</label>
            <input type="password" value={form.password} onChange={update('password')}
              className={`w-full px-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none ${errors.password ? 'border-red-400' : 'border-gray-300'}`} />
            <FieldError msg={errors.password} />
          </div>

          <button type="submit" disabled={loading}
            className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 disabled:opacity-50 transition">
            {loading ? 'Yuklanmoqda...' : "Ro'yxatdan o'tish"}
          </button>

          <p className="text-center text-sm text-gray-500">
            Hisobingiz bormi?{' '}
            <Link to="/login" className="text-brand-600 font-medium hover:underline">Kirish</Link>
          </p>
        </form>
      </div>
    </div>
  )
}
