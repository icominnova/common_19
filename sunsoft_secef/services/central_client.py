import logging
from urllib.parse import urljoin

import requests


_logger = logging.getLogger(__name__)


class SecefCentralClientError(Exception):
    """Erreur générique du client central SECeF."""


class SecefCentralTransportError(
    SecefCentralClientError
):
    """
    Erreur réseau.

    La requête peut avoir atteint le serveur même si
    aucune réponse n'a été reçue.
    """


class SecefCentralHTTPError(
    SecefCentralClientError
):
    """Réponse HTTP non valide du serveur central."""

    def __init__(
        self,
        message,
        *,
        status_code=None,
        response_payload=None,
    ):
        super().__init__(message)

        self.status_code = status_code
        self.response_payload = response_payload


class SecefCentralProtocolError(
    SecefCentralClientError
):
    """Réponse centrale invalide ou inattendue."""


class SecefCentralClient:
    """
    Client HTTP utilisé par Odoo pour communiquer
    avec la plateforme centrale Sunsoft SECeF.
    """

    def __init__(
        self,
        *,
        base_url,
        api_token,
        timeout=10.0,
        session=None,
    ):
        self.base_url = self._normalize_base_url(
            base_url
        )

        self.api_token = self._normalize_required(
            api_token,
            "api_token",
        )

        try:
            self.timeout = float(timeout)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Le timeout SECeF doit être numérique."
            ) from exc

        if self.timeout <= 0:
            raise ValueError(
                "Le timeout SECeF doit être supérieur à zéro."
            )

        self.session = (
            session
            if session is not None
            else requests.Session()
        )

    @staticmethod
    def _normalize_required(
        value,
        field_name,
    ):
        if not isinstance(value, str):
            raise ValueError(
                "%s doit être une chaîne."
                % field_name
            )

        normalized = value.strip()

        if not normalized:
            raise ValueError(
                "%s ne peut pas être vide."
                % field_name
            )

        return normalized

    @classmethod
    def _normalize_base_url(
        cls,
        base_url,
    ):
        normalized = cls._normalize_required(
            base_url,
            "base_url",
        )

        if not normalized.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "L'URL centrale SECeF doit commencer "
                "par http:// ou https://."
            )

        return normalized.rstrip("/") + "/"

    def _url(
        self,
        path,
    ):
        return urljoin(
            self.base_url,
            path.lstrip("/"),
        )

    def _headers(
        self,
    ):
        return {
            "Authorization": (
                "Bearer %s"
                % self.api_token
            ),
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": (
                "Sunsoft-SECeF-Odoo/19.0"
            ),
        }

    @staticmethod
    def _decode_json(
        response,
    ):
        try:
            payload = response.json()
        except ValueError as exc:
            raise SecefCentralProtocolError(
                "Le serveur central SECeF a retourné "
                "une réponse JSON invalide."
            ) from exc

        if not isinstance(payload, dict):
            raise SecefCentralProtocolError(
                "La réponse du serveur central SECeF "
                "doit être un objet JSON."
            )

        return payload

    def _raise_http_error(
        self,
        response,
    ):
        payload = None

        try:
            decoded = response.json()

            if isinstance(decoded, dict):
                payload = decoded

        except ValueError:
            pass

        detail = None

        if payload:
            detail = payload.get("detail")

        message = (
            detail
            or (
                "Erreur HTTP %s du serveur central SECeF."
                % response.status_code
            )
        )

        raise SecefCentralHTTPError(
            message,
            status_code=response.status_code,
            response_payload=payload,
        )

    def heartbeat(
        self,
    ):
        """
        Signale au serveur central que cette instance
        Odoo est actuellement active.
        """

        try:
            response = self.session.post(
                self._url(
                    "api/v1/odoo/heartbeat"
                ),
                headers=self._headers(),
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            _logger.warning(
                "Erreur réseau pendant le heartbeat "
                "Odoo SECeF : %s",
                exc,
            )

            raise SecefCentralTransportError(
                "Impossible de contacter le serveur "
                "central SECeF."
            ) from exc

        if not response.ok:
            self._raise_http_error(
                response
            )

        result = self._decode_json(
            response
        )

        if result.get("status") != "ok":
            raise SecefCentralProtocolError(
                "Statut heartbeat Odoo SECeF invalide."
            )

        credential_uid = result.get(
            "credential_uid"
        )

        if not credential_uid:
            raise SecefCentralProtocolError(
                "credential_uid manquant dans "
                "la réponse heartbeat Odoo SECeF."
            )

        return result

    def create_certification(
        self,
        *,
        request_uid,
        agent_uid,
        invoice_number,
        payload,
        job_type="invoice.certify",
    ):
        """
        Crée ou rejoue idempotemment une certification.

        request_uid doit rester identique lors d'un rejeu
        de la même tentative fiscale.
        """

        request_uid = self._normalize_required(
            request_uid,
            "request_uid",
        )

        agent_uid = self._normalize_required(
            agent_uid,
            "agent_uid",
        )

        invoice_number = self._normalize_required(
            invoice_number,
            "invoice_number",
        )

        job_type = self._normalize_required(
            job_type,
            "job_type",
        )

        if not isinstance(payload, dict):
            raise ValueError(
                "payload doit être un dictionnaire."
            )

        if not payload:
            raise ValueError(
                "payload ne peut pas être vide."
            )

        body = {
            "request_uid": request_uid,
            "agent_uid": agent_uid,
            "invoice_number": invoice_number,
            "job_type": job_type,
            "payload": payload,
        }

        try:
            response = self.session.post(
                self._url(
                    "api/v1/certifications"
                ),
                headers=self._headers(),
                json=body,
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            _logger.warning(
                "Erreur réseau pendant la création "
                "de la certification SECeF %s: %s",
                request_uid,
                exc,
            )

            raise SecefCentralTransportError(
                "Impossible de contacter le serveur "
                "central SECeF."
            ) from exc

        if not response.ok:
            self._raise_http_error(
                response
            )

        result = self._decode_json(
            response
        )

        self._validate_certification_response(
            result,
            expected_request_uid=request_uid,
            expected_agent_uid=agent_uid,
            expected_invoice_number=invoice_number,
        )

        return result

    def get_certification(
        self,
        *,
        request_uid,
    ):
        """Récupère l'état central d'une certification."""

        request_uid = self._normalize_required(
            request_uid,
            "request_uid",
        )

        try:
            response = self.session.get(
                self._url(
                    "api/v1/certifications/%s"
                    % request_uid
                ),
                headers=self._headers(),
                timeout=self.timeout,
            )

        except requests.RequestException as exc:
            _logger.warning(
                "Erreur réseau pendant la lecture "
                "de la certification SECeF %s: %s",
                request_uid,
                exc,
            )

            raise SecefCentralTransportError(
                "Impossible de contacter le serveur "
                "central SECeF."
            ) from exc

        if not response.ok:
            self._raise_http_error(
                response
            )

        result = self._decode_json(
            response
        )

        self._validate_certification_response(
            result,
            expected_request_uid=request_uid,
        )

        return result

    @staticmethod
    def _validate_certification_response(
        payload,
        *,
        expected_request_uid,
        expected_agent_uid=None,
        expected_invoice_number=None,
    ):
        required_fields = {
            "request_uid",
            "job_uid",
            "agent_uid",
            "invoice_number",
            "status",
            "result",
            "error_message",
        }

        missing = (
            required_fields
            - set(payload)
        )

        if missing:
            raise SecefCentralProtocolError(
                "Réponse centrale incomplète : %s."
                % ", ".join(
                    sorted(missing)
                )
            )

        if (
            payload["request_uid"]
            != expected_request_uid
        ):
            raise SecefCentralProtocolError(
                "request_uid incohérent dans "
                "la réponse centrale."
            )

        if (
            expected_agent_uid is not None
            and payload["agent_uid"]
            != expected_agent_uid
        ):
            raise SecefCentralProtocolError(
                "agent_uid incohérent dans "
                "la réponse centrale."
            )

        if (
            expected_invoice_number is not None
            and payload["invoice_number"]
            != expected_invoice_number
        ):
            raise SecefCentralProtocolError(
                "Numéro de facture incohérent dans "
                "la réponse centrale."
            )

        if payload["status"] not in {
            "pending",
            "processing",
            "completed",
            "failed",
            "unknown",
        }:
            raise SecefCentralProtocolError(
                "Statut SECeF central invalide."
            )

        if not payload["job_uid"]:
            raise SecefCentralProtocolError(
                "job_uid manquant dans "
                "la réponse centrale."
            )

        if (
            payload["result"] is not None
            and not isinstance(
                payload["result"],
                dict,
            )
        ):
            raise SecefCentralProtocolError(
                "Le résultat central SECeF "
                "doit être un objet JSON ou null."
            )