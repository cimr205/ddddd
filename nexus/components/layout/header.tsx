'use client'

import { useState } from 'react'
import { Search, Bell, Plus, ChevronDown, Command } from 'lucide-react'

export function Header() {
  const [searchOpen, setSearchOpen] = useState(false)

  return (
    <header className="h-16 bg-white border-b border-gray-200 flex items-center px-6 gap-4 flex-shrink-0 z-10">
      {/* Search */}
      <div className="flex-1 max-w-md">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Søg..."
            className="w-full pl-9 pr-16 py-2 text-sm bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:bg-white transition-all text-gray-900 placeholder-gray-400"
          />
          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-1">
            <kbd className="text-[10px] font-medium text-gray-400 bg-white border border-gray-200 rounded px-1 py-0.5">⌘K</kbd>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 ml-auto">
        {/* Quick create */}
        <button className="btn-primary text-xs py-1.5">
          <Plus className="w-3.5 h-3.5" />
          Ny
        </button>

        {/* Notifications */}
        <button className="relative w-9 h-9 flex items-center justify-center rounded-lg hover:bg-gray-100 transition-colors">
          <Bell className="w-4.5 h-4.5 text-gray-500" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
        </button>

        {/* User */}
        <button className="flex items-center gap-2 pl-1 pr-2 py-1 rounded-lg hover:bg-gray-100 transition-colors">
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <span className="text-[11px] font-bold text-white">MJ</span>
          </div>
          <span className="text-sm font-medium text-gray-700">Magnus</span>
          <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
        </button>
      </div>
    </header>
  )
}
