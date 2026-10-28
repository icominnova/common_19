
from datetime import date

from odoo import fields, models


class AccountPayment(models.Model):
    _inherit = "account.payment"

    ildo_piece_number = fields.Char(
        string="Numéro de pièce",
        copy=False,
        index=True,
        readonly=True,
    )

    ildo_piece_reference = fields.Char(
        string="Référence technique de pièce",
        copy=False,
        readonly=True,
        index=True,
    )

    def _ildo_get_piece_period(self, payment_date, frequency):
        payment_date = fields.Date.to_date(payment_date) or date.today()

        if frequency == "week":
            iso_year, iso_week, _ = payment_date.isocalendar()
            return f"{iso_year}-W{iso_week:02d}"

        if frequency == "month":
            return payment_date.strftime("%Y-%m")

        if frequency == "year":
            return payment_date.strftime("%Y")

        return "CONTINU"

    def _ildo_assign_piece_number(self):
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

        for payment in self.sorted(
            key=lambda p: (p.journal_id.id, p.id)
        ):
            # Odoo 19 : les paiements validés peuvent être
            # à l'état in_process ou paid.
            if payment.state not in ("in_process", "paid"):
                continue

            # Ne jamais remplacer un numéro déjà attribué.
            if payment.ildo_piece_number:
                continue

            journal = payment.journal_id

            # Numérotation de tout les  journaux bancaires.
            if not journal:
                continue

            # Verrouiller le journal pour éviter que deux
            # paiements simultanés créent deux compteurs.
            self.env.cr.execute(
                """
                SELECT id
                FROM account_journal
                WHERE id = %s
                FOR UPDATE
                """,
                [journal.id],
            )

            # Déterminer la période selon le paramétrage global.
            period = self._ildo_get_piece_period(
                payment.date,
                frequency,
            )

            # Une séquence indépendante par société,
            # journal bancaire et période.
            sequence_code = (
                f"ildo.piece.{payment.company_id.id}."
                f"{journal.id}.{period}"
            )

            Sequence = self.env["ir.sequence"].sudo()

            sequence = Sequence.search(
                [("code", "=", sequence_code)],
                limit=1,
            )

            # Création automatique de la séquence si
            # ce journal n'en possède pas pour la période.
            if not sequence:
                sequence = Sequence.create({
                    "name": (
                        f"Pièces ILDO - {journal.name} - {period}"
                    ),
                    "code": sequence_code,
                    "implementation": "standard",
                    "padding": 1,
                    "number_increment": 1,
                    "number_next": 1,
                    "company_id": payment.company_id.id,
                })

            # Attribution du prochain numéro disponible.
            number = sequence.next_by_id()

            payment.write({
                "ildo_piece_number": number,
                "ildo_piece_reference": (
                    f"{sequence_code}/{number}"
                ),
            })

    def action_post(self):
        # Exécuter d'abord la validation standard Odoo.
        result = super().action_post()

        # Attribuer automatiquement les numéros de pièce
        # aux paiements bancaires nouvellement validés.
        self._ildo_assign_piece_number()

        return result


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    ildo_piece_number = fields.Char(
        string="Numéro de pièce",
        readonly=True,
    )
