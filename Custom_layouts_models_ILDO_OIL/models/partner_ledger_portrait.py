from odoo import _, models
from odoo.exceptions import UserError


class IldoPartnerLedgerPortrait(models.Model):
    _inherit = "account.report"

    def _ildo_is_partner_ledger(self):
        self.ensure_one()

        partner_ledger = self.env.ref(
            "account_reports.partner_ledger_report",
            raise_if_not_found=False,
        )

        return bool(partner_ledger) and self.id == partner_ledger.id

    def _init_options_buttons(self, options, previous_options):
        super()._init_options_buttons(options, previous_options)

        if self._ildo_is_partner_ledger():
            options["buttons"].append({
                "name": _("PDF portrait"),
                "sequence": 15,
                "action": "export_file",
                "action_param": "export_to_pdf_portrait",
                "file_export_type": _("PDF"),
                "branch_allowed": True,
                "always_show": True,
            })

    def export_to_pdf_portrait(self, options):
        self.ensure_one()

        if not self._ildo_is_partner_ledger():
            raise UserError(
                _("L'export portrait est reserve au Livre des tiers.")
            )

        if options.get("sections"):
            raise UserError(
                _("L'export portrait ne prend pas en charge "
                  "les sections multiples.")
            )

        result = dict(
            self.with_context(
                ildo_partner_ledger_portrait=True
            ).export_to_pdf(options)
        )

        filename = (
            result.get("file_name")
            or "livre_des_tiers.pdf"
        )

        if filename.lower().endswith(".pdf"):
            filename = filename[:-4] + "_portrait.pdf"
        else:
            filename += "_portrait.pdf"

        result["file_name"] = filename

        return result

    def _get_pdf_export_html(
        self,
        options,
        lines,
        additional_context=None,
        template=None,
    ):
        if (
            self.env.context.get("ildo_partner_ledger_portrait")
            and self._ildo_is_partner_ledger()
        ):
            options = dict(options)

            config = dict(
                options.get("custom_display_config") or {}
            )

            templates = dict(
                config.get("pdf_export") or {}
            )

            templates["pdf_export_main"] = (
                "Custom_layouts_models_ILDO_OIL."
                "partner_ledger_portrait_pdf_main"
            )

            config["pdf_export"] = templates

            config["css_custom_class"] = (
                (config.get("css_custom_class") or "")
                + " ildo_tiers_portrait_pdf"
            ).strip()

            options["custom_display_config"] = config

        return super()._get_pdf_export_html(
            options,
            lines,
            additional_context=additional_context,
            template=template,
        )

    def _format_lines_for_display(self, lines, options):
        formatted = super()._format_lines_for_display(
            lines,
            options,
        )

        if not (
            self.env.context.get("ildo_partner_ledger_portrait")
            and self._ildo_is_partner_ledger()
        ):
            return formatted

        allowed = {
            "journal_code",
            "account_code",
            "invoice_date",
            "date_maturity",
            "matching_number",
            "debit",
            "credit",
            "amount_currency",
            "balance",
        }

        labels = [
            col.get("expression_label")
            for col in options.get("columns", [])
        ]

        # Eviter toute perte silencieuse de donnees si
        # Odoo propose une configuration inhabituelle.
        if (
            not labels
            or len(labels) != len(set(labels))
            or not set(labels).issubset(allowed)
        ):
            raise UserError(
                _(
                    "Configuration de colonnes non prise "
                    "en charge en portrait. Utilisez le "
                    "PDF standard pour conserver toutes "
                    "les colonnes."
                )
            )

        metadata = (
            ("journal_code", _("Journal")),
            ("account_code", _("Compte")),
            ("invoice_date", _("Date de facturation")),
            ("date_maturity", _("Echeance")),
            ("matching_number", _("Lettrage")),
            ("amount_currency", _("Montant en devise")),
        )

        for line in formatted:
            cells = line.get("columns") or []
            values = {}

            for position, label in enumerate(labels):
                if position < len(cells):
                    value = cells[position].get("name")

                    values[label] = (
                        "" if value is None else str(value)
                    )

            line["ildo_tiers_portrait_amounts"] = {
                key: values.get(key, "")
                for key in ("debit", "credit", "balance")
            }

            line["ildo_tiers_portrait_meta"] = [
                {
                    "label": caption,
                    "value": values[key],
                }
                for key, caption in metadata
                if values.get(key, "").strip()
            ]

        return formatted


class IldoPartnerLedgerPortraitPdfEngine(models.Model):
    _inherit = "ir.actions.report"

    def _run_wkhtmltopdf(self, bodies, *args, **kwargs):
        if (
            self.env.context.get("ildo_partner_ledger_portrait")
            and self.env.context.get("account_report_pdf_export")
        ):
            kwargs = dict(kwargs)
            kwargs["landscape"] = False

        return super()._run_wkhtmltopdf(
            bodies,
            *args,
            **kwargs,
        )
