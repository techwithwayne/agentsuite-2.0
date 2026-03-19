from __future__ import annotations

import re
from html import unescape
from typing import Any

from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from postpress_ai.models.license_site import LicenseSite, LicenseSiteStatus
from postpress_ai.models.remote_draft_log import RemoteDraftLog
from postpress_ai.services.remote_drafts import (
    call_remote_draft,
    call_site_handshake,
    generate_site_token,
)
from postpress_ai.views.license import (
    APIError,
    _ensure_license_active,
    _get_client_ip,
    _get_license_or_raise,
    _json_err,
    _json_ok,
    _license_limit_allows_site,
    _normalize_site_url,
    _parse_json_body,
    _rate_limit_or_raise,
)


def _site_row(site: LicenseSite) -> dict:
    return {
        "id": site.id,
        "name": (site.name or site.site_url),
        "url": site.site_url,
        "status": site.status,
    }


def _response_json(resp) -> dict:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {"raw": data}
    except Exception:
        text = getattr(resp, "text", "")
        return {"raw": text}


def _clean_text(value: Any) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shorten_text(value: str, limit: int = 220) -> str:
    value = str(value or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _compact_upstream_error(resp, body: dict, fallback: str) -> str:
    status = getattr(resp, "status_code", None)

    chunks: list[str] = []
    for key in ("message", "detail", "error", "raw"):
        if key in body and body.get(key):
            cleaned = _clean_text(body.get(key))
            if cleaned:
                chunks.append(cleaned)

    combined = _shorten_text(" ".join(chunks))

    if status == 502:
        if not combined or "cloudflare" in combined.lower():
            return "Upstream returned 502 Bad Gateway."
    if status == 503 and not combined:
        return "Upstream returned 503 Service Unavailable."
    if status == 504 and not combined:
        return "Upstream returned 504 Gateway Timeout."

    if combined:
        if status:
            return f"Upstream returned {status}: {combined}"
        return combined

    if status:
        return f"{fallback} [{status}]"

    return fallback


def _upstream_result(resp, body: dict) -> dict:
    return {
        "status_code": getattr(resp, "status_code", None),
        "summary": _compact_upstream_error(resp, body, "Upstream request failed."),
        "body": body,
    }


def _target_ok(resp, body: dict) -> bool:
    return getattr(resp, "status_code", None) == 200 and (
        bool(body.get("ok")) or body.get("status") == "ok"
    )


def _is_invalid_remote_draft_token(resp, body: dict) -> bool:
    if getattr(resp, "status_code", None) not in (401, 403):
        return False

    code = str(body.get("code") or "").strip().lower()
    message = str(body.get("message") or "").strip().lower()
    raw = str(body.get("raw") or "").strip().lower()

    if "invalid remote draft token" in message or "invalid remote draft token" in raw:
        return True

    return code == "forbidden" and "invalid remote draft token" in message


def _extract_remote_post_details(body: dict) -> tuple[Any, Any]:
    remote_post_id = body.get("post_id")
    edit_link = body.get("edit_link")

    remote_post_obj = body.get("remote_post")
    if isinstance(remote_post_obj, dict):
        remote_post_id = remote_post_obj.get("id", remote_post_id)
        edit_link = remote_post_obj.get("edit_link", edit_link)

    return remote_post_id, edit_link


@require_GET
def license_sites(request: HttpRequest) -> JsonResponse:
    try:
        license_key = (request.GET.get("license_key") or "").strip()
        if not license_key:
            raise APIError(
                code="missing_license_key",
                message="license_key is required.",
                http_status=400,
                err_type="validation",
            )

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="license_sites", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        _ensure_license_active(lic)

        rows = list(
            LicenseSite.objects.filter(
                license=lic,
            ).order_by("site_url")
        )

        return _json_ok(
            {
                "license_key": license_key,
                "sites": [_site_row(site) for site in rows],
            }
        )
    except APIError as e:
        return _json_err(e)
    except Exception as exc:
        err = APIError(
            code="internal_error_license_sites",
            message=f"Unexpected error in license_sites: {exc}",
            http_status=500,
            err_type="internal",
        )
        return _json_err(err)


@csrf_exempt
@require_POST
def register_site(request: HttpRequest) -> JsonResponse:
    base_data = None
    try:
        payload = _parse_json_body(request)

        license_key = (payload.get("license_key") or "").strip()
        site_url = _normalize_site_url(payload.get("site_url"))
        site_name = str(payload.get("site_name") or "").strip()

        if not license_key:
            raise APIError(
                code="missing_license_key",
                message="license_key is required.",
                http_status=400,
                err_type="validation",
            )

        if not site_url:
            raise APIError(
                code="missing_site_url",
                message="site_url is required.",
                http_status=400,
                err_type="validation",
            )

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="register_site", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        _ensure_license_active(lic)

        base_data = {
            "license_key": license_key,
            "site_url": site_url,
        }

        with transaction.atomic():
            existing = LicenseSite.objects.select_for_update().filter(
                license=lic,
                site_url=site_url,
            ).first()

            if existing:
                site = existing
                if site_name:
                    site.name = site_name
                if not site.site_token:
                    site.site_token = generate_site_token()
                site.status = LicenseSiteStatus.PENDING
                site.save(update_fields=["name", "site_token", "status", "updated_at"])
            else:
                if not _license_limit_allows_site(lic, site_url):
                    raise APIError(
                        code="site_limit_reached",
                        message="Site limit reached for this license.",
                        http_status=403,
                        err_type="plan_limit",
                    )

                site = LicenseSite.objects.create(
                    license=lic,
                    name=site_name,
                    site_url=site_url,
                    site_token=generate_site_token(),
                    status=LicenseSiteStatus.PENDING,
                )

        try:
            resp = call_site_handshake(
                site_url=site.site_url,
                license_key=license_key,
                site_id=site.id,
                site_token=site.site_token,
            )
            resp_json = _response_json(resp)
        except Exception as exc:
            raise APIError(
                code="handshake_failed",
                message=f"Handshake failed: {exc}",
                http_status=502,
                err_type="upstream",
            )

        ok_flag = bool(resp_json.get("ok")) or resp_json.get("status") == "ok"

        if resp.status_code != 200 or not ok_flag:
            raise APIError(
                code="handshake_failed",
                message=_compact_upstream_error(resp, resp_json, "Site handshake failed."),
                http_status=502,
                err_type="upstream",
            )

        site.status = LicenseSiteStatus.ACTIVE
        site.save(update_fields=["status", "updated_at"])

        return _json_ok(
            {
                "license_key": license_key,
                "site": _site_row(site),
            }
        )
    except APIError as e:
        return _json_err(e, data=base_data) if isinstance(base_data, dict) else _json_err(e)
    except Exception as exc:
        err = APIError(
            code="internal_error_register_site",
            message=f"Unexpected error in register_site: {exc}",
            http_status=500,
            err_type="internal",
        )
        return _json_err(err, data=base_data) if isinstance(base_data, dict) else _json_err(err)


@csrf_exempt
@require_POST
def remote_drafts_create(request: HttpRequest) -> JsonResponse:
    base_data = None
    log: RemoteDraftLog | None = None

    try:
        payload = _parse_json_body(request)

        license_key = (payload.get("license_key") or "").strip()
        source_site_id_raw = str(payload.get("source_site_id") or "").strip()
        target_site_id_raw = str(payload.get("target_site_id") or "").strip()

        post_payload = payload.get("post")
        if post_payload is None:
            post_payload = payload.get("payload")
        if post_payload is None:
            post_payload = {}

        if not license_key:
            raise APIError(
                code="missing_license_key",
                message="license_key is required.",
                http_status=400,
                err_type="validation",
            )

        if not target_site_id_raw:
            raise APIError(
                code="missing_target_site_id",
                message="target_site_id is required.",
                http_status=400,
                err_type="validation",
            )

        if not isinstance(post_payload, dict):
            raise APIError(
                code="invalid_post_payload",
                message="post must be an object.",
                http_status=400,
                err_type="validation",
            )

        ip = _get_client_ip(request)
        _rate_limit_or_raise(scope="remote_drafts_create", ip=ip, license_key=license_key)

        lic = _get_license_or_raise(license_key)
        _ensure_license_active(lic)

        source_site = None
        if source_site_id_raw.isdigit():
            source_site = LicenseSite.objects.filter(
                license=lic,
                id=int(source_site_id_raw),
            ).first()

        try:
            target_site_id = int(target_site_id_raw)
        except Exception:
            raise APIError(
                code="invalid_target_site_id",
                message="target_site_id must be an integer.",
                http_status=400,
                err_type="validation",
            )

        target_site = LicenseSite.objects.filter(
            license=lic,
            id=target_site_id,
            status=LicenseSiteStatus.ACTIVE,
        ).first()

        if not target_site:
            raise APIError(
                code="target_site_not_found",
                message="Target site not found for this license.",
                http_status=404,
                err_type="not_found",
            )

        base_data = {
            "license_key": license_key,
            "source_site_id": source_site_id_raw,
            "target_site_id": target_site_id_raw,
        }

        log = RemoteDraftLog.objects.create(
            license=lic,
            source_site=source_site,
            target_site=target_site,
            source_site_id_raw=source_site_id_raw,
            target_site_id_raw=target_site_id_raw,
            request_payload=payload,
        )

        attempt_log: dict[str, Any] = {}
        recovered_after_handshake = False

        try:
            resp = call_remote_draft(
                target_site_url=target_site.site_url,
                target_site_token=target_site.site_token,
                post_payload=post_payload,
            )
            resp_json = _response_json(resp)
        except Exception as exc:
            raise APIError(
                code="remote_draft_request_failed",
                message=f"Remote draft request failed: {exc}",
                http_status=502,
                err_type="upstream",
            )

        attempt_log["attempt_1"] = _upstream_result(resp, resp_json)

        if not _target_ok(resp, resp_json):
            if _is_invalid_remote_draft_token(resp, resp_json):
                try:
                    handshake_resp = call_site_handshake(
                        site_url=target_site.site_url,
                        license_key=license_key,
                        site_id=target_site.id,
                        site_token=target_site.site_token,
                    )
                    handshake_json = _response_json(handshake_resp)
                except Exception as exc:
                    attempt_log["handshake"] = {"error": str(exc)}
                    log.response_payload = attempt_log
                    log.success = False
                    log.error_message = "Target site rejected draft token; connection repair failed."
                    log.save(update_fields=["response_payload", "success", "error_message"])
                    raise APIError(
                        code="remote_draft_failed",
                        message="Target site connection repair failed.",
                        http_status=502,
                        err_type="upstream",
                    )

                attempt_log["handshake"] = _upstream_result(handshake_resp, handshake_json)
                handshake_ok = _target_ok(handshake_resp, handshake_json)

                if not handshake_ok:
                    log.response_payload = attempt_log
                    log.success = False
                    log.error_message = "Target site rejected draft token; connection repair failed."
                    log.save(update_fields=["response_payload", "success", "error_message"])
                    raise APIError(
                        code="remote_draft_failed",
                        message=_compact_upstream_error(
                            handshake_resp,
                            handshake_json,
                            "Target site connection repair failed.",
                        ),
                        http_status=502,
                        err_type="upstream",
                    )

                try:
                    retry_resp = call_remote_draft(
                        target_site_url=target_site.site_url,
                        target_site_token=target_site.site_token,
                        post_payload=post_payload,
                    )
                    retry_json = _response_json(retry_resp)
                except Exception as exc:
                    attempt_log["attempt_2"] = {"error": str(exc)}
                    log.response_payload = attempt_log
                    log.success = False
                    log.error_message = "Target site rejected draft token; connection repaired but retry still failed."
                    log.save(update_fields=["response_payload", "success", "error_message"])
                    raise APIError(
                        code="remote_draft_failed",
                        message="Target site connection was repaired, but draft creation still failed.",
                        http_status=502,
                        err_type="upstream",
                    )

                attempt_log["attempt_2"] = _upstream_result(retry_resp, retry_json)

                if not _target_ok(retry_resp, retry_json):
                    log.response_payload = attempt_log
                    log.success = False
                    log.error_message = "Target site rejected draft token; connection repaired but retry still failed."
                    log.save(update_fields=["response_payload", "success", "error_message"])
                    raise APIError(
                        code="remote_draft_failed",
                        message=_compact_upstream_error(
                            retry_resp,
                            retry_json,
                            "Target site connection was repaired, but draft creation still failed.",
                        ),
                        http_status=502,
                        err_type="upstream",
                    )

                resp = retry_resp
                resp_json = retry_json
                recovered_after_handshake = True
                attempt_log["recovery"] = {
                    "reason": "invalid_remote_draft_token",
                    "recovered": True,
                }
            else:
                compact_error = _compact_upstream_error(
                    resp,
                    resp_json,
                    "Target site failed to create the draft.",
                )
                log.response_payload = attempt_log
                log.success = False
                log.error_message = compact_error
                log.save(update_fields=["response_payload", "success", "error_message"])
                raise APIError(
                    code="remote_draft_failed",
                    message=compact_error,
                    http_status=502,
                    err_type="upstream",
                )

        remote_post_id, edit_link = _extract_remote_post_details(resp_json)

        log.response_payload = attempt_log
        log.success = True
        log.remote_post_id = str(remote_post_id or "")
        log.remote_edit_link = str(edit_link or "")
        log.error_message = "" if not recovered_after_handshake else "Recovered after automatic handshake repair."
        log.save(
            update_fields=[
                "response_payload",
                "success",
                "remote_post_id",
                "remote_edit_link",
                "error_message",
            ]
        )

        response_body = {
            "ok": True,
            "license_key": license_key,
            "target_site": {
                "id": target_site.id,
                "url": target_site.site_url,
            },
            "remote_post": {
                "id": remote_post_id,
                "edit_link": edit_link,
            },
        }

        if recovered_after_handshake:
            response_body["repair"] = {
                "performed": True,
                "reason": "invalid_remote_draft_token",
            }

        return JsonResponse(response_body, status=200)

    except APIError as e:
        if log:
            try:
                if not log.success:
                    log.error_message = log.error_message or e.message
                    log.save(update_fields=["error_message"])
            except Exception:
                pass
        return _json_err(e, data=base_data) if isinstance(base_data, dict) else _json_err(e)
    except Exception as exc:
        if log:
            try:
                if not log.success:
                    log.error_message = log.error_message or str(exc)
                    log.save(update_fields=["error_message"])
            except Exception:
                pass
        err = APIError(
            code="internal_error_remote_drafts_create",
            message=f"Unexpected error in remote_drafts_create: {exc}",
            http_status=500,
            err_type="internal",
        )
        return _json_err(err, data=base_data) if isinstance(base_data, dict) else _json_err(err)