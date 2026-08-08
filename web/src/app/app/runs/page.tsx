'use client';

import React, { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';
import { formatTimeAgo, formatDuration } from '@/utils/time';

type RunListItem = {
  id: string;
  suite_id: string;
  suite_version: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  summary: any;
};

export default function RunsPage() {
  const { setTitle } = useAppShell();
  const [runs, setRuns] = useState<RunListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'All' | 'Running' | 'Passed' | 'Failed'>('All');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setTitle('Your runs');
  }, [setTitle]);

  useEffect(() => {
    const fetchRuns = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/runs`);
        if (res.ok) {
          const data = await res.json();
          setRuns(data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchRuns();
    // Poll every 5 seconds for status updates
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleCopy = (e: React.MouseEvent, text: string) => {
    e.preventDefault();
    e.stopPropagation();
    navigator.clipboard.writeText(text);
  };

  const getBadgeConfig = (status: string, passRate: number) => {
    if (status === 'running') return { label: 'Running', class: styles.badgeRunning };
    if (status === 'queued') return { label: 'Queued', class: styles.badgeQueued };
    if (status === 'cancelled') return { label: 'Cancelled', class: styles.badgeCancelled };
    
    // completed/failed
    if (passRate === 1) return { label: 'Passed', class: styles.badgePassed };
    if (passRate > 0) return { label: 'Partial', class: styles.badgePartial };
    return { label: 'Failed', class: styles.badgeFailed };
  };

  const filteredRuns = useMemo(() => {
    return runs.filter(run => {
      // Status filter
      if (filter === 'Running' && run.status !== 'running') return false;
      
      const isComplete = run.status === 'completed' || run.status === 'failed';
      const passRate = run.summary?.metrics?.pass_rate ?? 0;
      
      if (filter === 'Passed' && (!isComplete || passRate !== 1)) return false;
      if (filter === 'Failed' && (!isComplete || passRate === 1)) return false;

      // Search filter (run ID or date)
      if (search) {
        const query = search.toLowerCase();
        if (!run.id.toLowerCase().includes(query) && !run.started_at.includes(query)) {
          return false;
        }
      }
      return true;
    });
  }, [runs, filter, search]);

  if (loading && runs.length === 0) {
    return <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Loading...</div>;
  }

  return (
    <div className={styles.container}>
      {runs.length === 0 ? (
        <div className={styles.emptyState}>
          <div className={styles.emptyTitle}>No runs yet</div>
          <div className={styles.emptyDesc}>Run your first evaluation to see results here.</div>
          <Link href="/app/runs/new" className={styles.startRunBtn}>
            Start a run
          </Link>
        </div>
      ) : (
        <>
          <div className={styles.filterBar}>
            <div className={styles.tabs}>
              {['All', 'Running', 'Passed', 'Failed'].map(f => (
                <button
                  key={f}
                  className={`${styles.tab} ${filter === f ? styles.active : ''}`}
                  onClick={() => setFilter(f as any)}
                >
                  {f}
                </button>
              ))}
            </div>
            <div className={styles.searchBox}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: '8px' }}>
                <circle cx="11" cy="11" r="8"></circle>
                <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
              </svg>
              <input 
                type="text" 
                placeholder="Search runs..." 
                className={styles.searchInput}
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>
          </div>

          <div className={styles.runsList}>
            {filteredRuns.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>No runs match your filters.</div>
            ) : (
              filteredRuns.map(run => {
                const total = run.summary?.metrics?.total_cases || 0;
                const passed = (run.summary?.metrics?.pass_rate || 0) * total;
                const isComplete = run.status === 'completed' || run.status === 'failed';
                const badge = getBadgeConfig(run.status, run.summary?.metrics?.pass_rate || 0);

                return (
                  <Link href={`/app/runs/${run.id}`} key={run.id} className={styles.runRow}>
                    <div className={styles.runLeft}>
                      <div className={styles.runIdBlock}>
                        <span className={styles.runId}>{run.id.substring(0, 8)}</span>
                        <button 
                          className={styles.copyBtn} 
                          onClick={(e) => handleCopy(e, run.id)}
                          title="Copy full ID"
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                          </svg>
                        </button>
                      </div>
                      <div className={styles.runMeta}>
                        <span className={styles.timeAgo}>{formatTimeAgo(run.started_at)}</span>
                        <span className={styles.duration}>
                          {run.status === 'running' ? 'running...' : formatDuration(run.started_at, run.finished_at)}
                        </span>
                      </div>
                    </div>
                    
                    <div className={styles.runRight}>
                      {(isComplete || total > 0) && (
                        <div className={styles.runStats}>
                          {Math.round(passed)} / {total} passed
                        </div>
                      )}
                      <div className={`${styles.badge} ${badge.class}`}>
                        {badge.label}
                      </div>
                    </div>
                  </Link>
                );
              })
            )}
          </div>
        </>
      )}
    </div>
  );
}
