import { useState, useEffect, useCallback } from 'react';
import { getMetrics } from '../api/api';

/**
 * Custom hook to fetch and cache business dashboard metrics.
 */
export function useDashboard() {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  const fetchMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getMetrics();
      setMetrics(data.dashboard_metrics || null);
      setLastUpdated(
        new Date().toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
        })
      );
    } catch (err) {
      console.error('Failed to fetch dashboard metrics:', err);
      setError(err.message || 'Failed to load executive dashboard metrics.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return {
    metrics,
    loading,
    error,
    lastUpdated,
    refreshMetrics: fetchMetrics,
  };
}
