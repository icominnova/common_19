from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    secef_item_type = fields.Selection(
        selection=[
            ("LOCBIE", "Bien local"),
            ("LOCSER", "Service local"),
            ("IMPBIE", "Bien importé"),
            ("IMPSER", "Service importé"),
        ],
        string="Type article SECeF",
        copy=False,
    )