from odoo import fields
from odoo.tests.common import TransactionCase, tagged
from odoo.exceptions import ValidationError

@tagged('post_install', '-at_install')
class TestStoreRequisition(TransactionCase):

    def setUp(self):
        super(TestStoreRequisition, self).setUp()
        self.Warehouse = self.env['stock.warehouse']
        self.Product = self.env['product.product']
        self.Requisition = self.env['store.requisition']
        
        # Create a warehouse
        self.warehouse = self.Warehouse.create({
            'name': 'Test Warehouse',
            'code': 'TWH'
        })
        
        # Create a product
        self.product = self.Product.create({
            'name': 'Test Product',
            'type': 'consu',
            'is_storable': True
        })
        
        # Give it some stock
        self.env['stock.quant']._update_available_quantity(self.product, self.warehouse.lot_stock_id, 100)

        # Create a GL Account (Expense)
        self.Account = self.env['account.account']
        self.gl_account = self.Account.create({
            'code': 'TEST600000',
            'name': 'Test Expense Account',
            'account_type': 'expense',
        })

        # Create an analytic plan
        self.AnalyticPlan = self.env['account.analytic.plan']
        self.plan = self.AnalyticPlan.create({
            'name': 'Test Plan',
        })

        # Create an analytic account (budget category)
        self.AnalyticAccount = self.env['account.analytic.account']
        self.budget_category = self.AnalyticAccount.create({
            'name': 'Test Budget Category',
            'plan_id': self.plan.id,
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
        self.BudgetLines = self.env['budget.lines']
        self.budget_line = self.BudgetLines.create({
            'budget_id': self.budget.id,
            'general_budget_id': self.budget_post.id,
            'analytic_account_id': self.budget_category.id,
            'date_from': fields.Date.today(),
            'date_to': fields.Date.today(),
            'planned_amount': 1000.0,
        })

    def test_01_requisition_creation_and_sequence(self):
        """Test that a requisition is created with the correct sequence format."""
        requisition = self.Requisition.create({
            'warehouse_id': self.warehouse.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 10,
                'budget_category_id': self.budget_post.id,
                'cost_center_id': self.budget_category.id
            })]
        })
        
        self.assertTrue(requisition.name.startswith('MTIV/OF/'), "Sequence should start with MTIV/OF/")
        self.assertEqual(requisition.state, 'draft', "Initial state should be draft")

    def test_02_requisition_workflow(self):
        """Test the requisition state transitions."""
        requisition = self.Requisition.create({
            'warehouse_id': self.warehouse.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 10,
                'budget_category_id': self.budget_post.id,
                'cost_center_id': self.budget_category.id
            })]
        })
        
        # Draft -> Submitted (Action: Submit)
        requisition.action_approve()
        self.assertEqual(requisition.state, 'submitted', "State should be submitted after Submit")
        
        # Submitted -> Verified (Action: Verify)
        requisition.action_approve()
        self.assertEqual(requisition.state, 'verified', "State should be verified after Verify")

        # Set GL Account before Budget Approval
        requisition.line_ids[0].account_id = self.gl_account.id

        # Verified -> Budget Approved (Action: Budget Approve)
        requisition.action_approve()
        self.assertEqual(requisition.state, 'budget_approved', "State should be budget_approved after Budget Approve")

        # Set Issued Quantity before moving to Waiting/SIV phase
        requisition.line_ids[0].qty_transferred = 10.0

        # Budget Approved -> Waiting
        requisition.action_approve()
        self.assertEqual(requisition.state, 'waiting', "State should be waiting after Budget Approved")

        # Waiting -> Processed
        requisition.action_approve()
        self.assertEqual(requisition.state, 'processed', "State should be processed")

        # Test Cancel
        requisition.action_draft() # Needs a custom action or just reset? Wait, action_draft works for any?
        # Actually my action_draft works from any state.
        requisition.action_approve() # Back to submitted
        requisition.action_cancel()
        self.assertEqual(requisition.state, 'cancelled', "State should be cancelled after action_cancel")

    def test_03_empty_requisition_validation(self):
        """Test that creating a requisition without lines raises a ValidationError."""
        with self.assertRaises(ValidationError):
            self.Requisition.create({
                'warehouse_id': self.warehouse.id,
                'line_ids': []
            })

    def test_04_budget_commitment_posting(self):
        """Test that validating a SIV creates a budget commitment (analytic line)."""
        requisition = self.Requisition.create({
            'warehouse_id': self.warehouse.id,
            'cost_center_id': self.budget_category.id,
            'line_ids': [(0, 0, {
                'product_id': self.product.id,
                'quantity': 10,
                'unit_price': 50.0,
                'budget_category_id': self.budget_post.id,
                'account_id': self.gl_account.id
            })]
        })
        
        # Approve until processed
        # Set issued_qty and create SIV
        requisition.line_ids[0].issued_qty = 10
        requisition.action_create_siv(skip_wizard=True)
        
        # Validate the picking
        picking = requisition.picking_ids[0]
        picking.button_validate()
        
        # Check if analytic line exists
        analytic_lines = self.env['account.analytic.line'].search([
            ('requisition_line_id', '=', requisition.line_ids[0].id)
        ])
        self.assertEqual(len(analytic_lines), 1, "One analytic line should be created")
        self.assertEqual(analytic_lines[0].amount, -500.0, "Amount should be -500.0")
        self.assertEqual(analytic_lines[0].general_account_id.id, self.gl_account.id, "GL account should match")
        
        # Verify double posting prevention
        requisition.post_budget_commitments()
        analytic_lines_after = self.env['account.analytic.line'].search([
            ('requisition_line_id', '=', requisition.line_ids[0].id)
        ])
        self.assertEqual(len(analytic_lines_after), 1, "Should not create duplicate analytic lines")
