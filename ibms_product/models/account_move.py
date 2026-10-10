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
    payment_proof = fields.Binary(
        string='Payment Proof / Receipt',
        attachment=True,
        copy=False,
        help="Upload payment screenshot, bank transfer slip, Telebirr/CBE Birr confirmation, or receipt.",
    )
    payment_proof_filename = fields.Char(string='Payment Proof Filename', copy=False)
    payment_note = fields.Char(
        string='Payment Note / Reference',
        copy=False,
        help="Notes about payment, e.g. Transaction ID, bank deposit reference, Telebirr/CBE Birr confirmation code, etc.",
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


    @api.onchange('partner_id')
    def _onchange_partner_id_update_prices(self):
        for line in self.invoice_line_ids:
            if line.product_id:
                line._compute_price_unit()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    @api.onchange('product_id')
    def _onchange_product_id_warehouse_analytics(self):
        if self.move_id.warehouse_id and self.move_id.warehouse_id.analytic_account_id:
            if not self.analytic_distribution:
                self.analytic_distribution = {str(self.move_id.warehouse_id.analytic_account_id.id): 100.0}

    @api.depends('product_id', 'product_uom_id', 'move_id.partner_id.customer_type')
    def _compute_price_unit(self):
        super()._compute_price_unit()
        for line in self:
            if not line.product_id or line.display_type in ('line_section', 'line_subsection', 'line_note') or line.is_imported:
                continue
            if line.move_id.is_sale_document(include_receipts=True):
                partner = line.move_id.partner_id.commercial_partner_id or line.move_id.partner_id
                if partner and partner.customer_type == 'wholesaler' and line.product_id.wholesale_price > 0:
                    line.price_unit = line.product_id._get_tax_included_unit_price(
                        line.move_id.company_id,
                        line.move_id.currency_id,
                        line.move_id.date,
                        'sale',
                        fiscal_position=line.move_id.fiscal_position_id,
                        product_uom=line.product_uom_id,
                        product_price_unit=line.product_id.wholesale_price,
                    )
