/**
 * API client for OpenCR run-centric endpoints.
 */
const API = {
  async health() {
    const res = await fetch('/api/health');
    return res.json();
  },

  async metricsSummary() {
    const res = await fetch('/api/metrics/summary');
    if (!res.ok) throw new Error('Failed to load metrics');
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

  async listDocuments(limit = 500) {
    const res = await fetch(`/api/documents?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to list documents');
    return res.json();
  },

  async updateDocument(documentId, payload) {
    const res = await fetch(`/api/documents/${encodeURIComponent(documentId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to update document');
    }
    return res.json();
  },

  async createRun(filePaths, { name, stripRefs = false, exportParquet = true } = {}) {
    const res = await fetch('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        file_paths: filePaths,
        name: name || null,
        strip_refs: stripRefs,
        export_parquet: exportParquet,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to create run');
    }
    return res.json();
  },

  async listRuns(limit = 50) {
    const res = await fetch(`/api/runs?limit=${limit}`);
    if (!res.ok) throw new Error('Failed to list runs');
    return res.json();
  },

  async getRun(runId) {
    const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
    if (!res.ok) throw new Error('Failed to load run');
    return res.json();
  },

  async deleteRun(runId) {
    const res = await fetch(`/api/runs/${encodeURIComponent(runId)}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'Failed to delete run');
    }
    return res.json();
  },

  async getRunDocument(runId, documentId) {
    const res = await fetch(
      `/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(documentId)}`
    );
    if (!res.ok) throw new Error('Failed to load document');
    return res.json();
  },

  async getDocumentText(runId, documentId, mode) {
    const res = await fetch(
      `/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(documentId)}/text?mode=${mode}`
    );
    if (!res.ok) throw new Error('Failed to load text');
    return res.text();
  },

  pageImageUrl(runId, documentId, pageNum, dpi = 120) {
    return `/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(documentId)}/pages/${pageNum}/image?dpi=${dpi}`;
  },

  artifactDownloadUrl(runId, documentId, artifact) {
    return `/api/runs/${encodeURIComponent(runId)}/documents/${encodeURIComponent(documentId)}/download/${encodeURIComponent(artifact)}`;
  },

  datasetDownloadUrl(runId) {
    return `/api/runs/${encodeURIComponent(runId)}/dataset/download`;
  },

  async publishToHF(runId, payload) {
    const res = await fetch(`/api/runs/${encodeURIComponent(runId)}/publish/hf`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || 'HuggingFace publish failed');
    }
    return res.json();
  },

  async authMe() {
    const res = await fetch('/api/auth/me');
    if (!res.ok) return { enabled: false, authenticated: false, user: null };
    return res.json();
  },

  async authLogout() {
    const res = await fetch('/api/auth/logout', { method: 'POST' });
    if (!res.ok) throw new Error('Logout failed');
    return res.json();
  },
};
