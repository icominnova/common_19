from odoo import fields, models


class AccountTax(models.Model):
    _inherit = "account.tax"

    secef_tax_group = fields.Selection(
        selection=[
            (letter, letter)
            for letter in "ABCDEFGHIJKLMNOP"
        ],
        string="Groupe taxe SECeF",
        copy=False,
    )