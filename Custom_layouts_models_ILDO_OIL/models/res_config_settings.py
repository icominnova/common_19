from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ildo_show_be_bl_numbers = fields.Boolean(
        related="company_id.ildo_show_be_bl_numbers",
        readonly=False,
    )
