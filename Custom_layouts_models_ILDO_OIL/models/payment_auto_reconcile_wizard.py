from collections import defaultdict
from datetime import date
from html import escape

from odoo import fields, models
from odoo.exceptions import UserError


class IldoPaymentAutoReconcileWizard(models.TransientModel):
    _name = "ildo.payment.auto.reconcile.wizard"
    _description = "Simulation de reconciliation multijournaux ILDO"

    date_from = fields.Date(
        string="Date de début",
        required=True,
        default=lambda self: date.today().replace(day=1),
    )
    date_to = fields.Date(
        string="Date de fin",
        required=True,
        default=fields.Date.context_today,
    )
    preview_html = fields.Html(
        string="Résultat de la simulation",
        readonly=True,
        sanitize=True,
    )

    def action_simulate(self):
        self.ensure_one()

        if self.date_from > self.date_to:
            raise UserError(
                "La date de début doit précéder la date de fin."
            )

        payments = self.env["account.payment"].search([
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("company_id", "in", self.env.companies.ids),
            ("journal_id.type", "in", ["bank", "cash"]),
            ("state", "in", ["in_process", "paid"]),
        ], order="journal_id, date, id")

        invoice_counts = defaultdict(int)
        for payment in payments:
            if payment.amount > 0:
                for invoice in payment.invoice_ids:
                    invoice_counts[invoice.id] += 1

        results = defaultdict(lambda: {
            "journal": "",
            "total": 0,
            "candidates": 0,
            "to_check": 0,
            "conflicts": 0,
        })

        for payment in payments:
            journal = payment.journal_id
            result = results[journal.id]
            result["journal"] = journal.display_name
            result["total"] += 1

            # Simulation : aucune écriture créée.
            shared_invoice = any(
                invoice_counts[invoice.id] > 1
                for invoice in payment.invoice_ids
            )

            if shared_invoice:
                result["conflicts"] += 1

            if (
                payment.amount > 0
                and not shared_invoice
                and payment.payment_type in ("inbound", "outbound")
                and payment.partner_id
                and (
                    not payment.move_id
                    or (
                        payment.move_id.state == "posted"
                        and payment.move_id.journal_id == journal
                    )
                )
                and not payment.reconciled_statement_line_ids
            ):
                result["candidates"] += 1
            else:
                result["to_check"] += 1

        rows = []
        for journal_id in sorted(results):
            item = results[journal_id]
            rows.append(
                "<tr>"
                f"<td>{escape(item['journal'])}</td>"
                f"<td>{item['total']}</td>"
                f"<td>{item['candidates']}</td>"
                f"<td>{item['to_check']}</td>"
                f"<td>{item['conflicts']}</td>"
                "</tr>"
            )

        if not rows:
            rows.append(
                '<tr><td colspan="5">'
                "Aucun paiement validé trouvé sur cette période."
                "</td></tr>"
            )

        self.preview_html = (
            "<p><strong>Simulation uniquement : "
            "aucune transaction créée.</strong></p>"
            "<table class='table table-sm table-bordered'>"
            "<thead><tr>"
            "<th>Journal</th>"
            "<th>Paiements</th>"
            "<th>Candidats à analyser</th>"
            "<th>À vérifier</th>"
            "<th>Facture partagée</th>"
            "</tr></thead>"
            f"<tbody>{''.join(rows)}</tbody>"
            "</table>"
            "<p>Les candidats ne sont pas encore déclarés "
            "réconciliables. La détection des transactions "
            "existantes et des doublons sera ajoutée avant "
            "l'activation du rapprochement automatique.</p>"
        )

        return {
            "type": "ir.actions.act_window",
            "name": "Réconciliation automatique — Simulation",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
