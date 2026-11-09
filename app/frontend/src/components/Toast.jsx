/* Toasts: action feedback that appears where the eye already is (bottom
   right), instead of a note at the top of a long page the user has scrolled
   away from. Announced politely to screen readers. */
import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import Icon from './Icon.jsx';

const Ctx = createContext(() => {});

export function ToastProvider({ children }) {
  const [items, setItems] = useState([]);
  const seq = useRef(0);
  const dismiss = useCallback((id) => setItems((xs) => xs.filter((x) => x.id !== id)), []);
  const push = useCallback(({ ok = true, text, ttl = 5000 }) => {
    seq.current += 1;
    const id = seq.current;
    setItems((xs) => [...xs.slice(-2), { id, ok, text }]);
    if (ttl) setTimeout(() => dismiss(id), ttl);
  }, [dismiss]);
  const value = useMemo(() => push, [push]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast ${t.ok ? 'ok' : 'err'}`}>
            <Icon name={t.ok ? 'checkCircle' : 'xCircle'} size={18} className="ic" />
            <div>{t.text}</div>
            <button type="button" className="btn ghost sm icon x" aria-label="Dismiss"
                    onClick={() => dismiss(t.id)}>
              <Icon name="x" size={14} />
            </button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}

export const useToast = () => useContext(Ctx);
