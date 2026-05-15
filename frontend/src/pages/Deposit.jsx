import { Wallet, CreditCard, Smartphone } from 'lucide-react'
import useAuthStore from '../hooks/useAuth'

export default function DepositPage() {
  const { user } = useAuthStore()

  const paymentMethods = [
    {
      name: 'Payme',
      icon: '💳',
      color: 'bg-cyan-50 border-cyan-200',
      textColor: 'text-cyan-700',
    },
    {
      name: 'Click',
      icon: '📱',
      color: 'bg-blue-50 border-blue-200',
      textColor: 'text-blue-700',
    },
    {
      name: 'Uzum Bank',
      icon: '🏦',
      color: 'bg-purple-50 border-purple-200',
      textColor: 'text-purple-700',
    },
  ]

  return (
    <div className="max-w-xl">
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900">Balansni to'ldirish</h1>
        <p className="text-gray-500 mt-1">Reklama kampanyalari uchun balans qo'shing</p>
      </div>

      {/* Current Balance */}
      <div className="bg-gradient-to-r from-brand-600 to-brand-700 rounded-xl p-6 text-white mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Wallet size={20} />
          <span className="text-sm text-brand-100">Joriy balans</span>
        </div>
        <p className="text-3xl font-bold">
          {Number(user?.balance || 0).toLocaleString()} UZS
        </p>
      </div>

      {/* Payment Methods */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">To'lov usulini tanlang</h2>

        <div className="space-y-3">
          {paymentMethods.map((method) => (
            <button
              key={method.name}
              className={`w-full flex items-center gap-4 p-4 border rounded-xl transition hover:shadow-sm ${method.color}`}
              onClick={() => {}}
            >
              <span className="text-2xl">{method.icon}</span>
              <div className="flex-1 text-left">
                <p className={`font-semibold ${method.textColor}`}>{method.name}</p>
                <p className="text-xs text-gray-400">Tez orada ishga tushiriladi</p>
              </div>
              <span className="text-xs bg-yellow-100 text-yellow-700 px-2 py-0.5 rounded-full font-medium">
                Tez orada
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Info */}
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-5">
        <div className="flex items-start gap-3">
          <CreditCard size={20} className="text-amber-600 mt-0.5" />
          <div>
            <p className="font-medium text-amber-800">To'lov tizimi ishga tushirilmoqda</p>
            <p className="text-sm text-amber-600 mt-1">
              Hozirda onlayn to'lov qabul qilish funksiyasi ustida ishlayapmiz.
              Tez orada Payme, Click va Uzum Bank orqali to'lov qilish imkoniyati paydo bo'ladi.
            </p>
            <p className="text-sm text-amber-600 mt-2">
              Savollar uchun: <span className="font-medium">@aimaa_ads_support</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
