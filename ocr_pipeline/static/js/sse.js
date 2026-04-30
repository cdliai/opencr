/**
 * Run-event stream manager. Replays missed events on reconnect via after_event_id.
 */
class RunStream {
  constructor() {
    this.source = null;
    this.runId = null;
    this.lastEventId = 0;
  }

  connect(runId, onEvent, onError) {
    this.disconnect();
    this.runId = runId;
    this.lastEventId = 0;

    const url = `/api/runs/${encodeURIComponent(runId)}/stream?after_event_id=${this.lastEventId}`;
    this.source = new EventSource(url);

    this.source.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.event_id) this.lastEventId = data.event_id;
        onEvent(data);
        if (data.type === 'run_complete' || data.type === 'run_failed') {
          this.disconnect();
        }
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    this.source.onerror = () => {
      if (onError) onError();
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
    this.runId = null;
  }

  isConnected() {
    return this.source !== null;
  }
}
