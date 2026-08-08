'use client';

import React, { createContext, useContext, useState, ReactNode } from 'react';

interface TerminalContextType {
  activeIndex: number;
  setActiveIndex: React.Dispatch<React.SetStateAction<number>>;
}

const TerminalContext = createContext<TerminalContextType | undefined>(undefined);

export function TerminalProvider({ children }: { children: ReactNode }) {
  const [activeIndex, setActiveIndex] = useState(0);

  return (
    <TerminalContext.Provider value={{ activeIndex, setActiveIndex }}>
      {children}
    </TerminalContext.Provider>
  );
}

export function useTerminalContext() {
  const context = useContext(TerminalContext);
  if (context === undefined) {
    throw new Error('useTerminalContext must be used within a TerminalProvider');
  }
  return context;
}
