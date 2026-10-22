from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AssetCategory(models.Model):
    _name = 'am.asset.category'
    _description = 'Asset Category'

    name = fields.Char(string='Category Name', required=True)
    code = fields.Char(
        string='Category Code', required=True, readonly=True, copy=False,
        default='New',
    )
    depreciation_rate = fields.Float(string='Depreciation Rate (%)')

    # Link to Accounting Asset Category (om_account_asset)
    accounting_category_id = fields.Many2one(
        'account.asset.category',
        string='Accounting Asset Category',
        domain="[('type', '=', 'purchase')]",
        help="Link to the Accounting Asset Category in the Accounting module. "
             "When an asset of this category is confirmed, a corresponding financial "
             "asset will be automatically created in accounting."
    )

    # Accounting Fields
    account_asset_id = fields.Many2one(
        'account.account', string='Asset Account',
        domain=[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'liability_credit_card'))],
        help="Account used to record the purchase of the asset at its original price."
    )
    account_depreciation_id = fields.Many2one(
        'account.account', string='Depreciation Asset Account',
        domain=[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'liability_credit_card'))],
        help="Account used in the depreciation entries, to decrease the asset value."
    )
    account_depreciation_expense_id = fields.Many2one(
        'account.account', string='Depreciation Expense Account',
        domain=[('account_type', 'not in', ('asset_receivable', 'liability_payable', 'asset_cash', 'liability_credit_card'))],
        help="Account used in the periodical entries to record a part of the asset as expense."
    )
    journal_id = fields.Many2one('account.journal', string='Journal')

    minor_ids = fields.One2many('am.asset.minor_category', 'major_category_id', string='Minor Categories')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        # Serialize code allocation so concurrent imports cannot receive the
        # same two-digit major-category code.
        self.env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [9172301])
        self.env.cr.execute("""
            SELECT COALESCE(MAX(CAST(code AS INTEGER)), 0)
              FROM am_asset_category
             WHERE code ~ '^[0-9]+$'
        """)
        next_code = self.env.cr.fetchone()[0] + 1
        for vals in vals_list:
            if not vals.get('code') or vals.get('code') == 'New':
                if next_code > 99:
                    raise ValidationError(
                        'Major category codes are limited to two digits (01-99).'
                    )
                vals['code'] = f'{next_code:02d}'
                next_code += 1
            if not vals.get('accounting_category_id') and vals.get('name') and vals.get('account_asset_id') and vals.get('account_depreciation_id') and vals.get('account_depreciation_expense_id') and vals.get('journal_id'):
                # Automatically create account.asset.category
                acc_cat = self.env['account.asset.category'].create({
                    'name': vals.get('name'),
                    'account_asset_id': vals.get('account_asset_id'),
                    'account_depreciation_id': vals.get('account_depreciation_id'),
                    'account_depreciation_expense_id': vals.get('account_depreciation_expense_id'),
                    'journal_id': vals.get('journal_id'),
                    'company_id': vals.get('company_id') or self.env.company.id,
                    'type': 'purchase',
                })
                vals['accounting_category_id'] = acc_cat.id
        return super(AssetCategory, self).create(vals_list)

    def write(self, vals):
        res = super(AssetCategory, self).write(vals)
        for rec in self:
            if not rec.accounting_category_id:
                if rec.name and rec.account_asset_id and rec.account_depreciation_id and rec.account_depreciation_expense_id and rec.journal_id:
                    acc_cat = self.env['account.asset.category'].create({
                        'name': rec.name,
                        'account_asset_id': rec.account_asset_id.id,
                        'account_depreciation_id': rec.account_depreciation_id.id,
                        'account_depreciation_expense_id': rec.account_depreciation_expense_id.id,
                        'journal_id': rec.journal_id.id,
                        'company_id': rec.company_id.id or self.env.company.id,
                        'type': 'purchase',
                    })
                    super(AssetCategory, rec).write({'accounting_category_id': acc_cat.id})
            else:
                # Sync updates to the linked accounting category
                update_vals = {}
                if 'name' in vals:
                    update_vals['name'] = vals['name']
                if 'account_asset_id' in vals:
                    update_vals['account_asset_id'] = vals['account_asset_id']
                if 'account_depreciation_id' in vals:
                    update_vals['account_depreciation_id'] = vals['account_depreciation_id']
                if 'account_depreciation_expense_id' in vals:
                    update_vals['account_depreciation_expense_id'] = vals['account_depreciation_expense_id']
                if 'journal_id' in vals:
                    update_vals['journal_id'] = vals['journal_id']
                
                if update_vals:
                    rec.accounting_category_id.write(update_vals)
        return res

class AssetMinorCategory(models.Model):
    _name = 'am.asset.minor_category'
    _description = 'Asset Minor Category'

    name = fields.Char(string='Minor Category Name', required=True)
    code = fields.Char(
        string='Minor Category Code', required=True, readonly=True, copy=False,
        default='New',
    )
    major_category_id = fields.Many2one('am.asset.category', string='Major Category', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)

    specification_template_ids = fields.One2many(
        'am.asset.specification.template',
        'minor_category_id',
        string='Specification Templates'
    )

    @api.model_create_multi
    def create(self, vals_list):
        next_by_major = {}
        for vals in vals_list:
            if not vals.get('code') or vals.get('code') == 'New':
                major_id = vals.get('major_category_id')
                if not major_id:
                    raise ValidationError(
                        'Select a major category before generating a minor category code.'
                    )
                if major_id not in next_by_major:
                    # One independent 01-99 counter for every major category.
                    self.env.cr.execute(
                        'SELECT pg_advisory_xact_lock(%s)', [9172301 + major_id]
                    )
                    self.env.cr.execute("""
                        SELECT COALESCE(MAX(CAST(code AS INTEGER)), 0)
                          FROM am_asset_minor_category
                         WHERE major_category_id = %s
                           AND code ~ '^[0-9]+$'
                    """, [major_id])
                    next_by_major[major_id] = self.env.cr.fetchone()[0] + 1
                next_code = next_by_major[major_id]
                if next_code > 99:
                    raise ValidationError(
                        'Minor category codes are limited to 01-99 per major category.'
                    )
                vals['code'] = f'{next_code:02d}'
                next_by_major[major_id] = next_code + 1
        return super().create(vals_list)
