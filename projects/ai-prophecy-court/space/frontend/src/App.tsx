import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { SiteShell } from "./components/site-shell";

const ArchivePage = lazy(() =>
  import("./pages/archive").then((module) => ({ default: module.ArchivePage })),
);
const DossierPage = lazy(() =>
  import("./pages/dossier").then((module) => ({ default: module.DossierPage })),
);
const HomePage = lazy(() =>
  import("./pages/home").then((module) => ({ default: module.HomePage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      retry: 1,
    },
  },
});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <SiteShell>
          <Suspense fallback={<RouteLoading />}>
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/people/:personId" element={<DossierPage />} />
              <Route path="/archive" element={<ArchivePage />} />
            </Routes>
          </Suspense>
        </SiteShell>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

function RouteLoading() {
  return (
    <section className="shell state-page">
      <div className="eyebrow">Calling the next case</div>
      <h1>The clerk is opening the file.</h1>
    </section>
  );
}
