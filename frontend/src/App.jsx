import { useState } from 'react'

function App() {
  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 flex flex-col items-center justify-center p-6">
      <div className="max-w-2xl w-full bg-slate-800 border border-slate-700 rounded-xl p-8 shadow-2xl">
        <h1 className="text-3xl font-bold text-indigo-400 mb-4">Monday.com BI Agent</h1>
        <p className="text-slate-300 mb-6">
          Welcome to the Monday.com BI Agent interface.
        </p>
        <div className="p-4 bg-slate-950/60 rounded-lg border border-slate-800 text-sm text-slate-400">
          Status: Ready for integration with backend API
        </div>
      </div>
    </div>
  )
}

export default App
