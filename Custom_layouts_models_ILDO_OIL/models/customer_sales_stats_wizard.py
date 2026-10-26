
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class IldoCustomerSalesStatsWizard(models.TransientModel):
    _name = "ildo.customer.sales.stats.wizard"
    _description = "Statistiques clients - Palmarès des ventes"

    date_from = fields.Date(
        string="Date de début",
        required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Date de fin",
        required=True,
        default=fields.Date.context_today,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Société",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from and wizard.date_to and wizard.date_from > wizard.date_to:
                raise ValidationError(
                    _("La date de début doit précéder la date de fin.")
                )

    def _get_statistics(self):
        self.ensure_one()

        domain = [
            ("company_id", "=", self.company_id.id),
            ("state", "=", "posted"),
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("invoice_date", ">=", self.date_from),
            ("invoice_date", "<=", self.date_to),
        ]

        moves = self.env["account.move"].search(domain)

        results = defaultdict(lambda: {
            "ca_ttc": 0.0,
            "avoirs": 0.0,
        })

        currency = self.company_id.currency_id

        for move in moves:
            partner = move.commercial_partner_id or move.partner_id
            values = results[partner.id]

            # Montant TTC dans la devise de la société.
            amount = abs(move.amount_total_signed)

            if move.move_type == "out_invoice":
                # CA : montant total des factures avant avoirs.
                values["ca_ttc"] += amount

            elif move.move_type == "out_refund":
                # Avoir : déduction utilisée pour calculer la marge.
                values["avoirs"] += amount

        partners = self.env["res.partner"].browse(list(results))

        lines = []

        for partner in partners:
            values = results[partner.id]

            ca_ttc = currency.round(values["ca_ttc"])
            avoirs = currency.round(values["avoirs"])

            # Marge ILDO OIL = CA TTC - Avoirs TTC.
            marge = currency.round(ca_ttc - avoirs)

            client_initials = "".join(
                part[:1].upper()
                for part in (partner.name or "").split()
            )

            number = (
                partner.code_client
                or f"C{client_initials}{partner.id}"
            )

            lines.append({
                "number": number,
                "name": partner.name or "",
                "ca_ttc": ca_ttc,
                "margin": marge,
            })

        # Classement par chiffre d'affaires décroissant.
        lines.sort(
            key=lambda line: (
                -line["ca_ttc"],
                line["name"].lower(),
            )
        )

        return {
            "lines": lines,
            "total_ca": currency.round(
                sum(line["ca_ttc"] for line in lines)
            ),
            "total_margin": currency.round(
                sum(line["margin"] for line in lines)
            ),
        }

    def action_print_report(self):
        self.ensure_one()

        statistics = self._get_statistics()

        if not statistics["lines"]:
            raise UserError(
                _("Aucune facture ou aucun avoir client comptabilisé sur cette période.")
            )

        return self.env.ref(
            "Custom_layouts_models_ILDO_OIL.action_customer_sales_stats_report"
        ).report_action(self)
