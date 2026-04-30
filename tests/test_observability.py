from ocr_pipeline.services.observability import Observability


def test_observability_tracks_pace_failures_and_renders_prometheus():
    metrics = Observability()

    metrics.job_created()
    metrics.page_retry()
    metrics.page_completed(processing_time_ms=500.0, token_count=250, validation_status="warn")
    metrics.page_completed(processing_time_ms=250.0, token_count=150, validation_status="fail")
    metrics.document_completed()
    metrics.job_completed()

    snapshot = metrics.snapshot()
    assert snapshot.jobs_created_total == 1
    assert snapshot.jobs_completed_total == 1
    assert snapshot.page_retries_total == 1
    assert snapshot.pages_warn_total == 1
    assert snapshot.pages_fail_total == 1
    assert round(snapshot.average_tokens_per_second, 2) == round(400 / 0.75, 2)

    rendered = metrics.render_prometheus()
    assert "opencr_jobs_created_total 1" in rendered
    assert "opencr_pages_fail_total 1" in rendered
