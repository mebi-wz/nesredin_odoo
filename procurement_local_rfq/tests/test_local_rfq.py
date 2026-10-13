from odoo.tests.common import TransactionCase, tagged
import logging
_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install')
class TestLocalRFQ(TransactionCase):

    def setUp(self):
        super(TestLocalRFQ, self).setUp()
        self.PR = self.env['local.purchase.requisition']
        self.RFQ = self.env['local.rfq']
        self.Product = self.env['product.product']
        self.Partner = self.env['res.partner']
        
        self.product_1 = self.Product.create({'name': 'RFQ Product 1'})
        self.product_2 = self.Product.create({'name': 'RFQ Product 2'})
        self.vendor = self.Partner.create({'name': 'Test Vendor', 'supplier_rank': 1})

    def test_01_create_rfq_from_pr(self):
        """Test creating an RFQ from a PR."""
        pr1 = self.PR.create({
            'line_ids': [(0, 0, {'product_id': self.product_1.id, 'quantity': 10})]
        })
        
        # Create RFQ and link the PR
        rfq = self.RFQ.create({
            'requisition_id': pr1.id
        })
        
        # Add vendor and trigger onchange
        rfq.vendor_ids = [(4, self.vendor.id)]
        rfq._onchange_vendor_ids()
        
        # Verify that lines from the PR are added to the comparison
        comparison_lines = rfq.quote_ids
        products_in_rfq = comparison_lines.mapped('product_id')
        self.assertIn(self.product_1, products_in_rfq)
        self.assertEqual(len(comparison_lines), 1)

    def test_02_submit_approve_create_po(self):
        """Test single approval workflow: Submit -> Approve -> Create PO."""
        pr = self.PR.create({
            'line_ids': [(0, 0, {'product_id': self.product_1.id, 'quantity': 5, 'unit_price': 100.0})]
        })
        rfq = self.RFQ.create({
            'requisition_id': pr.id,
            'vendor_ids': [(4, self.vendor.id)],
        })
        rfq._onchange_vendor_ids()
        self.assertTrue(rfq.quote_ids)
        # Select winning quote
        rfq.quote_ids[0].write({'selected': True, 'price_unit': 95.0})
        
        # 1. Submit
        rfq.action_submit()
        self.assertEqual(rfq.state, 'submitted', "RFQ should be in 'submitted' state after submit")

        # 2. Approve (Single approval)
        rfq.action_approve()
        self.assertEqual(rfq.state, 'approved', "RFQ should be in 'approved' state after single approval")

        # 3. Create PO
        rfq.action_create_po()
        self.assertEqual(rfq.state, 'po_created', "RFQ should be in 'po_created' state after PO creation")
        self.assertEqual(rfq.po_count, 1, "One PO should have been created")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        print("✅ All local rfq tests passed successfully!")
        _logger.info("✅ All local rfq tests passed successfully!")