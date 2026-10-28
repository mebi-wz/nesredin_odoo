# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    bank_amount_signed = fields.Monetary(
        string='Amount',
        compute='_compute_bank_amount_signed',
        currency_field='currency_id',
        store=True,
    )

    @api.depends(
        'amount_total',
        'amount_total_signed',
        'journal_id.type',
        'journal_id.default_account_id',
        'journal_id.suspense_account_id',
        'origin_payment_id.payment_type',
        'statement_line_id.amount',
        'line_ids.debit',
        'line_ids.credit',
        'line_ids.balance',
        'line_ids.account_id',
    )
    def _compute_bank_amount_signed(self):
        for move in self:
            if move.journal_id.type != 'bank':
                move.bank_amount_signed = move.amount_total_signed or move.amount_total or 0.0
                continue

            amount = move.amount_total or 0.0

            # 1. Connected payment
            payment = move.origin_payment_id
            if payment and payment.payment_type:
                move.bank_amount_signed = -abs(amount) if payment.payment_type == 'outbound' else abs(amount)
                continue

            # 2. Bank statement line
            if move.statement_line_id:
                move.bank_amount_signed = -abs(amount) if move.statement_line_id.amount < 0 else abs(amount)
                continue

            # 3. Bank / Liquidity lines balance (debit - credit)
            bank_accounts = set()
            if move.journal_id.default_account_id:
                bank_accounts.add(move.journal_id.default_account_id.id)
            if move.journal_id.suspense_account_id:
                bank_accounts.add(move.journal_id.suspense_account_id.id)
            for pml in (move.journal_id.inbound_payment_method_line_ids | move.journal_id.outbound_payment_method_line_ids):
                if pml.payment_account_id:
                    bank_accounts.add(pml.payment_account_id.id)

            bank_lines = move.line_ids.filtered(
                lambda l: (
                    l.account_id.id in bank_accounts or
                    l.account_id.account_type == 'asset_cash'
                )
            )

            if bank_lines:
                bank_balance = sum(bank_lines.mapped('balance'))
                move.bank_amount_signed = -abs(amount) if bank_balance < 0 else abs(amount)
            else:
                move.bank_amount_signed = move.amount_total_signed or amount
