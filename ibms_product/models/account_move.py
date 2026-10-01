# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse / Branch',
        check_company=True,
        readonly=False,
        help="Warehouse/Branch linked to this invoice. Invoice lines will automatically inherit its Analytic Account for reporting.",
    )

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id_analytics(self):
        if self.warehouse_id and self.warehouse_id.analytic_account_id:
            account_id_str = str(self.warehouse_id.analytic_account_id.id)
            for line in self.invoice_line_ids:
                if not line.display_type or line.display_type == 'product':
                    line.analytic_distribution = {account_id_str: 100.0}

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            if move.warehouse_id and move.warehouse_id.analytic_account_id:
                account_id_str = str(move.warehouse_id.analytic_account_id.id)
                for line in move.invoice_line_ids:
                    if (not line.display_type or line.display_type == 'product') and not line.analytic_distribution:
                        line.analytic_distribution = {account_id_str: 100.0}
        return moves


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('product_id')
    def _onchange_product_id_warehouse_analytics(self):
        if self.move_id.warehouse_id and self.move_id.warehouse_id.analytic_account_id:
            if not self.analytic_distribution:
                self.analytic_distribution = {str(self.move_id.warehouse_id.analytic_account_id.id): 100.0}
