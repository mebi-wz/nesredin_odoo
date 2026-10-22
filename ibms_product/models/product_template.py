# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import format_amount


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    part_number = fields.Char(
        string='Product Part Number',
        index=True,
        copy=False,
        help="Manufacturer or internal part number for this product.",
    )
    hs_code = fields.Char(
        string='HS Code',
        index=True,
        help="Harmonized System Code used for international trade, customs classification, and foreign procurement.",
    )
    hs_description = fields.Char(
        string='HS Description',
        help="Customs or tariff commodity description.",
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
    secondary_part_number_ids = fields.One2many(
        'product.secondary.part.number',
        'product_tmpl_id',
        domain=[('part_type', '=', 'secondary')],
        string='Secondary Part Numbers',
        copy=True,
        help="Alternative or cross-reference part numbers for purchasing and identification.",
    )
    all_part_number_ids = fields.One2many(
        'product.secondary.part.number',
        'product_tmpl_id',
        string='All Part Numbers',
        help="All part numbers (Primary and Secondary) available for this product.",
    )
    secondary_parts_display = fields.Char(
        string='Secondary Part Numbers',
        compute='_compute_secondary_parts_info',
        store=True,
        help="Summary list of all secondary / cross-reference part numbers.",
    )
    has_secondary_parts = fields.Boolean(
        string='Has Secondary Parts',
        compute='_compute_secondary_parts_info',
        store=True,
        help="Indicates whether this product has secondary / cross-reference part numbers.",
    )
    secondary_parts_count = fields.Integer(
        string='Secondary Parts Count',
        compute='_compute_secondary_parts_info',
        store=True,
    )

    @api.depends('secondary_part_number_ids.name', 'secondary_part_number_ids.part_type')
    def _compute_secondary_parts_info(self):
        for tmpl in self:
            sec_records = tmpl.secondary_part_number_ids.filtered(lambda r: r.part_type == 'secondary' and r.name)
            names = [r.name for r in sec_records]
            tmpl.secondary_parts_display = ", ".join(names) if names else False
            tmpl.secondary_parts_count = len(names)
            tmpl.has_secondary_parts = bool(names)

    def action_view_secondary_part_numbers(self):
        self.ensure_one()
        return {
            'name': _("Secondary / Cross-Reference Part Numbers - %s") % (self.name or self.part_number or ''),
            'type': 'ir.actions.act_window',
            'res_model': 'product.secondary.part.number',
            'view_mode': 'list',
            'domain': [('product_tmpl_id', '=', self.id), ('part_type', '=', 'secondary')],
            'context': {
                'default_product_tmpl_id': self.id,
                'default_part_type': 'secondary',
            },
            'target': 'new',
        }

    def _get_single_tax_amount_and_type(self, price):
        currency = self.currency_id
        taxes = self.taxes_id._filter_taxes_by_company(self.env.company)
        if not taxes:
            return None, ""
        res = taxes.compute_all(price, product=self, partner=self.env['res.partner'])
        included = res['total_included']
        excluded = res['total_excluded']
        if currency.compare_amounts(included, price) > 0:
            return format_amount(self.env, included, currency), "Incl. Taxes"
        elif currency.compare_amounts(excluded, price) < 0:
            return format_amount(self.env, excluded, currency), "Excl. Taxes"
        return None, ""

    @api.depends('taxes_id', 'list_price', 'wholesale_price')
    @api.depends_context('company')
    def _compute_tax_string(self):
        for record in self:
            if not record.taxes_id:
                record.tax_string = " "
                continue
            if record.wholesale_price > 0:
                r_amt, r_type = record._get_single_tax_amount_and_type(record.list_price)
                w_amt, w_type = record._get_single_tax_amount_and_type(record.wholesale_price)
                if r_amt and w_amt:
                    tax_type = r_type or w_type
                    record.tax_string = f"(= Retail: {r_amt} | Wholesale: {w_amt} {tax_type})"
                elif r_amt:
                    record.tax_string = f"(= Retail: {r_amt} {r_type})"
                else:
                    record.tax_string = record._construct_tax_string(record.list_price)
            else:
                record.tax_string = record._construct_tax_string(record.list_price)

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
                        _("The Primary Part Number '%(part)s' is already used by product '%(product)s'. Primary Part Number must be unique!")
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
            ('secondary_part_number_ids.name', '=', name),
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
                ('secondary_part_number_ids.name', operator, name),
            ]
            if existing_ids:
                partial_domain = [('id', 'not in', existing_ids)] + partial_domain
            if domain_list:
                partial_domain = ['&'] + domain_list + partial_domain
            sub_limit = (limit - len(results)) if limit else None
            partial_matches = self.search(partial_domain, limit=sub_limit)
            results.extend([(p.id, p.display_name) for p in partial_matches])

        return results

    def _sync_primary_part_number(self):
        for tmpl in self:
            pn = (tmpl.part_number or '').strip()
            if not pn:
                continue
            primary_rec = self.env['product.secondary.part.number'].sudo().search([
                ('product_tmpl_id', '=', tmpl.id),
                ('part_type', '=', 'primary'),
            ], limit=1)
            if primary_rec:
                if primary_rec.name != pn:
                    primary_rec.write({'name': pn})
            else:
                self.env['product.secondary.part.number'].sudo().create({
                    'product_tmpl_id': tmpl.id,
                    'name': pn,
                    'part_type': 'primary',
                    'is_primary': True,
                })

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('type') == 'service':
                if not vals.get('default_code'):
                    vals['default_code'] = 'DISC' if 'discount' in (vals.get('name') or '').lower() else 'SRV'
                if not vals.get('part_number'):
                    vals['part_number'] = vals['default_code']
            if self.env.context.get('create_product_product') is False:
                # Being created via product.product delegation; default_code is validated on product.product
                if not vals.get('part_number') and not self.env.context.get('install_mode'):
                    raise ValidationError(_("Product Part Number is required for product registration!"))
                continue

            if not vals.get('default_code') and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Code is required for product registration!"))
            if not vals.get('part_number') and not self.env.context.get('install_mode'):
                raise ValidationError(_("Product Part Number is required for product registration!"))
        records = super().create(vals_list)
        records._sync_primary_part_number()
        return records

    def write(self, vals):
        if 'default_code' in vals and not vals.get('default_code'):
            raise ValidationError(_("Product Code cannot be empty!"))
        if 'part_number' in vals and not vals.get('part_number'):
            raise ValidationError(_("Product Part Number cannot be empty!"))
        res = super().write(vals)
        if 'part_number' in vals:
            self._sync_primary_part_number()
        return res
