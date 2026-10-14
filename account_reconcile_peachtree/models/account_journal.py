# -*- coding: utf-8 -*-
from odoo import api, fields, models, _

class AccountJournal(models.Model):
    _inherit = 'account.journal'

    def _get_reconciliation_outstanding_accounts(self):
        self.ensure_one()
        accounts = self.env['account.account']
        accounts |= self._get_journal_inbound_outstanding_payment_accounts()
        accounts |= self._get_journal_outbound_outstanding_payment_accounts()

        for method in self.inbound_payment_method_line_ids:
            if method.payment_account_id:
                accounts |= method.payment_account_id
        for method in self.outbound_payment_method_line_ids:
            if method.payment_account_id:
                accounts |= method.payment_account_id

        # Fallback to company-wide default outstanding and transfer accounts
        company = self.company_id
        chart_template = self.env['account.chart.template'].with_context(allowed_company_ids=company.root_id.ids)
        debit_acc = chart_template.ref('account_journal_payment_debit_account_id', raise_if_not_found=False)
        credit_acc = chart_template.ref('account_journal_payment_credit_account_id', raise_if_not_found=False)
        if debit_acc:
            accounts |= debit_acc
        if credit_acc:
            accounts |= credit_acc
        if company.transfer_account_id:
            accounts |= company.transfer_account_id

        return accounts

    def action_open_unreconciled_amounts(self):
        self.ensure_one()
        # Find all outstanding accounts and the default account for this bank journal
        # Collect only the outstanding payment/receipt transit accounts.
        # Do NOT include self.default_account_id (the bank account itself) — its own
        # balance entries are NOT unreconciled outstanding amounts and should never appear here.
        accounts = self._get_reconciliation_outstanding_accounts()

        # Return a window action to show all posted, unreconciled move lines on these accounts
        # filtered by this journal
        action = {
            'name': _('Unreconciled Amounts: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('account_reconcile_peachtree.view_move_line_unreconciled_list').id, 'list'),
                (False, 'form')
            ],
            'domain': [
                ('journal_id', '=', self.id),
                ('account_id', 'in', accounts.ids),
                ('parent_state', '=', 'posted'),
                ('reconciled', '=', False),
                ('statement_line_id', '=', False),
            ],
            'context': {
                'search_default_groupby_date': 1,
                'search_default_group_by_account': 2,
                'create': False,
                'edit': False,
                'delete': False,
            }
        }
        return action

    def action_open_reconciled_amounts(self):
        self.ensure_one()

        # Return a window action to show all posted move lines on this journal's bank account
        # that are linked to a bank statement line (reconciled bank entries)
        action = {
            'name': _('Reconciled Amounts: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'views': [
                (self.env.ref('account_reconcile_peachtree.view_move_line_reconciled_list').id, 'list'),
                (False, 'form')
            ],
            'domain': [
                ('journal_id', '=', self.id),
                ('account_id', '=', self.default_account_id.id),
                ('parent_state', '=', 'posted'),
                ('statement_line_id', '!=', False),
            ],
            'context': {
                'search_default_groupby_date': 1,
                'search_default_group_by_account': 2,
                'create': False,
                'edit': False,
                'delete': False,
            }
        }
        return action

    def action_open_period_reconciliation(self):
        self.ensure_one()
        action = {
            'name': _('Bank Reconciliation: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'account.bank.reconciliation.period',
            'view_mode': 'list,form',
            'domain': [('journal_id', '=', self.id)],
            'context': {
                'default_journal_id': self.id,
            },
            'target': 'current',
        }
        return action

    @api.model
    def cron_create_missing_journals(self):
        """ Cron task to create journals for each bank and cash type accounts if it doesn't exist. """
        # Search for all active accounts of type 'asset_cash' (Bank and Cash)
        accounts = self.env['account.account'].search([('account_type', '=', 'asset_cash')])
        
        # Get all existing default accounts on journals to know which accounts already have journals
        existing_journal_accounts = self.search([('default_account_id', '!=', False)]).mapped('default_account_id')
        
        # Filter for accounts that don't have a journal yet
        missing_accounts = accounts - existing_journal_accounts
        
        created_journals = self.env['account.journal']
        for account in missing_accounts:
            company = account.company_ids[0] if account.company_ids else self.env.company
            
            # Determine if cash or bank
            journal_type = 'bank'
            if company.cash_account_code_prefix and account.code and account.code.startswith(company.cash_account_code_prefix):
                journal_type = 'cash'
            elif company.bank_account_code_prefix and account.code and account.code.startswith(company.bank_account_code_prefix):
                journal_type = 'bank'
            elif account.name and 'cash' in account.name.lower():
                journal_type = 'cash'
                
            # Compute a unique journal code
            journal_code = self._get_next_journal_default_code(journal_type, company)
            if not journal_code:
                # Fallback code generator
                prefix = 'BNK' if journal_type == 'bank' else 'CSH'
                for i in range(1, 1000):
                    candidate = f"{prefix}{i}"[:5]
                    existing = self.search([('code', '=', candidate), ('company_id', '=', company.id)])
                    if not existing:
                        journal_code = candidate
                        break
            
            if not journal_code:
                journal_code = 'BNK99' # Ultimate fallback
                
            # Create the journal
            journal = self.create({
                'name': account.name,
                'code': journal_code,
                'type': journal_type,
                'default_account_id': account.id,
                'company_id': company.id,
            })
            created_journals |= journal
            
        return created_journals


