"""Exercise the real SDK and OTLP exporter against local HTTP endpoints."""

import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


class Handler(BaseHTTPRequestHandler):
    requests = []

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        self.requests.append((self.path, dict(self.headers), body))
        if self.path == "/v1/messages":
            request_number = sum(path == "/v1/messages" for path, _, _ in self.requests)
            response = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "model": "claude-haiku-5-5",
                "content": [{"type": "text", "text": f"response {request_number}"}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 5, "output_tokens": 2},
            }
            payload = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        elif self.path == "/v1/traces":
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(404)

    def log_message(self, *args):
        pass


class LocalExportTest(unittest.TestCase):
    def test_multiple_chat_turns_reach_otlp_endpoint(self):
        Handler.requests = []
        api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        otlp = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (api, otlp)]
        for thread in threads:
            thread.start()
        try:
            env = os.environ.copy()
            env.update({
                "ANTHROPIC_API_KEY": "test-anthropic-key",
                "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{api.server_port}",
                "OTEL_EXPORTER_OTLP_ENDPOINT": f"http://127.0.0.1:{otlp.server_port}",
                "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=ApiKey test-elastic-key",
            })
            result = subprocess.run(
                [sys.executable, "-m", "claude_tracing"],
                input="first prompt\nsecond prompt\n/exit\n",
                env=env, text=True, capture_output=True, timeout=20,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Claude: response 1", result.stdout)
            self.assertIn("Claude: response 2", result.stdout)
            self.assertEqual(result.stderr.count("Trace ID:"), 2)

            sdk_requests = [item for item in Handler.requests if item[0] == "/v1/messages"]
            exports = [item for item in Handler.requests if item[0] == "/v1/traces"]
            self.assertEqual(len(sdk_requests), 2)
            self.assertEqual(len(exports), 2)
            first_messages = json.loads(sdk_requests[0][2])["messages"]
            second_messages = json.loads(sdk_requests[1][2])["messages"]
            self.assertEqual(len(first_messages), 1)
            self.assertEqual([item["role"] for item in second_messages], ["user", "assistant", "user"])
            self.assertEqual(second_messages[0]["content"], "first prompt")
            self.assertEqual(second_messages[1]["content"][0]["text"], "response 1")
            self.assertEqual(second_messages[2]["content"], "second prompt")

            conversation_ids = []
            for index, export in enumerate(exports, start=1):
                headers = {name.lower(): value for name, value in export[1].items()}
                self.assertEqual(headers["authorization"], "ApiKey test-elastic-key")
                payload = ExportTraceServiceRequest.FromString(export[2])
                spans = [span for resource in payload.resource_spans for scope in resource.scope_spans for span in scope.spans]
                parent = next(span for span in spans if span.name == "claude-chat-turn")
                child = next(span for span in spans if span.name == "anthropic.messages.create")
                self.assertEqual(child.parent_span_id, parent.span_id)
                self.assertEqual(child.trace_id, parent.trace_id)
                sdk_span = child.SerializeToString()
                self.assertIn(f"response {index}".encode(), sdk_span)
                self.assertIn(f"{['first', 'second'][index - 1]} prompt".encode(), sdk_span)
                attributes = {item.key: item.value.string_value for item in child.attributes}
                conversation_ids.append(attributes["gen_ai.conversation.id"])
            self.assertEqual(conversation_ids[0], conversation_ids[1])
        finally:
            for server in (api, otlp):
                server.shutdown()
                server.server_close()
            for thread in threads:
                thread.join()


if __name__ == "__main__":
    unittest.main()
