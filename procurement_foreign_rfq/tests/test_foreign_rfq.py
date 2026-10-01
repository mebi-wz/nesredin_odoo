from odoo.tests.common import TransactionCase, tagged
from odoo import fields

@tagged('post_install', '-at_install')
class TestForeignRFQ(TransactionCase):

    def setUp(self):
        super(TestForeignRFQ, self).setUp()
        self.Product = self.env['product.product']
        self.vendor = self.env['res.partner'].create({
            'name': 'Test Supplier Partner',
            'supplier_rank': 1,
        })
        self.product = self.Product.create({
            'name': 'Test Foreign Product',
            'type': 'consu'
        })

    def test_foreign_rfq_workflow_and_currency_request(self):
        """Test the full workflow of Foreign RFQ, auto currency request creation, and approval."""
        # 1. Create a Foreign RFQ in Draft state
        rfq = self.env['foreign.rfq'].create({
            'vendor_id': self.vendor.id,
            'proforma_invoice_no': 'PI-TEST-123',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 10.0,
                'price_unit': 15.0,
            })]
        })

        self.assertEqual(rfq.state, 'draft', "Initial RFQ state should be draft")
        self.assertEqual(rfq.amount_total, 150.0, "Total amount should be 150.0 USD")
        self.assertEqual(rfq.currency_count, 0, "No currency request should exist initially")

        # 2. Transition draft -> submitted (Submit button)
        rfq.action_approve()
        self.assertEqual(rfq.state, 'submitted', "RFQ state should transition to submitted")

        # 3. Transition submitted -> verified (Verify button)
        rfq.action_approve()
        self.assertEqual(rfq.state, 'verified', "RFQ state should transition to verified")

        # 4. Transition verified -> pending_currency (CEO Approve button)
        rfq.action_approve()
        self.assertEqual(rfq.state, 'pending_currency', "RFQ state should transition to pending_currency")

        # 5. Check if Currency Request was automatically created
        self.assertEqual(rfq.currency_count, 1, "A currency request should have been automatically created")
        currency_request = rfq.currency_request_ids[0]
        self.assertEqual(currency_request.state, 'draft', "New currency request should be in draft state")
        self.assertEqual(currency_request.supplier_id, self.vendor, "Supplier should match RFQ vendor")
        self.assertEqual(currency_request.proforma_invoice, 'PI-TEST-123', "Proforma invoice number should match")
        self.assertEqual(currency_request.total_amount_usd, 150.0, "Amount should match RFQ total amount")
        self.assertTrue(currency_request.amount_in_word, "Amount in word should be populated")

        # 6. Progress the Currency Request to approved
        currency_request.action_queue()
        self.assertEqual(currency_request.state, 'queued')
        
        currency_request.action_progress()
        self.assertEqual(currency_request.state, 'progress')
        
        currency_request.action_approve()
        self.assertEqual(currency_request.state, 'approved')

        # 7. Check if RFQ state is updated to approved (Currency Approved)
        self.assertEqual(rfq.state, 'approved', "RFQ state should automatically transition to approved once currency is approved")
