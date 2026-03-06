/**
 * SSE connection manager for job progress streaming.
 */
class SSEManager {
  constructor() {
    this.source = null;
    this.jobId = null;
  }

  /**
   * Connect to a job's SSE stream.
   * @param {string} jobId
   * @param {function} onEvent - Called with parsed event data
   * @param {function} onError - Called on connection error
   */
  connect(jobId, onEvent, onError) {
    this.disconnect();
    this.jobId = jobId;

    this.source = new EventSource(`/api/jobs/${jobId}/stream`);

    this.source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        onEvent(data);
        if (data.type === 'job_complete') {
          this.disconnect();
        }
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    this.source.onerror = () => {
      if (onError) onError();
      // EventSource auto-reconnects, but if job is done we close
      if (this.source && this.source.readyState === EventSource.CLOSED) {
        this.disconnect();
      }
    };
  }

  disconnect() {
    if (this.source) {
      this.source.close();
      this.source = null;
    }
    this.jobId = null;
  }
}
