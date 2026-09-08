from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    code_client = fields.Char(string="Code Client")
    ildo_client_reference = fields.Char(
        string="Référence client",
        help="Référence prioritaire affichée sur les documents ILDO OIL. Si elle est vide, le code client puis la référence automatique sont utilisés.",
    )
    rccm = fields.Char(string="RCCM")
    ifu = fields.Char(string="N° IFU")
    division_f = fields.Char(string="Division fiscale")
    regime_i = fields.Char(string="Régime d'imposition")

    ildo_customer_debit = fields.Monetary(
        string="Débit",
        compute="_compute_ildo_customer_balances",
        currency_field="currency_id",
        help="Total TTC des factures clients comptabilisées, diminué des avoirs.",
    )
    ildo_customer_credit = fields.Monetary(
        string="Crédit",
        compute="_compute_ildo_customer_balances",
        currency_field="currency_id",
        help="Montant réglé sur les factures clients comptabilisées.",
    )
    ildo_customer_balance = fields.Monetary(
        string="Solde",
        compute="_compute_ildo_customer_balances",
        currency_field="currency_id",
        help="Montant restant dû sur les factures clients comptabilisées.",
    )

    @api.depends_context("company")
    def _compute_ildo_customer_balances(self):
        self.ildo_customer_debit = 0.0
        self.ildo_customer_credit = 0.0
        self.ildo_customer_balance = 0.0
        commercial_partners = self.commercial_partner_id
        if not commercial_partners:
            return

        balances = {
            partner.id: (total, residual)
            for partner, total, residual in self.env["account.move"]._read_group(
                domain=[
                    ("state", "=", "posted"),
                    ("move_type", "in", ("out_invoice", "out_refund")),
                    ("company_id", "child_of", self.env.company.root_id.id),
                    ("commercial_partner_id", "in", commercial_partners.ids),
                ],
                groupby=["commercial_partner_id"],
                aggregates=["amount_total_signed:sum", "amount_residual_signed:sum"],
            )
        }
        for partner in self:
            total, residual = balances.get(partner.commercial_partner_id.id, (0.0, 0.0))
            partner.ildo_customer_debit = total
            partner.ildo_customer_credit = total - residual
            partner.ildo_customer_balance = residual
