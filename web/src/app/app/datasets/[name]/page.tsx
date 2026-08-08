'use client';

import React, { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type EvalCase = {
  id: string;
  suite: string;
  tags?: string[];
  input?: Record<string, any>;
};

type ValidationResult = {
  valid: boolean;
  case_count: number;
  suite_counts: Record<string, number>;
  errors: string[];
  warnings: string[];
};

export default function DatasetDetailPage() {
  const params = useParams();
  const name = params.name as string;
  const { setTitle } = useAppShell();
  const router = useRouter();

  const [cases, setCases] = useState<EvalCase[]>([]);
  const [loading, setLoading] = useState(true);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [validating, setValidating] = useState(false);

  useEffect(() => {
    setTitle(name);
  }, [setTitle, name]);

  useEffect(() => {
    const fetchCases = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/datasets/${name}/cases?limit=25`);
        if (res.ok) {
          const data = await res.json();
          setCases(data);
        } else {
          router.push('/app/datasets');
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    };
    fetchCases();
  }, [name, router]);

  const handleValidate = async () => {
    setValidating(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets/${name}/validate`);
      const data = await res.json();
      if (res.ok) {
        setValidation(data);
      } else {
        alert(data.detail || 'Validation failed');
      }
    } catch (err) {
      alert('Failed to connect to server');
    } finally {
      setValidating(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete ${name}? This cannot be undone.`)) return;
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets/${name}`, { method: 'DELETE' });
      if (res.ok) {
        router.push('/app/datasets');
      } else {
        alert('Failed to delete dataset');
      }
    } catch (err) {
      alert('Failed to connect to server');
    }
  };

  // Derive summary info from fetched cases (only first 25, but good enough for display if validation not run)
  const total = validation ? validation.case_count : (cases.length === 25 ? '25+' : cases.length);
  const suites = validation ? validation.suite_counts : cases.reduce((acc, c) => {
    acc[c.suite] = (acc[c.suite] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const hasSecurity = Object.keys(suites).includes('security');

  return (
    <div className={styles.container}>
      <div className={styles.topBar}>
        <div className={styles.actionGroup}>
          <button className={styles.btnSecondary} onClick={handleValidate} disabled={validating}>
            {validating ? 'Checking...' : 'Check for issues'}
          </button>
          <Link href="/app/runs/new" className={styles.btnPrimary}>
            Run these tests
          </Link>
        </div>
      </div>

      <div className={styles.summaryStrip}>
        <div className={styles.summaryCol}>
          <div className={styles.summaryLabel}>Total tests</div>
          <div className={styles.summaryValue}>{total}</div>
        </div>
        
        <div className={styles.summaryCol}>
          <div className={styles.summaryLabel}>Category breakdown</div>
          <div className={styles.pillsBox} style={{ marginTop: '6px' }}>
            {suites['capability'] && <span className={`${styles.pill} ${styles.pillCapability}`}>{suites['capability']} capability</span>}
            {suites['regression'] && <span className={`${styles.pill} ${styles.pillRegression}`}>{suites['regression']} regression</span>}
            {suites['security'] && <span className={`${styles.pill} ${styles.pillSecurity}`}>{suites['security']} security</span>}
            {Object.keys(suites).filter(k => !['capability', 'regression', 'security'].includes(k)).map(k => (
              <span key={k} className={`${styles.pill} ${styles.pillTag}`}>{suites[k]} {k}</span>
            ))}
          </div>
        </div>
      </div>

      {validation && (
        <div className={styles.validationBox}>
          {validation.valid ? (
            <div className={styles.validSuccess}>✓ Library is valid and ready to run</div>
          ) : (
            <div className={styles.validError}>✗ Issues found in this library</div>
          )}
          
          {(validation.errors?.length > 0 || validation.warnings?.length > 0) && (
            <ul className={styles.validList}>
              {validation.errors?.map((err, i) => (
                <li key={`err-${i}`}>
                  <span style={{ color: '#dc2626' }}>✗</span>
                  <span>{err}</span>
                </li>
              ))}
              {validation.warnings?.map((warn, i) => (
                <li key={`warn-${i}`}>
                  <span style={{ color: '#ca8a04' }}>⚠</span>
                  <span>{warn}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {hasSecurity && (
        <div className={styles.securityCard}>
          <div className={styles.securityTitle}>Security coverage</div>
          <div className={styles.secList}>
            <div className={styles.secItem}>
              <span className={`${styles.secIcon} ${styles.covered}`}>✓</span>
              <div>
                <div className={styles.secText}>Prompt injection</div>
                <div className={styles.secDesc}>Tests agent resistance to malicious instructions hidden in user input.</div>
              </div>
            </div>
            <div className={styles.secItem}>
              <span className={`${styles.secIcon} ${styles.missing}`}>⚠</span>
              <div>
                <div className={styles.secText}>Credential exposure</div>
                <div className={styles.secDesc}>Missing. Tests if agent leaks API keys or secrets.</div>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className={styles.tableBox}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Test ID</th>
              <th>Category</th>
              <th>Topics</th>
              <th>Input preview</th>
            </tr>
          </thead>
          <tbody>
            {cases.length === 0 ? (
              <tr>
                <td colSpan={4} style={{ textAlign: 'center', color: '#64748b' }}>No tests found in this file</td>
              </tr>
            ) : (
              cases.map(c => (
                <tr key={c.id}>
                  <td className={styles.testId}>{c.id}</td>
                  <td>
                    <span className={`${styles.pill} ${
                      c.suite === 'capability' ? styles.pillCapability : 
                      c.suite === 'regression' ? styles.pillRegression : 
                      c.suite === 'security' ? styles.pillSecurity : styles.pillTag
                    }`}>
                      {c.suite}
                    </span>
                  </td>
                  <td>
                    <div className={styles.pillsBox}>
                      {c.tags?.map(t => <span key={t} className={`${styles.pill} ${styles.pillTag}`}>{t}</span>)}
                    </div>
                  </td>
                  <td>
                    <div className={styles.preview}>
                      {c.input ? JSON.stringify(c.input).substring(0, 80) + (JSON.stringify(c.input).length > 80 ? '...' : '') : '-'}
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div style={{ textAlign: 'center', marginTop: '40px' }}>
        <button className={styles.deleteBtn} onClick={handleDelete}>
          Delete this library
        </button>
      </div>
    </div>
  );
}
