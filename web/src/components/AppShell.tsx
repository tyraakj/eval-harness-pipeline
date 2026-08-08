'use client';

import React, { useState, useEffect, createContext, useContext } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import Link from 'next/link';
import styles from './AppShell.module.css';
import CliGuideDrawer from './CliGuideDrawer';

// --- Shared Context for Page Titles ---
type AppShellContextType = {
  setTitle: (title: string) => void;
};
const AppShellContext = createContext<AppShellContextType>({ setTitle: () => {} });
export const useAppShell = () => useContext(AppShellContext);

// --- Icons (Inline SVGs) ---
const Icons = {
  Play: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"></polygon>
    </svg>
  ),
  TestTube: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
      <polyline points="7 10 12 15 17 10"></polyline>
      <line x1="12" y1="15" x2="12" y2="3"></line>
    </svg>
  ),
  FileText: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
      <polyline points="14 2 14 8 20 8"></polyline>
      <line x1="16" y1="13" x2="8" y2="13"></line>
      <line x1="16" y1="17" x2="8" y2="17"></line>
      <polyline points="10 9 9 9 8 9"></polyline>
    </svg>
  ),
  GitCompare: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="18" cy="18" r="3"></circle>
      <circle cx="6" cy="6" r="3"></circle>
      <path d="M13 6h3a2 2 0 0 1 2 2v7"></path>
      <line x1="6" y1="9" x2="6" y2="21"></line>
    </svg>
  ),
  Shield: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>
    </svg>
  ),
  Terminal: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5"></polyline>
      <line x1="12" y1="19" x2="20" y2="19"></line>
    </svg>
  ),
  ChevronRight: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6"></polyline>
    </svg>
  ),
  ChevronLeft: (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6"></polyline>
    </svg>
  )
};

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [serverOnline, setServerOnline] = useState(true);
  
  const pathname = usePathname();
  const router = useRouter();

  // Redirect /app to /app/runs
  useEffect(() => {
    if (pathname === '/app') {
      router.replace('/app/runs');
    }
  }, [pathname, router]);

  // Poll server health
  useEffect(() => {
    const checkHealth = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/health`);
        setServerOnline(res.ok);
      } catch (e) {
        setServerOnline(false);
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  const navItems = [
    { label: 'Runs', path: '/app/runs', icon: Icons.Play, exact: false },
    { label: 'Tests', path: '/app/datasets', icon: Icons.TestTube, exact: false },
    { label: 'Results', path: '/app/results', icon: Icons.FileText, exact: false },
    { label: 'Compare', path: '/app/compare', icon: Icons.GitCompare, exact: true },
    { label: 'Release check', path: '/app/release', icon: Icons.Shield, exact: true },
  ];

  return (
    <AppShellContext.Provider value={{ setTitle }}>
      <div className={styles.shell}>
        
        {/* Sidebar */}
        <div className={`${styles.sidebar} ${expanded ? styles.expanded : ''}`}>
          <div className={styles.sidebarTop}>
            {navItems.map((item) => {
              const isActive = item.exact 
                ? pathname === item.path 
                : pathname?.startsWith(item.path);
                
              return (
                <Link 
                  href={item.path} 
                  key={item.path}
                  className={`${styles.navItem} ${isActive ? styles.active : ''}`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </Link>
              );
            })}
            
            {/* Guide Button */}
            <button 
              className={`${styles.navItem} ${isGuideOpen ? styles.active : ''}`}
              onClick={() => setIsGuideOpen(true)}
              aria-label="Command guide"
            >
              {Icons.Terminal}
              <span>Command guide</span>
            </button>
          </div>
          
          <button 
            className={styles.expandToggle} 
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
          >
            {expanded ? Icons.ChevronLeft : Icons.ChevronRight}
            <span>Collapse</span>
          </button>
        </div>

        {/* Main Content Area */}
        <div className={styles.mainArea}>
          <div className={styles.topBar}>
            <div className={styles.pageTitle}>{title}</div>
            
            <div className={styles.topBarRight}>
              <div className={styles.serverStatus}>
                <div className={`${styles.statusDot} ${serverOnline ? styles.connected : styles.offline}`} />
                {serverOnline ? 'Connected' : 'Server offline — run `glyph serve`'}
              </div>
              <Link href="/app/runs/new" className={styles.newRunBtn}>
                Start new run
              </Link>
            </div>
          </div>
          
          <div className={styles.contentWrapper}>
            {children}
          </div>
        </div>

        {/* CLI Guide Drawer */}
        <CliGuideDrawer isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
      </div>
    </AppShellContext.Provider>
  );
}
