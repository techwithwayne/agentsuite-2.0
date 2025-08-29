"""
therapylib.services.pdf_service
Render a Django template to PDF bytes.
Order (default): WeasyPrint -> xhtml2pdf -> pdfkit(wkhtmltopdf)
You can force an engine by passing engine="weasyprint"|"xhtml2pdf"|"pdfkit".
"""
from io import BytesIO
from django.template.loader import render_to_string

REPLACEMENTS = {
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
    "\u00A0": " ",  # nbsp
    "\u2018": "'",  # left single quote
    "\u2019": "'",  # right single quote
    "\u201C": '"',  # left double quote
    "\u201D": '"',  # right double quote
    "\u2022": "*",  # bullet
}

def _sanitize(html: str) -> str:
    for k, v in REPLACEMENTS.items():
        if k in html:
            html = html.replace(k, v)
    return html

def render_pdf_from_template(template_name: str, context: dict, base_url: str | None = None, engine: str | None = None):
    """
    Returns: (pdf_bytes: bytes, engine_used: str)
    Raises RuntimeError on failure (with reasons for each engine).
    """
    html = render_to_string(template_name, context)

    engines = [engine] if engine else ["weasyprint", "xhtml2pdf", "pdfkit"]
    errors = {}

    for eng in engines:
        try:
            if eng == "weasyprint":
                from weasyprint import HTML  # type: ignore
                pdf_bytes = HTML(string=html, base_url=base_url).write_pdf()
                return pdf_bytes, "weasyprint"

            if eng == "xhtml2pdf":
                from xhtml2pdf import pisa  # type: ignore
                out = BytesIO()
                # sanitize Unicode that reportlab base fonts choke on
                safe_html = _sanitize(html)
                result = pisa.CreatePDF(src=safe_html, dest=out, encoding="utf-8")
                if result.err:
                    raise RuntimeError("xhtml2pdf failed to render")
                return out.getvalue(), "xhtml2pdf"

            if eng == "pdfkit":
                import pdfkit  # type: ignore
                # Try PA path, fallback to default discovery
                try:
                    config = pdfkit.configuration(wkhtmltopdf="/usr/bin/wkhtmltopdf")
                except Exception:
                    config = None
                pdf_bytes = pdfkit.from_string(html, False, configuration=config)
                return pdf_bytes, "pdfkit-wkhtmltopdf"

            raise RuntimeError(f"Unknown engine '{eng}'")

        except Exception as e:  # capture and try next
            errors[eng or "auto"] = str(e)

    raise RuntimeError(f"PDF render failed. errors={errors}")
