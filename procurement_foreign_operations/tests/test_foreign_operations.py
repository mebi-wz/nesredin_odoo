from odoo.tests.common import TransactionCase, tagged
from odoo import fields
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

@tagged('post_install', '-at_install')
class TestForeignOperations(TransactionCase):


    def setUp(self):

        super(TestForeignOperations, self).setUp()
        self.vendor = self.env['res.partner'].create({'name': 'Test Vendor'})
        self.currency = self.env.ref('base.USD')
        self.bank = self.env['res.bank'].create({'name': 'Test Bank'})
        
        # Ensure a purchase journal exists
        self.journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not self.journal:
            # Create a basic account for the journal
            account = self.env['account.account'].create({
                'name': 'Test Expense Account',
                'code': 'TESTEXP',
                'account_type': 'expense',
                'reconcile': True,
            })
            self.journal = self.env['account.journal'].create({
                'name': 'Test Purchase Journal',
                'code': 'TPJ',
                'type': 'purchase',
                'default_account_id': account.id,
            })

        # Ensure vendor has a payable account (required for bill creation)
        payable_account = self.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_ids', 'in', [self.env.company.id])
        ], limit=1)
        if not payable_account:
            payable_account = self.env['account.account'].create({
                'name': 'Test Payable Account',
                'code': 'TESTPAY',
                'account_type': 'liability_payable',
                'reconcile': True,
            })
        self.vendor.property_account_payable_id = payable_account

        # Create a PO
        self.po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'request_type': 'foreign',
            'order_line': [
                (0, 0, {
                    'name': 'Test Product',
                    'product_id': self.env['product.product'].create({'name': 'Test Product'}).id,
                    'product_qty': 10,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 100,
                    'date_planned': fields.Datetime.now(),
                })
            ]
        })

    def test_01_lc_lifecycle(self):
        """Test LC creation and state transitions"""
        lc = self.env['foreign.lc'].create({
            'purchase_order_id': self.po.id,
            'lc_number': 'LC/TEST/001',
            'amount': 1000.0,
            'currency_id': self.currency.id,
            'issuing_bank': self.bank.id,
        })
        self.assertEqual(lc.state, 'draft', "LC should start in draft")
        
        lc.action_issue()
        self.assertEqual(lc.state, 'issued', "LC should be in issued state")
        
        lc.action_activate()
        self.assertEqual(lc.state, 'active', "LC should be in active state")
        self.assertTrue(lc.start_date, "Start date should be set upon activation")

    def test_02_payment_request_lifecycle(self):
        """Test Foreign Payment Request creation and state transitions"""
        # We need a product with landed_cost_ok for the payment line
        product = self.env['product.product'].create({
            'name': 'Landed Cost Test',
            'landed_cost_ok': True,
        })
        
        payment_request = self.env['foreign.payment.request'].create({
            'purchase_order_id': self.po.id,
            'vendor_id': self.vendor.id,
            'amount': 500.0,
            'currency_id': self.currency.id,
            'payment_type': 'landed_cost',
            'line_ids': [
                (0, 0, {
                    'product_id': product.id,
                    'quantity': 1,
                    'price_unit': 500.0,
                })
            ]
        })
        self.assertEqual(payment_request.state, 'draft', "Payment request should start in draft")
        
        payment_request.action_submit()
        self.assertEqual(payment_request.state, 'submitted', "Payment request should be in submitted state")
        
        payment_request.action_approve()
        self.assertEqual(payment_request.state, 'approved', "Payment request should be in approved state")
        
        payment_request.action_pay()
        self.assertEqual(payment_request.state, 'paid', "Payment request should be in paid state")

    def test_03_po_extension_fields(self):
        """Test saving fields on PO extension"""
        self.po.write({
            'import_permit_number': 'PERMIT/001',
            'vessel_name': 'Sea Express',
            'bl_awb_number': 'BL123456',
            'declaration_number': 'DEC/789',
        })
        self.assertEqual(self.po.import_permit_number, 'PERMIT/001')
        self.assertEqual(self.po.vessel_name, 'Sea Express')
        self.assertEqual(self.po.bl_awb_number, 'BL123456')
        self.assertEqual(self.po.declaration_number, 'DEC/789')

    def test_04_po_line_extensions(self):
        """Test the new line_no and USD fields on PO lines"""
        line = self.po.order_line[0]
        # These fields were added in the previous task
        self.assertEqual(line.line_no, 1, "First line should have line_no 1")
        self.assertTrue(line.product_description, "Product description should be populated")
        
        # Test USD fields
        line.price_unit_usd = 50.0
        self.assertEqual(line.price_subtotal_usd, 500.0, "Subtotal USD should be quantity(10) * unit_usd(50)")

    def test_05_lc_expiry_calculation(self):
        """Test the days_to_expiry and is_expired logic"""
        today = fields.Date.today()
        future_date = fields.Date.add(today, days=10)
        past_date = fields.Date.add(today, days=-5)
        
        lc = self.env['foreign.lc'].create({
            'purchase_order_id': self.po.id,
            'lc_number': 'LC/EXPIRE/001',
            'amount': 100.0,
            'expiry_date': future_date,
        })
        self.assertFalse(lc.is_expired, "Future LC should not be expired")
        self.assertGreater(lc.days_to_expiry, 0)
        
        lc.expiry_date = past_date
        self.assertTrue(lc.is_expired, "Past LC should be expired")
        self.assertLess(lc.days_to_expiry, 0)

    def test_06_amendment_count(self):
        """Test amendment count calculation"""
        lc = self.env['foreign.lc'].create({
            'purchase_order_id': self.po.id,
            'lc_number': 'LC/AMD/001',
            'amount': 1000.0,
        })
        self.assertEqual(lc.amendment_count, 0)

        self.env['foreign.lc.amendment'].create({
            'lc_id': lc.id,
            'amendment_no': 'A1',
            'amendment_date': fields.Date.today(),
            'description': 'First amendment',
        })
        self.assertEqual(lc.amendment_count, 1)

    def test_07_custom_split_method(self):
        """Test custom split method based on Customs Product Cost"""
        # Create a FIFO/real_time product category
        categ_fifo = self.env['product.category'].create({
            'name': 'FIFO Test Category',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
        })
        
        # Create storable products using FIFO
        p1 = self.env['product.product'].create({
            'name': 'FIFO Product 1',
            'categ_id': categ_fifo.id,
            'standard_price': 100.0,
            'is_storable': True,
        })
        p2 = self.env['product.product'].create({
            'name': 'FIFO Product 2',
            'categ_id': categ_fifo.id,
            'standard_price': 200.0,
            'is_storable': True,
        })

        # Create a purchase order
        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'request_type': 'foreign',
            'order_line': [
                (0, 0, {
                    'name': p1.name,
                    'product_id': p1.id,
                    'product_qty': 2.0,
                    'price_unit': 100.0,
                    'customs_product_cost': 150.0,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'date_planned': fields.Datetime.now(),
                }),
                (0, 0, {
                    'name': p2.name,
                    'product_id': p2.id,
                    'product_qty': 3.0,
                    'price_unit': 200.0,
                    'customs_product_cost': 250.0,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'date_planned': fields.Datetime.now(),
                })
            ]
        })

        # Create LC to confirm foreign PO
        self.env['foreign.lc'].create({
            'purchase_order_id': po.id,
            'lc_number': 'LC/TEST/CUSTOMS',
            'amount': 800.0,
        })
        po.button_confirm()

        # Validate the picking
        picking = po.picking_ids[0]
        # In Odoo 17+, you must set quantities on the stock moves to validate
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_approval=True).button_validate()

        # Ensure a general journal exists for landed costs
        general_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        if not general_journal:
            general_journal = self.env['account.journal'].create({
                'name': 'General Test Journal',
                'code': 'GTJ',
                'type': 'general',
            })

        # Create Landed Cost record
        lc_rec = self.env['stock.landed.cost'].create({
            'picking_ids': [(6, 0, picking.ids)],
            'account_journal_id': general_journal.id,
        })

        # Create a landed cost product
        lc_product = self.env['product.product'].create({
            'name': 'Freight Cost',
            'landed_cost_ok': True,
            'split_method_landed_cost': 'by_customs_amount',
        })

        # Create Landed Cost Cost Line
        cost_line = self.env['stock.landed.cost.lines'].create({
            'cost_id': lc_rec.id,
            'product_id': lc_product.id,
            'price_unit': 1050.0,
            'split_method': 'by_customs_amount',
        })

        # Trigger Landed Cost valuation adjustments creation & computation
        lc_rec.compute_landed_cost()

        # Assert valuation adjustments are split correctly
        # Total customs amount = (150 * 2) + (250 * 3) = 300 + 750 = 1050
        # Line 1 (P1): 300 / 1050 * 1050 = 300
        # Line 2 (P2): 750 / 1050 * 1050 = 750
        p1_adj = lc_rec.valuation_adjustment_lines.filtered(lambda a: a.product_id == p1)
        p2_adj = lc_rec.valuation_adjustment_lines.filtered(lambda a: a.product_id == p2)

        self.assertEqual(len(p1_adj), 1)
        self.assertEqual(len(p2_adj), 1)
        self.assertAlmostEqual(p1_adj.additional_landed_cost, 300.0)
        self.assertAlmostEqual(p2_adj.additional_landed_cost, 750.0)

    def test_08_draft_landed_cost_validation_and_account_mapping(self):
        """Test Landed Cost drafting with customs cost validation and account mapping from vendor bill"""
        from odoo.exceptions import ValidationError

        categ_fifo = self.env['product.category'].create({
            'name': 'FIFO Test Category 2',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
        })
        
        product = self.env['product.product'].create({
            'name': 'FIFO Product 3',
            'categ_id': categ_fifo.id,
            'standard_price': 100.0,
            'is_storable': True,
        })

        po = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'request_type': 'foreign',
            'order_line': [
                (0, 0, {
                    'name': product.name,
                    'product_id': product.id,
                    'product_qty': 5.0,
                    'price_unit': 100.0,
                    'customs_product_cost': 0.0, # Start with 0 to test validation
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'date_planned': fields.Datetime.now(),
                })
            ]
        })

        self.env['foreign.lc'].create({
            'purchase_order_id': po.id,
            'lc_number': 'LC/TEST/DRAFT',
            'amount': 500.0,
        })
        po.button_confirm()

        picking = po.picking_ids[0]
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_approval=True).button_validate()

        # Create a landed cost product
        lc_product = self.env['product.product'].create({
            'name': 'Custom Broker Fee',
            'landed_cost_ok': True,
        })

        payment_request = self.env['foreign.payment.request'].create({
            'purchase_order_id': po.id,
            'vendor_id': self.vendor.id,
            'amount': 200.0,
            'currency_id': self.currency.id,
            'payment_type': 'landed_cost',
            'line_ids': [
                (0, 0, {
                    'product_id': lc_product.id,
                    'quantity': 1,
                    'price_unit': 200.0,
                })
            ]
        })
        payment_request.action_submit()
        payment_request.action_approve()

        # Verify that vendor bill is created
        self.assertTrue(payment_request.vendor_bill_id)

        # Try to draft landed cost; should fail because customs_product_cost is 0.0
        with self.assertRaises(ValidationError):
            po.action_draft_landed_cost()

        # Set customs cost
        po.order_line[0].customs_product_cost = 150.0

        # Change the account on the vendor bill line to a custom test account
        custom_mapping_account = self.env['account.account'].create({
            'name': 'Custom Mapping Account',
            'code': 'MAPEXP',
            'account_type': 'expense',
        })
        bill = payment_request.vendor_bill_id
        bill_line = bill.invoice_line_ids.filtered(lambda l: l.product_id == lc_product)[:1]
        self.assertTrue(bill_line)
        bill_line.account_id = custom_mapping_account.id

        # Now draft the landed cost
        res = po.action_draft_landed_cost()
        self.assertEqual(res.get('res_model'), 'stock.landed.cost')
        
        landed_cost = self.env['stock.landed.cost'].browse(res.get('res_id'))
        self.assertEqual(len(landed_cost.cost_lines), 1)
        
        # Verify that split method is 'by_customs_amount'
        self.assertEqual(landed_cost.cost_lines[0].split_method, 'by_customs_amount')
        
        # Verify that the account_id was taken from the payment bill line
        self.assertEqual(landed_cost.cost_lines[0].account_id.id, custom_mapping_account.id)

    def test_09_margin_modal_and_etb_billing(self):
        """Test margin modal action, margin bill currency, standard PO billing in ETB, payment request billing in ETB, and stock move pricing unit"""
        # 1. Test Margin Modal Action
        modal_action = self.po.action_open_margin_modal()
        self.assertEqual(modal_action.get('res_model'), 'purchase.order')
        self.assertEqual(modal_action.get('res_id'), self.po.id)
        self.assertEqual(modal_action.get('target'), 'new')
        view_id = modal_action.get('view_id')
        expected_view = self.env.ref('procurement_foreign_operations.view_purchase_order_margin_modal_form')
        self.assertEqual(view_id, expected_view.id)
        self.assertEqual(modal_action.get('context', {}).get('dialog_size'), 'extra-large')

        # 2. Test Margin Bill Creation in ETB
        # Set exchange rate on PO
        self.po.exchange_rate = 60.0
        # Create a margin installment line
        margin_account = self.env['account.account'].create({
            'name': 'Test Margin Account',
            'code': 'TESTMARG',
            'account_type': 'expense',
        })
        margin_line = self.env['purchase.import.margin'].create({
            'import_id': self.po.id,
            'margin_order': 'first_margin',
            'margin_percent': 10.0,
            'exchange_rate': 60.0,
            'usd_amount': 100.0,
            'etb_amount': 6000.0,
            'account_id': margin_account.id,
        })
        self.assertEqual(margin_line.etb_amount, 6000.0)

        # Create LC to confirm foreign PO
        self.env['foreign.lc'].create({
            'purchase_order_id': self.po.id,
            'lc_number': 'LC/TEST/MARGIN',
            'amount': 1000.0,
        })
        # Confirm PO to allow billing
        self.po.button_confirm()

        # Create bill from margin line
        bill_action = margin_line.action_create_bill()
        self.assertEqual(bill_action.get('res_model'), 'account.move')
        bill = self.env['account.move'].browse(bill_action.get('res_id'))
        
        # Verify bill currency is ETB and price unit is etb_amount
        self.assertEqual(bill.currency_id.name, 'ETB')
        self.assertEqual(len(bill.invoice_line_ids), 1)
        self.assertEqual(bill.invoice_line_ids[0].price_unit, 6000.0)

        # Verify billed quantity updates proportionally based on margin percent
        # self.po.order_line[0].product_qty is 10.0 (from setUpClass)
        # Billed margin percentage is 10.0%
        # So qty_invoiced should be 10.0 * 10% = 1.0
        po_line = self.po.order_line[0]
        self.assertEqual(po_line.qty_invoiced, 1.0)
        self.assertEqual(po_line.qty_to_invoice, 9.0)

        # What if margin bill is cancelled? It should not count.
        bill.button_cancel()
        # Trigger recompute
        self.po.order_line.modified(['qty_invoiced', 'qty_to_invoice'])
        self.assertEqual(po_line.qty_invoiced, 0.0)
        self.assertEqual(po_line.qty_to_invoice, 10.0)

        # 3. Test Standard PO Billing in ETB (when no margin lines exist)
        # Create a foreign PO with no margins
        po_no_margin = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'request_type': 'foreign',
            'exchange_rate': 55.0,
            'order_line': [
                (0, 0, {
                    'name': 'Test Product No Margin',
                    'product_id': self.env['product.product'].create({'name': 'Test Product No Margin'}).id,
                    'product_qty': 5,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 10,
                    'date_planned': fields.Datetime.now(),
                })
            ]
        })
        # Calculate price_unit_etb
        po_no_margin.order_line[0]._compute_etb_fields()
        self.assertEqual(po_no_margin.order_line[0].price_unit_etb, 550.0)

        # Prepare invoice vals
        inv_vals = po_no_margin._prepare_invoice()
        etb_currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ETB')], limit=1)
        self.assertEqual(inv_vals.get('currency_id'), etb_currency.id)

        # Prepare invoice line vals
        inv_line_vals = po_no_margin.order_line[0]._prepare_account_move_line()
        self.assertEqual(inv_line_vals.get('price_unit'), 550.0)

        # 4. Test Payment Request Billing (already in ETB)
        etb_currency = self.env['res.currency'].with_context(active_test=False).search([('name', '=', 'ETB')], limit=1)
        if etb_currency and not etb_currency.active:
            etb_currency.sudo().write({'active': True})
        product = self.env['product.product'].create({
            'name': 'Landed Cost Test 2',
            'landed_cost_ok': True,
        })
        payment_request = self.env['foreign.payment.request'].create({
            'purchase_order_id': self.po.id,
            'vendor_id': self.vendor.id,
            'amount': 200.0,
            'currency_id': etb_currency.id if etb_currency else self.env.company.currency_id.id,
            'payment_type': 'landed_cost',
            'exchange_rate': 1.0,
            'line_ids': [
                (0, 0, {
                    'product_id': product.id,
                    'quantity': 1,
                    'price_unit': 200.0,
                })
            ]
        })
        payment_request.action_submit()
        payment_request.action_approve()
        
        # Verify payment request bill currency is ETB and price unit is the direct ETB amount (200.0)
        self.assertTrue(payment_request.vendor_bill_id)
        pr_bill = payment_request.vendor_bill_id
        self.assertEqual(pr_bill.currency_id.name, 'ETB')
        self.assertEqual(pr_bill.invoice_line_ids[0].price_unit, 200.0)

        # 5. Test Stock Move Price Unit calculation
        pol = po_no_margin.order_line[0]
        calculated_price_unit = pol._get_stock_move_price_unit()
        self.assertEqual(calculated_price_unit, 550.0)

        # 6. Test Product Cost (standard_price) is updated to ETB price on stock move validation
        # Create a first payment request for po_no_margin so we can draft a landed cost
        pr1 = self.env['foreign.payment.request'].create({
            'purchase_order_id': po_no_margin.id,
            'vendor_id': self.vendor.id,
            'amount': 200.0,
            'currency_id': etb_currency.id if etb_currency else self.env.company.currency_id.id,
            'payment_type': 'landed_cost',
            'exchange_rate': 1.0,
            'line_ids': [
                (0, 0, {
                    'product_id': product.id,
                    'quantity': 1,
                    'price_unit': 200.0,
                })
            ]
        })
        pr1.action_submit()
        pr1.action_approve()

        # Create an LC for po_no_margin to allow confirmation
        self.env['foreign.lc'].create({
            'purchase_order_id': po_no_margin.id,
            'lc_number': 'LC/TEST/002',
            'amount': 50.0,
            'currency_id': self.currency.id,
            'issuing_bank': self.bank.id,
        })
        po_no_margin.button_confirm()
        self.assertTrue(po_no_margin.picking_ids)
        picking = po_no_margin.picking_ids[0]
        for move in picking.move_ids:
            move.quantity = move.product_uom_qty
            move.picked = True
        picking.with_context(skip_approval=True).button_validate()
        self.assertEqual(pol.product_id.standard_price, 550.0)

        # 7. Test Landed Cost Sync when a draft Landed Cost exists and a new payment request is approved
        pol.customs_product_cost = 10.0
        po_no_margin.action_draft_landed_cost()
        draft_lc = self.env['stock.landed.cost'].search([
            ('picking_ids', 'in', po_no_margin.picking_ids.ids),
            ('state', '=', 'draft')
        ], limit=1)
        self.assertTrue(draft_lc)
        initial_cost_lines_count = len(draft_lc.cost_lines)

        # Create a second payment request
        pr2 = self.env['foreign.payment.request'].create({
            'purchase_order_id': po_no_margin.id,
            'vendor_id': self.vendor.id,
            'amount': 300.0,
            'currency_id': etb_currency.id if etb_currency else self.env.company.currency_id.id,
            'payment_type': 'landed_cost',
            'exchange_rate': 1.0,
            'line_ids': [
                (0, 0, {
                    'product_id': product.id,
                    'quantity': 1,
                    'price_unit': 300.0,
                })
            ]
        })
        pr2.action_submit()
        pr2.action_approve()

        # Verify the new lines are synced/added to the draft Landed Cost
        self.assertEqual(len(draft_lc.cost_lines), initial_cost_lines_count + 1)
        self.assertEqual(draft_lc.cost_lines[-1].price_unit, 300.0)

    def test_10_payment_instrument_types(self):
        """Test PO confirmation constraint and custom payment instrument types (LC, TT, CAD)"""
        # 1. Create a PO without a payment instrument
        po_no_inst = self.env['purchase.order'].create({
            'partner_id': self.vendor.id,
            'request_type': 'foreign',
            'order_line': [
                (0, 0, {
                    'name': 'Test Product',
                    'product_id': self.env['product.product'].create({'name': 'Test Product Temp'}).id,
                    'product_qty': 5,
                    'product_uom_id': self.env.ref('uom.product_uom_unit').id,
                    'price_unit': 10,
                    'date_planned': fields.Datetime.now(),
                })
            ]
        })
        
        # Confirming should fail
        with self.assertRaises(UserError, msg="Should not confirm without a payment instrument"):
            po_no_inst.button_confirm()

        # 2. Create a TT payment instrument
        inst_tt = self.env['foreign.lc'].create({
            'purchase_order_id': po_no_inst.id,
            'lc_number': 'TT/TEST/999',
            'instrument_type': 'tt',
            'amount': 50.0,
            'currency_id': self.currency.id,
            'issuing_bank': self.bank.id,
        })
        self.assertEqual(inst_tt.instrument_type, 'tt')
        
        # Confirming should now succeed
        po_no_inst.button_confirm()
        self.assertEqual(po_no_inst.state, 'purchase')

        # 3. Create a CAD payment instrument to verify creation defaults and CAD type setting
        inst_cad = self.env['foreign.lc'].create({
            'purchase_order_id': self.po.id,
            'lc_number': 'CAD/TEST/888',
            'instrument_type': 'cad',
            'amount': 100.0,
            'currency_id': self.currency.id,
            'issuing_bank': self.bank.id,
        })
        self.assertEqual(inst_cad.instrument_type, 'cad')

    def test_11_margin_vs_standard_billing_visibility(self):
        """Test the visibility flags has_margin_lines and has_standard_bill"""
        po = self.po
        # Initially, no margins and no invoices
        self.assertFalse(po.margin_line_ids)
        self.assertFalse(po.invoice_ids)
        self.assertFalse(po.has_margin_lines)
        self.assertFalse(po.has_standard_bill)

        # 1. Create a standard vendor bill before adding margin
        invoice_vals = po._prepare_invoice()
        invoice = self.env['account.move'].create(invoice_vals)
        po.invoice_ids = [(4, invoice.id)]
        po._compute_has_standard_bill()
        self.assertTrue(po.has_standard_bill, "Should detect standard invoice when no margin matches it")

        # 2. Reset and test adding margin first
        po.invoice_ids = [(5, 0, 0)] # Clear invoices
        margin_line = self.env['purchase.import.margin'].create({
            'import_id': po.id,
            'calculation': 'post_full',
            'margin_percent': 30.0,
            'usd_amount': 30.0,
            'exchange_rate': 60.0,
            'account_id': self.env['account.account'].search([], limit=1).id,
        })
        po._compute_has_margin_lines()
        self.assertTrue(po.has_margin_lines, "Should have margin lines")
        
        # 3. Create a bill from margin line
        margin_line.action_create_bill()
        po._compute_has_standard_bill()
        self.assertFalse(po.has_standard_bill, "Should not treat margin bill as a standard bill")

        # 4. Verify that changing PO exchange_rate updates the margin lines exchange_rate and etb_amount
        po.exchange_rate = 75.0
        self.assertEqual(margin_line.exchange_rate, 75.0, "Margin exchange rate should dynamically update when PO exchange rate is updated")
        self.assertEqual(margin_line.etb_amount, 2250.0, "Margin etb_amount should dynamically update when PO exchange rate is updated (30% of PO amount_total = 30 USD * 75 = 2250 ETB)")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        print("✅ All Foreign Purchase Operations tests passed successfully!")
        _logger.info("✅ All Foreign Purchase Operations tests passed successfully!")