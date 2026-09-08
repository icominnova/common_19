from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ildo_show_be_bl_numbers = fields.Boolean(
        string="Afficher les champs N° BE et N° BL",
        default=True,
    )
