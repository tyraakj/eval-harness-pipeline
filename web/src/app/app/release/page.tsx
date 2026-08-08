'use client';

import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type ArtifactItem = {
  name: string;
  path: string;
  modified_at: string;
};

type ReleaseResult = {
  allowed: boolean;
  policy_name: string;
  reasons: string[];
  candidate_pass_rate: number;
  baseline_pass_rate: number | null;
};

function ReleaseContent() {
  const { setTitle } = useAppShell();
  const searchParams = useSearchParams();
  const initialCandidate = searchParams.get('candidate') || '';
  
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [candidatePath, setCandidatePath] = useState(initialCandidate);
  const [baselinePath, setBaselinePath] = useState('');
  const [policy, setPolicy] = useState('default');
  
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<ReleaseResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle('Check if safe to ship');
  }, [setTitle]);

  useEffect(() => {
    const fetchArtifacts = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/artifacts`);
        if (res.ok) {
          const data: ArtifactItem[] = await res.json();
          const sorted = data.sort((a, b) => new Date(b.modified_at).getTime() - new Date(a.modified_at).getTime());
          setArtifacts(sorted);
          
          if (!initialCandidate && sorted.length > 0) {
            setCandidatePath(`artifacts/${sorted[0].name}`);
            if (sorted.length > 1) {
              setBaselinePath(`artifacts/${sorted[1].name}`);
            }
          }
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchArtifacts();
  }, [initialCandidate]);

  const handleCheck = async () => {
    if (!candidatePath) return;
    
    setChecking(true);
    setError(null);
    setResult(null);
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload: any = {
        artifact_path: candidatePath,
        policy: policy
      };
      
      if (baselinePath) {
        payload.baseline_path = baselinePath;
      }
      
      const res = await fetch(`${apiUrl}/api/release`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Check failed');
      }
      
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setChecking(false);
    }
  };

  const formatDate = (isoString: string) => {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className={styles.container}>
      <div className={styles.title}>Release check</div>
      
      {error && (
        <div className={styles.errorBanner}>{error}</div>
      )}
      
      <div className={styles.selectionBox}>
        <div className={styles.dropdownsRow}>
          <div className={styles.dropdownCol}>
            <label className={styles.label}>Candidate run (what you want to ship)</label>
            <select 
              className={styles.select}
              value={candidatePath}
              onChange={e => setCandidatePath(e.target.value)}
            >
              <option value="">-- Select a candidate --</option>
              {artifacts.map(art => (
                <option key={art.name} value={`artifacts/${art.name}`}>
                  {art.name} ({formatDate(art.modified_at)})
                </option>
              ))}
            </select>
          </div>
          
          <div className={styles.dropdownCol}>
            <label className={styles.label}>Baseline run (optional, what is currently live)</label>
            <select 
              className={styles.select}
              value={baselinePath}
              onChange={e => setBaselinePath(e.target.value)}
            >
              <option value="">-- No baseline --</option>
              {artifacts.map(art => (
                <option key={art.name} value={`artifacts/${art.name}`}>
                  {art.name} ({formatDate(art.modified_at)})
                </option>
              ))}
            </select>
          </div>
          
          <div className={styles.dropdownCol}>
            <label className={styles.label}>Release policy</label>
            <select 
              className={styles.select}
              value={policy}
              onChange={e => setPolicy(e.target.value)}
            >
              <option value="default">Default (90% pass, no critical regs)</option>
              <option value="strict">Strict (100% pass)</option>
              <option value="staging">Staging (70% pass)</option>
            </select>
          </div>
        </div>
        
        <button 
          className={styles.checkBtn} 
          onClick={handleCheck}
          disabled={checking || !candidatePath}
        >
          {checking ? 'Checking...' : 'Check if safe to ship'}
        </button>
      </div>

      {result && (
        <div className={styles.resultsArea}>
          <div className={`${styles.decisionBox} ${result.allowed ? styles.safe : styles.unsafe}`}>
            <div className={styles.decisionTitle}>
              {result.allowed ? 'Safe to ship' : 'Not safe to ship'}
            </div>
            
            <ul className={styles.reasonsList}>
              {result.reasons.map((reason, idx) => (
                <li key={idx}>{reason}</li>
              ))}
            </ul>
          </div>
          
          {/* Note: In a fuller implementation, we could fetch /compare again if it wasn't safe and list regressions here */}
          {!result.allowed && result.baseline_pass_rate !== null && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <span style={{ color: '#dc2626' }}>⚠</span>
                Recommendation
              </div>
              <p style={{ color: '#475569', fontSize: '0.95rem' }}>
                Please review the regressions by comparing this candidate to the baseline. 
                Fix the broken tests and run a new evaluation before shipping.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ReleasePage() {
  return (
    <React.Suspense fallback={<div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Loading...</div>}>
      <ReleaseContent />
    </React.Suspense>
  );
}
