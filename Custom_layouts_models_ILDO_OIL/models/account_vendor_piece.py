
from datetime import date

from odoo import fields, models


class AccountVendorPiece(models.Model):
    _inherit = "account.move"

    ildo_vendor_piece_number = fields.Char(
        string="Numéro de pièce",
        copy=False,
        readonly=True,
        index=True,
    )

    ildo_vendor_piece_reference = fields.Char(
        string="Référence technique de pièce fournisseur",
        copy=False,
        readonly=True,
        index=True,
    )

    def _ildo_get_vendor_piece_period(self, invoice_date, frequency):
        invoice_date = (
            fields.Date.to_date(invoice_date)
            or fields.Date.context_today(self)
        )

        if frequency == "week":
            iso_year, iso_week, _ = invoice_date.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"

        if frequency == "month":
            return invoice_date.strftime("%Y-%m")

        if frequency == "year":
            return invoice_date.strftime("%Y")

        return "CONTINU"

    def _ildo_assign_vendor_piece_number(self):
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
            # Uniquement les factures fournisseurs comptabilisées.
            if move.state != "posted":
                continue

            if move.move_type != "in_invoice":
                continue

            # Ne pas remplacer les numéros existants.
            if move.ildo_vendor_piece_number:
                continue

            journal = move.journal_id

            if not journal:
                continue

            # Protéger la création de séquences concurrentes.
            self.env.cr.execute(
                """
                SELECT id
                FROM account_journal
                WHERE id = %s
                FOR UPDATE
                """,
                [journal.id],
            )

            period = self._ildo_get_vendor_piece_period(
                move.invoice_date or move.date,
                frequency,
            )

            # Séquence distincte des factures clients
            # et des paiements.
            sequence_code = (
                f"ildo.vendor.piece.{move.company_id.id}."
                f"{journal.id}.{period}"
            )

            sequence = Sequence.search(
                [("code", "=", sequence_code)],
                limit=1,
            )

            if not sequence:
                sequence = Sequence.create({
                    "name": (
                        f"Pièces fournisseurs ILDO - "
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
                "ildo_vendor_piece_number": number,
                "ildo_vendor_piece_reference": (
                    f"{sequence_code}/{number}"
                ),
            })

    def action_post(self):
        # Identifier les factures fournisseurs en brouillon
        # avant leur comptabilisation.
        invoices_to_number = self.filtered(
            lambda move:
                move.state == "draft"
                and move.move_type == "in_invoice"
        )

        # Exécuter les validations Odoo et les personnalisations
        # déjà présentes pour les autres documents.
        result = super().action_post()

        # Attribuer les numéros de pièce fournisseurs.
        invoices_to_number._ildo_assign_vendor_piece_number()

        return result
