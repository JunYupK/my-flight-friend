import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import AppShell from "./components/layout/AppShell";
import TripList from "./pages/TripList";
import NewTrip from "./pages/NewTrip";
import TripPage from "./pages/TripPage";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <BrowserRouter>
      <AppShell
        actions={
          <Button asChild variant="ghost" size="sm">
            <Link to="/trips/new">새 여행</Link>
          </Button>
        }
      >
        <Routes>
          <Route path="/" element={<TripList />} />
          <Route path="/trips/new" element={<NewTrip />} />
          <Route path="/trips/:id" element={<TripPage />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </AppShell>
    </BrowserRouter>
  );
}
