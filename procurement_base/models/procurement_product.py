from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_active_product = fields.Boolean(
        string="Active", 
        default=True,
        help="If unchecked, this product is inactive and cannot be purchased or sold."
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


class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_active_product = fields.Boolean(
        related='product_tmpl_id.is_active_product',
        string="Active",
        store=True,
        readonly=False
    )
