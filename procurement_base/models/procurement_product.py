from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_active_product = fields.Boolean(
        string="Active", 
        default=True,
        help="If unchecked, this product is inactive and cannot be purchased or sold."
    )
    avg_monthly_consumption = fields.Float(
        string="Average Monthly Consumption",
        company_dependent=True,
        default=0.0,
        digits='Product Unit of Measure',
        help="Average quantity consumed/delivered per month over the past 12 months."
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'is_active_product' in vals:
                is_active = vals['is_active_product']
                vals['sale_ok'] = is_active
                vals['purchase_ok'] = is_active
        return super().create(vals_list)

    def write(self, vals):
        if 'is_active_product' in vals:
            is_active = vals['is_active_product']
            vals['sale_ok'] = is_active
            vals['purchase_ok'] = is_active
        return super().write(vals)

    def _compute_amc_values(self):
        one_year_ago = fields.Datetime.now() - relativedelta(years=1)
        current_company_id = self.env.company.id

        for product in self:
            product.avg_monthly_consumption = 0.0

        if not self:
            return

        moves = self.env['stock.move']._read_group(
            domain=[
                ('product_id.product_tmpl_id', 'in', self.ids),
                ('company_id', '=', current_company_id),
                ('state', '=', 'done'),
                ('date', '>=', one_year_ago),
                ('location_id.usage', '=', 'internal'),
                '|',
                    ('location_dest_id.usage', '!=', 'internal'),
                    ('location_dest_id.company_id', '!=', current_company_id),
            ],
            groupby=['product_id.product_tmpl_id'],
            aggregates=['product_qty:sum'],
        )

        product_id_map = {product.id: product for product in self}

        for product_tmpl, total_qty in moves:
            if product_tmpl.id in product_id_map:
                product_id_map[product_tmpl.id].avg_monthly_consumption = round((total_qty or 0.0) / 12.0, 2)

    def action_compute_amc(self):
        self._compute_amc_values()

    @api.model
    def cron_recompute_amc(self):
        companies = self.env['res.company'].search([])
        for company in companies:
            products = self.with_company(company).search([])
            products.with_company(company)._compute_amc_values()
        return True


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_active_product = fields.Boolean(
        related='product_tmpl_id.is_active_product',
        string="Active",
        store=True,
        readonly=False
    )
    avg_monthly_consumption = fields.Float(
        related='product_tmpl_id.avg_monthly_consumption',
        string="Average Monthly Consumption",
        readonly=False
    )


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        res = super().button_validate()
        for picking in self:
            if picking.state == 'done':
                products = picking.move_ids.mapped('product_id.product_tmpl_id')
                if products:
                    products._compute_amc_values()
        return res
