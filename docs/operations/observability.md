# Observability

Every workflow has a `trace_id`. `Tracer.span(name, trace_id, **attrs)` records
spans (charter §23.1 names) with secret redaction; `JSONLExporter` writes them to
disk. `Metrics` tracks runs/attempts/tokens/cost/verification-failures. Optional
OTel/Braintrust/LangSmith/Phoenix exporters plug in behind the same surface.
