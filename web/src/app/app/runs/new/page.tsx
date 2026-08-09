'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAppShell } from '@/components/AppShell';
import styles from './page.module.css';

type DatasetItem = {
  name: string;
  size_bytes: number;
  modified_at: string;
  case_count?: number;
};

export default function NewRunPage() {
  const { setTitle } = useAppShell();
  const router = useRouter();

  const [datasets, setDatasets] = useState<DatasetItem[]>([]);
  const [loadingDatasets, setLoadingDatasets] = useState(true);

  // Form State
  const [datasetPath, setDatasetPath] = useState('');
  const [factory, setFactory] = useState('');
  const [targetFactory, setTargetFactory] = useState('');
  const [outputPath, setOutputPath] = useState(`artifacts/run-${Date.now()}.jsonl`);
  const [timeoutSeconds, setTimeoutSeconds] = useState(60);
  const [maxToolCalls, setMaxToolCalls] = useState(20);
  const [maxConcurrency, setMaxConcurrency] = useState(4);
  const [useExtraWorkers, setUseExtraWorkers] = useState(false);
  const [limitsExpanded, setLimitsExpanded] = useState(false);

  // Status State
  const [checkResult, setCheckResult] = useState<{ valid: boolean, msg: string } | null>(null);
  const [checking, setChecking] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    setTitle('Start a run');
  }, [setTitle]);

  useEffect(() => {
    const fetchDatasets = async () => {
      try {
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
        const res = await fetch(`${apiUrl}/api/datasets`);
        if (res.ok) {
          const data = await res.json();
          setDatasets(data);
          if (data.length > 0) {
            setDatasetPath(`datasets/${data[0].name}`);
          }
        }
      } catch (err) {
        console.error(err);
      } finally {
        setLoadingDatasets(false);
      }
    };
    fetchDatasets();
  }, []);

  const handleCheck = async () => {
    if (!factory) {
      setCheckResult({ valid: false, msg: 'Evaluation setup is required' });
      return;
    }
    if (!datasetPath) {
      setCheckResult({ valid: false, msg: 'Test library is required' });
      return;
    }

    setChecking(true);
    setCheckResult(null);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = {
        config: {
          factory,
          dataset: datasetPath,
          output: outputPath,
          enable_specialized_workers: useExtraWorkers,
          target_factory: targetFactory || null,
          budget: {
            timeout_seconds: timeoutSeconds,
            max_tool_calls: maxToolCalls,
            max_concurrency: maxConcurrency
          }
        }
      };
      
      const res = await fetch(`${apiUrl}/api/runs/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      const data = await res.json();
      if (res.ok && data.valid) {
        setCheckResult({ valid: true, msg: '✓ setup loaded' });
      } else {
        const errMsg = data.errors ? data.errors.join(', ') : 'Validation failed';
        setCheckResult({ valid: false, msg: errMsg });
      }
    } catch (err) {
      setCheckResult({ valid: false, msg: 'Failed to connect to server' });
    } finally {
      setChecking(false);
    }
  };

  const handleSubmit = async () => {
    if (!factory || !datasetPath) {
      setSubmitError('Please provide an evaluation setup and select a test library.');
      return;
    }

    setSubmitting(true);
    setSubmitError(null);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const payload = {
        config: {
          factory,
          dataset: datasetPath,
          output: outputPath,
          enable_specialized_workers: useExtraWorkers,
          target_factory: targetFactory || null,
          budget: {
            timeout_seconds: timeoutSeconds,
            max_tool_calls: maxToolCalls,
            max_concurrency: maxConcurrency
          }
        }
      };

      const res = await fetch(`${apiUrl}/api/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      
      if (!res.ok) {
        if (res.status === 429) {
          throw new Error('Too many requests. Please try again in a minute.');
        }
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start run');
      }
      
      const data = await res.json();
      router.push(`/app/runs/${data.job_id}`);
    } catch (err: any) {
      setSubmitError(err.message || 'An unexpected error occurred');
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.container}>
      {submitError && (
        <div className={styles.errorBanner}>{submitError}</div>
      )}

      <div className={styles.twoCol}>
        {/* Left Column */}
        <div className={styles.colLeft}>
          <div className={styles.field}>
            <label className={styles.fieldLabel}>Choose a test library</label>
            {loadingDatasets ? (
              <div className={styles.helperText}>Loading test libraries...</div>
            ) : datasets.length === 0 ? (
              <div className={styles.helperText}>No test libraries yet — upload one on the Tests page.</div>
            ) : (
              <select 
                className={styles.select} 
                value={datasetPath} 
                onChange={(e) => setDatasetPath(e.target.value)}
              >
                {datasets.map(ds => (
                  <option key={ds.name} value={`datasets/${ds.name}`}>
                    {ds.name} ({ds.case_count || 0} tests)
                  </option>
                ))}
              </select>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Evaluation setup (module:function)</label>
            <div className={styles.inputRow}>
              <input 
                type="text" 
                className={styles.input} 
                placeholder="my_app.eval:create_evaluation"
                value={factory}
                onChange={(e) => {
                  setFactory(e.target.value);
                  setCheckResult(null);
                }}
              />
              <button className={styles.checkBtn} onClick={handleCheck} disabled={checking}>
                {checking ? 'Checking...' : 'Check'}
              </button>
            </div>
            {checkResult && (
              <div className={`${styles.checkResult} ${checkResult.valid ? styles.checkSuccess : styles.checkError}`}>
                {checkResult.msg}
              </div>
            )}
            <div className={styles.helperText}>
              This is the Python function that describes how your agent is tested. Example: my_app.eval:create_evaluation
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Agent override (optional)</label>
            <input 
              type="text" 
              className={styles.input} 
              placeholder="my_app.agent:create_agent"
              value={targetFactory}
              onChange={(e) => setTargetFactory(e.target.value)}
            />
            <div className={styles.helperText}>
              Provide a different target factory to test against (e.g. for comparison).
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Save results to</label>
            <input 
              type="text" 
              className={styles.input} 
              value={outputPath}
              onChange={(e) => setOutputPath(e.target.value)}
            />
          </div>
        </div>

        {/* Right Column (Limits) */}
        <div className={styles.colRight}>
          <div className={styles.rightHeader} onClick={() => setLimitsExpanded(!limitsExpanded)}>
            <span>Advanced limits</span>
            <span>{limitsExpanded ? '▴' : '▾'}</span>
          </div>
          
          {limitsExpanded && (
            <div className={styles.rightBody}>
              <div className={styles.limitField}>
                <label className={styles.limitLabel}>Stop after (seconds)</label>
                <input 
                  type="number" 
                  className={styles.limitInput} 
                  value={timeoutSeconds}
                  onChange={(e) => setTimeoutSeconds(parseInt(e.target.value) || 0)}
                />
                <span className={styles.limitHelper}>Each test stops if it takes longer than this.</span>
              </div>
              
              <div className={styles.limitField}>
                <label className={styles.limitLabel}>Max tool calls per test</label>
                <input 
                  type="number" 
                  className={styles.limitInput} 
                  value={maxToolCalls}
                  onChange={(e) => setMaxToolCalls(parseInt(e.target.value) || 0)}
                />
                <span className={styles.limitHelper}>How many times the agent can use a tool per test.</span>
              </div>
              
              <div className={styles.limitField}>
                <label className={styles.limitLabel}>Run concurrency (tests at once)</label>
                <input 
                  type="number" 
                  className={styles.limitInput} 
                  value={maxConcurrency}
                  onChange={(e) => setMaxConcurrency(parseInt(e.target.value) || 0)}
                />
                <span className={styles.limitHelper}>Higher = faster but uses more resources.</span>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Toggle Box */}
      <div className={styles.toggleBox} onClick={() => setUseExtraWorkers(!useExtraWorkers)}>
        <input 
          type="checkbox" 
          className={styles.checkbox} 
          checked={useExtraWorkers}
          onChange={(e) => setUseExtraWorkers(e.target.checked)}
        />
        <div className={styles.toggleText}>
          <span className={styles.toggleTitle}>Run extra analysis checks (security, performance, output quality)</span>
          <span className={styles.toggleDesc}>Takes a bit longer. Recommended before shipping.</span>
        </div>
      </div>

      <button 
        className={styles.submitBtn} 
        onClick={handleSubmit} 
        disabled={submitting || datasets.length === 0}
      >
        {submitting ? 'Starting evaluation...' : 'Start evaluation'}
      </button>
    </div>
  );
}
