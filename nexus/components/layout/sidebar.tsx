'use client'

import { useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  LayoutDashboard, Users, GitMerge, Megaphone, BarChart3,
  Phone, Mic, Mail, Inbox, Send, CreditCard, FileText,
  Clock, CalendarCheck, CalendarDays, Umbrella, Calendar,
  CheckSquare, Bot, HelpCircle, Settings, ChevronDown,
  ChevronRight, Zap, UserCheck, Building2, TrendingUp
} from 'lucide-react'
import { clsx } from 'clsx'

type NavChild = { name: string; href: string; icon: React.ElementType }
type NavItem = {
  name: string
  href?: string
  icon: React.ElementType
  children?: NavChild[]
  badge?: string
}
type NavSection = { label: string; items: NavItem[] }

const navigation: NavSection[] = [
  {
    label: 'Oversigt',
    items: [
      { name: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    label: 'CRM',
    items: [
      { name: 'Leads', href: '/dashboard/crm/leads', icon: Users, badge: '24' },
      { name: 'Pipeline', href: '/dashboard/crm/pipeline', icon: GitMerge },
      { name: 'Kontakter', href: '/dashboard/crm/contacts', icon: UserCheck },
    ],
  },
  {
    label: 'Marketing',
    items: [
      { name: 'Meta Ads', href: '/dashboard/marketing/meta-ads', icon: BarChart3 },
      { name: 'Power Dialer', href: '/dashboard/marketing/power-dialer', icon: Phone },
      { name: 'Voice Agent', href: '/dashboard/marketing/voice-agent', icon: Mic },
      {
        name: 'Email',
        icon: Mail,
        children: [
          { name: 'Smart Indbakke', href: '/dashboard/marketing/email/smart-inbox', icon: Inbox },
          { name: 'Masse E-mail', href: '/dashboard/marketing/email/bulk-email', icon: Send },
        ],
      },
    ],
  },
  {
    label: 'Finans',
    items: [
      { name: 'Fakturering', href: '/dashboard/finance/invoicing', icon: FileText },
      { name: 'Betalinger', href: '/dashboard/finance/payments', icon: CreditCard },
    ],
  },
  {
    label: 'HR',
    items: [
      { name: 'Tidsporing', href: '/dashboard/hr/time-tracking', icon: Clock },
      { name: 'Fremmøde', href: '/dashboard/hr/attendance', icon: CalendarCheck },
      { name: 'Arbejdsplan', href: '/dashboard/hr/work-schedule', icon: CalendarDays },
      { name: 'Orlov', href: '/dashboard/hr/leave', icon: Umbrella },
    ],
  },
  {
    label: 'Produktivitet',
    items: [
      { name: 'Kalender', href: '/dashboard/productivity/calendar', icon: Calendar },
      { name: 'Opgaver', href: '/dashboard/productivity/tasks', icon: CheckSquare },
    ],
  },
  {
    label: 'System',
    items: [
      { name: 'PA Autopilot', href: '/dashboard/system/pa-autopilot', icon: Bot },
      { name: 'Hjælpecenter', href: '/dashboard/system/help-center', icon: HelpCircle },
      { name: 'Indstillinger', href: '/dashboard/system/settings', icon: Settings },
    ],
  },
]

export function Sidebar() {
  const pathname = usePathname()
  const [expandedItems, setExpandedItems] = useState<string[]>(['Email'])

  const toggle = (name: string) =>
    setExpandedItems(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    )

  const isActive = (href: string) =>
    href === '/dashboard' ? pathname === '/dashboard' : pathname.startsWith(href)

  return (
    <aside className="flex flex-col w-64 bg-gray-950 border-r border-gray-800/60 h-screen overflow-hidden flex-shrink-0">
      {/* Logo */}
      <div className="flex items-center h-16 px-5 border-b border-gray-800/60 flex-shrink-0">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center shadow-lg">
            <Zap className="w-4 h-4 text-white" fill="white" />
          </div>
          <div>
            <span className="text-white font-semibold text-base tracking-tight">Nexus</span>
            <span className="block text-gray-500 text-[10px] tracking-widest uppercase leading-none">Platform</span>
          </div>
        </div>
      </div>

      {/* Workspace selector */}
      <div className="px-3 py-3 border-b border-gray-800/60 flex-shrink-0">
        <button className="w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg hover:bg-gray-800/60 transition-colors group">
          <div className="w-6 h-6 rounded-md bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center flex-shrink-0">
            <Building2 className="w-3.5 h-3.5 text-indigo-400" />
          </div>
          <div className="flex-1 text-left min-w-0">
            <p className="text-xs font-medium text-gray-300 truncate">Acme ApS</p>
            <p className="text-[10px] text-gray-600 truncate">Business plan</p>
          </div>
          <ChevronDown className="w-3.5 h-3.5 text-gray-600 group-hover:text-gray-400 transition-colors flex-shrink-0" />
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-3 px-2.5 space-y-5 scrollbar-hide">
        {navigation.map((section) => (
          <div key={section.label}>
            <p className="text-[10px] font-semibold text-gray-600 uppercase tracking-widest px-2.5 mb-1.5">
              {section.label}
            </p>
            <div className="space-y-0.5">
              {section.items.map((item) => {
                if (item.children) {
                  const expanded = expandedItems.includes(item.name)
                  const childActive = item.children.some(c => isActive(c.href))
                  return (
                    <div key={item.name}>
                      <button
                        onClick={() => toggle(item.name)}
                        className={clsx(
                          'w-full flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors',
                          childActive
                            ? 'text-gray-200 bg-gray-800/80'
                            : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
                        )}
                      >
                        <item.icon className="w-4 h-4 flex-shrink-0" />
                        <span className="flex-1 text-left font-medium">{item.name}</span>
                        {expanded
                          ? <ChevronDown className="w-3.5 h-3.5 text-gray-600" />
                          : <ChevronRight className="w-3.5 h-3.5 text-gray-600" />
                        }
                      </button>
                      {expanded && (
                        <div className="ml-3.5 pl-3 border-l border-gray-800 mt-0.5 space-y-0.5">
                          {item.children.map((child) => (
                            <Link
                              key={child.href}
                              href={child.href}
                              className={clsx(
                                'flex items-center gap-2.5 px-2.5 py-1.5 rounded-lg text-sm transition-colors',
                                isActive(child.href)
                                  ? 'text-white bg-indigo-600 shadow-sm'
                                  : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
                              )}
                            >
                              <child.icon className="w-3.5 h-3.5 flex-shrink-0" />
                              <span className="font-medium">{child.name}</span>
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                }

                return (
                  <Link
                    key={item.href}
                    href={item.href!}
                    className={clsx(
                      'flex items-center gap-2.5 px-2.5 py-2 rounded-lg text-sm transition-colors',
                      isActive(item.href!)
                        ? 'text-white bg-indigo-600 shadow-sm'
                        : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
                    )}
                  >
                    <item.icon className="w-4 h-4 flex-shrink-0" />
                    <span className="flex-1 font-medium">{item.name}</span>
                    {item.badge && (
                      <span className="text-[10px] font-semibold bg-indigo-500/20 text-indigo-400 px-1.5 py-0.5 rounded-full">
                        {item.badge}
                      </span>
                    )}
                  </Link>
                )
              })}
            </div>
          </div>
        ))}
      </nav>

      {/* User */}
      <div className="border-t border-gray-800/60 p-3 flex-shrink-0">
        <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-lg hover:bg-gray-800/50 transition-colors cursor-pointer">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center flex-shrink-0">
            <span className="text-[11px] font-bold text-white">MJ</span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-gray-300 truncate">Magnus Jensen</p>
            <p className="text-[10px] text-gray-600 truncate">Administrator</p>
          </div>
          <TrendingUp className="w-3.5 h-3.5 text-emerald-500 flex-shrink-0" />
        </div>
      </div>
    </aside>
  )
}
