/**
 * Tests for the signals module.
 */
import { describe, it, expect } from 'vitest';
import { createSignal, createMemo, createEffect, batch } from './signals.js';

describe('createSignal', () => {
  it('should create a signal with initial value', () => {
    const [count] = createSignal(0);
    expect(count()).toBe(0);
  });

  it('should update signal value', () => {
    const [count, setCount] = createSignal(0);
    setCount(5);
    expect(count()).toBe(5);
  });

  it('should support functional updates', () => {
    const [count, setCount] = createSignal(10);
    setCount(prev => prev + 5);
    expect(count()).toBe(15);
  });
});

describe('createMemo', () => {
  it('should compute derived value', () => {
    const [count] = createSignal(5);
    const doubled = createMemo(() => count() * 2);
    expect(doubled()).toBe(10);
  });

  it('should update when dependency changes', () => {
    const [count, setCount] = createSignal(5);
    const doubled = createMemo(() => count() * 2);

    setCount(10);
    expect(doubled()).toBe(20);
  });
});

describe('createEffect', () => {
  it('should run effect on signal change', () => {
    const [count, setCount] = createSignal(0);
    let effectRan = false;

    createEffect(() => {
      count(); // Subscribe to signal
      effectRan = true;
    });

    expect(effectRan).toBe(true);

    effectRan = false;
    setCount(1);
    expect(effectRan).toBe(true);
  });
});

describe('batch', () => {
  it('should batch multiple updates', () => {
    const [a, setA] = createSignal(0);
    const [b, setB] = createSignal(0);
    let computeCount = 0;

    createMemo(() => {
      computeCount++;
      return a() + b();
    });

    const initialCount = computeCount;

    batch(() => {
      setA(1);
      setB(2);
    });

    // Should only have computed once more after batch
    expect(computeCount).toBe(initialCount + 1);
  });
});
