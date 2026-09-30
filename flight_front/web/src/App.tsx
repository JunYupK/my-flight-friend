import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import AppShell from "./components/layout/AppShell";

const Dashboard = lazy(() => import("./pages/Dashboard"));
const NewTrip = lazy(() => import("./pages/NewTrip"));
const TripPage = lazy(() => import("./pages/TripPage"));
const Admin = lazy(() => import("./pages/Admin"));

const fallback = (
  <div className="mx-auto max-w-5xl space-y-4 p-4">
    <Skeleton className="h-16 w-full" />
    <Skeleton className="h-56 w-full rounded-2xl" />
  </div>
);

function Shell({ children }: { children: ReactNode }) {
  return (
    <AppShell
      actions={
        <Button asChild variant="ghost" size="sm">
          <Link to="/trips/new">새 Trip</Link>
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
      <Suspense fallback={fallback}>
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
      </Suspense>
    </BrowserRouter>
  );
}
