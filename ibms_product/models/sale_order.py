# -*- coding: utf-8 -*-
from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        check_company=True,
        copy=False,
        help="Cost Center / Analytic account for this branch.",
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if 'warehouse_id' in fields_list and not res.get('warehouse_id'):
            if self.env.user.default_warehouse_id:
                res['warehouse_id'] = self.env.user.default_warehouse_id.id
            elif self.env.user.allowed_warehouse_ids:
                res['warehouse_id'] = self.env.user.allowed_warehouse_ids[0].id
        if res.get('warehouse_id') and 'analytic_account_id' in fields_list and not res.get('analytic_account_id'):
            warehouse = self.env['stock.warehouse'].browse(res['warehouse_id'])
            if warehouse.analytic_account_id:
                res['analytic_account_id'] = warehouse.analytic_account_id.id
        return res

    @api.onchange('analytic_account_id')
    def _onchange_analytic_account_id(self):
        if self.analytic_account_id:
            warehouses = self.env['stock.warehouse'].search([
                ('analytic_account_id', '=', self.analytic_account_id.id),
                ('company_id', '=', self.company_id.id)
            ])
            if self.warehouse_id and self.warehouse_id not in warehouses:
                self.warehouse_id = False
            if len(warehouses) == 1:
                self.warehouse_id = warehouses[0].id
            elif not warehouses:
                self.warehouse_id = False

            acc_str = str(self.analytic_account_id.id)
            for line in self.order_line:
                if not line.display_type:
                    line.analytic_distribution = {acc_str: 100.0}
        else:
            self.warehouse_id = False

    @api.onchange('warehouse_id')
    def _onchange_warehouse_id_analytic(self):
        if self.warehouse_id and self.warehouse_id.analytic_account_id:
            self.analytic_account_id = self.warehouse_id.analytic_account_id.id

    @api.onchange('partner_id')
    def _onchange_partner_id_update_prices(self):
        for line in self.order_line:
            if line.product_id and not line.is_downpayment:
                line._reset_price_unit()


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    @api.onchange('product_id')
    def _onchange_product_id_set_analytic(self):
        if self.order_id.analytic_account_id and not self.analytic_distribution:
            self.analytic_distribution = {str(self.order_id.analytic_account_id.id): 100.0}

    def _get_display_price_ignore_combo(self):
        self.ensure_one()
        partner = self.order_id.partner_id.commercial_partner_id or self.order_id.partner_id
        if partner and partner.customer_type == 'wholesaler' and self.product_id and self.product_id.wholesale_price > 0:
            price = self.product_id.wholesale_price
            if self.product_uom_id and self.product_id.uom_id and self.product_uom_id != self.product_id.uom_id:
                price = self.product_id.uom_id._compute_price(price, self.product_uom_id)
            return price
        return super()._get_display_price_ignore_combo()
