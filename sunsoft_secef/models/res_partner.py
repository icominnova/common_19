from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    secef_customer_type = fields.Selection(
        selection=[
            ("CC", "Client comptant"),
            ("PM", "Personne morale"),
            ("PP", "Personne physique"),
            ("PC", "Professionnel / commerçant"),
        ],
        string="Type client SECeF",
        copy=False,
    )
    secef_psvb_group = fields.Selection(
        selection=[
            ("A", "Groupe A - 2 %"),
            ("B", "Groupe B - 1 %"),
            ("C", "Groupe C - 0,2 %"),
            ("D", "Groupe D - 0 %"),
        ],
        string="Groupe PSVB SECeF par défaut",
        copy=False,
        help=(
            "Groupe PSVB proposé par défaut "
            "sur les nouvelles factures du client. "
            "Laisser vide si aucun PSVB n'est applicable."
        ),
    )
