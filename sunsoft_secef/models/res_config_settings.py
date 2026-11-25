from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    secef_enabled = fields.Boolean(
        related="company_id.secef_enabled",
        readonly=False,
    )

    secef_environment = fields.Selection(
        related="company_id.secef_environment",
        readonly=False,
    )

    secef_sfe_id = fields.Char(
        related="company_id.secef_sfe_id",
        readonly=False,
    )
    secef_tax_regime = fields.Char(
        related="company_id.secef_tax_regime",
        readonly=False,
    )

    secef_tax_office = fields.Char(
        related="company_id.secef_tax_office",
        readonly=False,
    )

    secef_central_url = fields.Char(
        related="company_id.secef_central_url",
        readonly=False,
    )

    secef_central_api_token = fields.Char(
        related="company_id.secef_central_api_token",
        readonly=False,
        groups="base.group_system",
    )

    secef_agent_uid = fields.Char(
        related="company_id.secef_agent_uid",
        readonly=False,
    )

    secef_http_timeout = fields.Float(
        related="company_id.secef_http_timeout",
        readonly=False,
    )