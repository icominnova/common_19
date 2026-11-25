from odoo import _, fields, models
from odoo.exceptions import UserError


class SecefZReportWizard(models.TransientModel):
    _name = "sunsoft.secef.z.report.wizard"
    _description = "Generation rapport Z SECeF"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Societe",
        required=True,
        default=lambda self:
            self.env.company,
    )

    period_end = fields.Datetime(
        string="Cloturer jusqu'au",
        required=True,
        default=fields.Datetime.now,
    )

    last_z_id = fields.Many2one(
        comodel_name="sunsoft.secef.report",
        string="Dernier rapport Z",
        compute="_compute_last_z_id",
        readonly=True,
    )

    def _compute_last_z_id(self):

        Report = self.env[
            "sunsoft.secef.report"
        ]

        for wizard in self:

            if not wizard.company_id:
                wizard.last_z_id = False
                continue

            wizard.last_z_id = (
                Report._secef_last_z(
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
                    "un rapport Z."
                )
            )

        report = (
            self.env[
                "sunsoft.secef.report"
            ]
            .generate_z(
                company=self.company_id,
                period_end=self.period_end,
            )
        )

        return {
            "type":
                "ir.actions.act_window",

            "name":
                _("Rapport Z SECeF"),

            "res_model":
                "sunsoft.secef.report",

            "res_id":
                report.id,

            "view_mode":
                "form",

            "target":
                "current",
        }
