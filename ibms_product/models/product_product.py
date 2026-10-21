# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    @api.depends('taxes_id', 'lst_price', 'wholesale_price')
    @api.depends_context('company')
    def _compute_tax_string(self):
        for record in self:
            if not record.taxes_id:
                record.tax_string = " "
                continue
            if record.wholesale_price > 0:
                r_amt, r_type = record.product_tmpl_id._get_single_tax_amount_and_type(record.lst_price)
                w_amt, w_type = record.product_tmpl_id._get_single_tax_amount_and_type(record.wholesale_price)
                if r_amt and w_amt:
                    tax_type = r_type or w_type
                    record.tax_string = f"(= Retail: {r_amt} | Wholesale: {w_amt} {tax_type})"
                elif r_amt:
                    record.tax_string = f"(= Retail: {r_amt} {r_type})"
                else:
                    record.tax_string = record.product_tmpl_id._construct_tax_string(record.lst_price)
            else:
                record.tax_string = record.product_tmpl_id._construct_tax_string(record.lst_price)

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
                        _("The Product Code '%(code)s' is already used by product variant '%(product)s'. Product Code must be unique!")
                        % {'code': code, 'product': duplicate.display_name}
                    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tmpl = self.env['product.template'].browse(vals['product_tmpl_id']) if vals.get('product_tmpl_id') else False
            prod_type = vals.get('type') or (tmpl and tmpl.type)
            if prod_type == 'service':
                if not vals.get('default_code') and not (tmpl and tmpl.default_code):
                    vals['default_code'] = 'DISC' if 'discount' in (vals.get('name') or (tmpl and tmpl.name) or '').lower() else 'SRV'
                if not vals.get('part_number') and not (tmpl and tmpl.part_number):
                    vals['part_number'] = vals.get('default_code') or 'SRV'
            code = vals.get('default_code') or (tmpl and tmpl.default_code)
            part = vals.get('part_number') or (tmpl and tmpl.part_number)
            if not code and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Code is required for product registration!"))
            if not part and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Part Number is required for product registration!"))
        return super().create(vals_list)

    def write(self, vals):
        if 'default_code' in vals and not vals.get('default_code'):
            raise ValidationError(_("Product Code cannot be empty!"))
        if 'part_number' in vals and not vals.get('part_number'):
            raise ValidationError(_("Product Part Number cannot be empty!"))
        return super().write(vals)

    def action_compute_amc(self):
        if hasattr(self.product_tmpl_id, 'action_compute_amc'):
            return self.product_tmpl_id.action_compute_amc()
        return True
