# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ProductProduct(models.Model):
    _inherit = 'product.product'

    secondary_parts_display = fields.Char(
        related='product_tmpl_id.secondary_parts_display',
        string='Secondary Part Numbers',
        readonly=True,
    )
    has_secondary_parts = fields.Boolean(
        related='product_tmpl_id.has_secondary_parts',
        string='Has Secondary Parts',
        readonly=True,
    )
    secondary_parts_count = fields.Integer(
        related='product_tmpl_id.secondary_parts_count',
        string='Secondary Parts Count',
        readonly=True,
    )

    def action_view_secondary_part_numbers(self):
        self.ensure_one()
        return self.product_tmpl_id.action_view_secondary_part_numbers()

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

    @api.constrains('part_number')
    def _check_part_number_unique(self):
        for record in self:
            part = (record.part_number or '').strip()
            if part:
                duplicate = self.search([
                    ('id', '!=', record.id),
                    ('part_number', '=ilike', part),
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        _("The Primary Part Number '%(part)s' is already used by product variant '%(product)s'. Primary Part Number must be unique!")
                        % {'part': part, 'product': duplicate.display_name}
                    )

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if not name:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        results = []
        domain_list = list(domain or [])

        # 1. Exact match on primary part number or secondary part numbers first
        exact_domain = [
            '|',
            ('part_number', '=', name),
            ('product_tmpl_id.secondary_part_number_ids.name', '=', name),
        ]
        if domain_list:
            exact_domain = ['&'] + domain_list + exact_domain
        exact_matches = self.search(exact_domain, limit=limit)
        results.extend([(p.id, p.display_name) for p in exact_matches])

        # 2. Super results (matches default_code, name, barcode)
        if limit is None or len(results) < limit:
            sub_limit = (limit - len(results)) if limit else None
            super_domain = domain_list
            if results:
                super_domain = [('id', 'not in', [r[0] for r in results])] + super_domain
            super_results = super().name_search(name=name, domain=super_domain, operator=operator, limit=sub_limit)
            results.extend(super_results)

        # 3. Partial match on primary or secondary part numbers
        if limit is None or len(results) < limit:
            existing_ids = [r[0] for r in results]
            partial_domain = [
                '|',
                ('part_number', operator, name),
                ('product_tmpl_id.secondary_part_number_ids.name', operator, name),
            ]
            if existing_ids:
                partial_domain = [('id', 'not in', existing_ids)] + partial_domain
            if domain_list:
                partial_domain = ['&'] + domain_list + partial_domain
            sub_limit = (limit - len(results)) if limit else None
            partial_matches = self.search(partial_domain, limit=sub_limit)
            results.extend([(p.id, p.display_name) for p in partial_matches])

        return results

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tmpl = self.env['product.template'].browse(vals['product_tmpl_id']) if vals.get('product_tmpl_id') else False
            is_landed_cost = bool(
                vals.get('landed_cost_ok')
                or (tmpl and tmpl.landed_cost_ok)
                or self.env.context.get('default_landed_cost_ok')
                or self.env.context.get('landed_cost_product_entry')
            )
            prod_type = vals.get('type') or (tmpl and tmpl.type)
            if prod_type == 'service' and not is_landed_cost:
                if not vals.get('default_code') and not (tmpl and tmpl.default_code):
                    vals['default_code'] = 'DISC' if 'discount' in (vals.get('name') or (tmpl and tmpl.name) or '').lower() else 'SRV'
                if not vals.get('part_number') and not (tmpl and tmpl.part_number):
                    vals['part_number'] = vals.get('default_code') or 'SRV'
            code = vals.get('default_code') or (tmpl and tmpl.default_code)
            part = vals.get('part_number') or (tmpl and tmpl.part_number)
            if not is_landed_cost:
                if not code and not self.env.context.get('install_mode'):
                    raise ValidationError(_("Product Code is required for product registration!"))
                if not part and not self.env.context.get('install_mode'):
                    raise ValidationError(_("Product Part Number is required for product registration!"))
        return super().create(vals_list)

    def write(self, vals):
        for product in self:
            is_landed_cost = vals.get('landed_cost_ok', product.landed_cost_ok)
            if not is_landed_cost:
                if 'default_code' in vals and not vals.get('default_code'):
                    raise ValidationError(_("Product Code cannot be empty!"))
                if 'part_number' in vals and not vals.get('part_number'):
                    raise ValidationError(_("Product Part Number cannot be empty!"))
        return super().write(vals)

    def action_compute_amc(self):
        if hasattr(self.product_tmpl_id, 'action_compute_amc'):
            return self.product_tmpl_id.action_compute_amc()
        return True
