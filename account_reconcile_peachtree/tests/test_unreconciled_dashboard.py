# -*- coding: utf-8 -*-
from odoo.tests import common
from odoo.tests.common import TransactionCase, tagged
from odoo import fields, Command
from odoo.exceptions import UserError

@tagged('post_install', '-at_install')
class TestUnreconciledDashboard(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Find a bank account type or configure one
        cls.company = cls.env.company
        cls.bank_account = cls.env['account.account'].create({
            'name': 'Test Bank Account',
            'code': '1002003',
            'account_type': 'asset_cash',
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.outstanding_receipts = cls.env['account.account'].create({
            'name': 'Test Outstanding Receipts',
            'code': '1002004',
            'account_type': 'asset_cash',
            'reconcile': True,
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.outstanding_payments = cls.env['account.account'].create({
            'name': 'Test Outstanding Payments',
            'code': '1002005',
            'account_type': 'asset_cash',
            'reconcile': True,
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.suspense_account = cls.env['account.account'].create({
            'name': 'Test Suspense Account',
            'code': '2009999',
            'account_type': 'asset_current',
            'reconcile': True,
            'company_ids': [Command.set(cls.company.ids)],
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Test Bank Journal',
            'code': 'TBANK',
            'type': 'bank',
            'default_account_id': cls.bank_account.id,
            'suspense_account_id': cls.suspense_account.id,
            'company_id': cls.company.id,
        })
        for line in cls.journal.inbound_payment_method_line_ids:
            line.payment_account_id = cls.outstanding_receipts.id
        for line in cls.journal.outbound_payment_method_line_ids:
            line.payment_account_id = cls.outstanding_payments.id

    def test_unreconciled_amounts_action(self):
        # Create an unreconciled move line on the bank account
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Debit Line',
                    'account_id': self.bank_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Credit Line',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ]
        })
        move.action_post()
        
        # Trigger the dashboard action
        action = self.journal.action_open_unreconciled_amounts()
        
        # Verify the action details
        self.assertEqual(action['res_model'], 'account.move.line')
        self.assertEqual(action['type'], 'ir.actions.act_window')
        
        # Search using the returned domain to verify it finds our unreconciled line
        unreconciled_lines = self.env['account.move.line'].search(action['domain'])
        # The credit line (outstanding receipts) must be present
        self.assertTrue(any(line.account_id == self.outstanding_receipts for line in unreconciled_lines))
        # The debit line (bank account itself) must NOT be present
        self.assertFalse(any(line.account_id == self.bank_account for line in unreconciled_lines))

    def test_unreconciled_amounts_fallback_action(self):
        # Create a new bank journal with NO outstanding accounts configured on payment method lines
        fallback_journal = self.env['account.journal'].create({
            'name': 'Fallback Bank Journal',
            'code': 'FBANK',
            'type': 'bank',
            'default_account_id': self.bank_account.id,
            'suspense_account_id': self.suspense_account.id,
            'company_id': self.company.id,
        })
        for line in fallback_journal.inbound_payment_method_line_ids:
            line.payment_account_id = False
        for line in fallback_journal.outbound_payment_method_line_ids:
            line.payment_account_id = False

        # Register or update the default outstanding accounts under the XML IDs so chart_template.ref resolves them
        debit_xml_id = f"{self.company.id}_account_journal_payment_debit_account_id"
        credit_xml_id = f"{self.company.id}_account_journal_payment_credit_account_id"

        debit_ref = self.env['ir.model.data'].search([('name', '=', debit_xml_id), ('module', '=', 'account')])
        if debit_ref:
            debit_ref.write({'res_id': self.outstanding_receipts.id})
        else:
            self.env['ir.model.data'].create({
                'name': debit_xml_id,
                'module': 'account',
                'model': 'account.account',
                'res_id': self.outstanding_receipts.id,
            })

        credit_ref = self.env['ir.model.data'].search([('name', '=', credit_xml_id), ('module', '=', 'account')])
        if credit_ref:
            credit_ref.write({'res_id': self.outstanding_payments.id})
        else:
            self.env['ir.model.data'].create({
                'name': credit_xml_id,
                'module': 'account',
                'model': 'account.account',
                'res_id': self.outstanding_payments.id,
            })

        # Create an unreconciled move line on the bank account
        move = self.env['account.move'].create({
            'journal_id': fallback_journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Debit Line',
                    'account_id': self.bank_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Credit Line',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ]
        })
        move.action_post()

        # Trigger the dashboard action
        action = fallback_journal.action_open_unreconciled_amounts()

        # Search using the returned domain to verify it finds our unreconciled line via company-wide fallback
        unreconciled_lines = self.env['account.move.line'].search(action['domain'])
        self.assertTrue(any(line.account_id == self.outstanding_receipts for line in unreconciled_lines))
        self.assertFalse(any(line.account_id == self.bank_account for line in unreconciled_lines))

    def test_reconciled_amounts_action(self):
        # Create an unreconciled move line on the bank account
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Debit Line',
                    'account_id': self.bank_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Credit Line',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ]
        })
        move.action_post()
        
        # Get the credit line (outstanding receipts)
        outstanding_line = move.line_ids.filtered(lambda l: l.account_id == self.outstanding_receipts)
        
        # Reconcile it manually
        outstanding_line.action_reconcile_row_manually()
        
        # Trigger the reconciled dashboard action
        action = self.journal.action_open_reconciled_amounts()
        
        # Verify the action details
        self.assertEqual(action['res_model'], 'account.move.line')
        self.assertEqual(action['type'], 'ir.actions.act_window')
        
        # Search using the returned domain to verify it finds our reconciled line (on bank account, not outstanding)
        reconciled_lines = self.env['account.move.line'].search(action['domain'])
        self.assertTrue(any(line.account_id == self.bank_account for line in reconciled_lines))
        self.assertFalse(any(line.account_id == self.outstanding_receipts for line in reconciled_lines))

    def test_unreconcile_row_manually(self):
        # Create an unreconciled move line
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Debit Line',
                    'account_id': self.bank_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Credit Line',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ]
        })
        move.action_post()
        
        # Get the credit line (outstanding receipts)
        outstanding_line = move.line_ids.filtered(lambda l: l.account_id == self.outstanding_receipts)
        
        # Reconcile it manually (creates statement line)
        outstanding_line.action_reconcile_row_manually()
        
        # Check that the statement line was created
        reconciled_lines = outstanding_line._all_reconciled_lines()
        st_line = reconciled_lines.mapped('statement_line_id')
        self.assertTrue(st_line)
        self.assertTrue(outstanding_line.reconciled)
        
        # Find the statement line's bank account line
        bank_stmt_line = st_line.move_id.line_ids.filtered(lambda l: l.account_id == self.bank_account)
        self.assertTrue(bank_stmt_line)

        # Unreconcile manually via the bank account line (not outstanding)
        bank_stmt_line.action_unreconcile_row_manually()
        
        # Check that the reconciliation is broken and statement line is deleted
        self.assertFalse(outstanding_line.reconciled)
        self.assertFalse(st_line.exists())



    def test_payment_link_wizard_no_res_model(self):
        # Create the wizard in-memory without setting res_model (to simulate onchange/initialization state)
        wizard = self.env['payment.link.wizard'].new({
            'amount': 50.0,
        })
        # Check computed fields; they should not crash and compute to False/empty
        self.assertFalse(wizard.company_id)
        self.assertFalse(wizard.link)

    def test_action_reconcile_manually(self):
        # Set default account on the journal if not set (it is set in setUpClass to bank_account)
        self.journal.default_account_id = self.bank_account.id
        
        # Create a partner/vendor
        partner = self.env['res.partner'].create({'name': 'Test Vendor'})
        
        # Create an unreconciled credit move line (simulating outstanding payment)
        move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Liquidity counterpart',
                    'account_id': self.bank_account.id,
                    'debit': 150.0,
                    'credit': 0.0,
                    'partner_id': partner.id,
                }),
                (0, 0, {
                    'name': 'Outstanding payment line',
                    'account_id': self.outstanding_payments.id,
                    'debit': 0.0,
                    'credit': 150.0,
                    'partner_id': partner.id,
                }),
            ]
        })
        move.action_post()

        outstanding_line = move.line_ids.filtered(lambda l: l.account_id == self.outstanding_payments)
        self.assertFalse(outstanding_line.reconciled)

        # Capture bank balance before reconciliation
        bank_line_before = move.line_ids.filtered(lambda l: l.account_id == self.bank_account)
        bank_debit_before = bank_line_before.debit

        # Perform manual reconciliation via bank statement line
        outstanding_line.action_reconcile_row_manually()

        # Verify the outstanding line is now reconciled
        self.assertTrue(outstanding_line.reconciled)

        # Verify a bank statement line was created (reconciled_pairs exist)
        reconciled_pairs = outstanding_line.matched_debit_ids or outstanding_line.matched_credit_ids
        self.assertTrue(reconciled_pairs)

        # Verify the original bank debit is NOT zeroed out — bank balance is preserved
        self.assertEqual(bank_line_before.debit, bank_debit_before,
                         "Bank account balance should not be cancelled by manual reconciliation")

    def test_bulk_reconciliation_and_unreconciliation(self):
        # Create two unreconciled credit move lines
        move1 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Liquidity counterpart 1',
                    'account_id': self.bank_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Outstanding line 1',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ]
        })
        move1.action_post()
        
        move2 = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {
                    'name': 'Liquidity counterpart 2',
                    'account_id': self.bank_account.id,
                    'debit': 200.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Outstanding line 2',
                    'account_id': self.outstanding_receipts.id,
                    'debit': 0.0,
                    'credit': 200.0,
                }),
            ]
        })
        move2.action_post()

        outstanding_line1 = move1.line_ids.filtered(lambda l: l.account_id == self.outstanding_receipts)
        outstanding_line2 = move2.line_ids.filtered(lambda l: l.account_id == self.outstanding_receipts)
        
        lines = outstanding_line1 | outstanding_line2
        self.assertFalse(any(lines.mapped('reconciled')))
        
        # Reconcile bulk
        lines.action_reconcile_bulk_manually()
        self.assertTrue(all(lines.mapped('reconciled')))
        
        # Verify statement lines were created
        st_lines = lines._all_reconciled_lines().mapped('statement_line_id')
        self.assertEqual(len(st_lines), 2)
        
        # Unreconcile bulk
        lines.action_unreconcile_bulk_manually()
        self.assertFalse(any(lines.mapped('reconciled')))
        self.assertFalse(st_lines.exists())

    def test_cron_create_missing_journals(self):
        # 1. Create a bank account of type asset_cash
        bank_acc = self.env['account.account'].create({
            'name': 'Test New Bank Account',
            'code': '1002099',
            'account_type': 'asset_cash',
            'company_ids': [Command.set(self.company.ids)],
        })
        
        # 2. Create a cash account of type asset_cash
        cash_acc = self.env['account.account'].create({
            'name': 'Test New Cash Account',
            'code': '1002098',
            'account_type': 'asset_cash',
            'company_ids': [Command.set(self.company.ids)],
        })
        
        # Verify no journals exist for these accounts yet
        existing_bank_journals = self.env['account.journal'].search([('default_account_id', '=', bank_acc.id)])
        existing_cash_journals = self.env['account.journal'].search([('default_account_id', '=', cash_acc.id)])
        self.assertFalse(existing_bank_journals)
        self.assertFalse(existing_cash_journals)
        
        # 3. Run the cron method
        created_journals = self.env['account.journal'].cron_create_missing_journals()
        
        # Verify journals were created
        bank_journal = self.env['account.journal'].search([('default_account_id', '=', bank_acc.id)])
        cash_journal = self.env['account.journal'].search([('default_account_id', '=', cash_acc.id)])
        self.assertTrue(bank_journal)
        self.assertTrue(cash_journal)
        
        # Verify the created journals properties
        self.assertEqual(bank_journal.name, bank_acc.name)
        self.assertEqual(bank_journal.type, 'bank')
        self.assertEqual(cash_journal.name, cash_acc.name)
        self.assertEqual(cash_journal.type, 'cash')
        
        # 4. Run the cron method again, verify no new journals are created
        newly_created = self.env['account.journal'].cron_create_missing_journals()
        self.assertFalse(newly_created)

    def test_period_reconciliation(self):
        # Set default account on the journal
        self.journal.default_account_id = self.bank_account.id

        # 1. Book Balance entry
        book_move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'name': 'Initial Bank Balance',
                        'account_id': self.bank_account.id,
                        'debit': 1000.0, 'credit': 0.0}),
                (0, 0, {'name': 'Counterpart',
                        'account_id': self.suspense_account.id,
                        'debit': 0.0, 'credit': 1000.0}),
            ]
        })
        book_move.action_post()

        # 2. Outstanding deposit (debit on transit receipts account)
        deposit_move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'name': 'Transit Deposit Counterpart',
                        'account_id': self.bank_account.id,
                        'debit': 0.0, 'credit': 200.0}),
                (0, 0, {'name': 'Transit Deposit',
                        'account_id': self.outstanding_receipts.id,
                        'debit': 200.0, 'credit': 0.0}),
            ]
        })
        deposit_move.action_post()

        # 3. Outstanding check (credit on transit payments account)
        check_move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': fields.Date.today(),
            'line_ids': [
                (0, 0, {'name': 'Transit Check',
                        'account_id': self.outstanding_payments.id,
                        'debit': 0.0, 'credit': 150.0}),
                (0, 0, {'name': 'Transit Check Counterpart',
                        'account_id': self.bank_account.id,
                        'debit': 150.0, 'credit': 0.0}),
            ]
        })
        check_move.action_post()

        # ── Create wizard (no state – everything visible immediately) ──────
        # Book Balance = 1000 (Bank Account + Outstanding Accounts)
        # Outstanding deposits = 200,  checks = 150
        # Statement Balance = 950  →  Adjusted = 950 + 200 - 150 = 1000
        # Difference = 1000 - 1000 = 0
        today = fields.Date.today()
        wizard = self.env['account.bank.reconciliation.wizard'].create({
            'journal_id': self.journal.id,
            'statement_date': today,
            'statement_balance': 950.0,
        })

        # Computed balances
        self.assertEqual(wizard.book_balance, 1000.0)
        self.assertEqual(wizard.outstanding_deposits, 200.0)
        self.assertEqual(wizard.outstanding_checks, 150.0)
        self.assertEqual(wizard.difference, 0.0)

        # Line counts
        self.assertEqual(len(wizard.outstanding_deposit_ids), 1)
        self.assertEqual(len(wizard.outstanding_check_ids), 1)
        self.assertEqual(len(wizard.reconciled_line_ids), 0)

        # Changing the statement balance adjusts the difference
        wizard.write({'statement_balance': 850.0})
        self.assertEqual(wizard.difference, -100.0)

        # Reset balance
        wizard.write({'statement_balance': 950.0})
        self.assertEqual(wizard.difference, 0.0)

        # Reconcile the outstanding deposit
        deposit_line = wizard.outstanding_deposit_ids[0]
        deposit_line.action_reconcile_row_manually()

        # After reconciliation the deposit should leave outstanding and appear in reconciled
        wizard.invalidate_recordset()
        self.assertEqual(len(wizard.outstanding_deposit_ids), 0)
        self.assertEqual(len(wizard.reconciled_line_ids), 1)

    def test_period_reconciliation_chronology(self):
        # 1. Create a period for Jan 2026
        period_jan = self.env['account.bank.reconciliation.period'].create({
            'journal_id': self.journal.id,
            'period_date': date(2026, 1, 31),
            'statement_balance': 1000.0,
            'state': 'open',
        })

        # 2. Try to create another period in the same month (Jan 2026) -> should fail
        with self.assertRaises(UserError):
            self.env['account.bank.reconciliation.period'].create({
                'journal_id': self.journal.id,
                'period_date': date(2026, 1, 15),
                'statement_balance': 1000.0,
            })

        # 3. Try to create a period in an earlier month (Dec 2025) -> should fail
        with self.assertRaises(UserError):
            self.env['account.bank.reconciliation.period'].create({
                'journal_id': self.journal.id,
                'period_date': date(2025, 12, 31),
                'statement_balance': 1000.0,
            })

        # 4. Create a period in a later month (Feb 2026) -> should succeed
        period_feb = self.env['account.bank.reconciliation.period'].create({
            'journal_id': self.journal.id,
            'period_date': date(2026, 2, 28),
            'statement_balance': 1100.0,
            'state': 'open',
        })

        # 5. Editing an older period (Jan) notes should succeed
        period_jan.write({'notes': 'Updated notes'})
        self.assertEqual(period_jan.notes, 'Updated notes')

    def test_outstanding_carry_forward(self):
        # 1. Create an outstanding deposit line in January 2026
        deposit_move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date(2026, 1, 15),
            'line_ids': [
                (0, 0, {'name': 'Transit Deposit Counterpart',
                        'account_id': self.bank_account.id,
                        'debit': 0.0, 'credit': 200.0}),
                (0, 0, {'name': 'Transit Deposit',
                        'account_id': self.outstanding_receipts.id,
                        'debit': 200.0, 'credit': 0.0}),
            ]
        })
        deposit_move.action_post()

        # 2. Open wizard for January 2026 and save the period
        wizard_jan = self.env['account.bank.reconciliation.wizard'].create({
            'journal_id': self.journal.id,
            'statement_date': date(2026, 1, 31),
            'statement_balance': 1000.0,
        })
        self.assertEqual(len(wizard_jan.outstanding_deposit_ids), 1)
        wizard_jan.action_save_period()

        # 3. Create a new wizard for February 2026
        wizard_feb = self.env['account.bank.reconciliation.wizard'].create({
            'journal_id': self.journal.id,
            'statement_date': date(2026, 2, 28),
            'statement_balance': 1000.0,
        })

        # 4. Verify that the January deposit is still visible in the February wizard as outstanding
        self.assertEqual(len(wizard_feb.outstanding_deposit_ids), 1)
        self.assertEqual(wizard_feb.outstanding_deposit_ids[0].id, wizard_jan.outstanding_deposit_ids[0].id)

    def test_direct_period_creation_and_validation(self):
        # 1. Create a transaction in January 2026
        deposit_move = self.env['account.move'].create({
            'journal_id': self.journal.id,
            'date': date(2026, 1, 15),
            'line_ids': [
                (0, 0, {'name': 'Transit Deposit Counterpart',
                        'account_id': self.bank_account.id,
                        'debit': 0.0, 'credit': 200.0}),
                (0, 0, {'name': 'Transit Deposit',
                        'account_id': self.outstanding_receipts.id,
                        'debit': 200.0, 'credit': 0.0}),
            ]
        })
        deposit_move.action_post()

        # 2. Create period directly
        period = self.env['account.bank.reconciliation.period'].create({
            'journal_id': self.journal.id,
            'period_date': date(2026, 1, 31),
            'statement_balance': 1000.0,
        })

        # 3. Verify computes
        self.assertEqual(len(period.outstanding_deposit_ids), 1)
        self.assertEqual(period.outstanding_deposits, 200.0)
        # book_balance = bank account GL balance (usually starting balance + other posted items)
        # Let's assert that difference is correctly calculated: (1000 + 200 - 0) - book_balance
        self.assertEqual(period.difference, (1000.0 + 200.0) - period.book_balance)

        # 4. Try to create duplicate period in January 2026 -> should raise UserError
        with self.assertRaises(UserError):
            self.env['account.bank.reconciliation.period'].create({
                'journal_id': self.journal.id,
                'period_date': date(2026, 1, 20),
                'statement_balance': 1000.0,
            })



