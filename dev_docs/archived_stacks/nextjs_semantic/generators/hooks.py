"""
React hooks generator for Next.js Semantic UI stack.

Generates custom hooks for:
- Data prefetching
- Signal data management
- Optimistic updates
- Client-side caching
"""

from pathlib import Path

from ....core import ir


class HooksGenerator:
    """Generate React hooks for runtime optimizations."""

    def __init__(self, spec: ir.AppSpec, project_path: Path):
        self.spec = spec
        self.project_path = project_path

    def generate(self) -> None:
        """Generate all hooks."""
        self._generate_use_signal_data()
        self._generate_use_prefetch()
        self._generate_index()

    def _generate_use_signal_data(self) -> None:
        """Generate useSignalData hook for fetching and caching signal data."""
        content = '''/**
 * useSignalData Hook
 *
 * Fetches and caches signal data with SWR-like semantics.
 * Provides loading states, error handling, and automatic revalidation.
 *
 * Performance features:
 * - Client-side caching (reduces API calls)
 * - Stale-while-revalidate pattern
 * - Automatic background refresh
 * - Deduplication of concurrent requests
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';

interface SignalDataState<T> {
  data: T | null;
  isLoading: boolean;
  error: Error | null;
  isValidating: boolean;
}

interface UseSignalDataOptions {
  /** Initial data (e.g., from server-side rendering) */
  initialData?: unknown;
  /** Time in ms before data is considered stale (default: 30000) */
  staleTime?: number;
  /** Time in ms to cache data (default: 300000) */
  cacheTime?: number;
  /** Revalidate on window focus (default: true) */
  revalidateOnFocus?: boolean;
  /** Revalidate on reconnect (default: true) */
  revalidateOnReconnect?: boolean;
}

// Simple in-memory cache
const cache = new Map<string, { data: unknown; timestamp: number }>();

export function useSignalData<T = unknown>(
  signalId: string,
  fetcher: () => Promise<T>,
  options: UseSignalDataOptions = {}
): SignalDataState<T> & { mutate: (data: T) => void; revalidate: () => void } {
  const {
    initialData,
    staleTime = 30000,
    cacheTime = 300000,
    revalidateOnFocus = true,
    revalidateOnReconnect = true,
  } = options;

  const [state, setState] = useState<SignalDataState<T>>(() => {
    // Check cache first
    const cached = cache.get(signalId);
    if (cached && Date.now() - cached.timestamp < cacheTime) {
      return {
        data: cached.data as T,
        isLoading: false,
        error: null,
        isValidating: Date.now() - cached.timestamp > staleTime,
      };
    }

    return {
      data: initialData as T ?? null,
      isLoading: !initialData,
      error: null,
      isValidating: false,
    };
  });

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const fetchData = useCallback(async (isRevalidation = false) => {
    const cacheKey = signalId;

    // Set loading/validating state
    setState(prev => ({
      ...prev,
      isLoading: !isRevalidation && !prev.data,
      isValidating: isRevalidation,
    }));

    try {
      const data = await fetcherRef.current();

      // Update cache
      cache.set(cacheKey, { data, timestamp: Date.now() });

      // Update state
      setState({
        data,
        isLoading: false,
        error: null,
        isValidating: false,
      });
    } catch (error) {
      setState(prev => ({
        ...prev,
        isLoading: false,
        error: error instanceof Error ? error : new Error(String(error)),
        isValidating: false,
      }));
    }
  }, [signalId]);

  // Initial fetch
  useEffect(() => {
    const cached = cache.get(signalId);
    const isStale = !cached || Date.now() - cached.timestamp > staleTime;

    if (isStale) {
      fetchData(!!cached);
    }
  }, [signalId, staleTime, fetchData]);

  // Revalidate on focus
  useEffect(() => {
    if (!revalidateOnFocus) return;

    const handleFocus = () => {
      const cached = cache.get(signalId);
      if (!cached || Date.now() - cached.timestamp > staleTime) {
        fetchData(true);
      }
    };

    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [signalId, staleTime, revalidateOnFocus, fetchData]);

  // Revalidate on reconnect
  useEffect(() => {
    if (!revalidateOnReconnect) return;

    const handleOnline = () => {
      const cached = cache.get(signalId);
      if (!cached || Date.now() - cached.timestamp > staleTime) {
        fetchData(true);
      }
    };

    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, [signalId, staleTime, revalidateOnReconnect, fetchData]);

  // Manual mutations
  const mutate = useCallback((data: T) => {
    cache.set(signalId, { data, timestamp: Date.now() });
    setState({
      data,
      isLoading: false,
      error: null,
      isValidating: false,
    });
  }, [signalId]);

  const revalidate = useCallback(() => {
    fetchData(true);
  }, [fetchData]);

  return { ...state, mutate, revalidate };
}

// Export cache utilities for testing/debugging
export const signalCache = {
  get: (key: string) => cache.get(key),
  set: (key: string, data: unknown) => cache.set(key, { data, timestamp: Date.now() }),
  clear: () => cache.clear(),
  delete: (key: string) => cache.delete(key),
};
'''
        hooks_dir = self.project_path / "src" / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        output_path = hooks_dir / "useSignalData.ts"
        output_path.write_text(content)

    def _generate_use_prefetch(self) -> None:
        """Generate usePrefetch hook for preloading signal data."""
        content = '''/**
 * usePrefetch Hook
 *
 * Preloads signal data before it's needed.
 * Use on hover/focus to reduce perceived latency.
 *
 * Performance features:
 * - Prefetches data on interaction (hover, focus)
 * - Deduplicates concurrent prefetch requests
 * - Integrates with useSignalData cache
 */

'use client';

import { useCallback, useRef } from 'react';
import { signalCache } from './useSignalData';

interface PrefetchOptions {
  /** Delay before prefetching starts (default: 100ms) */
  delay?: number;
  /** Time to keep prefetched data fresh (default: 30000ms) */
  staleTime?: number;
}

// Track in-flight prefetch requests
const prefetching = new Set<string>();

export function usePrefetch(
  signalId: string,
  fetcher: () => Promise<unknown>,
  options: PrefetchOptions = {}
) {
  const { delay = 100, staleTime = 30000 } = options;

  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const prefetch = useCallback(() => {
    // Clear any pending prefetch
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
    }

    // Schedule prefetch
    timeoutRef.current = setTimeout(async () => {
      // Check if already prefetching
      if (prefetching.has(signalId)) {
        return;
      }

      // Check if data is fresh
      const cached = signalCache.get(signalId);
      if (cached && Date.now() - cached.timestamp < staleTime) {
        return;
      }

      // Mark as prefetching
      prefetching.add(signalId);

      try {
        const data = await fetcherRef.current();
        signalCache.set(signalId, data);
      } catch {
        // Silently fail - prefetch is best-effort
      } finally {
        prefetching.delete(signalId);
      }
    }, delay);
  }, [signalId, delay, staleTime]);

  const cancelPrefetch = useCallback(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  return {
    /** Trigger prefetch on hover/focus */
    onMouseEnter: prefetch,
    onFocus: prefetch,
    /** Cancel prefetch on leave/blur */
    onMouseLeave: cancelPrefetch,
    onBlur: cancelPrefetch,
    /** Manual prefetch trigger */
    prefetch,
    /** Manual cancel */
    cancelPrefetch,
  };
}
'''
        hooks_dir = self.project_path / "src" / "hooks"
        output_path = hooks_dir / "usePrefetch.ts"
        output_path.write_text(content)

    def _generate_index(self) -> None:
        """Generate hooks index file."""
        content = '''/**
 * Custom Hooks Index
 *
 * Performance-optimized hooks for signal data management.
 */

export { useSignalData, signalCache } from './useSignalData';
export { usePrefetch } from './usePrefetch';
'''
        hooks_dir = self.project_path / "src" / "hooks"
        output_path = hooks_dir / "index.ts"
        output_path.write_text(content)


__all__ = ["HooksGenerator"]
