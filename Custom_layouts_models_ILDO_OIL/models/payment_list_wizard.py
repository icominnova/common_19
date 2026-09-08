from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class IldoPaymentListWizard(models.TransientModel):
    _name = "ildo.payment.list.wizard"
    _description = "Filtres de la liste des paiements"

    date_filter = fields.Selection(
        [
            ("today", "Aujourd'hui"),
            ("day", "Par jour"),
            ("period", "Par période"),
            ("all", "Toutes les dates"),
        ],
        string="Filtre de date",
        required=True,
        default="today",
    )
    day_date = fields.Date(string="Date", default=fields.Date.context_today)
    date_from = fields.Date(string="Date de début", default=fields.Date.context_today)
    date_to = fields.Date(string="Date de fin", default=fields.Date.context_today)
    journal_ids = fields.Many2many(
        "account.journal",
        string="Journaux",
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains("date_filter", "date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if (
                wizard.date_filter == "period"
                and wizard.date_from
                and wizard.date_to
                and wizard.date_from > wizard.date_to
            ):
                raise ValidationError(_("La date de début doit précéder la date de fin."))

    def _get_dates(self):
        self.ensure_one()
        today = fields.Date.context_today(self)
        if self.date_filter == "today":
            return today, today
        if self.date_filter == "day":
            return self.day_date, self.day_date
        if self.date_filter == "period":
            return self.date_from, self.date_to
        return False, False

    def action_print_report(self):
        self.ensure_one()
        date_from, date_to = self._get_dates()
        domain = [("company_id", "=", self.company_id.id)]

        partner_type = self.env.context.get("default_partner_type")
        payment_type = self.env.context.get("default_payment_type")
        if partner_type in ("customer", "supplier"):
            domain.append(("partner_type", "=", partner_type))
        if payment_type in ("inbound", "outbound"):
            domain.append(("payment_type", "=", payment_type))
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if self.journal_ids:
            domain.append(("journal_id", "in", self.journal_ids.ids))

        payments = self.env["account.payment"].search(
            domain, order="journal_id, date, name"
        )
        if not payments:
            raise UserError(_("Aucun paiement ne correspond aux filtres sélectionnés."))

        if date_from and date_to:
            period_label = _("Du %(start)s au %(end)s", start=date_from.strftime("%d/%m/%Y"), end=date_to.strftime("%d/%m/%Y"))
        else:
            period_label = _("Toutes les dates")

        return self.env.ref(
            "Custom_layouts_models_ILDO_OIL.action_print_payment_list"
        ).report_action(
            payments,
            data={
                "payment_ids": payments.ids,
                "period_label": period_label,
                "journal_label": ", ".join(self.journal_ids.mapped("name"))
                or _("Tous les journaux"),
            },
        )
