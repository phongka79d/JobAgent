import '@testing-library/jest-dom/vitest';

// AppShell uses matchMedia for responsive mobile nav; jsdom does not implement it.
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  configurable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }),
});

// ChatLayout / ChatMessageList use ResizeObserver (jsdom does not implement it).
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
Object.defineProperty(window, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: ResizeObserverStub,
});
Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  configurable: true,
  value: ResizeObserverStub,
});

// Spinner (tool activity / load-older) may call canvas getContext in jsdom.
HTMLCanvasElement.prototype.getContext = function getContext(
  this: HTMLCanvasElement,
  _contextId: string,
  _options?: unknown,
): RenderingContext | null {
  return {
    canvas: this,
    fillRect: () => {},
    clearRect: () => {},
    getImageData: () => ({data: new Uint8ClampedArray(0)}),
    putImageData: () => {},
    createImageData: () => ({data: new Uint8ClampedArray(0)}),
    setTransform: () => {},
    drawImage: () => {},
    save: () => {},
    fillText: () => {},
    restore: () => {},
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    closePath: () => {},
    stroke: () => {},
    translate: () => {},
    scale: () => {},
    rotate: () => {},
    arc: () => {},
    fill: () => {},
    measureText: () => ({width: 0}),
    transform: () => {},
    rect: () => {},
    clip: () => {},
  } as unknown as CanvasRenderingContext2D;
} as typeof HTMLCanvasElement.prototype.getContext;
