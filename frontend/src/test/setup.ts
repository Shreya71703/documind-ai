import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Stub out browser/localStorage/fetch globals if needed
class LocalStorageMock {
  private store: { [key: string]: string } = {};

  clear() {
    this.store = {};
  }

  getItem(key: string) {
    return this.store[key] || null;
  }

  setItem(key: string, value: string) {
    this.store[key] = String(value);
  }

  removeItem(key: string) {
    delete this.store[key];
  }
}

Object.defineProperty(window, 'localStorage', {
  value: new LocalStorageMock(),
});

// Mock confirm and alert dialogue boxes
window.confirm = vi.fn().mockReturnValue(true);
window.alert = vi.fn();

// Mock fetch
const mockFetch = vi.fn();
window.fetch = mockFetch as any;
