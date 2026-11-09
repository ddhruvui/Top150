import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  window.location.hash = '';
  document.documentElement.removeAttribute('data-theme');
  try { localStorage.clear(); } catch { /* ignore */ }
});

// jsdom has no layout: scrolling is a no-op we can assert on.
window.scrollTo = vi.fn();
Element.prototype.scrollIntoView = vi.fn();
