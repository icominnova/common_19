from odoo import _, fields, models
from odoo.exceptions import UserError


class SecefAReportWizard(models.TransientModel):
    _name = "sunsoft.secef.a.report.wizard"
    _description = "Generation rapport A SECeF"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Societe",
        required=True,
        default=lambda self:
            self.env.company,
    )

    last_a_id = fields.Many2one(
        comodel_name="sunsoft.secef.report",
        string="Dernier rapport A",
        compute="_compute_last_a_id",
        readonly=True,
    )

    def _compute_last_a_id(self):

        Report = self.env[
            "sunsoft.secef.report"
        ]

        for wizard in self:

            if not wizard.company_id:
                wizard.last_a_id = False
                continue

            wizard.last_a_id = (
                Report._secef_last_a(
                    wizard.company_id
                )
            )

    def action_generate(self):
        self.ensure_one()

        if not self.env.user.has_group(
            "account.group_account_manager"
        ):
            raise UserError(
                _(
                    "Seul un responsable "
                    "comptable peut generer "
                    "un rapport A."
                )
            )

        report = (
            self.env[
                "sunsoft.secef.report"
            ]
            .generate_a(
                company=self.company_id,
            )
        )

        return {
            "type":
                "ir.actions.act_window",

            "name":
                _("Rapport A SECeF"),

            "res_model":
                "sunsoft.secef.report",

            "res_id":
                report.id,

            "view_mode":
                "form",

            "target":
                "current",
        }
