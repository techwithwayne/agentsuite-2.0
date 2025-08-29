"""
CHANGE LOG
----------
2025-08-25 • Debug-first short-circuit + service fallback + engine default.
2025-08-25 • Structured JSON logging: req_id, engines tried, duration, UA/IP.     # CHANGED:
"""

import io
import json   # CHANGED:
import time   # CHANGED:
import uuid   # CHANGED:
import logging
from typing import Optional

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views import View  # CHANGED: for CBV wrapper (compat)
from django.conf import settings  # for THERAPYLIB_PDF_ENGINE
from django.template.loader import render_to_string

# Prefer the project's dedicated logger if configured in settings.LOGGING
logger = logging.getLogger("webdoctor")
if not logger.handlers:
    # Fallback to module logger if "webdoctor" not configured
    logger = logging.getLogger(__name__)  # pragma: no cover

# --- PDF engines (import defensively) ---
try:
    import weasyprint  # type: ignore
except Exception:
    weasyprint = None  # pragma: no cover

try:
    from xhtml2pdf import pisa  # type: ignore
except Exception:
    pisa = None  # pragma: no cover

try:
    import pdfkit  # type: ignore
except Exception:
    pdfkit = None  # pragma: no cover


# --- Optional service fallback (do not assume signature) ---
_render_handout_html = None
try:
    # If your service exposes a helper, we will reuse it.
    from therapylib.services.pdf_service import render_handout_html as _render_handout_html  # type: ignore
except Exception as e:
    logger.info(f"therapylib.services.pdf_service.render_handout_html not available: {e}")


def _try_service_html(slug: str, mode: str, request=None) -> Optional[str]:
    """Attempt to call an existing service function with multiple likely signatures."""
    if not _render_handout_html:
        return None
    attempts = [
        lambda: _render_handout_html(slug, mode, request=request),
        lambda: _render_handout_html(slug, mode),
        lambda: _render_handout_html(slug=slug, mode=mode),
        lambda: _render_handout_html(request, slug, mode),
    ]
    for i, fn in enumerate(attempts, 1):
        try:
            html = fn()
            if isinstance(html, (str, bytes)):
                return html.decode("utf-8") if isinstance(html, bytes) else html
        except TypeError:
            continue
        except Exception as e:
            logger.error(f"render_handout_html attempt {i} raised: {e}")
    return None


def render_pdf_from_html(html: str, engine: str) -> bytes:
    """Attempt to render PDF using the specified engine."""
    if engine == "weasyprint":
        if not weasyprint:
            raise RuntimeError("WeasyPrint not installed")
        return weasyprint.HTML(string=html).write_pdf()
    elif engine == "xhtml2pdf":
        if not pisa:
            raise RuntimeError("xhtml2pdf not installed")
        output = io.BytesIO()
        pisa_status = pisa.CreatePDF(io.BytesIO(html.encode("utf-8")), dest=output)
        if getattr(pisa_status, "err", 0):
            raise RuntimeError("xhtml2pdf rendering failed")
        return output.getvalue()
    elif engine == "pdfkit":
        if not pdfkit:
            raise RuntimeError("pdfkit not installed")
        return pdfkit.from_string(html, False)
    else:
        raise ValueError(f"Unknown PDF engine: {engine}")


def _get_req_id(request) -> str:  # CHANGED:
    """Use incoming X-Request-ID if present; otherwise generate one."""
    rid = request.META.get("HTTP_X_REQUEST_ID")
    return rid if rid else uuid.uuid4().hex


@csrf_exempt
def handout_pdf(request, slug):
    """
    Endpoint: /api/therapylib/handouts/<slug>/pdf/?mode=patient|provider
    Behavior:
      - If ?debug=1 → return minimal HTML immediately (status 200).
      - Else render full HTML (service first, fallback to template).
      - Convert HTML to PDF with preferred engine, fallback on failure.
    """
    t0 = time.monotonic()               # CHANGED:
    req_id = _get_req_id(request)       # CHANGED:
    mode = (request.GET.get("mode") or "patient").lower()

    # Decide the preferred engine (query param overrides settings)
    requested_engine = request.GET.get("engine")
    if requested_engine:
        engine = requested_engine.lower()
    else:
        engine = getattr(settings, "THERAPYLIB_PDF_ENGINE", "xhtml2pdf")

    client_ip = request.META.get("REMOTE_ADDR")              # CHANGED:
    user_agent = request.META.get("HTTP_USER_AGENT", "")     # CHANGED:

    # DEBUG SHORT-CIRCUIT (no template render)
    if request.GET.get("debug"):
        debug_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>TherapyLib Handout Debug</title></head>
