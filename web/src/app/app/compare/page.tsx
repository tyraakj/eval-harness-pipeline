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

type ComparisonResult = {
  improvements: Array<any>;
  regressions: Array<any>;
  no_change: Array<any>;
  summary: {
    total_compared: number;
    improved_count: number;
    regressed_count: number;
    no_change_count: number;
  };
};

function CompareContent() {
  const { setTitle } = useAppShell();
  const searchParams = useSearchParams();
  const initialCandidate = searchParams.get('candidate') || '';
  
  const [artifacts, setArtifacts] = useState<ArtifactItem[]>([]);
  const [candidatePath, setCandidatePath] = useState(initialCandidate);
  const [baselinePath, setBaselinePath] = useState('');
  
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState<ComparisonResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  
  const [expandedRow, setExpandedRow] = useState<string | null>(null);

  useEffect(() => {
    setTitle('Compare runs');
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

  const handleCompare = async () => {
    if (!candidatePath || !baselinePath) return;
    
    setComparing(true);
    setError(null);
    setResult(null);
    setExpandedRow(null);
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = {
        candidate_path: candidatePath,
        baseline_path: baselinePath
      };
      
      const res = await fetch(`${apiUrl}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Comparison failed');
      }
      
      const data = await res.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'An unexpected error occurred');
    } finally {
      setComparing(false);
    }
  };

  const formatDate = (isoString: string) => {
    const d = new Date(isoString);
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const getHeadline = () => {
    if (!result) return null;
    if (result.summary.regressed_count > 0 && result.summary.improved_count === 0) {
      return { text: `${result.summary.regressed_count} tests regressed`, class: styles.bad };
    }
    if (result.summary.improved_count > 0 && result.summary.regressed_count === 0) {
      return { text: `${result.summary.improved_count} tests improved`, class: styles.good };
    }
    if (result.summary.improved_count > 0 && result.summary.regressed_count > 0) {
      return { text: `${result.summary.improved_count} improved, ${result.summary.regressed_count} regressed`, class: styles.neutral };
    }
    return { text: 'No changes detected', class: styles.neutral };
  };

  const headline = getHeadline();

  const renderTable = (items: any[], type: 'improved' | 'regressed') => {
    if (items.length === 0) return <div style={{ padding: '16px', color: '#64748b' }}>None</div>;
    
    return (
      <div className={styles.tableBox}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Test ID</th>
              <th>Category</th>
              <th>Score Change</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => {
              const rowId = `${type}-${item.case_id}`;
              const oldScore = Math.round(item.old_score * 100);
              const newScore = Math.round(item.new_score * 100);
              
              return (
                <React.Fragment key={rowId}>
                  <tr className={styles.trMain} onClick={() => setExpandedRow(expandedRow === rowId ? null : rowId)}>
                    <td className={styles.testId}>{item.case_id}</td>
                    <td>{item.suite}</td>
                    <td>
                      <div className={`${styles.scoreChange} ${type === 'improved' ? styles.improved : styles.regressed}`}>
                        <span>{oldScore}%</span>
                        <span className={styles.scoreArrow}>→</span>
                        <span>{newScore}%</span>
                      </div>
                    </td>
                  </tr>
                  
                  {expandedRow === rowId && (
                    <tr className={styles.detailsRow}>
                      <td colSpan={3} style={{ padding: 0 }}>
                        <div className={styles.detailsContent}>
                          <div className={styles.detailsCol}>
                            <div className={styles.detailsColTitle}>Baseline ({oldScore}%)</div>
                            {item.old_graders && item.old_graders.length > 0 ? (
                              item.old_graders.map((gr: any, idx: number) => (
                                <div key={idx} className={styles.detailsCheck}>
                                  {gr.passed ? (
                                    <span style={{ color: '#16a34a' }}>✓</span>
                                  ) : (
                                    <span style={{ color: '#dc2626' }}>✗</span>
                                  )}
                                  <span>{gr.reason || gr.grader_name}</span>
                                </div>
                              ))
                            ) : (
                              <div style={{ fontSize: '0.85rem', color: '#64748b' }}>No details</div>
                            )}
                          </div>
                          
                          <div className={styles.detailsCol}>
                            <div className={styles.detailsColTitle}>Candidate ({newScore}%)</div>
                            {item.new_graders && item.new_graders.length > 0 ? (
                              item.new_graders.map((gr: any, idx: number) => (
                                <div key={idx} className={styles.detailsCheck}>
                                  {gr.passed ? (
                                    <span style={{ color: '#16a34a' }}>✓</span>
                                  ) : (
                                    <span style={{ color: '#dc2626' }}>✗</span>
                                  )}
                                  <span>{gr.reason || gr.grader_name}</span>
                                </div>
                              ))
                            ) : (
                              <div style={{ fontSize: '0.85rem', color: '#64748b' }}>No details</div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className={styles.container}>
      <div className={styles.title}>Compare runs</div>
      
      {error && (
        <div className={styles.errorBanner}>{error}</div>
      )}
      
      <div className={styles.selectionBox}>
        <div className={styles.dropdownsRow}>
          <div className={styles.dropdownCol}>
            <label className={styles.label}>Baseline run</label>
            <select 
              className={styles.select}
              value={baselinePath}
              onChange={e => setBaselinePath(e.target.value)}
            >
              <option value="">-- Select a baseline --</option>
              {artifacts.map(art => (
                <option key={art.name} value={`artifacts/${art.name}`}>
                  {art.name} ({formatDate(art.modified_at)})
                </option>
              ))}
            </select>
          </div>
          
          <div className={styles.dropdownCol}>
            <label className={styles.label}>Candidate run (new)</label>
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
        </div>
        
        <button 
          className={styles.compareBtn} 
          onClick={handleCompare}
          disabled={comparing || !candidatePath || !baselinePath || candidatePath === baselinePath}
        >
          {comparing ? 'Comparing...' : 'Compare runs'}
        </button>
      </div>

      {result && (
        <div className={styles.resultsArea}>
          {headline && (
            <div className={`${styles.summaryHeadline} ${headline.class}`}>
              {headline.text}
            </div>
          )}
          <div className={styles.summaryDesc}>
            Compared {result.summary.total_compared} tests in total.
          </div>
          
          {result.regressions.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <span style={{ color: '#dc2626' }}>✗</span>
                What broke (Regressions)
              </div>
              {renderTable(result.regressions, 'regressed')}
            </div>
          )}
          
          {result.improvements.length > 0 && (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>
                <span style={{ color: '#16a34a' }}>✓</span>
                What got fixed (Improvements)
              </div>
              {renderTable(result.improvements, 'improved')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <React.Suspense fallback={<div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>Loading...</div>}>
      <CompareContent />
    </React.Suspense>
  );
}
