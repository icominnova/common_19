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

                # Verrou transactionnel contre les validations simultanees.
                self.env.cr.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s), %s)",
                    (
                        "ILDO_OIL_customer_document_sequence",
                        move.company_id.id,
                    ),
                )

                prefix = (
                    "FA"
                    if move.move_type == "out_invoice"
                    else "FV"
                )

                sequence_code = (
                    "ildo_oil.customer_invoice"
                    if move.move_type == "out_invoice"
                    else "ildo_oil.customer_credit"
                )

                xmlid = (
                    "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_invoice"
                    if move.move_type == "out_invoice"
                    else "Custom_layouts_models_ILDO_OIL.seq_ildo_customer_credit"
                )

                sequence = self.env.ref(xmlid).sudo()

                # La periode correspond a la date comptable.
                # Chaque annee possede son propre compteur.
                date_range = sequence._get_current_sequence(move.date)

                current_next = date_range.number_next_actual

                expected = (
                    f"{prefix}{move.date.strftime('%y')}"
                    f"{current_next:04d}"
                )

                # Un numero saisi manuellement doit obligatoirement
                # correspondre au prochain numero attendu.
                if move.ildo_invoice_number:
                    supplied = move.ildo_invoice_number.strip()

                    if supplied != expected:
                        raise ValidationError(
                            _(
                                "Numéro manuel %s refusé. "
                                "Prochain numéro attendu : %s."
                            )
                            % (supplied, expected)
                        )

                # Recherche d'une collision sur l'ensemble
                # des documents de la societe, sans exclure
                # les brouillons et les documents annules.
                clash = self.sudo().search(
                    [
                        ("company_id", "=", move.company_id.id),
                        ("id", "!=", move.id),
                        "|",
                        ("name", "=", expected),
                        ("ildo_invoice_number", "=", expected),
                    ],
                    limit=1,
                )

                if clash:
                    raise ValidationError(
                        _(
                            "NUMÉROTATION ILDO OIL BLOQUÉE.\\n\\n"
                            "Le numéro %s existe déjà sur le "
                            "document ID %s (état : %s).\\n\\n"
                            "Veuillez demander une vérification "
                            "au service comptable.\\n"
                            "Aucun saut automatique n'est autorisé."
                        )
                        % (
                            expected,
                            clash.id,
                            clash.state,
                        )
                    )

                # Une seule consommation de la sequence.
                # Aucun parcours de 1000 numeros libres.
                assigned = (
                    self.env["ir.sequence"]
                    .with_company(move.company_id)
                    .sudo()
                    .next_by_code(
                        sequence_code,
                        sequence_date=move.date,
                    )
                )

                if not assigned:
                    raise UserError(
                        _("Séquence ILDO OIL introuvable.")
                    )

                if assigned != expected:
                    raise ValidationError(
                        _(
                            "Incohérence de séquence. "
                            "Numéro attendu : %s ; obtenu : %s."
                        )
                        % (expected, assigned)
                    )

                move.ildo_invoice_number = assigned

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
        return super().action_post()
