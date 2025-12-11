// @ts-check
/**
 * DNR-UI Signals - Reactive state primitives
 * Part of the Dazzle Native Runtime
 *
 * @module signals
 */

// =============================================================================
// Type Definitions
// =============================================================================

/**
 * @template T
 * @typedef {() => T} SignalGetter - Function that returns the current signal value
 */

/**
 * @template T
 * @typedef {(value: T | ((prev: T) => T)) => void} SignalSetter - Function to update signal value
 */

/**
 * @template T
 * @typedef {[SignalGetter<T>, SignalSetter<T>]} Signal - Tuple of getter and setter functions
 */

/**
 * @typedef {Object} SignalOptions
 * @property {boolean} [persistent] - Persist value to localStorage
 * @property {string} [key] - Storage key for persistence
 * @property {(a: any, b: any) => boolean} [equals] - Custom equality check
 */

/**
 * @typedef {Object} EffectOptions
 * @property {boolean} [defer] - Defer first execution to next animation frame
 */

/**
 * @template T
 * @typedef {Object} Resource
 * @property {SignalGetter<T|undefined>} data - The fetched data
 * @property {SignalGetter<boolean>} loading - Loading state
 * @property {SignalGetter<Error|null>} error - Error state
 * @property {(source?: any) => Promise<T>} refetch - Trigger a refetch
 */

// =============================================================================
// Internal State
// =============================================================================

let currentSubscriber = null;
// Reserved for future dependency tracking
const _signalDeps = new Map(); // eslint-disable-line no-unused-vars
let batchDepth = 0;
const pendingEffects = new Set();

// =============================================================================
// Signal Functions
// =============================================================================

/**
 * Create a reactive signal.
 *
 * @template T
 * @param {T} initialValue - Initial value for the signal
 * @param {SignalOptions} [options={}] - Signal configuration options
 * @returns {Signal<T>} Tuple of [getter, setter] functions
 *
 * @example
 * const [count, setCount] = createSignal(0);
 * console.log(count()); // 0
 * setCount(5);
 * setCount(prev => prev + 1); // Updater function
 */
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

/**
 * Batch multiple signal updates into a single effect run.
 *
 * @param {() => void} fn - Function containing signal updates
 *
 * @example
 * batch(() => {
 *   setX(1);
 *   setY(2);
 *   setZ(3);
 * }); // Effects run once, not three times
 */
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

/**
 * Create a reactive effect that re-runs when its dependencies change.
 *
 * @param {() => (void | (() => void))} fn - Effect function, may return cleanup
 * @param {EffectOptions} [options={}] - Effect configuration
 * @returns {() => void} Dispose function to stop the effect
 *
 * @example
 * const dispose = createEffect(() => {
 *   console.log('Count is:', count());
 *   return () => console.log('Cleanup');
 * });
 * dispose(); // Stop tracking
 */
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

/**
 * Create a memoized computed value that updates when dependencies change.
 *
 * @template T
 * @param {() => T} fn - Computation function
 * @param {SignalOptions} [options={}] - Signal options for the memo
 * @returns {SignalGetter<T>} Getter function for the computed value
 *
 * @example
 * const doubled = createMemo(() => count() * 2);
 * console.log(doubled()); // Recomputed when count changes
 */
export function createMemo(fn, options = {}) {
  const [signal, setSignal] = createSignal(undefined, options);
  createEffect(() => {
    setSignal(fn());
  });
  return signal;
}

/**
 * Create an async resource with loading and error states.
 *
 * @template T
 * @param {(source?: any) => Promise<T>} fetcher - Async fetch function
 * @param {Object} [options={}] - Resource options
 * @param {T} [options.initialValue] - Initial value before first fetch
 * @param {any} [options.source] - Source to pass to fetcher on creation
 * @returns {Resource<T>} Resource object with data, loading, error, and refetch
 *
 * @example
 * const { data, loading, error, refetch } = createResource(
 *   async () => fetch('/api/items').then(r => r.json())
 * );
 */
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
