import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import AppShell from './components/layout/AppShell';
import ErrorBoundary from './components/ui/ErrorBoundary';
import LoadingSpinner from './components/ui/LoadingSpinner';

// 静态导入:轻量页(快速进入)
import Dashboard from './pages/Dashboard';
import Screener from './pages/Screener';
import Watchlist from './pages/Watchlist';
import Trades from './pages/Trades';
import Settings from './pages/Settings';

// 动态导入:重型页(ECharts 体积大,延迟到首次访问再加载)
const StockAnalysis = lazy(() => import('./pages/StockAnalysis'));
const Backtest = lazy(() => import('./pages/Backtest'));
const Simulator = lazy(() => import('./pages/Simulator'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function PageFallback() {
  return (
    <div className="flex items-center justify-center h-96">
      <LoadingSpinner size="lg" text="加载中..." />
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="/" element={<Dashboard />} />
              <Route
                path="/stock/:tsCode"
                element={
                  <Suspense fallback={<PageFallback />}>
                    <StockAnalysis />
                  </Suspense>
                }
              />
              <Route path="/screen" element={<Screener />} />
              <Route path="/watchlist" element={<Watchlist />} />
              <Route
                path="/backtest"
                element={
                  <Suspense fallback={<PageFallback />}>
                    <Backtest />
                  </Suspense>
                }
              />
              <Route
                path="/simulator"
                element={
                  <Suspense fallback={<PageFallback />}>
                    <Simulator />
                  </Suspense>
                }
              />
              <Route path="/trades" element={<Trades />} />
              <Route path="/settings" element={<Settings />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
