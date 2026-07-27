import { useLocation } from "react-router-dom"

export default function PageNotFound() {
  const location = useLocation()
  const pageName = location.pathname.substring(1)

  return (
    <div className="min-h-screen flex items-center justify-center p-6 bg-[#0a0a0b] text-zinc-100">
      <div className="max-w-md w-full">
        <div className="text-center space-y-6">
          <div className="space-y-2">
            <h1 className="text-7xl font-light text-zinc-700">404</h1>
            <div className="h-0.5 w-16 bg-white/10 mx-auto" />
          </div>
          <div className="space-y-3">
            <h2 className="text-2xl font-medium">Page not found</h2>
            <p className="text-zinc-400 leading-relaxed">
              The page <span className="font-medium text-zinc-200">"{pageName}"</span> could not be found.
            </p>
          </div>
          <div className="pt-6">
            <button
              onClick={() => (window.location.href = "/")}
              className="inline-flex items-center px-4 py-2 text-sm font-medium text-zinc-200 ring-1 ring-white/15 rounded-lg hover:bg-white/5 transition-colors"
            >
              Go home
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
