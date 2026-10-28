
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    ildo_piece_auto_enabled = fields.Boolean(
        string="Numérotation automatique des pièces",
        config_parameter="ildo_piece.auto_enabled",
    )

    ildo_piece_reset_frequency = fields.Selection(
        selection=[
            ("never", "Jamais - compteur continu"),
            ("week", "Chaque semaine"),
            ("month", "Chaque mois"),
            ("year", "Chaque année"),
        ],
        string="Réinitialisation des numéros de pièce",
        default="never",
        required=True,
        config_parameter="ildo_piece.reset_frequency",
    )
