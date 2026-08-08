'use client';

import React, { useState, useEffect } from 'react';
import styles from './CliGuideDrawer.module.css';

type GuideFlag = {
  flag: string;
  description: string;
};

type GuideCommand = {
  name: string;
  description: string;
  example: string;
  flags: GuideFlag[];
};

type GuideSection = {
  section: string;
  commands: GuideCommand[];
  fallback?: boolean;
};

const FALLBACK_GUIDE: GuideSection[] = [
  {
    section: "Basic Reference",
    fallback: true,
    commands: [
      {
        name: "glyph run",
        description: "Run your evaluation against a test library.",
        example: "glyph run --factory my_app.eval:create_evaluation --dataset datasets/support.jsonl",
        flags: [
          { flag: "--factory", description: "Your evaluation setup (module:function)" },
          { flag: "--dataset", description: "Path to the test library (.jsonl file)" },
          { flag: "--output", description: "Where to save results (default: artifacts/)" },
          { flag: "--check", description: "Check config without running any tests" },
          { flag: "--workers", description: "Run extra analysis checks (security, performance, etc.)" }
        ]
      },
      {
        name: "glyph doctor",
        description: "Check if everything is set up",
        example: "glyph doctor",
        flags: []
      },
      {
        name: "glyph compare",
        description: "See what broke compared to last time",
        example: "glyph compare --candidate artifacts/new.jsonl --baseline artifacts/old.jsonl",
        flags: []
      },
      {
        name: "glyph release",
        description: "Decide if this version is safe to ship",
        example: "glyph release --deterministic artifacts/new.jsonl --baseline artifacts/old.jsonl",
        flags: []
      },
      {
        name: "glyph security audit",
        description: "Check a results file for security issues",
        example: "glyph security audit --results artifacts/new.jsonl",
        flags: []
      }
    ]
  }
];

export default function CliGuideDrawer({ isOpen, onClose }: { isOpen: boolean, onClose: () => void }) {
  const [guideData, setGuideData] = useState<GuideSection[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedFlags, setExpandedFlags] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!isOpen) return;
    
    // Only fetch if we don't have data yet
    if (guideData) return;
    
    const fetchGuide = async () => {
      setLoading(true);
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/guide`);
        if (!res.ok) throw new Error('Failed to fetch guide');
        const data = await res.json();
        setGuideData(data);
      } catch (err) {
        setGuideData(FALLBACK_GUIDE);
      } finally {
        setLoading(false);
      }
    };
    
    fetchGuide();
  }, [isOpen, guideData]);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  const toggleFlags = (commandName: string) => {
    setExpandedFlags(prev => ({ ...prev, [commandName]: !prev[commandName] }));
  };

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  // Filter logic
  const filteredData = React.useMemo(() => {
    if (!guideData) return [];
    if (!searchQuery.trim()) return guideData;
    
    const query = searchQuery.toLowerCase();
    
    return guideData.map(section => {
      const matchingCommands = section.commands.filter(cmd => 
        cmd.name.toLowerCase().includes(query) || 
        cmd.description.toLowerCase().includes(query)
      );
      
      if (matchingCommands.length > 0 || section.section.toLowerCase().includes(query)) {
        return {
          ...section,
          commands: matchingCommands.length > 0 ? matchingCommands : section.commands
        };
      }
      return null;
    }).filter(Boolean) as GuideSection[];
  }, [guideData, searchQuery]);

  const isFallback = guideData?.[0]?.fallback;

  return (
    <div className={`${styles.drawerOverlay} ${isOpen ? styles.open : ''}`} onClick={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>
      <div className={styles.drawer}>
        <div className={styles.drawerHeader}>
          <div className={styles.drawerTitle}>CLI quick reference</div>
          <button className={styles.closeButton} onClick={onClose} aria-label="Close guide">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        
        <div className={styles.searchBox}>
          <input 
            type="text" 
            placeholder="Search commands..." 
            className={styles.searchInput}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
        
        <div className={styles.drawerContent}>
          {loading ? (
            <div>
              {[1, 2, 3].map(i => (
                <div key={i} className={styles.skeletonSection}>
                  <div className={styles.skeletonTitle}></div>
                  <div className={styles.skeletonCard}></div>
                  <div className={styles.skeletonCard}></div>
                </div>
              ))}
            </div>
          ) : (
            <>
              {isFallback && (
                <div className={styles.fallbackNote}>
                  Showing basic reference. Start the server to see the full guide.
                </div>
              )}
              
              {filteredData.length === 0 ? (
                <div style={{ color: '#64748b', fontSize: '0.9rem', textAlign: 'center', marginTop: '20px' }}>
                  No commands match your search.
                </div>
              ) : (
                filteredData.map((section, idx) => (
                  <div key={idx} className={styles.section}>
                    <div className={styles.sectionTitle}>{section.section}</div>
                    
                    {section.commands.map(cmd => (
                      <div key={cmd.name} className={styles.commandCard}>
                        <div className={styles.commandHeader}>
                          <span className={styles.commandName}>{cmd.name}</span>
                          <button 
                            className={styles.copyButton}
                            onClick={() => handleCopy(cmd.example)}
                          >
                            Copy
                          </button>
                        </div>
                        
                        <div className={styles.commandDescription}>{cmd.description}</div>
                        
                        <div className={styles.exampleBlock}>
                          {cmd.example}
                        </div>
                        
                        {cmd.flags && cmd.flags.length > 0 && (
                          <>
                            <button 
                              className={styles.flagsToggle}
                              onClick={() => toggleFlags(cmd.name)}
                            >
                              {expandedFlags[cmd.name] ? 'Hide flags ▴' : 'Show flags ▾'}
                            </button>
                            
                            {expandedFlags[cmd.name] && (
                              <div className={styles.flagsList}>
                                {cmd.flags.map((flag, fIdx) => (
                                  <div key={fIdx} className={styles.flagItem}>
                                    <span className={styles.flagName}>{flag.flag}</span>
                                    <span className={styles.flagDesc}>{flag.description}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                ))
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
