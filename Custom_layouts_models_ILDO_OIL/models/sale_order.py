from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    ildo_destination = fields.Char(string="Destination", copy=True)
    ildo_account_partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Compte client",
        domain="[('ildo_client_reference', '!=', False)]",
        copy=True,
        help="Client titulaire du compte dont la référence sera utilisée sur les BE et BL.",
    )
    ildo_be_number = fields.Char(string="N° BE", copy=True)
    ildo_bl_number = fields.Char(string="N° BL", copy=True)
    ildo_show_be_bl_numbers = fields.Boolean(
        related="company_id.ildo_show_be_bl_numbers",
    )
