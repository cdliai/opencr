/**
 * OpenCR Alpine.js application component.
 */
function opencrApp() {
  return {
    // --- State ---
    tab: 'upload',
    version: '',
    healthStatus: 'checking...',
    healthClass: '',
    inputDir: '',

    // Upload
    dragOver: false,
    uploadProgress: null,
    inputFiles: [],
    selectedFiles: [],

    // Extraction
    extracting: false,
    activeJobId: null,
    jobStatus: '',
    progressPercent: 0,
    docsCompleted: 0,
    docsTotal: 0,
    currentDoc: '',
    currentPage: null,
    currentTotalPages: null,
    events: [],

    // Results
    outputFiles: [],
    viewingStem: null,
    viewingContent: '',
    viewingMeta: null,
    showMeta: false,

    // Toasts
    toasts: [],

    // Internal
    _sse: new SSEManager(),
    _healthInterval: null,

    // --- Lifecycle ---
    async init() {
      await this.checkHealth();
      this._healthInterval = setInterval(() => this.checkHealth(), 15000);
      await this.refreshInputFiles();
      await this.refreshOutputFiles();
    },

    // --- Health ---
    async checkHealth() {
      try {
        const data = await API.health();
        this.version = data.pipeline_version || '';
        this.inputDir = data.input_dir || '';
        this.healthStatus = data.status;
        this.healthClass = data.status === 'ready' ? 'ready' : 'waiting';
      } catch {
        this.healthStatus = 'offline';
        this.healthClass = 'error';
      }
    },

    // --- File listing ---
    async refreshInputFiles() {
      try {
        this.inputFiles = await API.listInputFiles();
      } catch (e) {
        this.toast('Failed to load input files', 'error');
      }
    },

    async refreshOutputFiles() {
      try {
        this.outputFiles = await API.listOutputFiles();
      } catch (e) {
        this.toast('Failed to load output files', 'error');
      }
    },

    // --- Upload ---
    async handleDrop(event) {
      this.dragOver = false;
      const files = Array.from(event.dataTransfer.files).filter(
        f => f.name.toLowerCase().endsWith('.pdf')
      );
      if (files.length === 0) {
        this.toast('Only PDF files are accepted', 'error');
        return;
      }
      await this.uploadFiles(files);
    },

    async handleFileSelect(event) {
      const files = Array.from(event.target.files);
      if (files.length > 0) await this.uploadFiles(files);
      event.target.value = '';
    },

    async uploadFiles(files) {
      let success = 0;
      for (const file of files) {
        try {
          this.uploadProgress = 0;
          await API.upload(file, (pct) => { this.uploadProgress = pct; });
          success++;
        } catch (e) {
          this.toast(`Upload failed: ${file.name} - ${e.message}`, 'error');
        }
      }
      this.uploadProgress = null;
      if (success > 0) {
        this.toast(`Uploaded ${success} file(s)`, 'success');
        await this.refreshInputFiles();
      }
    },

    // --- Selection ---
    get allSelected() {
      return this.inputFiles.length > 0 &&
        this.selectedFiles.length === this.inputFiles.length;
    },

    toggleSelectAll(event) {
      if (event.target.checked) {
        this.selectedFiles = this.inputFiles.map(f => f.path);
      } else {
        this.selectedFiles = [];
      }
    },

    // --- Extraction ---
    async startExtraction() {
      if (this.selectedFiles.length === 0 || this.extracting) return;
      this.extracting = true;
      this.events = [];

      try {
        const data = await API.createJob(this.selectedFiles);
        this.activeJobId = data.job_id;
        this.jobStatus = 'processing';
        this.progressPercent = 0;
        this.docsCompleted = 0;
        this.docsTotal = this.selectedFiles.length;
        this.currentDoc = '';
        this.currentPage = null;
        this.currentTotalPages = null;

        this.tab = 'progress';
        this.connectSSE(data.job_id);
        this.toast(`Job ${data.job_id} started`, 'info');
      } catch (e) {
        this.toast(`Failed to start extraction: ${e.message}`, 'error');
      } finally {
        this.extracting = false;
      }
    },

    connectSSE(jobId) {
      this._sse.connect(
        jobId,
        (event) => this.handleSSEEvent(event),
        () => {} // auto-reconnects
      );
    },

    handleSSEEvent(event) {
      const time = new Date().toLocaleTimeString();
      let detail = '';

      switch (event.type) {
        case 'page_start':
          this.currentDoc = event.document || '';
          this.currentPage = event.page;
          this.currentTotalPages = event.total_pages;
          detail = `${event.document} p${event.page}/${event.total_pages}`;
          break;

        case 'page_complete':
          detail = `${event.document || ''} p${event.page || ''} - ${event.verdict || ''}`;
          if (event.processing_time_ms) {
            detail += ` (${Math.round(event.processing_time_ms)}ms)`;
          }
          break;

        case 'page_retry':
          detail = `${event.document || ''} p${event.page || ''} retry #${event.attempt || ''}`;
          break;

        case 'document_complete':
          this.docsCompleted++;
          this.progressPercent = Math.round((this.docsCompleted / this.docsTotal) * 100);
          detail = `${event.document || event.filename || ''} done`;
          break;

        case 'document_error':
          detail = `${event.document || ''}: ${event.error || 'unknown error'}`;
          break;

        case 'job_complete':
          this.jobStatus = 'completed';
          this.progressPercent = 100;
          this.currentDoc = '';
          this.currentPage = null;
          const s = event.summary || {};
          detail = `${event.total_documents} docs, ${event.total_pages} pages (pass:${s.pass} warn:${s.warn} fail:${s.fail})`;
          this.toast('Extraction complete!', 'success');
          this.refreshOutputFiles();
          break;

        default:
          detail = JSON.stringify(event);
      }

      this.events.push({ type: event.type, time, detail });

      // Auto-scroll log
      this.$nextTick(() => {
        const el = this.$refs.logEntries;
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

    // --- Results ---
    async viewResult(stem) {
      this.viewingStem = stem;
      this.showMeta = false;
      this.viewingContent = 'Loading...';
      this.viewingMeta = null;

      try {
        const [content, meta] = await Promise.all([
          API.getOutputMd(stem),
          API.getOutputMeta(stem),
        ]);
        this.viewingContent = content;
        this.viewingMeta = meta;
      } catch (e) {
        this.viewingContent = 'Error loading file: ' + e.message;
      }
    },

    downloadResult(stem) {
      window.open(API.downloadUrl(stem), '_blank');
    },

    // --- Helpers ---
    formatSize(bytes) {
      if (bytes < 1024) return bytes + ' B';
      if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
      return (bytes / 1048576).toFixed(1) + ' MB';
    },

    toast(message, type = 'info') {
      this.toasts.push({ message, type });
    },
  };
}
