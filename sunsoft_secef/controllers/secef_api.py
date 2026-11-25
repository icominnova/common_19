import secrets
from datetime import datetime

from odoo import http
from odoo.http import request


class SunsoftSecefAPI(http.Controller):

    @http.route(
        "/sunsoft_secef/api/v1/jobs/next",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def next_job(self, **kwargs):
        agent_identifier = (
            request.httprequest.headers
            .get("X-Agent-Identifier", "")
            .strip()
        )

        authorization = (
            request.httprequest.headers
            .get("Authorization", "")
            .strip()
        )

        if not agent_identifier:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Agent identifier missing",
                },
                status=401,
            )

        if not authorization.startswith("Bearer "):
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        api_key = authorization[7:].strip()

        if not api_key:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        companies = (
            request.env["res.company"]
            .sudo()
            .search([
                ("secef_enabled", "=", True),
                (
                    "secef_agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ])
        )

        company = False

        for candidate in companies:
            expected_key = (
                candidate.secef_agent_api_key or ""
            )

            if expected_key and secrets.compare_digest(
                expected_key,
                api_key,
            ):
                company = candidate
                break

        if not company:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Invalid agent credentials",
                },
                status=401,
            )

        transaction, claim_status = (
            request.env["sunsoft.secef.transaction"]
            .sudo()
            ._claim_next_for_agent(
                company=company,
                agent_identifier=agent_identifier,
            )
        )

        if claim_status == "processing":
            return request.make_json_response(
                {
                    "success": False,
                    "error": (
                        "Agent already has a "
                        "processing transaction"
                    ),
                    "request_uid": transaction.request_uid,
                    "transaction_id": transaction.id,
                    "invoice_number": transaction.move_id.name,
                },
                status=409,
            )

        if claim_status == "none":
            return request.make_json_response({
                "success": True,
                "job": None,
            })

        return request.make_json_response({
            "success": True,
            "job": {
                "request_uid": transaction.request_uid,
                "transaction_id": transaction.id,
                "invoice_number": transaction.move_id.name,
                "agent_identifier": transaction.agent_identifier,
                "payload": transaction.request_payload,
            },
        })

    @http.route(
        "/sunsoft_secef/api/v1/jobs/current",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def current_job(self, **kwargs):
        agent_identifier = (
            request.httprequest.headers
            .get("X-Agent-Identifier", "")
            .strip()
        )

        authorization = (
            request.httprequest.headers
            .get("Authorization", "")
            .strip()
        )

        if not agent_identifier:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Agent identifier missing",
                },
                status=401,
            )

        if not authorization.startswith("Bearer "):
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        api_key = authorization[7:].strip()

        if not api_key:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        companies = (
            request.env["res.company"]
            .sudo()
            .search([
                ("secef_enabled", "=", True),
                (
                    "secef_agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ])
        )

        company = False

        for candidate in companies:
            expected_key = (
                candidate.secef_agent_api_key or ""
            )

            if expected_key and secrets.compare_digest(
                expected_key,
                api_key,
            ):
                company = candidate
                break

        if not company:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Invalid agent credentials",
                },
                status=401,
            )

        transactions = (
            request.env["sunsoft.secef.transaction"]
            .sudo()
            .search([
                ("company_id", "=", company.id),
                (
                    "agent_identifier",
                    "=",
                    agent_identifier,
                ),
                ("state", "=", "processing"),
            ], order="started_at asc, id asc", limit=2)
        )

        if not transactions:
            return request.make_json_response({
                "success": True,
                "job": None,
            })

        if len(transactions) > 1:
            return request.make_json_response(
                {
                    "success": False,
                    "error": (
                        "Multiple processing transactions "
                        "found for this Agent"
                    ),
                },
                status=409,
            )

        transaction = transactions[0]

        return request.make_json_response({
            "success": True,
            "job": {
                "request_uid": transaction.request_uid,
                "transaction_id": transaction.id,
                "invoice_number": transaction.move_id.name,
                "state": transaction.state,
                "agent_identifier": transaction.agent_identifier,
                "started_at": (
                    transaction.started_at.isoformat()
                    if transaction.started_at
                    else None
                ),
                "payload": transaction.request_payload,
            },
        })

    @http.route(
        "/sunsoft_secef/api/v1/jobs/status",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def job_status(self, **kwargs):
        agent_identifier = (
            request.httprequest.headers
            .get("X-Agent-Identifier", "")
            .strip()
        )

        authorization = (
            request.httprequest.headers
            .get("Authorization", "")
            .strip()
        )

        if not agent_identifier:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Agent identifier missing",
                },
                status=401,
            )

        if not authorization.startswith("Bearer "):
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        api_key = authorization[7:].strip()

        if not api_key:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        companies = (
            request.env["res.company"]
            .sudo()
            .search([
                ("secef_enabled", "=", True),
                (
                    "secef_agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ])
        )

        company = False

        for candidate in companies:
            expected_key = (
                candidate.secef_agent_api_key or ""
            )

            if expected_key and secrets.compare_digest(
                expected_key,
                api_key,
            ):
                company = candidate
                break

        if not company:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Invalid agent credentials",
                },
                status=401,
            )

        data = request.httprequest.get_json(
            silent=True,
        ) or {}

        request_uid = (
            data.get("request_uid") or ""
        ).strip()

        if not request_uid:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "request_uid missing",
                },
                status=400,
            )

        transaction = (
            request.env["sunsoft.secef.transaction"]
            .sudo()
            .search([
                ("request_uid", "=", request_uid),
                ("company_id", "=", company.id),
                (
                    "agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ], limit=1)
        )

        if not transaction:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Transaction not found",
                },
                status=404,
            )

        job = {
            "request_uid": transaction.request_uid,
            "transaction_id": transaction.id,
            "invoice_number": transaction.move_id.name,
            "state": transaction.state,
            "agent_identifier": transaction.agent_identifier,
            "started_at": (
                transaction.started_at.isoformat()
                if transaction.started_at
                else None
            ),
            "completed_at": (
                transaction.completed_at.isoformat()
                if transaction.completed_at
                else None
            ),
        }

        if transaction.state in (
            "pending",
            "processing",
        ):
            job["payload"] = transaction.request_payload

        if transaction.state == "success":
            job["result"] = transaction.response_payload

        if transaction.state == "error":
            job["error"] = transaction.error_message
            job["result"] = transaction.response_payload

        return request.make_json_response({
            "success": True,
            "job": job,
        })

    @http.route(
        "/sunsoft_secef/api/v1/jobs/result",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
        save_session=False,
    )
    def job_result(self, **kwargs):
        agent_identifier = (
            request.httprequest.headers
            .get("X-Agent-Identifier", "")
            .strip()
        )

        authorization = (
            request.httprequest.headers
            .get("Authorization", "")
            .strip()
        )

        if not agent_identifier:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Agent identifier missing",
                },
                status=401,
            )

        if not authorization.startswith("Bearer "):
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        api_key = authorization[7:].strip()

        if not api_key:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Authorization token missing",
                },
                status=401,
            )

        companies = (
            request.env["res.company"]
            .sudo()
            .search([
                ("secef_enabled", "=", True),
                (
                    "secef_agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ])
        )

        company = False

        for candidate in companies:
            expected_key = (
                candidate.secef_agent_api_key or ""
            )

            if expected_key and secrets.compare_digest(
                expected_key,
                api_key,
            ):
                company = candidate
                break

        if not company:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Invalid agent credentials",
                },
                status=401,
            )

        data = request.httprequest.get_json(
            silent=True,
        ) or {}

        request_uid = (
            data.get("request_uid") or ""
        ).strip()

        if not request_uid:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "request_uid missing",
                },
                status=400,
            )

        transaction = (
            request.env["sunsoft.secef.transaction"]
            .sudo()
            .search([
                ("request_uid", "=", request_uid),
                ("company_id", "=", company.id),
                (
                    "agent_identifier",
                    "=",
                    agent_identifier,
                ),
            ], limit=1)
        )

        if not transaction:
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Transaction not found",
                },
                status=404,
            )

        # Idempotence :
        # si l'Agent renvoie un résultat déjà enregistré,
        # on ne traite pas une seconde fois la transaction.
        if transaction.state in ("success", "error"):
            return request.make_json_response({
                "success": True,
                "already_processed": True,
                "state": transaction.state,
            })

        if transaction.state != "processing":
            return request.make_json_response(
                {
                    "success": False,
                    "error": "Transaction is not processing",
                },
                status=409,
            )

        job_success = data.get("success")

        # Le champ success doit obligatoirement être
        # un booléen JSON : true ou false.
        if type(job_success) is not bool:
            return request.make_json_response(
                {
                    "success": False,
                    "error": (
                        "Field 'success' must be "
                        "a boolean"
                    ),
                },
                status=400,
            )

        if job_success is True:
            result = data.get("result") or {}

            if not isinstance(result, dict):
                return request.make_json_response(
                    {
                        "success": False,
                        "error": (
                            "Field 'result' must be "
                            "a JSON object"
                        ),
                    },
                    status=400,
                )

            required_fields = [
                "mid",
                "ifu",
                "signature",
                "datetime",
                "invoice_counter",
                "total_counter",
                "qr_data",
                "invoice_number",
            ]

            missing = [
                field_name
                for field_name in required_fields
                if result.get(field_name) in (
                    None,
                    "",
                )
            ]

            if missing:
                return request.make_json_response(
                    {
                        "success": False,
                        "error": (
                            "Missing result fields: "
                            + ", ".join(missing)
                        ),
                    },
                    status=400,
                )

            # Le numéro retourné par l'Agent doit être
            # exactement celui de la facture Odoo.
            if (
                result["invoice_number"]
                != transaction.move_id.name
            ):
                return request.make_json_response(
                    {
                        "success": False,
                        "error": "Invoice number mismatch",
                    },
                    status=409,
                )

            # Le FIS-NANO renvoie la date de certification
            # sous le format YYYYMMDDHHMMSS.
            try:
                datetime.strptime(
                    str(result["datetime"]),
                    "%Y%m%d%H%M%S",
                )
            except (TypeError, ValueError):
                return request.make_json_response(
                    {
                        "success": False,
                        "error": (
                            "Invalid SECeF datetime format. "
                            "Expected YYYYMMDDHHMMSS"
                        ),
                    },
                    status=400,
                )

            # Les compteurs fiscaux doivent être des
            # entiers positifs ou nuls.
            for counter_name in (
                "invoice_counter",
                "total_counter",
            ):
                counter_value = result[counter_name]

                if (
                    not isinstance(counter_value, int)
                    or isinstance(counter_value, bool)
                    or counter_value < 0
                ):
                    return request.make_json_response(
                        {
                            "success": False,
                            "error": (
                                f"Invalid {counter_name}"
                            ),
                        },
                        status=400,
                    )

            # Le QR doit correspondre exactement aux
            # informations fiscales retournées.
            expected_qr_data = ";".join([
                "BFSECEF01",
                str(result["mid"]),
                str(result["signature"]),
                str(result["ifu"]),
                str(result["datetime"]),
            ])

            if result["qr_data"] != expected_qr_data:
                return request.make_json_response(
                    {
                        "success": False,
                        "error": (
                            "SECeF QR data does not match "
                            "the certification result"
                        ),
                    },
                    status=409,
                )

            transaction._mark_success(result)

            return request.make_json_response({
                "success": True,
                "request_uid": request_uid,
                "state": "success",
            })

        error_message = (
            data.get("error")
            or "Unknown SECeF Agent error"
        )

        transaction._mark_error(
            error_message=error_message,
            response_payload=data,
        )

        return request.make_json_response({
            "success": True,
            "request_uid": request_uid,
            "state": "error",
        })