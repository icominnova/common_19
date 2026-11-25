from odoo import _, fields, models
from odoo.exceptions import UserError


class SecefReportWizard(models.TransientModel):
    _name = "sunsoft.secef.report.wizard"
    _description = "Generation rapport X SECeF"

    report_type = fields.Selection(
        selection=[
            (
                "x_daily",
                "Rapport X quotidien",
            ),
            (
                "x_periodic",
                "Rapport X periodique",
            ),
        ],
        string="Type de rapport",
        required=True,
        default="x_daily",
    )

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Societe",
        required=True,
        default=lambda self:
            self.env.company,
    )

    period_start = fields.Datetime(
        string="Debut de periode",
    )

    period_end = fields.Datetime(
        string="Fin de periode",
        required=True,
        default=fields.Datetime.now,
    )

    def action_generate(self):
        self.ensure_one()

        if (
            self.company_id
            not in self.env.companies
        ):
            raise UserError(
                _(
                    "Vous n'avez pas acces "
                    "a cette societe."
                )
            )

        Report = self.env[
            "sunsoft.secef.report"
        ]

        if (
            self.report_type
            == "x_daily"
        ):
            report = (
                Report.generate_x_daily(
                    company=(
                        self.company_id
                    ),
                    period_end=(
                        self.period_end
                    ),
                )
            )

        elif (
            self.report_type
            == "x_periodic"
        ):

            if not self.period_start:
                raise UserError(
                    _(
                        "Le debut de periode "
                        "est obligatoire pour "
                        "un rapport X periodique."
                    )
                )

            report = (
                Report.generate_x_periodic(
                    period_start=(
                        self.period_start
                    ),
                    period_end=(
                        self.period_end
                    ),
                    company=(
                        self.company_id
                    ),
                )
            )

        else:
            raise UserError(
                _(
                    "Type de rapport X "
                    "invalide."
                )
            )

        return {
            "type":
                "ir.actions.act_window",

            "name":
                _("Rapport SECeF"),

            "res_model":
                "sunsoft.secef.report",

            "res_id":
                report.id,

            "view_mode":
                "form",

            "target":
                "current",
        }
