"""titiler app, based on titiler.application.main"""

import json
import logging
import time
from dataclasses import dataclass
from logging import config as log_config

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from rio_tiler.io import Reader
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette_cramjam.middleware import CompressionMiddleware
from titiler.application import __version__ as titiler_version
from titiler.application.settings import ApiSettings
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import (
    TilerFactory,
)
from titiler.core.middleware import (
    CacheControlMiddleware,
    LoggerMiddleware,
)
from titiler.core.utils import update_openapi
from titiler.extensions import (
    cogValidateExtension,
    cogViewerExtension,
    stacExtension,
)


@dataclass
class MetricsMiddleware:
    """Middleware for collecting tile request metrics."""

    app: ASGIApp

    def __post_init__(self):
        self.meter = metrics.get_meter("titiler.metrics")

        self.tile_requests = self.meter.create_counter(
            name="titiler_tile_requests_total",
            description="Total number of tile requests",
            unit="1",
        )

        self.requests_total = self.meter.create_counter(
            name="titiler_requests_total", description="Total HTTP requests", unit="1"
        )

        self.request_duration = self.meter.create_histogram(
            name="titiler_request_duration_seconds",
            description="Request duration in seconds",
            unit="s",
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """Handle request metrics collection."""
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request = Request(scope, receive=receive)
        start_time = time.perf_counter()

        method = request.method

        response_size = 0
        status_code = 200

        # Wrap send to capture response info
        async def send_wrapper(message):
            nonlocal response_size, status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            elif message["type"] == "http.response.body":
                if body := message.get("body"):
                    response_size += len(body)
            await send(message)

        exception = None
        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as e:
            exception = e
            status_code = 500

        duration = time.perf_counter() - start_time

        route = scope.get("route")
        endpoint = route.path if route else None
        base_labels = {
            "method": method,
            "endpoint": endpoint,
            "status_code": str(status_code),
        }

        # Record metrics
        self.requests_total.add(1, base_labels)
        self.request_duration.record(duration, base_labels)

        # Handle tile-specific metrics
        if endpoint is not None and "tile" in endpoint:
            tile_labels = {
                **base_labels,
                "zoom_level": request.path_params.get("z"),
            }
            self.tile_requests.add(1, tile_labels)

        if exception:
            raise exception


logging.getLogger("botocore.credentials").disabled = True
logging.getLogger("botocore.utils").disabled = True
logging.getLogger("rasterio.session").setLevel(logging.ERROR)
logging.getLogger("rio-tiler").setLevel(logging.ERROR)


api_settings = ApiSettings()

app_dependencies = []

###############################################################################

app = FastAPI(
    title=api_settings.name,
    openapi_url="/api",
    docs_url="/api.html",
    description="""A demo application that uses OpenTelemetry to power observability in Grafana

---

**Source Code**: <a href="https://github.com/developmentseed/titiler-observability" target="_blank">https://github.com/developmentseed/titiler-observability</a>

---
    """,
    version=titiler_version,
    root_path=api_settings.root_path,
    dependencies=app_dependencies,
)

# Fix OpenAPI response header for OGC Common compatibility
update_openapi(app)


###############################################################################
# Simple Dataset endpoints (e.g Cloud Optimized GeoTIFF)
cog = TilerFactory(
    reader=Reader,
    router_prefix="/cog",
    extensions=[
        cogValidateExtension(),
        cogViewerExtension(),
        stacExtension(),
    ],
    enable_telemetry=True,
)

app.include_router(
    cog.router,
    prefix="/cog",
    tags=["Cloud Optimized GeoTIFF"],
)


add_exception_handlers(app, DEFAULT_STATUS_CODES)

# Set all CORS enabled origins
if api_settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=api_settings.cors_origins,
        allow_credentials=True,
        allow_methods=api_settings.cors_allow_methods,
        allow_headers=["*"],
    )

app.add_middleware(
    CompressionMiddleware,
    minimum_size=0,
    exclude_mediatype={
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/jp2",
        "image/webp",
    },
    compression_level=6,
)

app.add_middleware(
    CacheControlMiddleware,
    cachecontrol=api_settings.cachecontrol,
    exclude_path={r"/healthz"},
)

app.add_middleware(MetricsMiddleware)
app.add_middleware(LoggerMiddleware)

### OTEL Configuration ###

# Resource configuration
resource = Resource.create(
    {
        SERVICE_NAME: "titiler",
        SERVICE_VERSION: titiler_version,
    }
)

# Trace provider setup
provider = TracerProvider(resource=resource)
processor = BatchSpanProcessor(OTLPSpanExporter())
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

# Logger provider setup
logger_provider = LoggerProvider(resource=resource)
log_exporter = OTLPLogExporter()
logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

# Create OTLP handler
otlp_handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)

# Configure logging with OTLP handler
log_config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s - %(levelname)s - %(name)s - trace_id=%(otelTraceID)s span_id=%(otelSpanID)s - %(message)s"
            },
            "request": {
                "format": (
                    "%(asctime)s - %(levelname)s - %(name)s - trace_id=%(otelTraceID)s span_id=%(otelSpanID)s - %(message)s "
                    + json.dumps(
                        {
                            k: f"%({k})s"
                            for k in [
                                "http.method",
                                "http.referer",
                                "http.request.header.origin",
                                "http.target",
                                "http.request.header.content-length",
                                "http.request.header.accept-encoding",
                                "http.request.header.origin",
                                "titiler.path_params",
                                "titiler.query_params",
                            ]
                        }
                    )
                ),
            },
        },
        "handlers": {
            "console_detailed": {
                "class": "logging.StreamHandler",
                "level": "WARNING",
                "formatter": "detailed",
                "stream": "ext://sys.stdout",
            },
            "console_request": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "request",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "titiler": {
                "level": "INFO",
                "handlers": ["console_detailed"],
                "propagate": True,
            },
            "titiler.requests": {
                "level": "INFO",
                "handlers": ["console_request"],
                "propagate": True,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": [],
        },
    }
)


# Add OTLP handler to root logger so all logs propagate to it
root_logger = logging.getLogger()
root_logger.addHandler(otlp_handler)

# Instrument logging and FastAPI
LoggingInstrumentor().instrument(
    set_logging_format=True, enable_tracing=True, log_level=logging.INFO
)
FastAPIInstrumentor.instrument_app(app)

# Metrics provider setup
metric_exporter = OTLPMetricExporter(
    endpoint="http://otel-collector:4317",  # Same endpoint as your traces
    insecure=True,
)

metric_reader = PeriodicExportingMetricReader(
    exporter=metric_exporter,
    export_interval_millis=5000,  # Export every 5 seconds
    export_timeout_millis=3000,  # Timeout after 3 seconds
)

metrics_provider = MeterProvider(
    resource=resource,  # Same resource as your traces
    metric_readers=[metric_reader],
)

# Set the global metrics provider
metrics.set_meter_provider(metrics_provider)
