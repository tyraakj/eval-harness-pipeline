'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type ArtifactItem = {
  name: string;
  path: string;
  size_bytes: number;
  modified_at: string;
};

type ArtifactSummary = {
  run_id: string;
  config: any;
  metrics: {
    total_cases: number;
    completed: number;
    failed: number;
    errors: number;
    pass_rate: number;
  };
  duration_ms: number;
};

type ArtifactWithSummary = ArtifactItem & {
  summary: ArtifactSummary | null;
  loading: boolean;
};

export default function ResultsPage() {
  const { setTitle } = useAppShell();
  const router = useRouter();

  const [artifacts, setArtifacts] = useState<ArtifactWithSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTitle('Results');
  }, [setTitle]);

  useEffect(() => {
    const fetchArtifacts = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/artifacts`);
        
        if (res.ok) {
          const data: ArtifactItem[] = await res.json();
          // Initialize list
          const initial = data.map(item => ({ ...item, summary: null, loading: true }));
          setArtifacts(initial);
          
          // Fetch summaries concurrently
          initial.forEach(async (item) => {
            try {
              const sumRes = await fetch(`${apiUrl}/api/artifacts/${item.name}/summary`);
              if (sumRes.ok) {
                const summary = await sumRes.json();
                setArtifacts(prev => prev.map(a => a.name === item.name ? { ...a, summary, loading: false } : a));
              } else {
                setArtifacts(prev => prev.map(a => a.name === item.name ? { ...a, loading: false } : a));
              }
            } catch {
              setArtifacts(prev => prev.map(a => a.name === item.name ? { ...a, loading: false } : a));
            }
          });
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchArtifacts();
  }, []);

  const formatDate = (isoString: string) => {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  };

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return bytes + ' B';
    const kb = bytes / 1024;
    if (kb < 1024) return kb.toFixed(1) + ' KB';
    return (kb / 1024).toFixed(1) + ' MB';
  };

  return (
    <div className={styles.container}>
      <div className={styles.title}>Saved Results</div>

      {loading ? (
        <div style={{ color: '#64748b' }}>Loading results...</div>
      ) : artifacts.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', backgroundColor: '#fff', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b' }}>
          No results found. Run an evaluation to generate results.
        </div>
      ) : (
        <div className={styles.grid}>
          {artifacts.sort((a, b) => new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime()).map(art => {
            const hasSummary = !art.loading && art.summary !== null;
            const passRate = hasSummary ? Math.round((art.summary!.metrics?.pass_rate || 0) * 100) : null;
            const totalTests = hasSummary ? art.summary!.metrics?.total_cases || 0 : 0;

            let rateClass = styles.none;
            if (passRate !== null) {
              if (passRate >= 90) rateClass = styles.good;
              else if (passRate >= 70) rateClass = styles.ok;
              else rateClass = styles.bad;
            }

            return (
              <div 
                key={art.name} 
                className={styles.card}
                onClick={() => router.push(`/app/results/${art.name}`)}
              >
                <div className={styles.cardTop}>
                  <div className={styles.runDate}>{formatDate(art.modified_at)}</div>
                  <div className={styles.fileSize}>{formatSize(art.size_bytes)}</div>
                </div>

                <div className={styles.passRateBlock}>
                  {art.loading ? (
                    <div style={{ color: '#cbd5e1', fontSize: '2rem', fontWeight: 700 }}>--%</div>
                  ) : hasSummary ? (
                    <div className={`${styles.passRate} ${rateClass}`}>
                      {passRate}% passed
                    </div>
                  ) : (
                    <div className={`${styles.passRate} ${styles.none}`}>N/A</div>
                  )}
                </div>

                {hasSummary && <div className={styles.testCount}>{totalTests} tests</div>}
                {!art.loading && !hasSummary && <div className={styles.incompleteLabel}>Incomplete</div>}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
