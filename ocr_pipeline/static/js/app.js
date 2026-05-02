const STATUS_PILL = {
  completed: 'pill-success',
  failed: 'pill-error',
  processing: 'pill-active',
  queued: 'pill-warn',
};
const PAGE_STATUS = {
  pass: 'page-pass',
  warn: 'page-warn',
  fail: 'page-fail',
  empty: 'page-empty',
};

function emptyHFModal() {
  return { open: false, runId: null, repoId: '', private: false, token: '', submitting: false, result: null };
}

function emptyInspector() {
  return { documentId: null, document: null, pageNum: 1, mode: 'txt', text: '' };
}

function opencrApp() {
  return {
    version: '',
    healthStatus: 'checking...',
    healthClass: '',
    metrics: {},

    auth: { enabled: false, authenticated: false, user: null },

    runs: [],
    selectedRunId: null,
    selectedRun: null,

    inputFiles: [],
    selectedPaths: [],
    intakeOptions: { stripRefs: false, exportParquet: true, name: '' },
    creating: false,
    dragOver: false,
    uploadProgress: null,

    inspector: emptyInspector(),
    hfModal: emptyHFModal(),
    toasts: [],

    _stream: new RunStream(),

    async init() {
      await Promise.all([
        this.refreshHealth(),
        this.refreshMetrics(),
        this.refreshInputFiles(),
        this.refreshRuns(),
        this.refreshAuth(),
      ]);
      setInterval(() => this.refreshHealth(), 15000);
      setInterval(() => this.refreshMetrics(), 10000);
    },

    async refreshAuth() {
      try { this.auth = await API.authMe(); } catch { this.auth = { enabled: false, authenticated: false, user: null }; }
    },

    signIn() { window.location.href = '/api/auth/login'; },

    async signOut() {
      try {
        await API.authLogout();
        await this.refreshAuth();
        this.toast('Signed out', 'info');
      } catch (e) {
        this.toast(`Sign out failed: ${e.message}`, 'error');
      }
    },

    get canPublish() {
      // OAuth disabled → publish is always available (paste-token mode).
      // OAuth enabled  → publish requires a signed-in user.
      return !this.auth.enabled || this.auth.authenticated;
    },

    async refreshHealth() {
      try {
        const data = await API.health();
        this.version = data.pipeline_version || '';
        this.healthStatus = data.status;
        this.healthClass = data.status === 'ready' ? 'ready' : 'waiting';
      } catch {
        this.healthStatus = 'offline';
        this.healthClass = 'error';
      }
    },

    async refreshMetrics() {
      try { this.metrics = await API.metricsSummary(); } catch {}
    },

    async refreshInputFiles() {
      try { this.inputFiles = await API.listInputFiles(); }
      catch (e) { this.toast(`Failed to load inputs: ${e.message}`, 'error'); }
    },

    async refreshRuns() {
      try { this.runs = await API.listRuns(50); }
      catch (e) { this.toast(`Failed to load runs: ${e.message}`, 'error'); }
    },

    async refreshSelectedRun() {
      if (!this.selectedRunId) return;
      try { this.selectedRun = await API.getRun(this.selectedRunId); }
      catch (e) { this.toast(`Failed to refresh run: ${e.message}`, 'error'); }
    },

    async selectRun(runId) {
      this._stream.disconnect();
      if (!runId) {
        this.selectedRunId = null;
        this.selectedRun = null;
        this.inspector = emptyInspector();
        return;
      }
      this.selectedRunId = runId;
      try {
        this.selectedRun = await API.getRun(runId);
        const firstCompleted = (this.selectedRun.documents || []).find(d => d.status === 'completed');
        if (firstCompleted) await this.openDocument(firstCompleted.document_id);
        else this.inspector = emptyInspector();
        if (['queued', 'processing'].includes(this.selectedRun.status)) this.connectStream(runId);
      } catch (e) {
        this.toast(`Failed to load run: ${e.message}`, 'error');
      }
    },

    connectStream(runId) {
      this._stream.connect(runId, async (event) => {
        if (event.type === 'page_complete' || event.type === 'document_complete') {
          await this.refreshSelectedRun();
        }
        if (event.type === 'run_complete' || event.type === 'run_failed') {
          await Promise.all([this.refreshSelectedRun(), this.refreshRuns(), this.refreshMetrics()]);
          const completed = event.type === 'run_complete';
          this.toast(`Run ${runId} ${completed ? 'completed' : 'failed'}`, completed ? 'success' : 'error');
        }
        if (event.type === 'run_started') await this.refreshRuns();
      });
    },

    async openDocument(documentId) {
      if (!this.selectedRunId || !documentId) return;
      this.inspector.documentId = documentId;
      try {
        this.inspector.document = await API.getRunDocument(this.selectedRunId, documentId);
        this.inspector.pageNum = 1;
        await this.loadInspectorText();
      } catch (e) {
        this.toast(`Open document failed: ${e.message}`, 'error');
      }
    },

    async loadInspectorText() {
      if (!this.selectedRunId || !this.inspector.documentId) return;
      try {
        this.inspector.text = await API.getDocumentText(
          this.selectedRunId, this.inspector.documentId, this.inspector.mode,
        );
      } catch (e) {
        this.inspector.text = `(${e.message})`;
      }
    },

    setInspectorMode(mode) {
      this.inspector.mode = mode;
      this.loadInspectorText();
    },

    setInspectorPage(num) {
      const total = this.inspector.document?.total_pages || 1;
      this.inspector.pageNum = Math.min(Math.max(1, num), total);
    },

    pageImageUrl(pageNum) {
      if (!this.selectedRunId || !this.inspector.documentId) return '';
      return API.pageImageUrl(this.selectedRunId, this.inspector.documentId, pageNum);
    },

    pageStatusFor(pageNum) {
      return (this.inspector.document?.pages || []).find(p => p.page_num === pageNum)?.status || 'pending';
    },

    pageStatusClass(status) { return PAGE_STATUS[status] || 'page-pending'; },
    runStatusClass(status) { return STATUS_PILL[status] || 'pill-muted'; },

    async startNewRun() {
      if (this.selectedPaths.length === 0 || this.creating) return;
      this.creating = true;
      try {
        const result = await API.createRun(this.selectedPaths, {
          name: this.intakeOptions.name || null,
          stripRefs: this.intakeOptions.stripRefs,
          exportParquet: this.intakeOptions.exportParquet,
        });
        const dedup = result.documents.filter(d => d.deduped).length;
        if (dedup > 0) this.toast(`${dedup} document(s) recognized from prior runs`, 'info');
        this.toast(`Run ${result.run_id} queued`, 'success');
        this.selectedPaths = [];
        await this.refreshRuns();
        await this.selectRun(result.run_id);
      } catch (e) {
        this.toast(`Failed to start run: ${e.message}`, 'error');
      } finally {
        this.creating = false;
      }
    },

    async deleteSelectedRun() {
      if (!this.selectedRunId) return;
      if (!confirm(`Delete run ${this.selectedRunId}? Artifact files remain on disk.`)) return;
      try {
        await API.deleteRun(this.selectedRunId);
        this.toast(`Run ${this.selectedRunId} deleted`, 'info');
        await this.selectRun(null);
        await this.refreshRuns();
      } catch (e) {
        this.toast(`Delete failed: ${e.message}`, 'error');
      }
    },

    toggleSelected(path) {
      const i = this.selectedPaths.indexOf(path);
      if (i === -1) this.selectedPaths.push(path); else this.selectedPaths.splice(i, 1);
    },

    selectAllInputs(checked) {
      this.selectedPaths = checked ? this.inputFiles.map(f => f.path) : [];
    },

    get allInputsSelected() {
      return this.inputFiles.length > 0 && this.selectedPaths.length === this.inputFiles.length;
    },

    async handleDrop(event) {
      this.dragOver = false;
      const files = Array.from(event.dataTransfer.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
      if (files.length === 0) return this.toast('Only PDF files are accepted', 'error');
      await this.uploadFiles(files);
    },

    async handleFileSelect(event) {
      const files = Array.from(event.target.files || []);
      if (files.length > 0) await this.uploadFiles(files);
      event.target.value = '';
    },

    async uploadFiles(files) {
      let count = 0;
      for (const file of files) {
        try {
          this.uploadProgress = 0;
          await API.upload(file, p => { this.uploadProgress = p; });
          count += 1;
        } catch (e) {
          this.toast(`Upload failed: ${file.name} — ${e.message}`, 'error');
        }
      }
      this.uploadProgress = null;
      if (count > 0) {
        this.toast(`Uploaded ${count} file(s)`, 'success');
        await this.refreshInputFiles();
      }
    },

    downloadArtifact(documentId, artifact) {
      this._download(API.artifactDownloadUrl(this.selectedRunId, documentId, artifact));
    },

    downloadDataset() {
      if (this.selectedRunId) this._download(API.datasetDownloadUrl(this.selectedRunId));
    },

    openHFModal() {
      if (!this.selectedRunId) return;
      if (!this.canPublish) {
        this.toast('Sign in with HuggingFace to publish.', 'error');
        return;
      }
      const defaultRepo = this.auth.user?.name
        ? `${this.auth.user.name}/${this.selectedRun?.name || `opencr-${this.selectedRunId}`}`
        : '';
      this.hfModal = { ...emptyHFModal(), open: true, runId: this.selectedRunId, repoId: defaultRepo };
    },

    closeHFModal() { this.hfModal.open = false; },

    async submitHFPublish() {
      if (!this.hfModal.repoId) return this.toast('Repo id required (e.g. user/dataset)', 'error');
      this.hfModal.submitting = true;
      try {
        this.hfModal.result = await API.publishToHF(this.hfModal.runId, {
          repo_id: this.hfModal.repoId,
          private: this.hfModal.private,
          token: this.hfModal.token || null,
        });
        this.toast('Published to HuggingFace', 'success');
      } catch (e) {
        this.toast(`Publish failed: ${e.message}`, 'error');
      } finally {
        this.hfModal.submitting = false;
      }
    },

    _download(url) {
      const a = document.createElement('a');
      a.href = url; a.target = '_blank'; a.rel = 'noopener';
      document.body.appendChild(a); a.click(); a.remove();
    },

    formatSize(bytes) {
      if (!bytes) return '0 B';
      if (bytes < 1024) return `${bytes} B`;
      if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${(bytes / 1048576).toFixed(1)} MB`;
    },

    formatMetric(value, digits = 1) { return Number(value || 0).toFixed(digits); },

    formatTimestamp(iso) {
      if (!iso) return '—';
      try { return new Date(iso).toLocaleString(); } catch { return iso; }
    },

    toast(message, type = 'info') {
      const id = Math.random().toString(36).slice(2);
      this.toasts.push({ id, message, type });
      setTimeout(() => { this.toasts = this.toasts.filter(t => t.id !== id); }, 4000);
    },
  };
}
