import { useCallback, useEffect, useState } from "react";

import { ApiError } from "../api/client";

export interface AsyncState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Minimal data-fetching hook.
 *
 * No react-query. At this scale its cache, retry and invalidation machinery
 * would be more code to understand than the thing it manages, and the one
 * behaviour that actually matters here — discard the response of a request
 * that has been superseded — is eight lines. If background refetching or
 * optimistic updates become real requirements, that trade flips.
 */
export function useApi<T>(fetcher: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);

    fetcher()
      .then((result) => {
        // Guards against the out-of-order response: switch profile twice
        // quickly and the slower first request must not overwrite the second.
        if (current) setData(result);
      })
      .catch((cause: unknown) => {
        if (!current) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setData(null);
      })
      .finally(() => {
        if (current) setLoading(false);
      });

    return () => {
      current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return { data, error, loading, reload };
}
