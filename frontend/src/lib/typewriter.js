/**
 * Typewriter buffer — drains a queue of tokens at a target reveal rate.
 * Compensates for proxy/server-side burst-buffering so the UI feels smooth.
 *
 * Usage:
 *   const tw = createTypewriter({ rate: 60, onUpdate: (text) => setText(text) });
 *   tw.append("Hello ");
 *   tw.append("World");
 *   await tw.flush(); // wait for queue to drain
 *   tw.dispose();
 */
export function createTypewriter({ rate = 60, onUpdate, maxBurst = 8 } = {}) {
  let buffer = "";
  let revealed = "";
  let timer = null;
  let onDone = null;
  let aborted = false;

  const tick = () => {
    if (aborted) return;
    if (buffer.length === 0) {
      if (onDone) { const cb = onDone; onDone = null; cb(); }
      timer = null;
      return;
    }
    // If buffer is very large (proxy burst), reveal multiple chars per tick
    const step = Math.max(1, Math.min(maxBurst, Math.floor(buffer.length / 30)));
    revealed += buffer.slice(0, step);
    buffer = buffer.slice(step);
    try { onUpdate?.(revealed); } catch {}
    timer = setTimeout(tick, 1000 / rate);
  };

  return {
    append(text) {
      if (!text) return;
      buffer += text;
      if (!timer && !aborted) timer = setTimeout(tick, 0);
    },
    flush() {
      return new Promise((resolve) => {
        if (aborted || (buffer.length === 0 && !timer)) return resolve();
        onDone = resolve;
      });
    },
    forceComplete() {
      revealed += buffer;
      buffer = "";
      try { onUpdate?.(revealed); } catch {}
      if (timer) { clearTimeout(timer); timer = null; }
      if (onDone) { const cb = onDone; onDone = null; cb(); }
    },
    dispose() {
      aborted = true;
      if (timer) { clearTimeout(timer); timer = null; }
    },
    getRevealed() { return revealed; },
  };
}
