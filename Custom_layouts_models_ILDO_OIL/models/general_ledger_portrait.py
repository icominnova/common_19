from odoo import _, models
from odoo.exceptions import UserError


class IldoGeneralLedgerPortrait(models.Model):
    _inherit = "account.report"

    def _ildo_is_general_ledger(self):
        self.ensure_one()
        general_ledger = self.env.ref(
            "account_reports.general_ledger_report",
            raise_if_not_found=False,
        )
        return bool(general_ledger) and self.id == general_ledger.id

    def _init_options_buttons(self, options, previous_options):
        super()._init_options_buttons(options, previous_options)

        if self._ildo_is_general_ledger():
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

        if not self._ildo_is_general_ledger():
            raise UserError(
                _("L'export portrait est reserve au Grand livre general.")
            )

        if options.get("sections"):
            raise UserError(
                _("L'export portrait ne prend pas en charge "
                  "les rapports contenant plusieurs sections.")
            )

        result = self.with_context(
            ildo_gl_portrait_pdf=True,
        ).export_to_pdf(options)

        result = dict(result)

        filename = result.get("file_name") or "grand_livre_general.pdf"

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
            self.env.context.get("ildo_gl_portrait_pdf")
            and self._ildo_is_general_ledger()
        ):
            options = dict(options)

            display_config = dict(
                options.get("custom_display_config") or {}
            )

            previous_class = (
                display_config.get("css_custom_class") or ""
            )

            display_config["css_custom_class"] = (
                previous_class + " ildo_gl_portrait_pdf"
            ).strip()

            options["custom_display_config"] = display_config

        return super()._get_pdf_export_html(
            options,
            lines,
            additional_context=additional_context,
            template=template,
        )


class IldoGeneralLedgerPortraitPdfEngine(models.Model):
    _inherit = "ir.actions.report"

    def _run_wkhtmltopdf(self, bodies, *args, **kwargs):
        if (
            self.env.context.get("ildo_gl_portrait_pdf")
            and self.env.context.get("account_report_pdf_export")
        ):
            kwargs = dict(kwargs)
            kwargs["landscape"] = False

        return super()._run_wkhtmltopdf(
            bodies,
            *args,
            **kwargs,
        )
