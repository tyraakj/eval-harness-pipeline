'use client';

import React, { useEffect, useState, useMemo } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type TrialEvent = {
  case_id: string;
  status: string;
  suite: string;
  score: number;
  duration_ms: number;
  grades: Array<{
    grader: string;
    passed: boolean;
    score: number;
    reason: string;
  }>;
  error?: string;
};

export default function ResultDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const { setTitle } = useAppShell();
  
  const [loading, setLoading] = useState(true);
  const [trials, setTrials] = useState<TrialEvent[]>([]);
  const [metrics, setMetrics] = useState<any>(null);
  
  const [expandedRow, setExpandedRow] = useState<string | null>(null);
  const [showErrors, setShowErrors] = useState(false);

  useEffect(() => {
    setTitle(`Result: ${name}`);
  }, [setTitle, name]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        
        // Fetch summary
        const sumRes = await fetch(`${apiUrl}/api/artifacts/${name}/summary`);
        if (sumRes.ok) {
          const sumData = await sumRes.json();
          setMetrics(sumData.metrics);
        }

        // Fetch trials
        const trialsRes = await fetch(`${apiUrl}/api/artifacts/${name}/trials`);
        if (trialsRes.ok) {
          const trialsData = await trialsRes.json();
          setTrials(trialsData);
        }
      } catch (e) {
        console.error('Failed to fetch artifact data', e);
      } finally {
        setLoading(false);
      }
    };
    
    fetchData();
  }, [name]);

  const totalPassed = trials.filter(t => t.status === 'passed').length;
  const totalFailed = trials.filter(t => t.status === 'failed').length;
  const totalErrors = trials.filter(t => t.status === 'error').length;
  const totalCases = metrics?.total_cases || trials.length;

  // Calculate stats by grader
  const graderStats = useMemo(() => {
    const stats: Record<string, { total: number, passed: number }> = {};
    trials.forEach(trial => {
      if (!trial.grades) return;
      trial.grades.forEach(gr => {
        const name = gr.grader;
        if (!stats[name]) stats[name] = { total: 0, passed: 0 };
        stats[name].total++;
        if (gr.passed) stats[name].passed++;
      });
    });
    return stats;
  }, [trials]);

  // UI Helpers
  const formatResultLabel = (status: string) => {
    if (status === 'passed') return <span className={`${styles.resultLabel} ${styles.passed}`}>✓ Passed</span>;
    if (status === 'failed') return <span className={`${styles.resultLabel} ${styles.failed}`}>✗ Failed</span>;
    if (status === 'error') return <span className={`${styles.resultLabel} ${styles.error}`}>⚠ Error</span>;
    return <span>{status}</span>;
  };

  const errorTrials = trials.filter(t => t.status === 'error');

  if (loading) {
    return <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Loading results...</div>;
  }

  if (!metrics && trials.length === 0) {
    return <div style={{ padding: '40px', textAlign: 'center', color: '#dc2626' }}>Failed to load result data. The file might be corrupted or empty.</div>;
  }

  return (
    <div className={styles.container}>
      {/* Top Strip */}
      <div className={styles.topStrip}>
        <div className={styles.statsRow}>
          <div className={styles.statItem}>
            <span>{totalCases} tests</span>
          </div>
          <div className={styles.statItem}>
            <span className={`${styles.statVal} ${styles.passed}`}>{totalPassed} passed</span>
          </div>
          <div className={styles.statItem}>
            <span className={`${styles.statVal} ${styles.failed}`}>{totalFailed} failed</span>
          </div>
          {totalErrors > 0 && (
            <div className={styles.statItem}>
              <span className={`${styles.statVal} ${styles.error}`}>{totalErrors} errors</span>
            </div>
          )}
        </div>
        
        <div className={styles.metaRow}>
          <Link href={`/app/compare?candidate=artifacts/${name}`} className={styles.actionBtn}>
            Compare to another run
          </Link>
          <a 
            href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/artifacts/${name}/download`} 
            className={styles.actionBtn}
            style={{ backgroundColor: '#0f172a', color: '#fff', borderColor: '#0f172a' }}
          >
            Download results
          </a>
        </div>
      </div>

      {/* Errors Banner */}
      {errorTrials.length > 0 && (
        <div className={styles.errorBanner}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>{errorTrials.length} tests could not complete due to errors.</span>
            <button 
              onClick={() => setShowErrors(!showErrors)}
              style={{ background: 'transparent', border: 'none', color: 'inherit', textDecoration: 'underline', cursor: 'pointer', fontWeight: 600 }}
            >
              {showErrors ? 'Hide errors' : 'Show errors'}
            </button>
          </div>
          {showErrors && (
            <div className={styles.errorDetails}>
              {errorTrials.map(t => (
                <div key={t.case_id} style={{ marginBottom: '4px' }}>
                  <strong>{t.case_id}</strong>: {t.error || 'Unknown error'}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Middle - Progress Bars */}
      {Object.keys(graderStats).length > 0 && (
        <div className={styles.progressSection}>
          <div className={styles.sectionTitle}>Checks</div>
          {Object.entries(graderStats).map(([gName, stats]) => {
            const pct = stats.total > 0 ? (stats.passed / stats.total) * 100 : 0;
            let barClass = styles.green;
            if (pct < 90) barClass = styles.yellow;
            if (pct < 70) barClass = styles.red;
            
            return (
              <div key={gName} className={styles.barRow}>
                <div className={styles.barLabel} title={gName}>
                  "{gName.toLowerCase().replace(/grader$/, '').trim()}"
                </div>
                <div className={styles.barTrack}>
                  <div className={`${styles.barFill} ${barClass}`} style={{ width: `${pct}%` }} />
                </div>
                <div className={styles.barStats}>
                  {stats.passed} / {stats.total} ({Math.round(pct)}%)
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Bottom - Test Results Table */}
      <table className={styles.testTable}>
        <thead>
          <tr>
            <th>Test</th>
            <th>Category</th>
            <th>Result</th>
            <th>Score</th>
            <th>Time</th>
          </tr>
        </thead>
        <tbody>
          {trials.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: 'center', color: '#64748b', padding: '32px' }}>
                No tests found in this file.
              </td>
            </tr>
          ) : (
            trials.map(trial => (
              <React.Fragment key={trial.case_id}>
                <tr className={styles.trMain} onClick={() => setExpandedRow(expandedRow === trial.case_id ? null : trial.case_id)}>
                  <td className={styles.testId}>{trial.case_id}</td>
                  <td><span className={styles.categoryPill}>{trial.suite || 'capability'}</span></td>
                  <td>{formatResultLabel(trial.status)}</td>
                  <td>{Math.round(trial.score * 100)}%</td>
                  <td>{(trial.duration_ms / 1000).toFixed(1)}s</td>
                </tr>
                
                {expandedRow === trial.case_id && (
                  <tr className={styles.detailsRow}>
                    <td colSpan={5} style={{ padding: 0 }}>
                      <div className={styles.detailsContent}>
                        <div style={{ fontSize: '0.8rem', fontWeight: 600, color: '#64748b', marginBottom: '8px', textTransform: 'uppercase' }}>What was checked</div>
                        <div className={styles.checksList}>
                        {trial.grades && trial.grades.length > 0 ? (
                          trial.grades.map((gr, idx) => (
                            <div key={idx} className={`${styles.checkItem} ${gr.passed ? styles.passed : styles.failed}`}>
                              <span className={styles.checkIcon}>{gr.passed ? '✓' : '✗'}</span>
                              <span className={styles.checkName}>{gr.grader}</span>
                              {!gr.passed && gr.reason && (
                                <span className={styles.checkReason}>- {gr.reason}</span>
                              )}
                            </div>
                          ))
                        ) : (
                          <div style={{ fontSize: '0.85rem', color: '#64748b' }}>No check details available</div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
