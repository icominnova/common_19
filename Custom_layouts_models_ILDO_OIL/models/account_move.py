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

            duplicate = self.search(
                [
                    ("id", "!=", move.id),
                    ("journal_id", "=", move.journal_id.id),
                    ("state", "=", "posted"),
                    ("name", "=", invoice_number),
                ],
                limit=1,
            )
            if duplicate:
                raise ValidationError(
                    _("Le numéro de facture %s est déjà utilisé.", invoice_number)
                )

            move[number_field] = invoice_number
            move.name = invoice_number

        return super().action_post()
