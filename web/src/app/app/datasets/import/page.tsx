'use client';

import React, { useState, useRef, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

export default function DatasetImportPage() {
  const { setTitle } = useAppShell();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    setTitle('Import test cases');
  }, [setTitle]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setLoading(true);
    setError(null);
    setPreview(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const formData = new FormData();
      formData.append('file', selectedFile);

      const res = await fetch(`${apiUrl}/api/datasets/convert`, {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Conversion preview failed');
      }

      const data = await res.json();
      setPreview(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview?.output_file) return;

    setConfirming(true);
    setError(null);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets/convert/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ output_file: preview.output_file }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || 'Confirmation failed');
      }

      const data = await res.json();
      router.push(`/app/datasets/${data.name}`);
    } catch (err: any) {
      setError(err.message);
      setConfirming(false);
    }
  };

  const isFuzzy = (col: string) => {
    return preview?.fuzzy_matches?.some((f: string) => f.includes(`"${col}"`));
  };

  return (
    <div className={styles.container}>
      <div className={styles.title}>Import test cases</div>
      <div className={styles.subtitle}>
        Turn your existing tests, spreadsheets, or failure logs into a Glyph test library.
      </div>

      {!preview && (
        <div 
          className={styles.uploadZone} 
          onClick={() => fileInputRef.current?.click()}
        >
          <div className={styles.uploadTitle}>
            {loading ? 'Analyzing file...' : 'Drop your file here, or click to browse.'}
          </div>
          {!loading && (
            <div className={styles.uploadDesc}>
              We support CSV, Excel, JSON, pytest files, OpenAI evals, LangSmith exports, and plain text. No special format required.
            </div>
          )}
          <input 
            type="file" 
            ref={fileInputRef} 
            onChange={handleFileChange} 
            className={styles.fileInput} 
          />
        </div>
      )}

      {error && <div style={{ color: 'red', marginTop: '16px' }}>{error}</div>}

      {preview && (
        <div className={styles.previewBox}>
          <div style={{ fontSize: '1.2rem', fontWeight: 600, marginBottom: '16px' }}>Column Mapping Preview</div>
          
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Original Column</th>
                <th>Mapped To</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(preview.column_mapping).map(([raw, mapped]) => (
                <tr key={raw}>
                  <td>{raw}</td>
                  <td>
                    {mapped as string}
                    {isFuzzy(raw) && <span className={styles.fuzzyMatch}>fuzzy match — please verify</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className={styles.summaryBox}>
            <div style={{ fontWeight: 600, marginBottom: '12px' }}>Ready to import</div>
            <div className={styles.summaryItem}>
              <span>Total cases detected:</span>
              <span className={styles.summaryValue}>{preview.cases_converted + preview.cases_quarantined}</span>
            </div>
            <div className={styles.summaryItem}>
              <span>Cases lacking expected answers:</span>
              <span className={styles.summaryValue} style={{ color: preview.cases_missing_expected > 0 ? '#ca8a04' : 'inherit' }}>
                {preview.cases_missing_expected}
              </span>
            </div>
            <div className={styles.summaryItem}>
              <span>Ready to use immediately:</span>
              <span className={styles.summaryValue}>{preview.cases_converted}</span>
            </div>
          </div>

          {preview.cases_quarantined > 0 && (
            <div className={styles.quarantineWarning}>
              <strong>Warning:</strong> {preview.cases_quarantined} cases contain possible sensitive data (secrets or PII). 
              These have been quarantined to <code>{preview.quarantine_file}</code> and will NOT be imported.
            </div>
          )}

          <div className={styles.actionRow}>
            <button className={styles.btnSecondary} onClick={() => setPreview(null)} disabled={confirming}>
              Cancel
            </button>
            <button className={styles.btnPrimary} onClick={handleConfirm} disabled={confirming}>
              {confirming ? 'Importing...' : `Import ${preview.cases_converted} cases`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
