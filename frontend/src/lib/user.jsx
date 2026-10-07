import { createContext, useContext, useState } from 'react';
import { loadJSON, saveJSON } from './format';

// MVP auth: name, email and department kept in localStorage (as in the project plan).
const KEY = 'mercury.user';
const UserContext = createContext({ user: null, setUser: () => {} });

export function UserProvider({ children }) {
  const [user, setUserState] = useState(() => loadJSON(KEY, null));

  const setUser = (next) => {
    setUserState(next);
    if (next) saveJSON(KEY, next);
    else {
      try { localStorage.removeItem(KEY); } catch { /* ignore */ }
    }
  };

  return <UserContext.Provider value={{ user, setUser }}>{children}</UserContext.Provider>;
}

export const useUser = () => useContext(UserContext);

export function initials(name = '') {
  const parts = name.trim().split(/\s+/).filter(Boolean).slice(0, 2);
  return parts.map((p) => p[0].toUpperCase()).join('') || '?';
}
