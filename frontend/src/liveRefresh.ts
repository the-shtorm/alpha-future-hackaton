export type LiveRefreshEnvironment = {
  isVisible: () => boolean;
  schedule: (callback: () => void, delayMs: number) => unknown;
  cancel: (handle: unknown) => void;
  onFocus: (callback: () => void) => () => void;
  onVisibilityChange: (callback: () => void) => () => void;
};

type LiveRefreshOptions = {
  intervalMs?: number;
  environment?: LiveRefreshEnvironment;
};

function browserEnvironment(): LiveRefreshEnvironment {
  const listen = (target: Window | Document, event: string, callback: () => void) => {
    target.addEventListener(event, callback);
    return () => target.removeEventListener(event, callback);
  };
  return {
    isVisible: () => document.visibilityState !== 'hidden',
    schedule: (callback, delayMs) => window.setTimeout(callback, delayMs),
    cancel: (handle) => window.clearTimeout(handle as number),
    onFocus: (callback) => listen(window, 'focus', callback),
    onVisibilityChange: (callback) => listen(document, 'visibilitychange', callback),
  };
}

// The initial load belongs to the component. Callers also guard applying an
// in-flight response after their effect is disposed; cleanup stops future work.
export function startLiveRefresh(
  refresh: () => Promise<void>,
  { intervalMs = 5000, environment = browserEnvironment() }: LiveRefreshOptions = {},
): () => void {
  let disposed = false;
  let inFlight = false;
  let timer: unknown;
  let scheduled = false;

  const cancelTimer = () => {
    if (scheduled) environment.cancel(timer);
    scheduled = false;
  };
  const schedule = () => {
    if (disposed || inFlight || !environment.isVisible()) return;
    cancelTimer();
    timer = environment.schedule(() => {
      scheduled = false;
      void run();
    }, intervalMs);
    scheduled = true;
  };
  const run = async () => {
    if (disposed || inFlight || !environment.isVisible()) return;
    cancelTimer();
    inFlight = true;
    try {
      await refresh();
    } catch {
      // The caller reports request errors. A transient failure must not stop polling.
    } finally {
      inFlight = false;
      schedule();
    }
  };
  const wake = () => {
    if (environment.isVisible()) void run();
    else cancelTimer();
  };
  const removeFocus = environment.onFocus(wake);
  const removeVisibility = environment.onVisibilityChange(wake);
  schedule();
  return () => {
    disposed = true;
    cancelTimer();
    removeFocus();
    removeVisibility();
  };
}
