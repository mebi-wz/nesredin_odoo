# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    part_number = fields.Char(
        string='Product Part Number',
        index=True,
        copy=False,
        help="Manufacturer or internal part number for this product.",
    )
    wholesale_price = fields.Float(
        string='Wholesale Price',
        digits='Product Price',
        default=0.0,
        help="Wholesale selling price for this product.",
    )
    additional_image = fields.Image(
        string='Additional Image',
        max_width=1920,
        max_height=1920,
        help="Secondary or additional image for this product.",
    )

    @api.constrains('default_code')
    def _check_default_code_unique(self):
        for record in self:
            code = (record.default_code or '').strip()
            if code:
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('default_code', '=ilike', code),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _("The Product Code '%(code)s' is already used by product '%(product)s'. Product Code must be unique!")
                        % {'code': code, 'product': duplicate.display_name}
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.context.get('create_product_product') is False:
                # Being created via product.product delegation; default_code is validated on product.product
                if not vals.get('part_number') and not self.env.context.get('install_mode'):
                    raise ValidationError(_("Product Part Number is required for product registration!"))
                continue

            if not vals.get('default_code') and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Code is required for product registration!"))
            if not vals.get('part_number') and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Part Number is required for product registration!"))
        return super().create(vals_list)

    def write(self, vals):
        if 'default_code' in vals and not vals.get('default_code'):
            raise ValidationError(_("Product Code cannot be empty!"))
        if 'part_number' in vals and not vals.get('part_number'):
            raise ValidationError(_("Product Part Number cannot be empty!"))
        return super().write(vals)
