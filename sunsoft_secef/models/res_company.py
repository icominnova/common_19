import logging
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..services.central_client import (
    SecefCentralClient,
    SecefCentralClientError,
)


_logger = logging.getLogger(__name__)

class ResCompany(models.Model):
    _inherit = "res.company"

    secef_enabled = fields.Boolean(
        string="Activer SECeF",
        default=False,
    )

    secef_environment = fields.Selection(
        selection=[
            ("test", "Test"),
            ("production", "Production"),
        ],
        string="Environnement SECeF",
        default="test",
        required=True,
    )

    secef_sfe_id = fields.Char(
        string="Identifiant SFE",
    )

    secef_tax_regime = fields.Char(
        string="Régime d'imposition",
    )

    secef_tax_office = fields.Char(
        string="Service des impôts",
    )

    # ---------------------------------------------------------
    # Plateforme centrale Sunsoft SECeF
    # ---------------------------------------------------------

    secef_central_url = fields.Char(
        string="URL serveur central SECeF",
        copy=False,
        help=(
            "Adresse HTTPS de la plateforme centrale "
            "Sunsoft SECeF."
        ),
    )

    secef_central_api_token = fields.Char(
        string="Token API Odoo SECeF",
        copy=False,
        groups="base.group_system",
        help=(
            "Token Bearer Odoo utilisé pour authentifier "
            "cette société auprès de la plateforme centrale."
        ),
    )

    secef_agent_uid = fields.Char(
        string="UID Agent SECeF",
        copy=False,
        help=(
            "Identifiant unique de l'Agent Windows "
            "rattaché à cette société."
        ),
    )

    secef_agent_last_seen_at = fields.Datetime(
        string="Dernière connexion Agent SECeF",
        readonly=True,
        copy=False,
    )

    secef_agent_connection_alert = fields.Boolean(
        string="Alerte connexion Agent SECeF",
        compute="_compute_secef_agent_connection_alert",
    )

    secef_http_timeout = fields.Float(
        string="Timeout HTTP SECeF",
        default=10.0,
        help=(
            "Durée maximale, en secondes, d'attente "
            "d'une réponse HTTP du serveur central."
        ),
    )

    # ---------------------------------------------------------
    # Compatibilité temporaire avec l'ancienne architecture
    # Odoo -> Agent.
    #
    # Ces champs seront supprimés lorsque secef_api.py
    # sera retiré.
    # ---------------------------------------------------------

    secef_agent_identifier = fields.Char(
        string="Identifiant Agent SECeF (legacy)",
        copy=False,
    )

    secef_agent_api_key = fields.Char(
        string="Clé API Agent SECeF (legacy)",
        copy=False,
        groups="base.group_system",
    )

    def _compute_secef_agent_connection_alert(self):
        now = fields.Datetime.now()

        for company in self:
            company.secef_agent_connection_alert = False

            if not company.secef_agent_last_seen_at:
                continue

            elapsed = (
                now
                - company.secef_agent_last_seen_at
            )

            company.secef_agent_connection_alert = (
                elapsed > timedelta(days=7)
            )

    @api.model
    def _cron_secef_central_heartbeat(self):
        """
        Signale périodiquement au serveur central
        les instances Odoo SECeF actives.
        """

        companies = self.sudo().search([
            ("secef_enabled", "=", True),
            ("secef_central_url", "!=", False),
            ("secef_central_api_token", "!=", False),
        ])

        for company in companies:
            central_url = (
                company.secef_central_url
                or ""
            ).strip()

            api_token = (
                company.secef_central_api_token
                or ""
            ).strip()

            if not central_url or not api_token:
                continue

            timeout = (
                company.secef_http_timeout
                or 10.0
            )

            try:
                client = SecefCentralClient(
                    base_url=central_url,
                    api_token=api_token,
                    timeout=timeout,
                )

                client.heartbeat()

            except (
                SecefCentralClientError,
                ValueError,
            ) as exc:
                _logger.warning(
                    "Heartbeat Odoo SECeF impossible "
                    "pour la société %s (id=%s) : %s",
                    company.display_name,
                    company.id,
                    exc,
                )

    @api.constrains("secef_http_timeout")
    def _check_secef_http_timeout(self):
        for company in self:
            if company.secef_http_timeout <= 0:
                raise ValidationError(
                    _(
                        "Le timeout HTTP SECeF doit être "
                        "supérieur à zéro."
                    )
                )