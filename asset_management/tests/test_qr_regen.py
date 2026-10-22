# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase

class TestAssetQRRegen(TransactionCase):
    
    def setUp(self):
        super(TestAssetQRRegen, self).setUp()
        self.company = self.env.user.company_id
        
        # Get or create an analytic plan to satisfy the plan_id constraint on account.analytic.account
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].create({'name': 'Default Plan'})
            
        self.branch = self.env['account.analytic.account'].create({
            'name': 'Test Branch for QR',
            'plan_id': plan.id,
        })
        self.major_cat = self.env['am.asset.category'].create({
            'name': 'Test Major for QR',
            'code': 'TMAJ',
        })
        self.minor_cat = self.env['am.asset.minor_category'].create({
            'name': 'Test Minor for QR',
            'code': 'TMIN',
            'major_category_id': self.major_cat.id,
        })

    def test_qr_regeneration_flow(self):
        # Create 3 assets
        asset1 = self.env['am.asset'].create({
            'name': 'Asset 1',
            'employee_name': 'Employee 1',
            'company_id': self.company.id,
            'branch_id': self.branch.id,
            'major_category_id': self.major_cat.id,
            'minor_category_id': self.minor_cat.id,
        })
        asset2 = self.env['am.asset'].create({
            'name': 'Asset 2',
            'employee_name': 'Employee 2',
            'company_id': self.company.id,
            'branch_id': self.branch.id,
            'major_category_id': self.major_cat.id,
            'minor_category_id': self.minor_cat.id,
        })
        asset3 = self.env['am.asset'].create({
            'name': 'Asset 3',
            'employee_name': 'Employee 3',
            'company_id': self.company.id,
            'branch_id': self.branch.id,
            'major_category_id': self.major_cat.id,
            'minor_category_id': self.minor_cat.id,
        })

        # Verify they have sequential tag numbers ending in 0001, 0002, 0003
        self.assertTrue(asset1.tag_number.endswith('-0001'))
        self.assertTrue(asset2.tag_number.endswith('-0002'))
        self.assertTrue(asset3.tag_number.endswith('-0003'))
        self.assertEqual(asset1.tag_number, asset1.qr_code_number)

        # Delete asset2 (this creates a sequence gap)
        asset2.unlink()

        # Trigger tag number regeneration
        self.env['am.asset'].action_regenerate_all_qr_codes()

        # Verify remaining assets are re-sequenced to 0001 and 0002
        self.assertTrue(asset1.tag_number.endswith('-0001'))
        self.assertTrue(asset3.tag_number.endswith('-0002'))
