import { Toaster } from "@/components/ui/toaster"
import { QueryClientProvider } from "@tanstack/react-query"
import { queryClientInstance } from "@/lib/query-client"
import { BrowserRouter as Router, Route, Routes } from "react-router-dom"
import PageNotFound from "./lib/PageNotFound"
import ScrollToTop from "./components/ScrollToTop"
import Layout from "@/components/Layout"
import Landing from "@/pages/Landing"
import Studio from "@/pages/Studio"
import Collaborate from "@/pages/Collaborate"
import Settings from "@/pages/Settings"

// Single-user local tool — no auth. The app opens straight on the character
// picker (Landing) and the Studio; both talk to the FastAPI backend.
function App() {
  return (
    <QueryClientProvider client={queryClientInstance}>
      <Router>
        <ScrollToTop />
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Landing />} />
            <Route path="/studio" element={<Studio />} />
            <Route path="/collaborate" element={<Collaborate />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<PageNotFound />} />
        </Routes>
      </Router>
      <Toaster />
    </QueryClientProvider>
  )
}

export default App
