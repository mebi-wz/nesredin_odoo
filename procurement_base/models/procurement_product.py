import re
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.fields import Domain


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

    @api.depends('name', 'default_code')
    def _compute_display_name(self):
        super()._compute_display_name()
        has_part = 'part_number' in self._fields
        for template in self:
            code = (template.default_code or '').strip()
            part = (getattr(template, 'part_number', '') or '').strip() if has_part else ''
            if not code and not part:
                continue
            name = template.name or ''
            parts = []
            if code:
                parts.append(code)
            if part and part != code:
                parts.append(f"PN: {part}")
            if parts:
                template.display_name = f"[{' | '.join(parts)}] {name}"

    def _search_display_name(self, operator, value):
        is_positive = operator not in Domain.NEGATIVE_OPERATORS
        base_domain = super()._search_display_name(operator, value)
        if not is_positive or not value or not isinstance(value, str):
            return base_domain

        val = value.strip()
        matching_categories = self.env['product.category'].search([('name', operator, val)])
        categ_clause = [('categ_id', 'child_of', matching_categories.ids)] if matching_categories else [('categ_id.name', operator, val)]

        extra_domains = [categ_clause]
        if 'part_number' in self._fields:
            extra_domains.append([('part_number', operator, val)])

        words = val.split()
        if len(words) > 1:
            multi_domain = Domain.TRUE
            for w in words:
                w_cats = self.env['product.category'].search([('name', 'ilike', w)])
                w_categ_clause = [('categ_id', 'child_of', w_cats.ids)] if w_cats else [('categ_id.name', 'ilike', w)]
                word_or_list = [
                    [('name', 'ilike', w)],
                    [('default_code', 'ilike', w)],
                    w_categ_clause,
                ]
                if 'part_number' in self._fields:
                    word_or_list.append([('part_number', 'ilike', w)])
                multi_domain = multi_domain & Domain.OR(word_or_list)
            extra_domains.append(multi_domain)

        return Domain.OR([base_domain] + extra_domains)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if not name:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        name_str = name.strip()
        positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
        if operator not in positive_operators:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        domain = Domain(domain or Domain.TRUE)
        ordered_templates = self.browse()
        has_part = 'part_number' in self._fields

        def _add_matches(search_domain, current_limit):
            nonlocal ordered_templates
            if current_limit <= 0:
                return
            already_ids = ordered_templates.ids
            sub_domain = search_domain
            if already_ids:
                sub_domain = sub_domain & Domain('id', 'not in', already_ids)
            found = self.search_fetch(sub_domain, ['display_name'], limit=current_limit)
            ordered_templates |= found

        max_limit = limit or 100

        # Exact match
        exact_clauses = [('default_code', '=', name_str), ('barcode', '=', name_str)]
        if has_part:
            exact_clauses.append(('part_number', '=', name_str))
        exact_domain_list = ['|'] * (len(exact_clauses) - 1) + exact_clauses
        _add_matches(domain & Domain(exact_domain_list), max_limit - len(ordered_templates))

        # Code or Part Number ilike
        if len(ordered_templates) < max_limit:
            if has_part:
                _add_matches(domain & Domain(['|', ('default_code', operator, name_str), ('part_number', operator, name_str)]), max_limit - len(ordered_templates))
            else:
                _add_matches(domain & Domain('default_code', operator, name_str), max_limit - len(ordered_templates))

        # Name ilike
        if len(ordered_templates) < max_limit:
            _add_matches(domain & Domain('name', operator, name_str), max_limit - len(ordered_templates))

        # Category ilike
        if len(ordered_templates) < max_limit:
            matching_categories = self.env['product.category'].search([('name', operator, name_str)])
            if matching_categories:
                _add_matches(domain & Domain('categ_id', 'child_of', matching_categories.ids), max_limit - len(ordered_templates))

        # Multi-word
        words = name_str.split()
        if len(ordered_templates) < max_limit and len(words) > 1:
            multi_domain = Domain.TRUE
            for word in words:
                word_categories = self.env['product.category'].search([('name', 'ilike', word)])
                categ_clause = [('categ_id', 'child_of', word_categories.ids)] if word_categories else []
                word_or_list = [
                    [('default_code', 'ilike', word)],
                    [('name', 'ilike', word)],
                ]
                if has_part:
                    word_or_list.append([('part_number', 'ilike', word)])
                if categ_clause:
                    word_or_list.append(categ_clause)
                multi_domain = multi_domain & Domain.OR(word_or_list)
            _add_matches(domain & multi_domain, max_limit - len(ordered_templates))

        if not ordered_templates:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        return [(t.id, t.display_name) for t in ordered_templates.sudo()]

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

    @api.depends('name', 'default_code', 'product_tmpl_id')
    @api.depends_context('display_default_code', 'seller_id', 'company_id', 'partner_id', 'formatted_display_name', 'lang')
    def _compute_display_name(self):
        super()._compute_display_name()
        has_part = 'part_number' in self._fields
        for product in self:
            if not self.env.context.get('display_default_code', True):
                continue
            code = (product.default_code or '').strip()
            part = (getattr(product, 'part_number', '') or '').strip() if has_part else ''
            if not code and not part:
                continue
            name = product.name or ''
            variant = product.product_template_attribute_value_ids._get_combination_name()
            full_name = f"{name} ({variant})" if variant else name

            parts = []
            if code:
                parts.append(code)
            if part and part != code:
                parts.append(f"PN: {part}")

            if parts:
                product.display_name = f"[{' | '.join(parts)}] {full_name}"

    def _search_display_name(self, operator, value):
        is_positive = operator not in Domain.NEGATIVE_OPERATORS
        base_domain = super()._search_display_name(operator, value)
        if not is_positive or not value or not isinstance(value, str):
            return base_domain

        val = value.strip()
        matching_categories = self.env['product.category'].search([('name', operator, val)])
        categ_clause = [('categ_id', 'child_of', matching_categories.ids)] if matching_categories else [('categ_id.name', operator, val)]

        extra_domains = [categ_clause]
        if 'part_number' in self._fields:
            extra_domains.append([('part_number', operator, val)])

        words = val.split()
        if len(words) > 1:
            multi_domain = Domain.TRUE
            for w in words:
                w_cats = self.env['product.category'].search([('name', 'ilike', w)])
                w_categ_clause = [('categ_id', 'child_of', w_cats.ids)] if w_cats else [('categ_id.name', 'ilike', w)]
                word_or_list = [
                    [('name', 'ilike', w)],
                    [('default_code', 'ilike', w)],
                    w_categ_clause,
                ]
                if 'part_number' in self._fields:
                    word_or_list.append([('part_number', 'ilike', w)])
                multi_domain = multi_domain & Domain.OR(word_or_list)
            extra_domains.append(multi_domain)

        return Domain.OR([base_domain] + extra_domains)

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if not name:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        name_str = name.strip()
        positive_operators = ['=', 'ilike', '=ilike', 'like', '=like']
        if operator not in positive_operators:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        domain = Domain(domain or Domain.TRUE)
        ordered_products = self.browse()
        has_part = 'part_number' in self._fields

        def _add_matches(search_domain, current_limit):
            nonlocal ordered_products
            if current_limit <= 0:
                return
            already_ids = ordered_products.ids
            sub_domain = search_domain
            if already_ids:
                sub_domain = sub_domain & Domain('id', 'not in', already_ids)
            found = self.search_fetch(sub_domain, ['display_name'], limit=current_limit)
            ordered_products |= found

        max_limit = limit or 100

        # Check bracketed code/part number e.g. [SP001 | PN: 123] or [SP001]
        m = re.search(r'\[(.*?)\]', name_str)
        if m:
            bracket_val = m.group(1).split('|')[0].replace('PN:', '').strip()
            if bracket_val:
                bracket_clauses = [('default_code', '=', bracket_val)]
                if has_part:
                    bracket_clauses = ['|', ('default_code', '=', bracket_val), ('part_number', '=', bracket_val)]
                _add_matches(domain & Domain(bracket_clauses), max_limit - len(ordered_products))

        # 1. Exact match on Product Code, Part Number, or Barcode
        if len(ordered_products) < max_limit:
            exact_clauses = [('default_code', '=', name_str), ('barcode', '=', name_str)]
            if has_part:
                exact_clauses.append(('part_number', '=', name_str))
            exact_domain_list = ['|'] * (len(exact_clauses) - 1) + exact_clauses
            _add_matches(domain & Domain(exact_domain_list), max_limit - len(ordered_products))

        # 2. Match Product Code or Part Number with operator (ilike)
        if len(ordered_products) < max_limit:
            if has_part:
                _add_matches(domain & Domain([
                    '|',
                    ('default_code', operator, name_str),
                    ('part_number', operator, name_str),
                ]), max_limit - len(ordered_products))
            else:
                _add_matches(domain & Domain('default_code', operator, name_str), max_limit - len(ordered_products))

        # 3. Match Product Name (ilike)
        if len(ordered_products) < max_limit:
            _add_matches(domain & Domain('name', operator, name_str), max_limit - len(ordered_products))

        # 4. Match Category Name (ilike)
        if len(ordered_products) < max_limit:
            matching_categories = self.env['product.category'].search([('name', operator, name_str)])
            if matching_categories:
                _add_matches(domain & Domain('categ_id', 'child_of', matching_categories.ids), max_limit - len(ordered_products))

        # 5. Multi-token / multi-word search (e.g. "04465 brake" or "oil filter 123")
        words = name_str.split()
        if len(ordered_products) < max_limit and len(words) > 1:
            multi_domain = Domain.TRUE
            for word in words:
                word_categories = self.env['product.category'].search([('name', 'ilike', word)])
                categ_clause = [('categ_id', 'child_of', word_categories.ids)] if word_categories else []
                word_or_list = [
                    [('default_code', 'ilike', word)],
                    [('name', 'ilike', word)],
                ]
                if has_part:
                    word_or_list.append([('part_number', 'ilike', word)])
                if categ_clause:
                    word_or_list.append(categ_clause)
                multi_domain = multi_domain & Domain.OR(word_or_list)
            _add_matches(domain & multi_domain, max_limit - len(ordered_products))

        # 6. Fallback if still no products found (e.g. supplier info or super)
        if not ordered_products:
            return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

        return [(p.id, p.display_name) for p in ordered_products.sudo()]

    def action_compute_amc(self):
        return self.product_tmpl_id.action_compute_amc()


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    image_128 = fields.Image(
        string='Image',
        related='product_id.image_128',
        readonly=True,
    )
    image_1920 = fields.Image(
        string='Full Image',
        related='product_id.image_1920',
        readonly=True,
    )
    part_number = fields.Char(
        string='Part Number',
        related='product_id.part_number',
        readonly=True,
    )
    categ_id = fields.Many2one(
        'product.category',
        string='Category',
        related='product_id.categ_id',
        readonly=True,
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

