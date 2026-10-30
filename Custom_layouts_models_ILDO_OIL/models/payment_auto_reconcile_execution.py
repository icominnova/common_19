from collections import Counter, defaultdict
from html import escape

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError


class IldoPaymentAutoReconcileExecution(models.TransientModel):
    _inherit = 'ildo.payment.auto.reconcile.wizard'

    confirm_real_movements = fields.Boolean(
        string='Je confirme que ces mouvements ont réellement eu lieu et ne sont pas déjà importés',
    )
    execution_report_html = fields.Html(string='Résultat d’exécution', readonly=True)

    def _execution_candidates(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('La date de début doit précéder la date de fin.'))
        return self.env['account.payment'].search([
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', 'in', self.env.companies.ids),
            ('journal_id.type', 'in', ['bank', 'cash']),
            ('state', 'in', ['in_process', 'paid']),
        ], order='journal_id,date,id')

    def _execution_blocker(self, payment, invoice_counts):
        journal = payment.journal_id
        currency = journal.currency_id or payment.company_id.currency_id
        if payment.currency_id.is_zero(payment.amount):
            return 'Montant nul'
        if payment.payment_type != 'inbound':
            return 'Paiement sortant non encore testé'
        if not payment.partner_id:
            return 'Partenaire manquant'
        if payment.currency_id != currency:
            return 'Devise différente du journal'
        if journal.company_id != payment.company_id:
            return 'Société du journal différente'
        if not journal.default_account_id or not journal.suspense_account_id:
            return 'Compte de liquidité ou attente manquant'
        if payment.move_id:
            return 'Paiement avec écriture (cas non testé)'
        if payment.reconciled_statement_line_ids:
            return 'Paiement déjà rapproché'
        if any(invoice_counts[i.id] > 1 for i in payment.invoice_ids):
            return 'Facture partagée par plusieurs paiements dans la période'
        if len(payment.invoice_ids) > 1:
            return 'Paiement multi-factures non testé'
        if payment.invoice_ids:
            inv = payment.invoice_ids
            if inv.state != 'posted' or inv.company_id != payment.company_id:
                return 'Facture non comptabilisée ou autre société'
            if inv.move_type != 'out_invoice' or inv.partner_id != payment.partner_id:
                return 'Facture ou partenaire incompatible'
            if inv.currency_id != payment.currency_id:
                return 'Devise facture différente'
            if inv.currency_id.compare_amounts(inv.amount_residual, payment.amount) < 0:
                return 'Paiement supérieur au solde de la facture'
            # Vérification hors de la plage aussi, y compris les autres journaux.
            if self.env['account.payment'].search_count([
                ('id', '!=', payment.id),
                ('invoice_ids', 'in', inv.ids),
                ('state', 'in', ['in_process', 'paid']),
                ('amount', '>', 0),
            ]):
                return 'Autre paiement existant sur cette facture'
        else:
            if not payment.partner_id.property_account_receivable_id:
                return 'Compte client absent'
        st_model = self.env['account.bank.statement.line']
        if st_model.search_count([('ildo_source_payment_id', '=', payment.id)]):
            return 'Transaction ILDO déjà créée'
        if self.env['account.move.line'].search_count([
            ('payment_lines_ids', 'in', [payment.id]),
        ]):
            return 'Ligne comptable déjà liée au paiement'
        # Une transaction ILDO d'un autre paiement correctement
        # rapproché ne constitue pas un doublon du paiement courant.
        #
        # En revanche, une transaction importée, non identifiée
        # ou incohérente reste bloquante par précaution.
        same_amount_lines = st_model.search([
            ('journal_id', '=', journal.id),
            ('company_id', '=', payment.company_id.id),
            ('amount', '=', payment.amount),
        ])

        for st_line in same_amount_lines:
            source = st_line.ildo_source_payment_id

            if not source:
                return 'Transaction potentiellement importée de même montant'

            if source == payment:
                return 'Transaction ILDO déjà créée pour ce paiement'

            linked = st_line.move_id.line_ids.filtered(
                lambda line: source in line.payment_lines_ids
            )

            if not (
                st_line.is_reconciled
                and linked
                and source.state == 'paid'
                and source.journal_id == journal
                and source.company_id == payment.company_id
            ):
                return 'Transaction ILDO existante à vérifier'

        return None

    def action_execute_ildo_reconciliation(self):
        self.ensure_one()
        enabled = self.env['ir.config_parameter'].sudo().get_param(
            'ildo_auto_reconcile.execution_enabled',
            default='False',
        )
        if enabled != 'True':
            raise UserError(_(
                'La réconciliation automatique n’est pas activée '
                'sur cette base de données. '
                'Contactez votre administrateur Odoo.'
            ))
        if not self.env.user.has_group('account.group_account_manager'):
            raise UserError(_('Seul un responsable comptable peut lancer ce traitement.'))
        if not self.confirm_real_movements:
            raise UserError(_('Confirmez la réalité des mouvements et leur absence des imports.'))
        if 'account.batch.payment' not in self.env.registry.models:
            raise UserError(_('Le module account_batch_payment doit être installé.'))

        payments = self._execution_candidates()
        counts = Counter(i.id for p in payments if p.amount > 0 for i in p.invoice_ids)
        results = []
        for p in payments:
            reason = self._execution_blocker(p, counts)
            if reason:
                results.append((p, 'Ignoré : ' + reason))
                continue
            try:
                with self.env.cr.savepoint():
                    # Empêche deux actions simultanées de traiter le même paiement.
                    self.env.cr.execute(
                        'SELECT id FROM account_payment WHERE id = %s FOR UPDATE NOWAIT',
                        [p.id],
                    )
                    p.invalidate_recordset()
                    reason = self._execution_blocker(p, counts)
                    if reason:
                        results.append((p, 'Ignoré : ' + reason))
                        continue
                    invoice = p.invoice_ids
                    invoice_residual_before = (
                        invoice.amount_residual if invoice else None
                    )

                    statement = self.env['account.bank.statement.line'].with_company(
                        p.company_id
                    ).with_context(
                        ildo_defer_reconcile_piece=True
                    ).create({
                        'journal_id': p.journal_id.id,
                        'company_id': p.company_id.id,
                        'date': p.date,
                        'amount': p.amount,
                        'partner_id': p.partner_id.id,
                        'payment_ref': p.name,
                        'ildo_source_payment_id': p.id,
                    })
                    counterpart_vals = p.with_company(
                        p.company_id
                    )._get_amls_for_payment_without_move()
                    if not counterpart_vals:
                        raise ValidationError(_('Aucune contrepartie calculée.'))
                    statement.with_company(p.company_id)._reconcile_payments(
                        p, counterpart_vals,
                    )
                    self.env.flush_all()
                    statement.invalidate_recordset()
                    p.invalidate_recordset()
                    linked = statement.move_id.line_ids.filtered(
                        lambda line: p in line.payment_lines_ids
                    )
                    if not statement.is_reconciled or not linked or p.state != 'paid':
                        raise ValidationError(_('Rapprochement ou lien de paiement non confirmé.'))

                    if invoice:
                        invoice.invalidate_recordset()
                        expected_residual = invoice_residual_before - p.amount
                        if invoice.currency_id.compare_amounts(
                            invoice.amount_residual,
                            expected_residual,
                        ) != 0:
                            raise ValidationError(_(
                                'Solde de facture incorrect après rapprochement : '
                                'attendu %(expected)s, obtenu %(actual)s',
                                expected=expected_residual,
                                actual=invoice.amount_residual,
                            ))

                    # Attribuer la pièce seulement après tous les contrôles.
                    # L'attribution reste dans le savepoint du paiement.
                    statement._ildo_assign_reconcile_piece_number()
                    statement.invalidate_recordset()

                    if not statement.ildo_reconcile_piece_number:
                        raise ValidationError(_(
                            'Numéro de pièce non attribué après réconciliation.'
                        ))

                    results.append((
                        p,
                        'Réconcilié : transaction %s, pièce %s' % (
                            statement.id,
                            statement.ildo_reconcile_piece_number,
                        ),
                    ))
            except Exception as exc:
                results.append((p, 'Échec — annulé : %s' % str(exc)[:160]))

        by_journal = defaultdict(Counter)
        lines = []
        for p, status in results:
            by_journal[p.journal_id.display_name][status.split(' :', 1)[0]] += 1
            lines.append('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                escape(p.journal_id.display_name), escape(p.name or ''), escape(status),
            ))
        summary = ''.join('<p><b>%s</b> : %s</p>' % (
            escape(journal), ', '.join('%s %s' % (escape(k), v) for k, v in sorted(stats.items()))
        ) for journal, stats in sorted(by_journal.items()))
        self.execution_report_html = (
            '<p><strong>Résultat de l’exécution sur odoo_local</strong></p>'
            + summary
            + '<table class="table table-sm table-bordered"><thead><tr>'
            '<th>Journal</th><th>Paiement</th><th>Résultat</th>'
            '</tr></thead><tbody>' + ''.join(lines) + '</tbody></table>'
        )
        self.confirm_real_movements = False
        success_count = sum(
            status.startswith('Réconcilié :')
            for _, status in results
        )
        skipped_count = sum(
            status.startswith('Ignoré :')
            for _, status in results
        )
        failed_count = len(results) - success_count - skipped_count

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Réconciliation terminée'),
                'message': _(
                    '%(success)s réconcilié(s), '
                    '%(skipped)s ignoré(s), '
                    '%(failed)s échec(s).',
                    success=success_count,
                    skipped=skipped_count,
                    failed=failed_count,
                ),
                'type': (
                    'warning' if failed_count or skipped_count
                    else 'success'
                ),
                'sticky': bool(failed_count),
                'next': {
                    'type': 'ir.actions.act_window_close',
                },
            },
        }


    def action_simulate(self):
        self.ensure_one()

        payments = self._execution_candidates()
        counts = Counter(
            invoice.id
            for payment in payments
            if payment.amount > 0
            for invoice in payment.invoice_ids
        )

        grouped = defaultdict(lambda: {
            "total": 0,
            "ready": 0,
            "blocked": 0,
        })
        details = []

        for payment in payments:
            journal = payment.journal_id.display_name
            reason = self._execution_blocker(payment, counts)

            grouped[journal]["total"] += 1

            if reason:
                grouped[journal]["blocked"] += 1
                status = "Bloqué : " + reason
            else:
                grouped[journal]["ready"] += 1
                status = "Candidat aux contrôles actuels"

            details.append(
                "<tr>"
                "<td>%s</td>"
                "<td>%s</td>"
                "<td>%s</td>"
                "<td>%s</td>"
                "</tr>" % (
                    escape(journal),
                    escape(payment.name or ""),
                    escape(str(payment.amount)),
                    escape(status),
                )
            )

        summary_rows = []

        for journal, item in sorted(grouped.items()):
            summary_rows.append(
                "<tr>"
                "<td>%s</td>"
                "<td>%s</td>"
                "<td>%s</td>"
                "<td>%s</td>"
                "</tr>" % (
                    escape(journal),
                    item["total"],
                    item["ready"],
                    item["blocked"],
                )
            )

        total_ready = sum(item["ready"] for item in grouped.values())
        total_blocked = sum(item["blocked"] for item in grouped.values())

        self.preview_html = (
            "<p><strong>Simulation uniquement : "
            "aucune transaction créée.</strong></p>"
            "<p>Paiements présélectionnés : %s | "
            "Candidats aux contrôles actuels : %s | "
            "Bloqués : %s</p>"
            "<table class='table table-sm table-bordered w-100'>"
            "<thead><tr>"
            "<th>Journal</th>"
            "<th>Paiements</th>"
            "<th>Candidats</th>"
            "<th>Bloqués</th>"
            "</tr></thead><tbody>%s</tbody></table>"
            "<p><strong>Détail des paiements et des motifs</strong></p>"
            "<table class='table table-sm table-bordered w-100'>"
            "<thead><tr>"
            "<th>Journal</th>"
            "<th>Paiement</th>"
            "<th>Montant</th>"
            "<th>Résultat</th>"
            "</tr></thead><tbody>%s</tbody></table>"
            "<p>Les candidats doivent encore correspondre à des "
            "mouvements bancaires ou de caisse réellement constatés. "
            "Le contrôle est recalculé avant chaque exécution.</p>"
        ) % (
            len(payments),
            total_ready,
            total_blocked,
            "".join(summary_rows),
            "".join(details),
        )

        self.confirm_real_movements = False

        return {
            "type": "ir.actions.act_window",
            "name": "Réconciliation automatique — Simulation",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }
