
from datetime import date

from odoo import fields, models


class AccountInvoicePiece(models.Model):
    _inherit = "account.move"

    ildo_invoice_piece_number = fields.Char(
        string="Numéro de pièce",
        copy=False,
        readonly=True,
        index=True,
    )

    ildo_invoice_piece_reference = fields.Char(
        string="Référence technique de pièce facture",
        copy=False,
        readonly=True,
        index=True,
    )

    def _ildo_get_invoice_piece_period(self, invoice_date, frequency):
        invoice_date = fields.Date.to_date(invoice_date) or date.today()

        if frequency == "week":
            iso_year, iso_week, _ = invoice_date.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"

        if frequency == "month":
            return invoice_date.strftime("%Y-%m")

        if frequency == "year":
            return invoice_date.strftime("%Y")

        return "CONTINU"

    def _ildo_assign_invoice_piece_number(self):
        parameters = self.env["ir.config_parameter"].sudo()

        enabled = parameters.get_param(
            "ildo_piece.auto_enabled", "False"
        ) == "True"

        if not enabled:
            return

        frequency = parameters.get_param(
            "ildo_piece.reset_frequency", "never"
        )

        if frequency not in ("never", "week", "month", "year"):
            frequency = "never"

        Sequence = self.env["ir.sequence"].sudo()

        for move in self.sorted(
            key=lambda record: (record.journal_id.id, record.id)
        ):
            # Uniquement les factures clients comptabilisées.
            if move.state != "posted":
                continue

            if move.move_type != "out_invoice":
                continue

            # Conserver les numéros déjà attribués.
            if move.ildo_invoice_piece_number:
                continue

            journal = move.journal_id

            if not journal:
                continue

            # Verrouiller le journal pour protéger la création
            # des séquences lors des validations simultanées.
            self.env.cr.execute(
                """
                SELECT id
                FROM account_journal
                WHERE id = %s
                FOR UPDATE
                """,
                [journal.id],
            )

            period = self._ildo_get_invoice_piece_period(
                move.invoice_date or move.date,
                frequency,
            )

            # Espace de numérotation distinct des paiements.
            sequence_code = (
                f"ildo.invoice.piece.{move.company_id.id}."
                f"{journal.id}.{period}"
            )

            sequence = Sequence.search(
                [("code", "=", sequence_code)],
                limit=1,
            )

            if not sequence:
                sequence = Sequence.create({
                    "name": (
                        f"Pièces factures ILDO - "
                        f"{journal.name} - {period}"
                    ),
                    "code": sequence_code,
                    "implementation": "standard",
                    "padding": 1,
                    "number_increment": 1,
                    "number_next": 1,
                    "company_id": move.company_id.id,
                })

            number = sequence.next_by_id()

            move.write({
                "ildo_invoice_piece_number": number,
                "ildo_invoice_piece_reference": (
                    f"{sequence_code}/{number}"
                ),
            })

    def action_post(self):
        # Mémoriser uniquement les factures clients
        # encore en brouillon avant la validation.
        invoices_to_number = self.filtered(
            lambda move:
                move.state == "draft"
                and move.move_type == "out_invoice"
        )

        # Conserver toutes les personnalisations existantes :
        # numéro de facture, avoirs et validation standard Odoo.
        result = super().action_post()

        # Numéro de pièce propre à la facture.
        invoices_to_number._ildo_assign_invoice_piece_number()

        return result
