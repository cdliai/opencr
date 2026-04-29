/**
 * API client for OpenCR pipeline endpoints.
 */
const API = {
  async health() {
    const res = await fetch('/api/health');
    return res.json();
  },

  async metricsSummary() {
    const res = await fetch('/api/metrics/summary');
    if (!res.ok) throw new Error('Failed to load metrics summary');
    return res.json();
  },

  upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');

      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText));
        } else {
          let msg = 'Upload failed';
          try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
          reject(new Error(msg));
        }
      };

      xhr.onerror = () => reject(new Error('Upload network error'));

      const form = new FormData();
      form.append('file', file);
      xhr.send(form);
    });
  },

  async listInputFiles() {
    const res = await fetch('/api/files/input');
    if (!res.ok) throw new Error('Failed to list input files');
    return res.json();
  },

  async listOutputFiles() {
    const res = await fetch('/api/files/output');
    if (!res.ok) throw new Error('Failed to list output files');
    return res.json();
  },

  async listDatasetFiles() {
    const res = await fetch('/api/files/datasets');
    if (!res.ok) throw new Error('Failed to list dataset bundles');
    return res.json();
  },

  async getOutputRawTxt(stem) {
    const res = await fetch(`/api/files/output/${encodeURIComponent(stem)}.raw.txt`);
    if (!res.ok) throw new Error('Failed to load raw text');
    return res.text();
  },

  async getOutputTxt(stem) {
    const res = await fetch(`/api/files/output/${encodeURIComponent(stem)}.txt`);
    if (!res.ok) throw new Error('Failed to load clean text');
    return res.text();
  },

  async getOutputMd(stem) {
    const res = await fetch(`/api/files/output/${encodeURIComponent(stem)}.md`);
    if (!res.ok) throw new Error('Failed to load markdown');
    return res.text();
  },

  async getOutputMeta(stem) {
    const res = await fetch(`/api/files/output/${encodeURIComponent(stem)}.meta.json`);
    if (!res.ok) throw new Error('Failed to load metadata');
    return res.json();
  },

  artifactDownloadUrl(stem, artifact) {
    return `/api/files/output/${encodeURIComponent(stem)}/download/${encodeURIComponent(artifact)}`;
  },

  datasetDownloadUrl(name) {
    return `/api/files/datasets/${encodeURIComponent(name)}/download`;
  },

  async createJob(filePaths, { stripRefs = false, exportParquet = false } = {}) {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_paths: filePaths,
        strip_refs: stripRefs,
        export_parquet: exportParquet,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to create job');
    }
    return res.json();
  },

  async getJobStatus(jobId) {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) throw new Error('Failed to get job status');
    return res.json();
  },
};
