# TiTiler OpenTelemetry Observability Stack

A complete observability stack for TiTiler applications using OpenTelemetry, demonstrating distributed tracing, metrics collection, and structured logging with Grafana visualization.
The goal is to demonstrate how OpenTelemetry can be used to provide correlated traces and logs and how those can be pulled into an observability platform like Grafana.

## Architecture

The stack consists of six containerized services orchestrated on a single Docker bridge network (`observability-net`):

### Core Services

**titiler** (`main.py:139`)

- FastAPI application with OpenTelemetry instrumentation
- Exports traces, metrics, and logs to OpenTelemetry Collector via OTLP/gRPC
- Custom metrics middleware tracks tile requests, HTTP requests, and response times
- Configured with GDAL optimizations for raster processing
- Exposed on port 8000

**otel-collector** (`otel-collector-config.yml`)

- OpenTelemetry Collector with contrib distribution
- Receives telemetry data via OTLP protocol (ports 4317/4318)
- Processes and routes data to appropriate backends:
  - Traces ’ Jaeger
  - Metrics ’ Prometheus
  - Logs ’ Loki
- Applies resource attributes and batching for performance

### Observability Backends

**prometheus** (`prometheus.yml`)

- Time-series database for metrics storage
- Receives metrics from OpenTelemetry Collector via remote write API
- Exposed on port 9090

**jaeger** (`jaeger:latest`)

- Distributed tracing backend with OpenTelemetry Logging Protocol (OTLP) ingestion enabled
- Receives traces from OpenTelemetry Collector
- Web UI exposed on port 16686

**loki** (`loki-config.yaml`)

- Log aggregation system for structured log storage
- Receives logs from OpenTelemetry Collector via push API
- Exposed on port 3100

**grafana** (`grafana-*.yml`)

- Visualization platform with pre-configured datasources
- Unified dashboard for metrics, traces, and logs correlation
- Default credentials: admin/admin
- Exposed on port 3000

## Network Flow

1. TiTiler application generates telemetry data during request processing
2. OpenTelemetry SDKs export data to Collector via OTLP
3. Collector processes and forwards data to appropriate backends
4. Grafana queries all backends for unified observability dashboard

## Key Features

- **Distributed Tracing**: Full request flow visibility with OpenTelemetry spans
- **Custom Metrics**: Tile-specific metrics including zoom levels and response times
- **Structured Logging**: JSON-formatted logs with trace correlation
- **Zero-configuration**: Pre-provisioned Grafana datasources and dashboards
- **Hot Reload**: Development mode with file watching for rapid iteration

## Usage

```bash
docker compose up
```

Access services:

- TiTiler API: <http://localhost:8000>
- Grafana: <http://localhost:3000>
- Prometheus: <http://localhost:9090>
- Jaeger: <http://localhost:16686>

