'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

export default function SecurityAuditPage() {
  const params = useParams();
  const runId = params.id as string;
  const router = useRouter();
  const { setTitle } = useAppShell();
  
  const [audit, setAudit] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTitle(`Security Audit - ${runId}`);
    
    const fetchAudit = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/runs/${runId}/security-audit`);
        if (res.ok) {
          const data = await res.json();
          setAudit(data);
        } else {
          throw new Error('Failed to load security audit');
        }
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    
    fetchAudit();
  }, [runId, setTitle]);

  return (
    <div className={styles.container}>
      <button onClick={() => router.back()} style={{ background: 'none', border: 'none', color: '#6366f1', cursor: 'pointer', marginBottom: '16px' }}>← Back to Run</button>
      <div className={styles.title}>Security Audit Report</div>
      
      {loading && <div>Loading audit data...</div>}
      {error && <div style={{ color: 'red' }}>{error}</div>}
      
      {audit && (
        <div className={styles.box}>
          <div className={styles.headerRow}>
            <div>
              <div style={{ fontSize: '1.2rem', fontWeight: 600 }}>Status: {audit.status}</div>
              <div style={{ fontSize: '0.85rem', color: '#64748b' }}>Run ID: {audit.run_id}</div>
            </div>
            <div className={audit.findings?.length > 0 ? styles.statusBad : styles.statusGood}>
              {audit.findings?.length > 0 ? `${audit.findings.length} findings detected` : 'No vulnerabilities found'}
            </div>
          </div>
          
          {audit.findings?.length > 0 ? (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Severity</th>
                  <th>Type</th>
                  <th>Case ID</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {audit.findings.map((f: any, i: number) => {
                  const sevClass = styles[f.severity.toLowerCase()] || '';
                  return (
                    <tr key={i}>
                      <td className={sevClass}>{f.severity.toUpperCase()}</td>
                      <td>{f.finding_type}</td>
                      <td style={{ color: '#64748b', fontSize: '0.85rem' }}>{f.case_id}</td>
                      <td>{f.description}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          ) : (
            <div style={{ padding: '32px', textAlign: 'center', color: '#64748b' }}>
              ✓ All security checks passed
            </div>
          )}
        </div>
      )}
    </div>
  );
}
