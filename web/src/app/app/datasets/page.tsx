'use client';

import React, { useEffect, useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type DatasetItem = {
  name: string;
  size_bytes: number;
  modified_at: string;
  case_count: number;
};

export default function DatasetsPage() {
  const { setTitle } = useAppShell();
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{msg: string, isError: boolean} | null>(null);

  useEffect(() => {
    setTitle('Test libraries');
    fetchDatasets();
  }, [setTitle]);

  const fetchDatasets = async () => {
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets`);
      if (res.ok) {
        const data = await res.json();
        setDatasets(data);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const showToast = (msg: string, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 4000);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.jsonl')) {
      showToast('Must be a .jsonl file', true);
      return;
    }

    const formData = new FormData();
    formData.append('file', file);

    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets`, {
        method: 'POST',
        body: formData
      });
      
      if (res.ok) {
        showToast('Library uploaded');
        fetchDatasets();
      } else {
        const data = await res.json();
        showToast(data.detail || 'Failed to upload', true);
      }
    } catch (err) {
      showToast('Failed to connect to server', true);
    }
    
    // Reset input
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleCheck = async (e: React.MouseEvent, name: string) => {
    e.preventDefault();
    e.stopPropagation();
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const res = await fetch(`${apiUrl}/api/datasets/${name}/validate`);
      const data = await res.json();
      
      if (res.ok) {
        if (data.valid) {
          showToast(`✓ Library is valid (${data.case_count} tests)`);
        } else {
          showToast(`✗ Found ${data.errors?.length || 0} errors and ${data.warnings?.length || 0} warnings`, true);
        }
      } else {
        showToast(data.detail || 'Validation failed', true);
      }
    } catch (err) {
      showToast('Failed to connect to server', true);
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.headerRow}>
        <div className={styles.title}>Your test libraries</div>
        
        <div>
          <input 
            type="file" 
            accept=".jsonl" 
            ref={fileInputRef} 
            className={styles.hiddenInput}
            onChange={handleFileUpload}
          />
          <button className={styles.uploadBtn} onClick={() => fileInputRef.current?.click()}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="17 8 12 3 7 8"></polyline>
              <line x1="12" y1="3" x2="12" y2="15"></line>
            </svg>
            Upload test library
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ color: '#64748b' }}>Loading...</div>
      ) : datasets.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', backgroundColor: '#fff', border: '1px dashed #cbd5e1', borderRadius: '8px', color: '#64748b' }}>
          No test libraries found.
        </div>
      ) : (
        <div className={styles.grid}>
          {datasets.map(ds => (
            <div 
              key={ds.name} 
              className={styles.card}
              onClick={() => router.push(`/app/datasets/${ds.name}`)}
            >
              <div className={styles.cardTop}>
                <div className={styles.libraryName}>{ds.name}</div>
                <div className={styles.testCount}>{ds.case_count || 0} tests</div>
              </div>
              
              <div className={styles.pillsRow} title="Tests that check nothing broke compared to before">
                {/* Normally we'd get these counts from the API, but fallback to general pills for now */}
                <span className={`${styles.pill} ${styles.pillCapability}`}>capability</span>
                <span className={`${styles.pill} ${styles.pillRegression}`}>regression</span>
                <span className={`${styles.pill} ${styles.pillSecurity}`}>security</span>
              </div>
              
              <button 
                className={styles.checkBtn}
                onClick={(e) => handleCheck(e, ds.name)}
              >
                Check library
              </button>
            </div>
          ))}
        </div>
      )}

      {toast && (
        <div className={styles.toast} style={{ backgroundColor: toast.isError ? '#ef4444' : '#0f172a' }}>
          {toast.msg}
        </div>
      )}
    </div>
  );
}
