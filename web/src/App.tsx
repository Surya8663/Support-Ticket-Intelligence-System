import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Anomalies } from "./pages/Anomalies";
import { Ask } from "./pages/Ask";
import { Overview } from "./pages/Overview";
import { Tickets } from "./pages/Tickets";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="ask" element={<Ask />} />
        <Route path="anomalies" element={<Anomalies />} />
        <Route path="tickets" element={<Tickets />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
