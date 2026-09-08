from odoo import models


class IldoThirdPartyBalanceReportHandler(models.AbstractModel):
    """Affiche la balance des tiers avec l'interface des rapports comptables."""

    _name = "ildo.third.party.balance.report.handler"
    _inherit = "account.report.custom.handler"
    _description = "Moteur de la balance des tiers"

    def _get_balance_domain(self, options, date_field, partner_field):
        """Apply the same period and partner filters to invoices and payments."""
        companies = [company["id"] for company in options.get("companies", [])]
        domain = [("company_id", "in", companies or self.env.companies.ids)]
        for key, operator in (("date_from", ">="), ("date_to", "<=")):
            if options.get("date", {}).get(key):
                domain.append((date_field, operator, options["date"][key]))
        if options.get("partner_ids"):
            partners = self.env["res.partner"].browse(options["partner_ids"]).commercial_partner_id
            domain.append((partner_field, "in", partners.ids))
        if options.get("partner_categories"):
            domain.append((partner_field + ".category_id", "in", options["partner_categories"]))
        if term := options.get("filter_search_bar"):
            domain += ["|", "|", (partner_field + ".name", "ilike", term),
                       (partner_field + ".ref", "ilike", term),
                       (partner_field + ".vat", "ilike", term)]
        journals = [journal["id"] for journal in options.get("journals", [])
                    if journal.get("selected") and isinstance(journal.get("id"), int)]
        if journals:
            domain.append(("journal_id", "in", journals))
        return domain

    def _get_invoice_balance_values(self, options):
        """ILDO balances: actual payments, customer refunds, no vendor refunds.

        Dates filter each document's own date. These are period totals, not
        historical residuals. In combined mode balances sum both party roles.
        """
        selected = {item["id"] for item in options.get("account_type", []) if item.get("selected")}
        customers = not selected or any("receivable" in item for item in selected)
        suppliers = not selected or any("payable" in item for item in selected)
        move_types = (["out_invoice", "out_refund"] if customers else []) + (["in_invoice"] if suppliers else [])
        domain = self._get_balance_domain(options, "invoice_date", "commercial_partner_id")
        domain += [("move_type", "in", move_types),
                   ("state", "in", ["posted", "draft"] if options.get("all_entries") else ["posted"])]
        values_by_partner = {}

        def add(partner, column, amount, balance_sign):
            if not partner:
                return
            values = values_by_partner.setdefault(partner.id, {"debit": 0.0, "credit": 0.0, "balance": 0.0})
            values[column] += amount
            values["balance"] += balance_sign * amount

        for partner, move_type, total in self.env["account.move"]._read_group(
            domain, ["commercial_partner_id", "move_type"], ["amount_total_signed:sum"]
        ):
            if move_type == "out_invoice":
                add(partner, "debit", total, 1)
            elif move_type == "out_refund":
                add(partner, "credit", -total, -1)
            else:
                add(partner, "credit", -total, 1)

        payment_domain = self._get_balance_domain(options, "date", "partner_id.commercial_partner_id")
        payment_domain += [("state", "in", ["in_process", "paid"]), ("partner_id", "!=", False)]
        roles = []
        if customers:
            roles.append("customer")
        if suppliers:
            roles.append("supplier")
        payment_domain.append(("partner_type", "in", roles))
        for partner, role, direction, amount in self.env["account.payment"]._read_group(
            payment_domain, ["partner_id", "partner_type", "payment_type"],
            ["amount_company_currency_signed:sum"],
        ):
            # Count only receipts from customers and payments to suppliers.
            if role == "customer" and direction == "inbound":
                add(partner.commercial_partner_id, "credit", amount, -1)
            elif role == "supplier" and direction == "outbound":
                add(partner.commercial_partner_id, "debit", -amount, -1)
        return values_by_partner

    def _report_custom_engine_third_party_balance(
        self,
        expressions,
        options,
        date_scope,
        current_groupby,
        next_groupby,
        offset=0,
        limit=None,
        warnings=None,
    ):
        """Retourne les chiffres attendus par l'interface account.report."""
        values_by_partner = self._get_invoice_balance_values(options)

        if not current_groupby:
            totals = {"balance": 0.0, "debit": 0.0, "credit": 0.0}
            for values in values_by_partner.values():
                for key in totals:
                    totals[key] += values[key]
            return {**totals, "has_sublines": False}

        if current_groupby != "partner_id":
            return []

        partner_ids = list(values_by_partner)
        ordered_partners = self.env["res.partner"].browse(partner_ids).sorted(
            key=lambda partner: (partner.display_name or "").lower()
        )
        rows = [
            (partner.id, {**values_by_partner[partner.id], "has_sublines": False})
            for partner in ordered_partners
        ]
        return rows[offset : offset + limit if limit else None]

    def _caret_options_initializer(self):
        """Aucun lien vers les écritures comptables n'est proposé."""
        return {}
