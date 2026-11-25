from odoo import Command, fields
from odoo.exceptions import UserError
from odoo.tests import Form, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSecefRefund(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.write({
            "secef_enabled": True,
            "secef_environment": "test",
            "secef_sfe_id": "SUNAPPTEST",
            "vat": "00225673B",
        })
        cls.partner = cls.env["res.partner"].create({
            "name": "Client Avoir SECeF Test",
            "secef_customer_type": "PM",
            "vat": "12345678A",
        })
        cls.tax_group = cls.env["account.tax.group"].create({
            "name": "TVA SECeF Avoir Test",
            "company_id": cls.company.id,
        })

        cls.tax = cls.env["account.tax"].create({
            "name": "TVA 18% SECeF Avoir Test",
            "amount": 18.0,
            "amount_type": "percent",
            "type_tax_use": "sale",
            "price_include": False,
            "company_id": cls.company.id,
            "tax_group_id": cls.tax_group.id,
            "secef_tax_group": "B",
        })
        cls.product_template = cls.env["product.template"].create({
            "name": "Produit Avoir SECeF Test",
            "list_price": 1000.0,
            "secef_item_type": "LOCBIE",
        })
        cls.product = cls.product_template.product_variant_id

    def _create_invoice(self, quantity=2.0, price_unit=1000.0):
        move_form = Form(
            self.env["account.move"].with_context(
                default_move_type="out_invoice"
            )
        )
        move_form.partner_id = self.partner
        move_form.invoice_date = fields.Date.today()
        with move_form.invoice_line_ids.new() as line:
            line.product_id = self.product
            line.quantity = quantity
            line.price_unit = price_unit
            line.tax_ids.clear()
            line.tax_ids.add(self.tax)
        move = move_form.save()
        move.action_post()
        return move

    def _create_refund(
        self,
        original=None,
        reason="COR",
        reference=None,
        quantity=2.0,
        price_unit=1000.0,
    ):
        move = self.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": self.partner.id,
            "invoice_date": fields.Date.today(),
            "company_id": self.company.id,
            "reversed_entry_id": original.id if original else False,
            "secef_refund_reason": reason,
            "secef_reference_number": reference,
            "invoice_line_ids": [
                Command.create({
                    "product_id": self.product.id,
                    "name": self.product.display_name,
                    "quantity": quantity,
                    "price_unit": price_unit,
                    "tax_ids": [Command.set(self.tax.ids)],
                }),
            ],
        })
        move.action_post()
        return move

    def test_01_invoice_stays_fv(self):
        move = self._create_invoice()
        payload = move._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["invoice_type"],
            "FV",
        )
        self.assertNotIn(
            "refund_reason",
            payload["invoice"],
        )
        self.assertNotIn(
            "reference_number",
            payload["invoice"],
        )

    def test_02_refund_is_fa(self):
        invoice = self._create_invoice()
        invoice.write({
            "secef_mid": "DT02200630-1",
            "secef_total_counter": 92,
        })
        refund = self._create_refund(
            original=invoice,
            reason="COR",
        )
        payload = refund._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["invoice_type"],
            "FA",
        )
        self.assertEqual(
            payload["invoice"]["refund_reason"],
            "COR",
        )
        self.assertEqual(
            payload["invoice"]["reference_number"],
            "DT02200630-1-92",
        )

    def test_03_ran_uses_original_invoice(self):
        invoice = self._create_invoice()
        invoice.write({
            "secef_mid": "DT02200630-1",
            "secef_total_counter": 92,
        })
        refund = self._create_refund(
            original=invoice,
            reason="RAN",
        )
        payload = refund._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["refund_reason"],
            "RAN",
        )
        self.assertEqual(
            payload["invoice"]["reference_number"],
            "DT02200630-1-92",
        )

    def test_04_ram_uses_original_invoice(self):
        invoice = self._create_invoice()
        invoice.write({
            "secef_mid": "DT02200630-1",
            "secef_total_counter": 92,
        })
        refund = self._create_refund(
            original=invoice,
            reason="RAM",
        )
        payload = refund._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["refund_reason"],
            "RAM",
        )
        self.assertEqual(
            payload["invoice"]["reference_number"],
            "DT02200630-1-92",
        )

    def test_05_rrr_does_not_require_reference(self):
        refund = self._create_refund(
            reason="RRR",
        )
        payload = refund._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["invoice_type"],
            "FA",
        )
        self.assertEqual(
            payload["invoice"]["refund_reason"],
            "RRR",
        )
        self.assertNotIn(
            "reference_number",
            payload["invoice"],
        )

    def test_05b_export_refund_inherits_ea(
        self,
    ):
        invoice = self._create_invoice()

        invoice.secef_sale_type = "export"

        invoice.write({
            "secef_mid": "MID-EXPORT-001",
            "secef_total_counter": 501,
        })

        refund = self._create_refund(
            original=invoice,
            reason="COR",
        )

        self.assertEqual(
            refund.secef_sale_type,
            "local",
        )

        self.assertEqual(
            refund.secef_effective_sale_type,
            "export",
        )

        payload = refund._prepare_secef_payload()

        self.assertEqual(
            payload["invoice"]["invoice_type"],
            "EA",
        )

        self.assertEqual(
            payload["invoice"]["reference_number"],
            "MID-EXPORT-001-501",
        )

    def test_05c_manual_export_refund_is_ea(
        self,
    ):
        refund = self._create_refund(
            original=None,
            reason="COR",
            reference="MID-MANUAL-42",
        )

        refund.secef_sale_type = "export"

        payload = refund._prepare_secef_payload()

        self.assertEqual(
            refund.secef_effective_sale_type,
            "export",
        )

        self.assertEqual(
            payload["invoice"]["invoice_type"],
            "EA",
        )

        self.assertEqual(
            payload["invoice"]["reference_number"],
            "MID-MANUAL-42",
        )

    def test_05d_refund_has_no_psvb(
        self,
    ):
        self.partner.secef_psvb_group = "A"

        invoice = self._create_invoice()

        invoice.write({
            "secef_mid": "MID-PSVB-001",
            "secef_total_counter": 502,
        })

        refund = self._create_refund(
            original=invoice,
            reason="COR",
        )

        self.assertFalse(
            refund.secef_psvb_group
        )

        payload = (
            refund._prepare_secef_payload()
        )

        self.assertEqual(
            refund.secef_psvb_amount,
            0.0,
        )

        self.assertNotIn(
            "psvb",
            payload["invoice"],
        )

    def test_06_refund_requires_reason(self):
        refund = self._create_refund(
            reason=False,
            reference="INV/TEST/001",
        )
        with self.assertRaisesRegex(
            UserError,
            "nature SECeF",
        ):
            refund._prepare_secef_payload()

    def test_07_refund_requires_reference_without_original(self):
        refund = self._create_refund(
            reason="COR",
        )
        with self.assertRaisesRegex(
            UserError,
            "référence",
        ):
            refund._prepare_secef_payload()

    def test_08_manual_reference_is_used(self):
        refund = self._create_refund(
            reason="COR",
            reference="INV/HIST/00001",
        )
        payload = refund._prepare_secef_payload()
        self.assertEqual(
            payload["invoice"]["reference_number"],
            "INV/HIST/00001",
        )

    def test_08b_linked_refund_requires_original_mcf_reference(self):
        invoice = self._create_invoice()

        refund = self._create_refund(
            original=invoice,
            reason="COR",
            reference="INV/HIST/00001",
        )

        with self.assertRaisesRegex(
            UserError,
            "MID",
        ):
            refund._prepare_secef_payload()

    def test_09_refund_amounts_are_positive(self):
        invoice = self._create_invoice(
            quantity=2.0,
            price_unit=1000.0,
        )
        invoice.write({
            "secef_mid": "DT02200630-1",
            "secef_total_counter": 92,
        })
        refund = self._create_refund(
            original=invoice,
            reason="COR",
            quantity=2.0,
            price_unit=1000.0,
        )
        payload = refund._prepare_secef_payload()
        item = payload["items"][0]
        self.assertEqual(
            item["quantity"],
            "2",
        )
        self.assertEqual(
            item["unit_price"],
            "1000",
        )
        self.assertEqual(
            item["amount"],
            "2360",
        )

    def test_10_certified_refund_is_locked(self):
        invoice = self._create_invoice()
        refund = self._create_refund(
            original=invoice,
            reason="COR",
        )
        refund.write({
            "secef_state": "certified",
        })
        with self.assertRaises(UserError):
            refund.write({
                "secef_refund_reason": "RAM",
            })
        with self.assertRaises(UserError):
            refund.button_draft()