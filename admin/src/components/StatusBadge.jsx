import clsx from 'clsx'

const styles = {
  active: 'bg-emerald-100 text-emerald-700',
  approved: 'bg-emerald-100 text-emerald-700',
  pending: 'bg-yellow-100 text-yellow-700',
  rejected: 'bg-red-100 text-red-700',
  paused: 'bg-orange-100 text-orange-700',
  suspended: 'bg-red-100 text-red-700',
  draft: 'bg-gray-100 text-gray-600',
  completed: 'bg-blue-100 text-blue-700',
}

const labels = {
  active: 'Aktiv',
  approved: 'Tasdiqlangan',
  pending: 'Kutilmoqda',
  rejected: 'Rad etilgan',
  paused: 'Pauza',
  suspended: "To'xtatilgan",
  draft: 'Taslak',
  completed: 'Tugallangan',
}

export default function StatusBadge({ status }) {
  return (
    <span className={clsx(
      'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium',
      styles[status] || 'bg-gray-100 text-gray-600'
    )}>
      {labels[status] || status}
    </span>
  )
}
