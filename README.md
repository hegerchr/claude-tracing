# Claude SDK tracing to Elastic

A small interactive Python chat that sends Claude SDK OpenTelemetry spans to the Elastic Cloud Managed OTLP Endpoint. Each turn has its own trace, and SDK spans share a conversation ID. Prompt and response content is included in the spans.

## Setup

Requires Python 3.10+ and an Anthropic API key. In Elastic Cloud, copy the **Managed OTLP endpoint** from your deployment or project's OpenTelemetry settings and create an encoded API key with the `apm` application `event:write` privilege (the Add data flow can create one).

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

export ANTHROPIC_API_KEY='your-anthropic-api-key'
export OTEL_EXPORTER_OTLP_ENDPOINT='https://your-managed-otlp-endpoint'
export OTEL_EXPORTER_OTLP_HEADERS='Authorization=ApiKey your-encoded-elastic-api-key'

claude-tracing
```

Enter a message at the `You:` prompt, then continue chatting. Type `/exit` or `/quit`, or press Ctrl+D, to stop. You can pass an optional first message: `claude-tracing 'Hello'`. Conversation history stays in memory until you exit and is sent with each new request.

The OTLP URL is the **base** endpoint; the Python HTTP exporter appends `/v1/traces`. The API key header must contain the space after `ApiKey`. Keep these values out of source control and shell history where possible. Prompt and response content is sent to Elastic as trace data, so use test content you are comfortable storing there. The app prints a trace ID after each turn; search for it under the `claude-tracing-test` service in Elastic Observability. Exporter failures are reported by OpenTelemetry on stderr.

For a local check of span generation, set only `ANTHROPIC_API_KEY` and run `claude-tracing --console`. This still calls Claude, but prints spans instead of sending them to Elastic. Use `--model` to choose another Claude model. The default is `claude-haiku-5-5`.

## References

- [Anthropic: Set up OpenTelemetry with the Claude SDK](https://platform.claude.com/docs/en/manage-claude/opentelemetry/sdk)
- [Elastic: Send OTLP data to the Managed OTLP Endpoint](https://www.elastic.co/docs/solutions/observability/get-started/quickstart-elastic-cloud-otel-endpoint)
- [OpenTelemetry: Python OTLP exporters](https://opentelemetry.io/docs/languages/python/exporters/)
