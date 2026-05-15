import { useEffect, useState } from 'react'
import { FolderOpen, Plus, Pencil, Trash2, X } from 'lucide-react'
import { adminAPI } from '../services/api'
import toast from 'react-hot-toast'

export default function CategoryManagement() {
  const [categories, setCategories] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({ name_uz: '', name_ru: '', icon: '', is_active: true })

  const fetchCategories = () => {
    setLoading(true)
    adminAPI.categories()
      .then(({ data }) => setCategories(data.results || data || []))
      .catch(() => toast.error('Xatolik'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetchCategories() }, [])

  const resetForm = () => {
    setForm({ name_uz: '', name_ru: '', icon: '', is_active: true })
    setEditing(null)
    setShowForm(false)
  }

  const openEdit = (cat) => {
    setForm({
      name_uz: cat.name_uz || '',
      name_ru: cat.name_ru || '',
      icon: cat.icon || '',
      is_active: cat.is_active !== false,
    })
    setEditing(cat.id)
    setShowForm(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    try {
      if (editing) {
        await adminAPI.updateCategory(editing, form)
        toast.success('Kategoriya yangilandi')
      } else {
        await adminAPI.createCategory(form)
        toast.success('Kategoriya yaratildi')
      }
      resetForm()
      fetchCategories()
    } catch {
      toast.error('Xatolik')
    }
  }

  const handleDelete = async (id) => {
    if (!confirm("Bu kategoriyani o'chirmoqchimisiz?")) return
    try {
      await adminAPI.deleteCategory(id)
      toast.success("Kategoriya o'chirildi")
      fetchCategories()
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
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
            <FolderOpen size={24} /> Kategoriyalar
          </h1>
          <p className="text-gray-500 mt-1">Kanal kategoriyalarini boshqarish</p>
        </div>
        <button
          onClick={() => { resetForm(); setShowForm(true) }}
          className="inline-flex items-center gap-2 bg-brand-600 text-white px-5 py-2.5 rounded-lg font-medium hover:bg-brand-700 transition"
        >
          <Plus size={18} />
          Yangi kategoriya
        </button>
      </div>

      {/* Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={resetForm}>
          <div className="bg-white rounded-2xl p-6 max-w-md w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                {editing ? 'Kategoriyani tahrirlash' : 'Yangi kategoriya'}
              </h3>
              <button onClick={resetForm} className="p-1 hover:bg-gray-100 rounded-lg transition">
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomi (O'zbekcha)</label>
                <input
                  type="text"
                  value={form.name_uz}
                  onChange={(e) => setForm({ ...form, name_uz: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Nomi (Ruscha)</label>
                <input
                  type="text"
                  value={form.name_ru}
                  onChange={(e) => setForm({ ...form, name_ru: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Emoji ikoni</label>
                <input
                  type="text"
                  value={form.icon}
                  onChange={(e) => setForm({ ...form, icon: e.target.value })}
                  placeholder="📱"
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
                />
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={form.is_active}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  className="w-4 h-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500"
                />
                <label htmlFor="is_active" className="text-sm text-gray-700">Aktiv</label>
              </div>

              <button
                type="submit"
                className="w-full bg-brand-600 text-white py-2.5 rounded-lg font-medium hover:bg-brand-700 transition"
              >
                {editing ? 'Saqlash' : 'Yaratish'}
              </button>
            </form>
          </div>
        </div>
      )}

      {/* Categories Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {categories.map((cat) => (
          <div
            key={cat.id}
            className={`bg-white rounded-xl border p-5 transition ${
              cat.is_active !== false ? 'border-gray-200' : 'border-gray-200 opacity-50'
            }`}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-3">
                <span className="text-2xl">{cat.icon || '📁'}</span>
                <div>
                  <p className="font-semibold text-gray-900">{cat.name_uz}</p>
                  {cat.name_ru && <p className="text-xs text-gray-400">{cat.name_ru}</p>}
                </div>
              </div>
              {cat.is_active === false && (
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">Nofaol</span>
              )}
            </div>

            <div className="flex items-center gap-2 mt-3">
              <button
                onClick={() => openEdit(cat)}
                className="flex-1 flex items-center justify-center gap-1 py-1.5 text-sm text-gray-600 hover:bg-gray-50 rounded-lg border border-gray-200 transition"
              >
                <Pencil size={14} />
                Tahrirlash
              </button>
              <button
                onClick={() => handleDelete(cat.id)}
                className="flex items-center justify-center p-1.5 text-red-400 hover:bg-red-50 rounded-lg border border-gray-200 transition"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
        ))}

        {categories.length === 0 && (
          <div className="col-span-3 text-center py-12 text-gray-400">
            Hali kategoriya yo'q
          </div>
        )}
      </div>
    </div>
  )
}
