import re

from odoo import _, fields, models
from odoo.exceptions import UserError, ValidationError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_ildo_create_credit_note(self):
        """Open a standard, linked credit note without displaying the wizard."""
        self.ensure_one()
        if self.move_type != "out_invoice" or self.state != "posted":
            raise UserError(_("Vous devez sélectionner une facture client comptabilisée."))

        reversal = self.env["account.move.reversal"].with_context(
            active_model="account.move",
            active_ids=self.ids,
            active_id=self.id,
        ).create({
            "move_ids": [(6, 0, self.ids)],
            "date": fields.Date.context_today(self),
            "journal_id": self.journal_id.id,
            "company_id": self.company_id.id,
        })
        action = reversal.reverse_moves(is_modify=False)
        action.update({
            "name": _("Avoir client"),
            "views": [(self.env.ref("account.view_move_form").id, "form")],
            "target": "current",
        })
        return action

    ildo_invoice_number = fields.Char(
        string="Numéro de facture",
        copy=False,
        help="Si ce champ est renseigné, sa valeur devient le numéro de la facture client lors de sa comptabilisation.",
    )
    ildo_vendor_invoice_number = fields.Char(
        string="Numéro de facturation",
        copy=False,
        help="Si ce champ est renseigné, sa valeur devient le numéro de la facture fournisseur lors de sa comptabilisation.",
    )

    def action_post(self):
        for move in self.filtered(lambda item: item.state == "draft"):
            managed = (
                move.company_id == self.env.ref("base.main_company")
                and move.move_type in ("out_invoice", "out_refund")
            )
            if managed and not move.posted_before:
                self.env.cr.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), %s)",
                    ("ILDO_OIL_customer_document_sequence", move.company_id.id),
                )
                prefix = "FA" if move.move_type == "out_invoice" else "FV"
                xmlid = (
                    "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_invoice"
                    if move.move_type == "out_invoice"
                    else "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_credit"
                )
                sequence = self.env.ref(xmlid).sudo()
                date_range = sequence._get_current_sequence(move.date)
                # Starting numbers agreed for the year 2026.
                minimum_next = (
                    (1390 if move.move_type == "out_invoice" else 1091)
                    if move.date.year == 2026
                    else 1
                )

                # The database may already contain higher numbers than
                # the sequence counter, particularly after a restore.
                # Only canonical four-digit numbers are considered here.
                self.env["account.move"].flush_model(["name", "company_id"])
                self.env.cr.execute(
                    """
                    SELECT COALESCE(MAX(RIGHT(name, 4)::integer), 0)
                    FROM account_move
                    WHERE company_id = %s
                      AND id != %s
                      AND name ~ %s
                    """,
                    (
                        move.company_id.id,
                        move.id,
                        rf"^{prefix}{move.date.strftime('%y')}[0-9]{{4}}$",
                    ),
                )
                maximum_existing = self.env.cr.fetchone()[0]

                current_next = date_range.number_next_actual
                target_next = max(
                    minimum_next,
                    current_next,
                    maximum_existing + 1,
                )
                if current_next < target_next:
                    date_range.sudo().write({"number_next": target_next})
                if move.ildo_invoice_number:
                    supplied = move.ildo_invoice_number.strip()
                    expected = (
                        f"{prefix}{move.date.strftime('%y')}"
                        f"{target_next:04d}"
                    )
                    if supplied != expected:
                        raise ValidationError(
                            _("Numéro manuel %s refusé. Prochain numéro attendu : %s.")
                            % (supplied, expected)
                        )
            if (
                move.move_type in ("out_invoice", "out_refund")
                and move.company_id == self.env.ref("base.main_company")
                and not move.ildo_invoice_number
                and not move.posted_before
            ):
                sequence_code = (
                    "ildo_oil.customer_invoice"
                    if move.move_type == "out_invoice"
                    else "ildo_oil.customer_credit"
                )
                for attempt in range(1000):
                    assigned = (
                        self.env["ir.sequence"]
                        .with_company(move.company_id)
                        .sudo()
                        .next_by_code(sequence_code, sequence_date=move.date)
                    )
                    if not assigned:
                        raise UserError(_("Séquence ILDO OIL introuvable."))
                    clash = self.sudo().search(
                        [
                            ("company_id", "=", move.company_id.id),
                            ("id", "!=", move.id),
                            ("name", "=", assigned),
                        ],
                        limit=1,
                    )
                    if not clash:
                        move.ildo_invoice_number = assigned
                        break
                else:
                    raise UserError(
                        _("Impossible de trouver un numéro ILDO OIL libre.")
                    )
            number_field = False
            if move.move_type in ("out_invoice", "out_refund") and move.ildo_invoice_number:
                number_field = "ildo_invoice_number"
            elif move.move_type in ("in_invoice", "in_refund") and move.ildo_vendor_invoice_number:
                number_field = "ildo_vendor_invoice_number"
            if not number_field:
                continue

            invoice_number = move[number_field].strip()
            if not invoice_number or invoice_number == "/":
                raise ValidationError(_("Veuillez saisir un numéro de facture valide."))

            duplicate_domain = [
                ("id", "!=", move.id),
                ("state", "=", "posted"),
                ("name", "=", invoice_number),
            ]
            if move.move_type in ("out_invoice", "out_refund"):
                duplicate_domain.append(
                    ("company_id", "=", move.company_id.id)
                )
            else:
                duplicate_domain.append(
                    ("journal_id", "=", move.journal_id.id)
                )
            duplicate = self.sudo().search(duplicate_domain, limit=1)
            if duplicate:
                raise ValidationError(
                    _("Le numéro de facture %s est déjà utilisé.", invoice_number)
                )

            move[number_field] = invoice_number
            move.name = invoice_number
            if managed and not move.posted_before:
                prefix = "FA" if move.move_type == "out_invoice" else "FV"
                match = re.fullmatch(
                    rf"{prefix}{move.date.strftime('%y')}([0-9]{{4,}})",
                    invoice_number,
                )
                if match:
                    xmlid = (
                        "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_invoice"
                        if move.move_type == "out_invoice"
                        else "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_credit"
                    )
                    sequence = self.env.ref(xmlid).sudo()
                    date_range = sequence._get_current_sequence(move.date)
                    target_next = int(match.group(1)) + 1
                    if date_range.number_next_actual < target_next:
                        date_range.sudo().write({"number_next": target_next})

        return super().action_post()