<body>
  <h1>TherapyLib Handout Debug</h1>
  <ul>
    <li><strong>slug</strong>: {slug}</li>
    <li><strong>mode</strong>: {mode}</li>
    <li><strong>engine</strong>: {engine}</li>
  </ul>
  <p>This is a debug stub (no template render).</p>
</body></html>"""
        # JSON log
        logger.info(json.dumps({                                               # CHANGED:
            "event": "handout_pdf_debug",
            "req_id": req_id,
            "slug": slug,
            "mode": mode,
            "engine": engine,
            "status": 200,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "ip": client_ip,
            "ua": user_agent[:200],
        }))
        return HttpResponse(debug_html, content_type="text/html")

    # FULL HTML RENDER (service → template fallback)
    html = _try_service_html(slug, mode, request=request)

    if not html:
        template_map = {
            "patient": "therapylib/handouts/patient.html",
            "provider": "therapylib/handouts/practitioner.html",
            "practitioner": "therapylib/handouts/practitioner.html",
        }
        template_name = template_map.get(mode, "therapylib/handouts/patient.html")
        context = {"slug": slug, "mode": mode}
        try:
            html = render_to_string(template_name, context)
        except Exception as e:
            logger.error(json.dumps({                                         # CHANGED:
                "event": "handout_pdf_template_error",
                "req_id": req_id,
                "slug": slug,
                "mode": mode,
                "template": template_name,
                "error": str(e),
            }))
            return JsonResponse(
                {"error": "Template render failed", "template": template_name, "detail": str(e)},
                status=500,
            )

    # PDF RENDER with fallback chain
    tried, errors, pdf_bytes = [], [], None
    engines_to_try = [engine] + [e for e in ["weasyprint", "xhtml2pdf", "pdfkit"] if e != engine]

    for eng in engines_to_try:
        tried.append(eng)
        try:
            pdf_bytes = render_pdf_from_html(html, eng)
            if pdf_bytes:
                logger.info(json.dumps({                                     # CHANGED:
                    "event": "handout_pdf_success",
                    "req_id": req_id,
                    "slug": slug,
                    "mode": mode,
                    "engine_selected": engine,
                    "engine_success": eng,
                    "engines_tried": tried,
                    "status": 200,
                    "bytes": len(pdf_bytes),
                    "duration_ms": int((time.monotonic() - t0) * 1000),
                    "ip": client_ip,
                    "ua": user_agent[:200],
                }))
                break
        except Exception as e:
            msg = f"{eng}: {e}"
            errors.append(msg)
            logger.error(json.dumps({                                        # CHANGED:
                "event": "handout_pdf_engine_error",
                "req_id": req_id,
                "slug": slug,
                "mode": mode,
                "engine": eng,
                "error": str(e),
            }))

    if not pdf_bytes:
        logger.error(json.dumps({                                            # CHANGED:
            "event": "handout_pdf_all_failed",
            "req_id": req_id,
            "slug": slug,
            "mode": mode,
            "engine_selected": engine,
            "engines_tried": tried,
            "errors": errors,
            "status": 500,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "ip": client_ip,
            "ua": user_agent[:200],
        }))
        return JsonResponse({"error": "All PDF engines failed", "tried": tried, "errors": errors}, status=500)

    # Success
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{slug}-{mode}.pdf"'
    resp["Cache-Control"] = "public, max-age=86400"
    return resp


# ---- Compatibility CBV wrapper for URLConfs expecting HandoutPDFView ---------
class HandoutPDFView(View):  # CHANGED:
    """Thin CBV wrapper so urls.py can keep using HandoutPDFView.as_view()."""  # CHANGED:
    def get(self, request, slug):                                              # CHANGED:
        return handout_pdf(request, slug)                                      # CHANGED:
