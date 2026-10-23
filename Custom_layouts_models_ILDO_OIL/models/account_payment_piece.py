from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    ildo_piece_number = fields.Char(
        string="Numéro de pièce",
        copy=False,
        index=True,
    )


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    ildo_piece_number = fields.Char(
        string="Numéro de pièce",
    )

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        vals["ildo_piece_number"] = self.ildo_piece_number or False
        return vals

    def _create_payment_vals_from_batch(self, batch_result):
        vals = super()._create_payment_vals_from_batch(batch_result)
        vals["ildo_piece_number"] = self.ildo_piece_number or False
        return vals
