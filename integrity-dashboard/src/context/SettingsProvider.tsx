import { createContext, useContext, useState, useEffect } from 'react';
import type { ReactNode } from 'react';

type Theme = 'dark' | 'light' | 'xibalba-sovereign' | 'system';
type Font = 'Raleway' | 'Inter' | 'Outfit';

interface SettingsContextType {
  theme: Theme;
  font: Font;
  setTheme: (t: Theme) => void;
  setFont: (f: Font) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    return (localStorage.getItem('integrity_theme') as Theme) || 'dark';
  });
  
  const [font, setFontState] = useState<Font>(() => {
    return (localStorage.getItem('integrity_font') as Font) || 'Raleway';
  });

  const setTheme = (t: Theme) => {
    setThemeState(t);
    localStorage.setItem('integrity_theme', t);
  };

  const setFont = (f: Font) => {
    setFontState(f);
    localStorage.setItem('integrity_font', f);
  };

  useEffect(() => {
    const root = document.documentElement;
    // Apply Theme
    root.classList.remove('light-theme', 'xibalba-sovereign-theme');

    if (theme === 'xibalba-sovereign') {
      root.classList.add('xibalba-sovereign-theme');
    } else if (theme === 'light' || (theme === 'system' && !window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      root.classList.add('light-theme');
    }
    
    // Apply Font
    root.style.setProperty('--font-sans', `'${font}', system-ui, sans-serif`);
    document.body.style.fontFamily = `'${font}', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`;
  }, [theme, font]);

  return (
    <SettingsContext.Provider value={{ theme, font, setTheme, setFont }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error('useSettings must be used within SettingsProvider');
  return ctx;
}
