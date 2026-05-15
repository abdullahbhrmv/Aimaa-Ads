import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Radio, Megaphone, Users, DollarSign,
  FolderOpen, Settings, LogOut, Shield, Banknote
} from 'lucide-react'
import useAuthStore from '../hooks/useAuth'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/channels', icon: Radio, label: 'Kanallar' },
  { to: '/campaigns', icon: Megaphone, label: 'Kampanyalar' },
  { to: '/users', icon: Users, label: 'Foydalanuvchilar' },
  { to: '/revenue', icon: DollarSign, label: 'Daromad' },
  { to: '/categories', icon: FolderOpen, label: 'Kategoriyalar' },
  { to: '/payouts', icon: Banknote, label: "To'lovlar" },
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
            : 'text-gray-300 hover:bg-gray-800 hover:text-white'
        )
      }
    >
      <Icon size={18} />
      {label}
    </NavLink>
  )
}

export default function AdminLayout({ children }) {
  const { user, logout } = useAuthStore()

  return (
    <div className="flex h-screen bg-gray-100">
      {/* Dark Sidebar */}
      <aside className="w-64 bg-gray-900 flex flex-col">
        <div className="p-6">
          <div className="flex items-center gap-2">
            <Shield size={20} className="text-brand-400" />
            <h1 className="text-lg font-bold text-white">
              Aimaa<span className="text-accent-400">Ads</span>
              <span className="text-xs font-normal text-gray-400 ml-2">Admin</span>
            </h1>
          </div>
        </div>

        <nav className="flex-1 px-3 space-y-1">
          {navItems.map((item) => (
            <SidebarLink key={item.to} {...item} />
          ))}
        </nav>

        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-8 h-8 rounded-full bg-brand-600 flex items-center justify-center">
              <span className="text-sm font-semibold text-white">
                {user?.username?.[0]?.toUpperCase()}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">{user?.username}</p>
              <p className="text-xs text-gray-400">Administrator</p>
            </div>
          </div>
          <button
            onClick={logout}
            className="flex items-center gap-2 text-sm text-gray-400 hover:text-red-400 transition-colors"
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
