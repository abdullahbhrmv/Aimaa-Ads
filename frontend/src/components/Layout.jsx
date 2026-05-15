import { NavLink } from 'react-router-dom'
import { LayoutDashboard, Megaphone, Radio, LogOut, Wallet, Settings, CreditCard } from 'lucide-react'
import useAuthStore from '../hooks/useAuth'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/campaigns', icon: Megaphone, label: 'Kampanyalar' },
  { to: '/channels', icon: Radio, label: 'Kanallar' },
  { to: '/deposit', icon: CreditCard, label: 'Balans' },
  { to: '/settings', icon: Settings, label: 'Sozlamalar' },
]

function SidebarLink({ to, icon: Icon, label }) {
  return (
    <NavLink
      to={to}
      end={to === '/'}
      className={({ isActive }) =>
        clsx(
          'flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors',
          isActive
            ? 'bg-brand-600 text-white'
            : 'text-gray-600 hover:bg-gray-100'
        )
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  )
}

export default function Layout({ children }) {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold text-brand-700">
            Aimaa<span className="text-accent-500">Ads</span>
          </h1>
          <p className="text-xs text-gray-400 mt-1">Telegram Reklam Platformasi</p>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          {navItems.map((item) => (
            <SidebarLink key={item.to} {...item} />
          ))}
        </nav>

        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-brand-100 flex items-center justify-center">
              <span className="text-sm font-semibold text-brand-700">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">{user?.username}</p>
              <p className="text-xs text-gray-400 flex items-center gap-1">
                <Wallet size={12} />
                {Number(user?.balance || 0).toLocaleString()} UZS
              </p>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 text-sm text-gray-500 hover:text-red-500 transition-colors"
          >
            <LogOut size={16} />
            Chiqish
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto p-8">
        {children}
      </main>
    </div>
  )
}
