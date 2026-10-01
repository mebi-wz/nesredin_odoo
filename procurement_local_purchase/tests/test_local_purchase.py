from odoo.tests.common import TransactionCase, tagged
from odoo import fields

@tagged('post_install', '-at_install')
class TestLocalPurchase(TransactionCase):

    def setUp(self):
        super(TestLocalPurchase, self).setUp()
        self.Product = self.env['product.product']
        self.Requisition = self.env['local.purchase.requisition']
        
        self.product = self.Product.create({
            'name': 'Test Purchase Product',
            'type': 'consu'
        })

        # Create a GL Account (Expense)
        self.Account = self.env['account.account']
        self.gl_account = self.Account.create({
            'code': 'TEST600000',
            'name': 'Test Expense Account',
            'account_type': 'expense',
        })

        # Create analytic plan and account for budget category
        self.AnalyticPlan = self.env['account.analytic.plan']
        self.analytic_plan = self.AnalyticPlan.create({'name': 'Test Plan'})
        self.AnalyticAccount = self.env['account.analytic.account']
        self.budget_category = self.AnalyticAccount.create({
            'name': 'Test Cost Center',
            'plan_id': self.analytic_plan.id
        })

        # Create a budget post (Budgetary Position)
        self.BudgetPost = self.env['account.budget.post']
        self.budget_post = self.BudgetPost.create({
            'name': 'Test Budgetary Position',
            'account_ids': [(6, 0, [self.gl_account.id])]
        })

        # Create a budget
        self.Budget = self.env['budget.budget']
        self.budget = self.Budget.create({
            'name': 'Test Budget',
            'date_from': fields.Date.today(),
            'date_to': fields.Date.today(),
        })

        # Create a budget line
        self.BudgetLine = self.env['budget.lines']
        self.budget_line = self.BudgetLine.create({
            'budget_id': self.budget.id,
            'planned_amount': 1000.0,
            'analytic_account_id': self.budget_category.id,
            'general_budget_id': self.budget_post.id,
            'date_from': fields.Date.today(),
            'date_to': fields.Date.today(),
        })


    def test_01_purchase_requisition_sequence(self):
        """Test local purchase requisition sequence generation."""
        requisition = self.Requisition.create({
            'procurement_method': 'po',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 5,
                'unit_price': 100.0,
                'budget_category_id': self.budget_post.id,
                'cost_center_id': self.budget_category.id
            })]
        })

        
        self.assertTrue(requisition.name.startswith('PR-DL'), "Sequence should start with PR-DL")
        self.assertEqual(requisition.state, 'draft')

    def test_02_po_creation_from_requisition(self):
        """Test creation of PO from a local purchase requisition."""
        requisition = self.Requisition.create({
            'procurement_method': 'po',
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 5,
                'unit_price': 100.0,
                'budget_category_id': self.budget_post.id,
                'cost_center_id': self.budget_category.id
            })]
        })

        
        requisition.action_submit()
        requisition.action_approve()
        
        # Test PO action context
        action = requisition.action_create_po()
        self.assertEqual(action['res_model'], 'purchase.order')
        context = action['context']
        self.assertEqual(context['default_local_purchase_request_id'], requisition.id)
        
        # Manually create PO to verify sequence and linkage
        po_vals = {
            'partner_id': self.env['res.partner'].create({'name': 'Test Vendor'}).id,
            'local_purchase_request_id': context['default_local_purchase_request_id'],
            'origin': context['default_origin'],
            'order_line': context['default_order_line']
        }
        po = self.env['purchase.order'].create(po_vals)
        
        self.assertEqual(requisition.po_count, 1, "One PO should have been created manually")
        self.assertTrue(po.name.startswith('PO-DL'), f"PO name {po.name} should start with local prefix PO-DL")
        self.assertEqual(po.local_purchase_request_id.id, requisition.id)
        self.assertEqual(po.order_line[0].price_unit, 100.0, "The PO order line unit price should match the requisition line unit price")
