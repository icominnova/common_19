from odoo import fields, models


class IldoStatementPaymentTrace(models.Model):
    _inherit = 'account.bank.statement.line'

    ildo_source_payment_id = fields.Many2one(
        'account.payment',
        string='Paiement source ILDO',
        copy=False, readonly=True, index=True, ondelete='restrict',
        check_company=True,
    )

    _ildo_unique_source_payment = models.Constraint(
        'UNIQUE(ildo_source_payment_id)',
        'Une transaction ILDO existe déjà pour ce paiement.',
    )
