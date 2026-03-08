from __future__ import annotations

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
                status=LicenseSiteStatus.ACTIVE,
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
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {"ok": False, "raw": resp.text}
        except Exception as exc:
            raise APIError(
                code="handshake_failed",
                message=f"Handshake failed: {exc}",
                http_status=502,
                err_type="upstream",
            )

        if resp.status_code != 200 or not bool(resp_json.get("ok")):
            raise APIError(
                code="handshake_failed",
                message="Site handshake failed.",
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


@csrf_exempt
@require_POST
def remote_drafts_create(request: HttpRequest) -> JsonResponse:
    base_data = None
    log = None

    try:
        payload = _parse_json_body(request)

        license_key = (payload.get("license_key") or "").strip()
        source_site_id_raw = str(payload.get("source_site_id") or "").strip()
        target_site_id_raw = str(payload.get("target_site_id") or "").strip()
        post_payload = payload.get("post") or {}

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

        try:
            resp = call_remote_draft(
                target_site_url=target_site.site_url,
                target_site_token=target_site.site_token,
                post_payload=post_payload,
            )
            try:
                resp_json = resp.json()
            except Exception:
                resp_json = {"ok": False, "raw": resp.text}
        except Exception as exc:
            raise APIError(
                code="remote_draft_request_failed",
                message=f"Remote draft request failed: {exc}",
                http_status=502,
                err_type="upstream",
            )

        log.response_payload = resp_json

        if resp.status_code != 200 or not bool(resp_json.get("ok")):
            log.success = False
            log.error_message = f"Target site error [{resp.status_code}]"
            log.save(update_fields=["response_payload", "success", "error_message"])
            raise APIError(
                code="remote_draft_failed",
                message="Target site failed to create the draft.",
                http_status=502,
                err_type="upstream",
            )

        remote_post_id = resp_json.get("post_id")
        edit_link = resp_json.get("edit_link")

        log.success = True
        log.remote_post_id = str(remote_post_id or "")
        log.remote_edit_link = str(edit_link or "")
        log.save(update_fields=["response_payload", "success", "remote_post_id", "remote_edit_link"])

        return _json_ok(
            {
                "license_key": license_key,
                "target_site_id": target_site.id,
                "remote_post_id": remote_post_id,
                "edit_link": edit_link,
            }
        )
    except APIError as e:
        if log:
            try:
                if not log.success:
                    log.error_message = log.error_message or e.message
                    log.save(update_fields=["error_message"])
            except Exception:
                pass
        return _json_err(e, data=base_data) if isinstance(base_data, dict) else _json_err(e)
