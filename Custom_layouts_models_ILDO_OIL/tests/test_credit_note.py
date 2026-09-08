from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged("post_install", "-at_install")
class TestIldoCreditNote(AccountTestInvoicingCommon):

    def _create_invoice(self, move_type="out_invoice"):
        return self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": self.partner_a.id,
            "invoice_date": fields.Date.context_today(self.env["account.move"]),
            "invoice_line_ids": [Command.create({
                "product_id": self.product_a.id,
                "quantity": 10,
                "price_unit": 100,
                "discount": 5,
                "tax_ids": [Command.set(self.tax_sale_a.ids)],
            })],
        })

    def test_credit_note_is_linked_editable_draft(self):
        invoice = self._create_invoice()
        order = self.env["sale.order"].create({"partner_id": self.partner_a.id})
        sale_line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.product_a.id,
            "product_uom_qty": 10,
            "price_unit": 100,
        })
        invoice.invoice_line_ids.sale_line_ids = sale_line
        invoice.action_post()
        # A manually supplied number must never become the new credit note number.
        invoice.ildo_invoice_number = invoice.name
        original_residual = invoice.amount_residual

        action = invoice.action_ildo_create_credit_note()
        refund = self.env["account.move"].browse(action["res_id"])
        self.assertEqual(action["target"], "current")
        self.assertEqual(refund.move_type, "out_refund")
        self.assertEqual(refund.state, "draft")
        self.assertEqual(refund.reversed_entry_id, invoice)
        self.assertEqual(refund.partner_id, invoice.partner_id)
        self.assertEqual(refund.journal_id, invoice.journal_id)
        self.assertEqual(refund.currency_id, invoice.currency_id)
        self.assertFalse(refund.ildo_invoice_number)
        self.assertEqual(refund.auto_post, "no")
        self.assertEqual(refund.amount_total, invoice.amount_total)
        self.assertEqual(refund.invoice_line_ids.sale_line_ids, sale_line)
        self.assertEqual(refund.invoice_line_ids.quantity, 10)
        self.assertEqual(refund.invoice_line_ids.discount, 5)
        self.assertEqual(refund.invoice_line_ids.tax_ids, invoice.invoice_line_ids.tax_ids)
        refund.invoice_line_ids.quantity = 2
        self.assertEqual(invoice.invoice_line_ids.quantity, 10)
        self.assertEqual(invoice.state, "posted")
        self.assertEqual(invoice.amount_residual, original_residual)

    def test_reject_draft_and_credit_note(self):
        invoice = self._create_invoice()
        with self.assertRaises(UserError):
            invoice.action_ildo_create_credit_note()
        refund = self._create_invoice(move_type="out_refund")
        refund.action_post()
        with self.assertRaises(UserError):
            refund.action_ildo_create_credit_note()
