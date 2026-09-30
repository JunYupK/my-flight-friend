import type { ReactNode } from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import AppShell from "./components/layout/AppShell";
import Dashboard from "./pages/Dashboard";
import NewTrip from "./pages/NewTrip";
import TripPage from "./pages/TripPage";
import Admin from "./pages/Admin";

function Shell({ children }: { children: ReactNode }) {
  return (
    <AppShell
      actions={
        <Button asChild variant="ghost" size="sm">
          <Link to="/trips/new">새 여행</Link>
        </Button>
      }
    >
      {children}
    </AppShell>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route
          path="/trips/new"
          element={
            <Shell>
              <NewTrip />
            </Shell>
          }
        />
        <Route
          path="/trips/:id"
          element={
            <Shell>
              <TripPage />
            </Shell>
          }
        />
        <Route
          path="/admin"
          element={
            <Shell>
              <Admin />
            </Shell>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
