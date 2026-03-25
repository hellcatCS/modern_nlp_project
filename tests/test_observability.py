import logging
import os
from unittest.mock import MagicMock, patch

from src import observability as obs


def test_log_record_to_elasticsearch_document_basic():
    logger = logging.getLogger("test.logger")
    record = logger.makeRecord(
        name="test.logger",
        level=logging.INFO,
        fn="x.py",
        lno=10,
        msg="Привет, лог",
        args=(),
        exc_info=None,
    )
    record.pathname = "/app/src/main.py"
    record.filename = "main.py"
    record.process = 1
    record.thread = 2
    record.threadName = "MainThread"

    doc = obs.log_record_to_elasticsearch_document(record)
    assert doc["message"] == "Привет, лог"
    assert doc["log"]["level"] == "INFO"
    assert doc["log"]["logger"] == "test.logger"
    assert "@timestamp" in doc
    assert "T" in doc["@timestamp"]


def test_log_record_to_elasticsearch_document_with_exc():
    logger = logging.getLogger("err")
    try:
        raise ValueError("boom")
    except ValueError:
        record = logger.makeRecord(
            name="err",
            level=logging.ERROR,
            fn="x.py",
            lno=1,
            msg="failed",
            args=(),
            exc_info=True,
        )
    record.pathname = "x.py"
    record.filename = "x.py"

    doc = obs.log_record_to_elasticsearch_document(record)
    assert doc["log"]["level"] == "ERROR"
    assert "error" in doc


def test_elasticsearch_handler_emit_calls_index():
    mock_es_class = MagicMock()
    mock_client = MagicMock()
    mock_es_class.return_value = mock_client

    with patch.dict(os.environ, {"OPENAI_API_KEY": "k"}, clear=False):
        with patch("elasticsearch.Elasticsearch", mock_es_class):
            h = obs.ElasticsearchLogHandler("http://localhost:9200", "test-logs")
            record = logging.getLogger("t").makeRecord(
                "t",
                logging.WARNING,
                "f.py",
                3,
                "warn body",
                (),
                None,
            )
            record.pathname = "f.py"
            record.filename = "f.py"
            h.emit(record)

    mock_client.index.assert_called_once()
    call_kw = mock_client.index.call_args.kwargs
    assert "index" in call_kw
    assert call_kw["index"].startswith("test-logs-")
    assert call_kw["document"]["message"] == "warn body"


def test_record_llm_round_updates_metrics_when_registered():
    from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest

    reg = CollectorRegistry()
    c_rounds = Counter("llm_rounds_total", "test", registry=reg)
    c_tools = Counter("llm_tool_calls_total", "test", ["tool_name"], registry=reg)
    c_esc = Counter("llm_escalations_total", "test", registry=reg)
    h = Histogram("llm_round_duration_seconds", "test", registry=reg)

    obs.llm_rounds_total = c_rounds
    obs.llm_tool_calls_total = c_tools
    obs.llm_escalations_total = c_esc
    obs.llm_round_duration_seconds = h

    try:
        obs.record_llm_round(0.12, ["retrieve_knowledge", "check_availability"], True)
        out = generate_latest(reg).decode()
        assert "llm_rounds_total 1.0" in out
        assert 'llm_tool_calls_total{tool_name="retrieve_knowledge"} 1.0' in out
        assert 'llm_tool_calls_total{tool_name="check_availability"} 1.0' in out
        assert "llm_escalations_total 1.0" in out
    finally:
        obs.llm_rounds_total = None
        obs.llm_tool_calls_total = None
        obs.llm_escalations_total = None
        obs.llm_round_duration_seconds = None
