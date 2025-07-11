# Service Tracing Decision & Design Document

## Overview

This document outlines the decision framework and design considerations for implementing service tracing in applications like TiTiler, comparing deployment environments and establishing benchmarks for telemetry implementation.

## Advantages Over Basic Logging

### Traditional Setup (e.g. Lambda + CloudWatch)

**Limitations:**

- No request correlation across services
- Manual log parsing and filtering
- Limited performance insights
- Reactive debugging only

### OpenTelemetry Approach

**Benefits:**

- Automatic trace correlation with `trace_id`
- Request flow visualization across distributed services
- Proactive performance monitoring with service-level indicators (SLIs)
- Structured metrics for capacity planning
- Root cause analysis through span relationships

## Key Telemetry Points

### Essential Metrics

- **Request rate, error rate, duration (RED metrics)**
- **Resource utilization (CPU, memory, I/O)**
- **Usage metrics (tiles served, requests per data source, cache hits)**

### Critical Trace Points

- **HTTP request boundaries**
- **Database queries and external API calls**
- **Async operations and queue processing**
- **Error conditions and retry logic**

### Recommended Sampling

- **Production:** 10-25% sampling rate
- **Development:** 100% sampling
- **Error traces:** Always sample (100%)

## Unintrusive Tracing Infrastructure

### Standard Logging with Trace Correlation

**Philosophy:** Minimize code changes while maximizing observability value through automatic trace correlation.

**Approach:**

- Use existing `logging` statements without modification
- OpenTelemetry automatically injects `trace_id` and `span_id` into log records
- Correlate logs with traces using shared identifiers
- Preserve existing log formatting and practices

**Example Implementation:**

```python
# Standard logging (no changes needed)
logger.info("Processing tile request", extra={"zoom": z, "x": x, "y": y})

# OpenTelemetry automatically adds:
# - trace_id: correlates with distributed trace
# - span_id: links to specific operation
# - resource attributes: service.name, service.version
```

**Benefits:**

- No learning curve for developers
- Existing log statements gain trace context
- Gradual adoption without code rewrites
- Backward compatibility with non-instrumented services

### Automatic Instrumentation Priority

**Zero-Code Instrumentation:**

OpenTelemetry provides automatic instrumentation libraries that add tracing without code modifications by patching common frameworks and libraries at runtime.

- FastAPI/Flask/Django automatic request tracing
- Database query instrumentation (SQLAlchemy, psycopg2)
- HTTP client libraries (requests, httpx, aiohttp)
- Redis/Memcached cache operations

**Manual Instrumentation Only When Needed:**

- Business logic spans for critical operations
- Custom metrics for domain-specific KPIs
- Error context for debugging complex workflows

## Deployment Environment Considerations

### AWS Lambda

**Characteristics:**

- Cold start overhead: ~50-100ms additional latency for OTLP exporters
- Memory impact: +20-30MB for OpenTelemetry SDKs
- Use AWS X-Ray SDK instead of OTLP for native integration
- Async exporters essential to avoid timeout issues
- CloudWatch Logs automatic, but limited correlation

**Recommendation:** Use AWS X-Ray for Lambda deployments to minimize cold start impact and leverage native AWS integration.

### Kubernetes/Container Platforms

**Characteristics:**

- Sidecar collector pattern reduces application overhead
- Service mesh (Istio) provides automatic trace propagation
- Persistent connections to collectors reduce export latency
- Resource allocation: Reserve 0.1 CPU, 128MB for telemetry
- Better suited for complex distributed applications

**Recommendation:** Full OpenTelemetry stack with collector pattern for containerized environments.

## Performance Impact Benchmarks

### Instrumentation Overhead

- **HTTP request latency:** +2-5ms per request
- **Memory usage:** +15-25MB baseline
- **CPU overhead:** ~1-3% under normal load
- **Batch size optimization:** 100-500 spans reduces network calls

### Network Impact

- **OTLP/gRPC:** ~1KB per span, 200-500 bytes per metric
- **Sampling strategies:** 10-50% for high-volume services
- **Async export:** Prevents blocking application threads

## Decision Matrix

| Factor | AWS Lambda | Kubernetes | Container Platform |
|--------|------------|------------|-------------------|
| Cold Start Impact | High | Low | Low |
| Memory Overhead | Critical | Manageable | Manageable |
| Trace Correlation | Limited | Excellent | Excellent |
| Implementation Complexity | Low | Medium | Medium |
| Operational Overhead | Low | High | Medium |

## Implementation Recommendations

1. **Start with sampling:** Begin with 10% sampling in production
2. **Prioritize errors:** Always trace error conditions
3. **Monitor overhead:** Track instrumentation performance impact
4. **Batch exports:** Use batch processors to reduce network calls
5. **Resource allocation:** Reserve compute resources for telemetry
6. **Preserve existing logging:** Use standard logging statements with automatic trace correlation
