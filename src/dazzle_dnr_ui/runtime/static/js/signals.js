/**
 * DNR-UI Signals - Reactive state primitives
 * Part of the Dazzle Native Runtime
 */

let currentSubscriber = null;
// Reserved for future dependency tracking
const _signalDeps = new Map(); // eslint-disable-line no-unused-vars
let batchDepth = 0;
const pendingEffects = new Set();

export function createSignal(initialValue, options = {}) {
  let value = initialValue;
  const subscribers = new Set();
  const { persistent, key, equals } = options;
  const isEqual = equals || ((a, b) => a === b);

  // Load from storage if persistent
  if (persistent && key) {
    const stored = localStorage.getItem(`dnr_${key}`);
    if (stored !== null) {
      try {
        value = JSON.parse(stored);
      } catch (e) {
        console.warn(`Failed to parse stored value for ${key}`, e);
      }
    }
  }

  function getter() {
    if (currentSubscriber) {
      subscribers.add(currentSubscriber);
    }
    return value;
  }

  function setter(newValue) {
    if (typeof newValue === 'function') {
      newValue = newValue(value);
    }
    if (!isEqual(value, newValue)) {
      value = newValue;
      // Persist if needed
      if (persistent && key) {
        localStorage.setItem(`dnr_${key}`, JSON.stringify(value));
      }
      // Notify subscribers
      if (batchDepth > 0) {
        subscribers.forEach(fn => pendingEffects.add(fn));
      } else {
        subscribers.forEach(fn => fn());
      }
    }
  }

  return [getter, setter];
}

export function batch(fn) {
  batchDepth++;
  try {
    fn();
  } finally {
    batchDepth--;
    if (batchDepth === 0) {
      const effects = Array.from(pendingEffects);
      pendingEffects.clear();
      effects.forEach(fn => fn());
    }
  }
}

export function createEffect(fn, options = {}) {
  let cleanup = null;
  const { defer = false } = options;

  function execute() {
    if (cleanup && typeof cleanup === 'function') {
      cleanup();
    }
    currentSubscriber = execute;
    try {
      cleanup = fn();
    } finally {
      currentSubscriber = null;
    }
  }

  if (defer) {
    requestAnimationFrame(execute);
  } else {
    execute();
  }

  return function dispose() {
    if (cleanup && typeof cleanup === 'function') {
      cleanup();
    }
  };
}

export function createMemo(fn, options = {}) {
  const [signal, setSignal] = createSignal(undefined, options);
  createEffect(() => {
    setSignal(fn());
  });
  return signal;
}

export function createResource(fetcher, options = {}) {
  const [data, setData] = createSignal(options.initialValue);
  const [loading, setLoading] = createSignal(false);
  const [error, setError] = createSignal(null);

  async function refetch(source) {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher(source);
      setData(result);
      return result;
    } catch (e) {
      setError(e);
      throw e;
    } finally {
      setLoading(false);
    }
  }

  // Auto-fetch if source provided
  if (options.source) {
    refetch(options.source);
  }

  return { data, loading, error, refetch };
}
