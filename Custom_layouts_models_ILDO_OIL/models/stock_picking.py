from odoo import fields, models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    ildo_show_be_bl_numbers = fields.Boolean(
        related="company_id.ildo_show_be_bl_numbers",
    )
    ildo_be_number = fields.Char(
        string="N° BE",
        related="sale_id.ildo_be_number",
        store=True,
        readonly=False,
    )
    ildo_bl_number = fields.Char(
        string="N° BL",
        related="sale_id.ildo_bl_number",
        store=True,
        readonly=False,
    )
