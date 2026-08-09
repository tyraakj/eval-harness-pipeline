'use client';

import React, { useState, useEffect } from 'react';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

export default function CompareAgentsPage() {
  const { setTitle } = useAppShell();
  const [datasets, setDatasets] = useState<any[]>([]);
  const [datasetPath, setDatasetPath] = useState('');
  const [targetA, setTargetA] = useState('');
  const [targetB, setTargetB] = useState('');
  
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'running' | 'completed' | 'error'>('idle');
  const [error, setError] = useState<string | null>(null);
  
  const [statsA, setStatsA] = useState({ passed: 0, failed: 0, errors: 0, total: 0 });
  const [statsB, setStatsB] = useState({ passed: 0, failed: 0, errors: 0, total: 0 });
  const [logsA, setLogsA] = useState<string[]>([]);
  const [logsB, setLogsB] = useState<string[]>([]);

  useEffect(() => {
    setTitle('Compare Agents');
    const fetchDatasets = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/datasets`);
        if (res.ok) {
          const data = await res.json();
          setDatasets(data);
          if (data.length > 0) setDatasetPath(`datasets/${data[0].name}`);
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchDatasets();
  }, [setTitle]);

  const handleStart = async () => {
    if (!targetA || !targetB || !datasetPath) {
      setError('Please fill in all fields.');
      return;
    }
    
    setError(null);
    setStatus('running');
    setStatsA({ passed: 0, failed: 0, errors: 0, total: 0 });
    setStatsB({ passed: 0, failed: 0, errors: 0, total: 0 });
    setLogsA([]);
    setLogsB([]);
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = {
        config_a: { factory: targetA, dataset: datasetPath, output: `artifacts/cmpA-${Date.now()}.jsonl` },
        config_b: { factory: targetB, dataset: datasetPath, output: `artifacts/cmpB-${Date.now()}.jsonl` }
      };
      
      const res = await fetch(`${apiUrl}/api/compare-targets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start comparison');
      }
      
      const data = await res.json();
      setJobId(data.job_id);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
      setStatus('error');
    }
  };

  useEffect(() => {
    if (!jobId || status !== 'running') return;
    
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const eventSource = new EventSource(`${apiUrl}/api/compare-targets/${jobId}`);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.event === 'trial_complete') {
          if (data.target === 'A') {
            setStatsA(prev => ({ ...prev, [data.status]: prev[data.status as keyof typeof prev] + 1, total: prev.total + 1 }));
            setLogsA(prev => [...prev.slice(-49), `[${data.status.toUpperCase()}] ${data.case_id}`]);
          } else {
            setStatsB(prev => ({ ...prev, [data.status]: prev[data.status as keyof typeof prev] + 1, total: prev.total + 1 }));
            setLogsB(prev => [...prev.slice(-49), `[${data.status.toUpperCase()}] ${data.case_id}`]);
          }
        } else if (data.event === 'run_complete') {
          setStatus('completed');
          eventSource.close();
        }
      } catch (err) {
        console.error('SSE Error', err);
      }
    };
    
    eventSource.onerror = () => {
      setStatus('error');
      setError('Connection lost.');
      eventSource.close();
    };
    
    return () => eventSource.close();
  }, [jobId, status]);

  return (
    <div className={styles.container}>
      <div className={styles.title}>Compare Agents Side-by-Side</div>
      
      {error && <div className={styles.errorBanner}>{error}</div>}
      
      <div className={styles.formBox}>
        <div className={styles.inputRow}>
          <div className={styles.field}>
            <label className={styles.label}>Test library</label>
            <select className={styles.select} value={datasetPath} onChange={(e) => setDatasetPath(e.target.value)}>
              <option value="">-- Select dataset --</option>
              {datasets.map(ds => (
                <option key={ds.name} value={`datasets/${ds.name}`}>{ds.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div className={styles.inputRow}>
          <div className={styles.field}>
            <label className={styles.label}>Target A Factory</label>
            <input className={styles.input} placeholder="my_app.agent:create_agent_a" value={targetA} onChange={e => setTargetA(e.target.value)} />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Target B Factory</label>
            <input className={styles.input} placeholder="my_app.agent:create_agent_b" value={targetB} onChange={e => setTargetB(e.target.value)} />
          </div>
        </div>
        <button className={styles.startBtn} onClick={handleStart} disabled={status === 'running'}>
          {status === 'running' ? 'Running Comparison...' : 'Start Comparison'}
        </button>
      </div>
      
      {(status === 'running' || status === 'completed') && (
        <div className={styles.progressArea}>
          <div className={styles.sideBySide}>
            <div className={styles.targetCard}>
              <div className={styles.targetHeader}>
                <span className={styles.targetName}>{targetA || 'Target A'}</span>
                <span className={`${styles.targetBadge} ${styles.badgeA}`}>TARGET A</span>
              </div>
              <div className={styles.statsGrid}>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Passed</span>
                  <span className={`${styles.statValue} ${styles.passed}`}>{statsA.passed}</span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Failed</span>
                  <span className={`${styles.statValue} ${styles.failed}`}>{statsA.failed}</span>
                </div>
              </div>
              <div className={styles.logBox}>
                {logsA.map((log, i) => <div key={i} className={styles.logEntry}>{log}</div>)}
              </div>
            </div>
            
            <div className={styles.targetCard}>
              <div className={styles.targetHeader}>
                <span className={styles.targetName}>{targetB || 'Target B'}</span>
                <span className={`${styles.targetBadge} ${styles.badgeB}`}>TARGET B</span>
              </div>
              <div className={styles.statsGrid}>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Passed</span>
                  <span className={`${styles.statValue} ${styles.passed}`}>{statsB.passed}</span>
                </div>
                <div className={styles.statItem}>
                  <span className={styles.statLabel}>Failed</span>
                  <span className={`${styles.statValue} ${styles.failed}`}>{statsB.failed}</span>
                </div>
              </div>
              <div className={styles.logBox}>
                {logsB.map((log, i) => <div key={i} className={styles.logEntry}>{log}</div>)}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
