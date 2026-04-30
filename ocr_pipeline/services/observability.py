from dataclasses import dataclass, asdict
from threading import Lock


@dataclass
class MetricsSnapshot:
    jobs_created_total: int = 0
    jobs_completed_total: int = 0
    jobs_failed_total: int = 0
    active_jobs: int = 0
    documents_processed_total: int = 0
    pages_processed_total: int = 0
    page_retries_total: int = 0
    pages_warn_total: int = 0
    pages_fail_total: int = 0
    pages_empty_total: int = 0
    tokens_total: int = 0
    processing_seconds_total: float = 0.0

    @property
    def average_tokens_per_second(self) -> float:
        if self.processing_seconds_total <= 0:
            return 0.0
        return self.tokens_total / self.processing_seconds_total

    @property
    def average_page_latency_ms(self) -> float:
        if self.pages_processed_total <= 0:
            return 0.0
        return (self.processing_seconds_total / self.pages_processed_total) * 1000


class Observability:
    def __init__(self):
        self._lock = Lock()
        self._snapshot = MetricsSnapshot()

    def job_created(self):
        with self._lock:
            self._snapshot.jobs_created_total += 1
            self._snapshot.active_jobs += 1

    def job_completed(self):
        with self._lock:
            self._snapshot.jobs_completed_total += 1
            self._snapshot.active_jobs = max(0, self._snapshot.active_jobs - 1)

    def job_failed(self):
        with self._lock:
            self._snapshot.jobs_failed_total += 1
            self._snapshot.active_jobs = max(0, self._snapshot.active_jobs - 1)

    def document_completed(self):
        with self._lock:
            self._snapshot.documents_processed_total += 1

    def page_retry(self):
        with self._lock:
            self._snapshot.page_retries_total += 1

    def page_completed(self, *, processing_time_ms: float, token_count: int, validation_status: str):
        with self._lock:
            self._snapshot.pages_processed_total += 1
            self._snapshot.tokens_total += token_count
            self._snapshot.processing_seconds_total += processing_time_ms / 1000

            if validation_status == "warn":
                self._snapshot.pages_warn_total += 1
            elif validation_status == "fail":
                self._snapshot.pages_fail_total += 1
            elif validation_status == "empty":
                self._snapshot.pages_empty_total += 1

    def snapshot(self) -> MetricsSnapshot:
        with self._lock:
            return MetricsSnapshot(**asdict(self._snapshot))

    def render_prometheus(self) -> str:
        snapshot = self.snapshot()
        metrics = {
            "opencr_jobs_created_total": snapshot.jobs_created_total,
            "opencr_jobs_completed_total": snapshot.jobs_completed_total,
            "opencr_jobs_failed_total": snapshot.jobs_failed_total,
            "opencr_active_jobs": snapshot.active_jobs,
            "opencr_documents_processed_total": snapshot.documents_processed_total,
            "opencr_pages_processed_total": snapshot.pages_processed_total,
            "opencr_page_retries_total": snapshot.page_retries_total,
            "opencr_pages_warn_total": snapshot.pages_warn_total,
            "opencr_pages_fail_total": snapshot.pages_fail_total,
            "opencr_pages_empty_total": snapshot.pages_empty_total,
            "opencr_tokens_total": snapshot.tokens_total,
            "opencr_processing_seconds_total": round(snapshot.processing_seconds_total, 6),
            "opencr_average_tokens_per_second": round(snapshot.average_tokens_per_second, 3),
            "opencr_average_page_latency_ms": round(snapshot.average_page_latency_ms, 3),
        }
        return "\n".join(f"{name} {value}" for name, value in metrics.items()) + "\n"


observability = Observability()
