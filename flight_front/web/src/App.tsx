import { BrowserRouter, Routes, Route, Link, useParams } from "react-router-dom";
import ThemeToggle from "./components/ThemeToggle";
import TripList from "./pages/TripList";
import NewTrip from "./pages/NewTrip";

function TripPlaceholder() {
  const { id } = useParams();
  return <p className="text-apple-secondary text-sm">여행 #{id} 상세 화면은 준비 중입니다.</p>;
}

function AdminPlaceholder() {
  return <p className="text-apple-secondary text-sm">관리 화면은 준비 중입니다.</p>;
}

function Layout() {
  return (
    <div className="min-h-screen bg-apple-bg">
      <header className="sticky top-0 z-30 backdrop-blur-xl bg-apple-surface/80 border-b border-apple-text/5">
        <div className="max-w-5xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-12">
            <div className="flex items-center gap-1 sm:gap-2">
              <Link
                to="/"
                className="font-semibold text-apple-text text-sm tracking-tight shrink-0 hover:opacity-70 transition-opacity mr-1 sm:mr-3"
              >
                Flight Friend
              </Link>
              <nav className="flex gap-0.5">
                <Link
                  to="/trips/new"
                  className="px-3 py-1 rounded-full text-xs font-medium text-apple-secondary hover:text-apple-text hover:bg-apple-text/5 transition-all duration-200"
                >
                  새 여행
                </Link>
              </nav>
            </div>
            <ThemeToggle />
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 sm:px-6 py-6 sm:py-10">
        <Routes>
          <Route path="/" element={<TripList />} />
          <Route path="/trips/new" element={<NewTrip />} />
          <Route path="/trips/:id" element={<TripPlaceholder />} />
          <Route path="/admin" element={<AdminPlaceholder />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Layout />
    </BrowserRouter>
  );
}
