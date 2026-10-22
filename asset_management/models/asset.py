import base64
from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError

class AssetRegistration(models.Model):
    _name = 'am.asset'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Asset Registration'

    name = fields.Char(string='Asset Name', required=True, tracking=True)
    active = fields.Boolean(default=True)
    employee_name = fields.Char(string='Employee Name', tracking=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', tracking=True)
    description = fields.Text(string='Description', tracking=True)
    years_of_manufacture = fields.Selection(
        selection='_get_year_selection',
        string='Year of Manufacture',
        tracking=True
    )

    def _get_year_selection(self):
        from datetime import datetime
        current_year = datetime.now().year
        return [(str(year), str(year)) for year in range(current_year, current_year - 100, -1)]
    acquisition_date = fields.Date(string='Acquisition Date', tracking=True)
    original_cost = fields.Float(string='Original Cost', tracking=True)
    accumulated_depreciation = fields.Float(string='Accumulated Depreciation', compute='_compute_accumulated_depreciation', store=True, tracking=True)
    net_book_value = fields.Float(string='Net Book Value', compute='_compute_net_book_value', store=True, tracking=True)
    
    # Depreciation History
    depreciation_line_ids = fields.One2many('am.asset.depreciation.line', 'asset_id', string='Depreciation History')
    salvage_value = fields.Float(string='Salvage Value', tracking=True, help="Amount that cannot be depreciated.")
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('open', 'Running'),
        ('close', 'Closed')
    ], string='Status', default='draft', readonly=True, tracking=True)

    # Link to Accounting Asset
    financial_asset_id = fields.Many2one(
        'account.asset.asset',
        string='Accounting Asset',
        readonly=True,
        copy=False,
        help="Linked financial asset created automatically upon validation in the Accounting module."
    )

    serial_number = fields.Char(string='Serial Number', tracking=True)
    tag_number = fields.Char('Tag Number', store=True, tracking=True, copy=False)
    qr_code_number = fields.Char('Tag Number', related='tag_number', readonly=False, store=True)
    old_tag_number = fields.Char('Tag Number', related='tag_number', readonly=False)
    status_id = fields.Many2one('am.asset.status', string='Status', tracking=True)
    major_category_id = fields.Many2one('am.asset.category', string='Major Category', required=True, tracking=True)
    minor_category_id = fields.Many2one(
        'am.asset.minor_category',
        string='Minor Category',
        domain="[('major_category_id', '=', major_category_id)]",
        tracking=True
    )
    is_scannable = fields.Boolean(string='Is Scannable', default=True, tracking=True)
    grn_file = fields.Binary(string='GRN Document')

    # Vehicle-related fields
    is_vehicle = fields.Boolean(string="Is Vehicle Asset", default=False, tracking=True)
    vehicle_id = fields.One2many('am.asset.vehicle', 'asset_id', string='Vehicle Info')


    @api.constrains('is_vehicle', 'vehicle_id')
    def _check_vehicle_details_required(self):
        for rec in self:
            if rec.is_vehicle and not rec.vehicle_id:
                raise ValidationError(
                    "Vehicle details are mandatory when 'Is Vehicle Asset' is enabled.\n"
                    "Please add vehicle information (type, model, plate number) in the "
                    "Vehicle Details tab."
                )
            if rec.is_vehicle and len(rec.vehicle_id) > 1:
                raise ValidationError("Only one vehicle record is allowed per asset.")

    # Component logic
    is_component = fields.Boolean(string="Is Component", default=False, tracking=True)
    parent_asset_id = fields.Many2one(
        'am.asset',
        string='Parent Asset',
        domain="[('is_component', '=', False)]",
        tracking=True
    )
    child_asset_ids = fields.One2many('am.asset', 'parent_asset_id', string='Components/Child Assets')

    # Specifications
    specification_ids = fields.One2many('am.asset.specification', 'asset_id', string='Specifications')

    def _sync_specification_templates(self):
        for rec in self:
            if not rec.minor_category_id:
                continue

            existing_names = set(rec.specification_ids.mapped('name'))
            existing_specs = {spec.template_id.id: spec for spec in rec.specification_ids if spec.template_id}

            for template in rec.minor_category_id.specification_template_ids:
                existing_spec = existing_specs.get(template.id)
                if existing_spec:
                    if existing_spec.is_accessory != template.is_accessory or existing_spec.is_required != template.is_required:
                        existing_spec.write({
                            'is_accessory': template.is_accessory,
                            'is_required': template.is_required,
                        })
                    continue
                if template.name in existing_names:
                    continue

                self.env['am.asset.specification'].create({
                    'asset_id': rec.id,
                    'template_id': template.id,
                    'name': template.name,
                    'value': template.default_value or '',
                    'uom': template.uom or '',
                    'is_accessory': template.is_accessory,
                    'is_required': template.is_required,
                })

    branch_id = fields.Many2one('account.analytic.account', string="Branch", required=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True, tracking=True)
    currency_id = fields.Many2one('res.currency', string='Currency', related='company_id.currency_id', readonly=True)

    location = fields.Selection(
        [
            ('employee', 'Employee'),
            ('warehouse', 'Warehouse'),
            ('neither', 'Not Assigned'),
        ],
        string="Location",
        compute='_compute_location',
        store=True,
        tracking=True
    )

    @api.depends()
    def _compute_location(self):
        EmployeeAsset = self.env['am.employee.asset']
        WarehouseStock = self.env['am.asset.warehouse.stock']

        for asset in self:
            # Look if this asset is assigned to an employee
            if EmployeeAsset.search([('asset_id', '=', asset.id)], limit=1):
                asset.location = 'employee'
            # Look if this asset is in a warehouse
            elif WarehouseStock.search([('asset_id', '=', asset.id)], limit=1):
                asset.location = 'warehouse'
            # If neither, mark as unassigned
            else:
                asset.location = 'neither'

    @api.depends('depreciation_line_ids.amount', 'depreciation_line_ids.move_id')
    def _compute_accumulated_depreciation(self):
        for record in self:
            # If we are doing accounting, we might only want to count posted lines.
            # For now, let's show total generated, but we can add a filter for posted.
            record.accumulated_depreciation = sum(record.depreciation_line_ids.mapped('amount'))

    @api.model
    def _cron_generate_depreciation(self):
        """Called by Scheduled Action to generate yearly depreciation lines."""
        assets = self.search([('acquisition_date', '!=', False), ('original_cost', '>', 0)])
        assets.action_generate_depreciation_lines()

    def action_generate_depreciation_lines(self):
        """Generates missing yearly depreciation lines for the assets."""
        today = fields.Date.today()
        for asset in self:
            if not asset.acquisition_date or not asset.major_category_id.depreciation_rate:
                continue
            
            # Calculate how many years have passed since acquisition
            acquisition_year = asset.acquisition_date.year
            current_year = today.year
            rate = asset.major_category_id.depreciation_rate / 100.0
            yearly_amount = asset.original_cost * rate

            for year in range(acquisition_year, current_year + 1):
                # Check if line already exists for this year
                year_start = fields.Date.to_date(f'{year}-01-01')
                year_end = fields.Date.to_date(f'{year}-12-31')
                
                # Special case for acquisition year: check if we should depreciate full year or pro-rata
                # Here we'll do full year for simplicity as requested "every year should be depreciate"
                
                existing = self.env['am.asset.depreciation.line'].search([
                    ('asset_id', '=', asset.id),
                    ('date', '>=', year_start),
                    ('date', '<=', year_end)
                ])
                
                if not existing:
                    # Create the line
                    # Cap it so we don't exceed original cost
                    total_so_far = sum(asset.depreciation_line_ids.mapped('amount'))
                    remaining = asset.original_cost - total_so_far
                    if remaining > 0:
                        amount_to_add = min(yearly_amount, remaining)
                        if amount_to_add > 0.01:
                            self.env['am.asset.depreciation.line'].create({
                                'asset_id': asset.id,
                                'date': year_end if year < current_year else today,
                                'amount': amount_to_add,
                                'notes': f'Automatic Yearly Depreciation - {year}'
                            })

    def action_validate(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.acquisition_date:
                raise ValidationError("Acquisition Date is required to validate the asset.")
            if rec.original_cost <= 0:
                raise ValidationError("Original Cost must be greater than 0.")

            # ── Optional accounting category mapping ───────────────────────
            accounting_cat = rec.major_category_id.accounting_category_id
            if not accounting_cat:
                major_cat = rec.major_category_id
                if (major_cat.account_asset_id
                        and major_cat.account_depreciation_id
                        and major_cat.account_depreciation_expense_id
                        and major_cat.journal_id):
                    # Auto-create the accounting category from the category's accounts
                    accounting_cat = self.env['account.asset.category'].create({
                        'name': major_cat.name,
                        'account_asset_id': major_cat.account_asset_id.id,
                        'account_depreciation_id': major_cat.account_depreciation_id.id,
                        'account_depreciation_expense_id': major_cat.account_depreciation_expense_id.id,
                        'journal_id': major_cat.journal_id.id,
                        'company_id': major_cat.company_id.id or self.env.company.id,
                        'type': 'purchase',
                    })
                    major_cat.write({'accounting_category_id': accounting_cat.id})
                # else: no accounting configured — asset validates without a financial entry

            rec.state = 'open'
            rec.action_generate_depreciation_lines()

            # ── Create linked financial asset (only when accounting is set up) ──
            if accounting_cat:
                asset_vals = {
                    'name': rec.name,
                    'category_id': accounting_cat.id,
                    'value': rec.original_cost,
                    'salvage_value': rec.salvage_value or 0.0,
                    'date': rec.acquisition_date,
                    'code': rec.tag_number or rec.qr_code_number or '',
                    'company_id': rec.company_id.id,
                    'currency_id': rec.currency_id.id,
                    'physical_asset_id': rec.id,
                }
                AccountAsset = self.env['account.asset.asset']
                cat_defaults = AccountAsset.onchange_category_id_values(accounting_cat.id)
                if cat_defaults and cat_defaults.get('value'):
                    asset_vals.update(cat_defaults['value'])
                financial_asset = AccountAsset.create(asset_vals)
                rec.financial_asset_id = financial_asset.id

    def action_set_to_draft(self):
        for rec in self:
            if any(line.move_id for line in rec.depreciation_line_ids):
                raise ValidationError("Cannot reset to draft because some depreciation lines are already posted to accounting.")
            # Handle linked financial asset
            if rec.financial_asset_id:
                if rec.financial_asset_id.state in ('open', 'close'):
                    raise ValidationError(
                        "Cannot reset to draft: The linked Accounting Asset '%s' is already confirmed. "
                        "Please reset or dispose the accounting asset first." % rec.financial_asset_id.name
                    )
                # Delete draft financial asset
                rec.financial_asset_id.unlink()
                rec.financial_asset_id = False
            rec.state = 'draft'

    def action_close(self):
        for rec in self:
            rec.state = 'close'
            # Close the linked financial asset if it's running
            if rec.financial_asset_id and rec.financial_asset_id.state == 'open':
                rec.financial_asset_id.set_to_close()

    def action_view_financial_asset(self):
        self.ensure_one()
        return {
            'name': 'Accounting Asset',
            'type': 'ir.actions.act_window',
            'res_model': 'account.asset.asset',
            'res_id': self.financial_asset_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_print_tag(self):
        """Print the physical Asset Tag(s) / Label(s) for this recordset."""
        records = self
        if not records:
            active_ids = self.env.context.get('active_ids')
            if active_ids:
                records = self.browse(active_ids)
            else:
                raise UserError("Please select at least one asset to print tag(s).")
        return self.env.ref('asset_management.action_report_asset_tag').report_action(records)

    def get_tag_barcode_base64(self):
        """Return base64-encoded Code128 barcode image for reliable PDF printing."""
        self.ensure_one()
        val = (self.tag_number or self.name or 'UNKNOWN').strip()
        try:
            barcode_bytes = self.env['ir.actions.report'].barcode('Code128', val, width=600, height=80, quiet=0)
            return base64.b64encode(barcode_bytes).decode('ascii')
        except Exception:
            return False

    def get_tag_qr_base64(self):
        """Return base64-encoded QR code image for reliable PDF printing."""
        self.ensure_one()
        val = (self.tag_number or self.name or 'UNKNOWN').strip()
        try:
            qr_bytes = self.env['ir.actions.report'].barcode('QR', val, width=200, height=200, quiet=0)
            return base64.b64encode(qr_bytes).decode('ascii')
        except Exception:
            return False

    def _get_current_location_name(self):
        """Return human-readable current location name (employee, warehouse, or unassigned)."""
        self.ensure_one()
        if self.location == 'employee':
            emp = self.env['am.employee.asset'].search([('asset_id', '=', self.id), ('status', '=', 'active')], limit=1)
            if emp and emp.employee_id:
                return emp.employee_id.name
            if self.employee_id:
                return self.employee_id.name
        elif self.location == 'warehouse':
            wh_stock = self.env['am.asset.warehouse.stock'].search([('asset_id', '=', self.id)], limit=1)
            if wh_stock and wh_stock.warehouse_id:
                loc = wh_stock.warehouse_id.name
                if wh_stock.location_id:
                    loc += f" ({wh_stock.location_id.name})"
                return loc
        return "Unassigned"

    def open_entries(self):
        self.ensure_one()
        move_ids = self.depreciation_line_ids.mapped('move_id').ids
        return {
            'name': 'Journal Entries',
            'view_mode': 'list,form',
            'res_model': 'account.move',
            'domain': [('id', 'in', move_ids)],
            'type': 'ir.actions.act_window',
            'context': {'default_move_type': 'entry'}
        }

    @api.depends('original_cost', 'accumulated_depreciation')
    def _compute_net_book_value(self):
        for record in self:
            record.net_book_value = (record.original_cost or 0.0) - (record.accumulated_depreciation or 0.0)

    def _get_qr_configuration(self):
        self.ensure_one()
        return self.env['am.asset.qr.config'].sudo().search([
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _qr_counter_key(self, config=None):
        self.ensure_one()
        config = config or self._get_qr_configuration()
        if not config:
            return (
                self.company_id.id, self.branch_id.id,
                self.major_category_id.id, self.minor_category_id.id,
            )
        return tuple(
            value for enabled, value in [
                (config.include_company, self.company_id.id),
                (config.include_branch, self.branch_id.id),
                (config.include_major_category, self.major_category_id.id),
                (config.include_minor_category, self.minor_category_id.id),
            ] if enabled
        )

    def _qr_counter_domain(self, config=None):
        self.ensure_one()
        config = config or self._get_qr_configuration()
        if not config:
            return [
                ('company_id', '=', self.company_id.id),
                ('branch_id', '=', self.branch_id.id),
                ('major_category_id', '=', self.major_category_id.id),
                ('minor_category_id', '=', self.minor_category_id.id),
            ]
        domain = []
        if config.include_company:
            domain.append(('company_id', '=', self.company_id.id))
        if config.include_branch:
            domain.append(('branch_id', '=', self.branch_id.id))
        if config.include_major_category:
            domain.append(('major_category_id', '=', self.major_category_id.id))
        if config.include_minor_category:
            domain.append(('minor_category_id', '=', self.minor_category_id.id))
        return domain

    def _build_tag_number(self, counter):
        self.ensure_one()
        config = self._get_qr_configuration()
        separators = {
            'hyphen': '-', 'slash': '/', 'dot': '.',
            'underscore': '_', 'none': '',
        }
        parts = []
        if not config or config.include_company:
            comp_prefix = getattr(self.company_id, 'prefix', None) or (self.company_id.name[:3] if self.company_id.name else 'COM')
            parts.append(comp_prefix.upper())
        if not config or config.include_branch:
            parts.append((self.branch_id.code or '0').upper())
        if not config or config.include_major_category:
            parts.append((self.major_category_id.code or '0').upper())
        if not config or config.include_minor_category:
            parts.append((self.minor_category_id.code or '0').upper())
        padding = config.sequence_padding if config else 4
        parts.append(str(counter).zfill(padding))
        separator = separators.get(config.separator, '-') if config else '-'
        return separator.join(parts)

    def _build_qr_number(self, counter):
        return self._build_tag_number(counter)

    @api.model
    def create(self, vals):
        record = super(AssetRegistration, self).create(vals)

        if record.minor_category_id:
            record._sync_specification_templates()

        if not record.tag_number:
            counter = self.search_count(record._qr_counter_domain())
            record.tag_number = record._build_tag_number(counter)

        # Vehicle validation
        if record.is_vehicle and len(record.vehicle_id) > 1:
            raise ValidationError("Only one vehicle record is allowed per asset.")
        if record.is_vehicle and not record.vehicle_id:
            raise ValidationError(
                "Vehicle details are mandatory when 'Is Vehicle Asset' is enabled.\n"
                "Please add vehicle information (type, model, plate number) in the "
                "Vehicle Details tab before saving."
            )

        return record

    @api.model
    def get_dashboard_data(self):
        Company = self.env.company
        currency = Company.currency_id

        # Basic Stats
        total_count = self.search_count([('is_component', '=', False)])
        assets = self.search([('is_component', '=', False)])
        total_value = sum(assets.mapped('net_book_value'))
        warehouse_count = self.search_count([('location', '=', 'warehouse'), ('is_component', '=', False)])
        employee_count = self.search_count([('location', '=', 'employee'), ('is_component', '=', False)])
        component_count = self.search_count([('is_component', '=', True)])

        # Category Data
        categories = self.env['am.asset.category'].search([])
        category_data = []
        for cat in categories:
            cat_assets = assets.filtered(lambda a: a.major_category_id.id == cat.id)
            if cat_assets:
                val = sum(cat_assets.mapped('net_book_value'))
                category_data.append({
                    'id': cat.id,
                    'name': cat.name,
                    'count': len(cat_assets),
                    'value_fmt': currency.format(val)
                })

        # Branch Data
        branch_stats = self.read_group([('is_component', '=', False)], ['id:count'], ['branch_id'], orderby='branch_id_count desc')
        branch_data = []
        if total_count > 0:
            for stat in branch_stats:
                if stat['branch_id']:
                    branch_name = stat['branch_id'][1]
                    count = stat['branch_id_count']
                    branch_data.append({
                        'id': stat['branch_id'][0],
                        'name': branch_name,
                        'count': count,
                        'perc': round((count / total_count) * 100, 1)
                    })

        # Additional Statistics for Redesigned Dashboard
        draft_count = self.search_count([('state', '=', 'draft'), ('is_component', '=', False)])
        running_count = self.search_count([('state', '=', 'open'), ('is_component', '=', False)])
        closed_count = self.search_count([('state', '=', 'close'), ('is_component', '=', False)])

        return {
            'total_count': total_count,
            'total_value_fmt': currency.format(total_value),
            'warehouse_count': warehouse_count,
            'employee_count': employee_count,
            'component_count': component_count,
            'category_data': sorted(category_data, key=lambda x: x['count'], reverse=True),
            'branch_data': branch_data,
            'draft_count': draft_count,
            'running_count': running_count,
            'closed_count': closed_count,
        }

    def action_regenerate_all_qr_codes(self):
        """
        Regenerates and updates all asset tag numbers sequentially.
        """
        all_assets = self.search([], order='id asc')
        counters = {}
        for rec in all_assets:
            config = rec._get_qr_configuration()
            key = rec._qr_counter_key(config)
            counters[key] = counters.get(key, 0) + 1
            counter = counters[key]

            tag_number = rec._build_tag_number(counter)
            rec.write({'tag_number': tag_number})
            if rec.financial_asset_id:
                rec.financial_asset_id.write({'code': tag_number})

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'All asset tag numbers have been regenerated successfully.',
                'type': 'success',
                'sticky': False,
            }
        }

    def write(self, vals):
        tag_fields = ['company_id', 'branch_id', 'major_category_id', 'minor_category_id']
        change_tag = any(f in vals for f in tag_fields)

        res = super(AssetRegistration, self).write(vals)

        if 'minor_category_id' in vals:
            for rec in self:
                rec._sync_specification_templates()

        for rec in self:
            # Vehicle validation
            if rec.is_vehicle and len(rec.vehicle_id) > 1:
                raise ValidationError("Only one vehicle record is allowed per asset.")
            if rec.is_vehicle and not rec.vehicle_id:
                raise ValidationError(
                    "Vehicle details are mandatory when 'Is Vehicle Asset' is enabled.\n"
                    "Please add vehicle information (type, model, plate number) in the "
                    "Vehicle Details tab."
                )

            # 1. Handle tag number regeneration (only in draft state if not explicitly supplied)
            if change_tag and rec.state == 'draft' and not vals.get('tag_number'):
                counter = self.search_count(
                    [('id', '!=', rec.id)] + rec._qr_counter_domain()
                ) + 1
                tag_number = rec._build_tag_number(counter)
                super(AssetRegistration, rec).write({'tag_number': tag_number})

            # 2. Sync fields to linked accounting asset
            if rec.financial_asset_id:
                asset_vals = {}
                if 'name' in vals:
                    asset_vals['name'] = rec.name
                if 'original_cost' in vals:
                    asset_vals['value'] = rec.original_cost
                if 'salvage_value' in vals:
                    asset_vals['salvage_value'] = rec.salvage_value or 0.0
                if 'acquisition_date' in vals:
                    asset_vals['date'] = rec.acquisition_date
                if 'tag_number' in vals or 'qr_code_number' in vals or (change_tag and rec.state == 'draft'):
                    asset_vals['code'] = rec.tag_number
                if 'company_id' in vals:
                    asset_vals['company_id'] = rec.company_id.id
                if 'major_category_id' in vals:
                    accounting_cat = rec.major_category_id.accounting_category_id
                    if accounting_cat:
                        asset_vals['category_id'] = accounting_cat.id

                if asset_vals:
                    rec.financial_asset_id.write(asset_vals)

        return res



class AssetWarehouseStock(models.Model):
    _name = 'am.asset.warehouse.stock'
    _description = 'Assets in Warehouse'

    asset_id = fields.Many2one('am.asset', string='Asset', required=True, ondelete='cascade')
    tag_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True, store=True)
    qr_code_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True)
    branch_id = fields.Many2one('account.analytic.account', string='Branch', required=True)
    warehouse_id = fields.Many2one('am.asset.warehouse', string='Warehouse', required=True)
    location_id = fields.Many2one('am.asset.location', string='Location')
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company.id,
        index=True
    )

    # Related fields from asset_id for UI enhancements
    serial_number = fields.Char(related='asset_id.serial_number', string='Serial Number', readonly=True, store=True)
    old_tag_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True)
    category_id = fields.Many2one('am.asset.category', related='asset_id.major_category_id', string='Major Category', readonly=True, store=True)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.context.get('allowed_bypass_request_check') and not self.env.context.get('install_mode'):
            raise ValidationError("Direct creation of Warehouse Stock Assignment is not allowed. Please use Handover/Store Requests or the Transaction Wizard.")

        for vals in vals_list:
            tag_val = vals.get('tag_number') or vals.get('qr_code_number')
            if tag_val and not vals.get('asset_id'):
                asset = self.env['am.asset'].search(['|', ('tag_number', '=', tag_val), ('qr_code_number', '=', tag_val)], limit=1)
                if not asset:
                    raise ValidationError(f"No asset found with tag number {tag_val}.")
                vals['asset_id'] = asset.id

        records = super().create(vals_list)
        for record in records:
            if record.asset_id:
                record.asset_id._compute_location()
        return records


    def unlink(self):
        if not self.env.context.get('allowed_bypass_request_check') and not self.env.context.get('install_mode'):
            raise ValidationError("Direct deletion of Warehouse Stock Assignment is not allowed. Please use Handover/Store Requests or the Transaction Wizard.")
        assets = self.mapped('asset_id')
        res = super(AssetWarehouseStock, self).unlink()
        assets._compute_location()
        return res

    def action_print_tag(self):
        """Print the physical Asset Tag for this warehouse stock asset."""
        records = self
        if not records:
            active_ids = self.env.context.get('active_ids')
            if active_ids:
                records = self.browse(active_ids)
            else:
                raise UserError("Please select at least one warehouse stock record to print tag(s).")
        assets = records.mapped('asset_id')
        if not assets:
            raise UserError("No linked asset found for the selected warehouse stock item(s).")
        return assets.action_print_tag()

    @api.constrains('asset_id')
    def _check_global_asset_uniqueness(self):
        for rec in self:
            # Check for other warehouse stock
            other_stock = self.search_count([
                ('asset_id', '=', rec.asset_id.id),
                ('id', '!=', rec.id)
            ])
            if other_stock > 0:
                raise ValidationError(f"Asset '{rec.asset_id.name}' is already in another warehouse.")
            
            # Check for active employee assignment
            emp_assign = self.env['am.employee.asset'].search_count([
                ('asset_id', '=', rec.asset_id.id),
                ('status', '=', 'active')
            ])
            if emp_assign > 0:
                raise ValidationError(f"Asset '{rec.asset_id.name}' is currently assigned to an employee. It must be returned first.")
class AssetSpecificationTemplate(models.Model):
    _name = 'am.asset.specification.template'
    _description = 'Asset Specification Template'

    name = fields.Char(string='Specification Name', required=True)
    minor_category_id = fields.Many2one('am.asset.minor_category', string='Minor Category', required=True, ondelete='cascade')
    default_value = fields.Char(string='Default Value')
    uom = fields.Char(string='Unit (Optional)')
    is_accessory = fields.Boolean(string='Is Accessory', default=False, help="Mark if this specification is an accessory/optional component.")
    is_required = fields.Boolean(string='Is Required', default=True, help="Mark if this specification is mandatory for assets of this category.")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)


class AssetSpecification(models.Model):
    _name = 'am.asset.specification'
    _description = 'Asset Specifications'

    asset_id = fields.Many2one('am.asset', string="Asset", required=True, ondelete='cascade')
    tag_number = fields.Char(related='asset_id.tag_number', string="Tag Number", readonly=True, store=True)
    qr_code_number = fields.Char(string="Asset QR Code")  # optional, for lookup
    template_id = fields.Many2one('am.asset.specification.template', string='Template')
    name = fields.Char(string="Specification Name", required=True)
    value = fields.Char(string="Specification Value")
    uom = fields.Char(string="Unit (Optional)")
    is_accessory = fields.Boolean(string="Is Accessory", default=False, help="Indicates if this is an accessory specification.")
    is_required = fields.Boolean(string="Is Required", default=True, help="Indicates if this specification is mandatory.")

    @api.model
    def create(self, vals):
        # If QR code is provided, find the asset
        if 'qr_code_number' in vals and vals['qr_code_number']:
            asset = self.env['am.asset'].search([('qr_code_number', '=', vals['qr_code_number'])], limit=1)
            if not asset:
                raise ValidationError(f"No asset found with QR code {vals['qr_code_number']}.")
            vals['asset_id'] = asset.id

        if vals.get('template_id') and not vals.get('name'):
            template = self.env['am.asset.specification.template'].browse(vals['template_id'])
            if template.exists():
                vals['name'] = template.name
                vals['uom'] = vals.get('uom') or template.uom or ''
                vals['value'] = vals.get('value') or template.default_value or ''
                vals['is_accessory'] = template.is_accessory
                vals['is_required'] = template.is_required

        return super(AssetSpecification, self).create(vals)

    @api.constrains('name', 'asset_id')
    def _check_unique_spec_name(self):
        for rec in self:
            specs = self.search([
                ('asset_id', '=', rec.asset_id.id),
                ('name', '=', rec.name),
                ('id', '!=', rec.id)
            ])
            if specs:
                raise ValidationError(f"Specification '{rec.name}' already exists for this asset.")


class AssetDepreciationLine(models.Model):
    _name = 'am.asset.depreciation.line'
    _description = 'Asset Depreciation Line'
    _order = 'date desc'

    asset_id = fields.Many2one('am.asset', string='Asset', required=True, ondelete='cascade')
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    amount = fields.Float(string='Depreciation Amount', required=True)
    remaining_value = fields.Float(string='Remaining Value', compute='_compute_remaining_value', store=True)
    notes = fields.Char(string='Notes')
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, copy=False)
    is_posted = fields.Boolean(string='Posted', compute='_compute_is_posted', store=True)

    @api.depends('move_id.state')
    def _compute_is_posted(self):
        for line in self:
            line.is_posted = True if line.move_id and line.move_id.state == 'posted' else False

    def action_post_move(self):
        self.ensure_one()
        if self.move_id:
            raise ValidationError("This line is already posted.")
        
        category = self.asset_id.major_category_id
        if not category.journal_id or not category.account_depreciation_id or not category.account_depreciation_expense_id:
            raise ValidationError("Please configure Accounting Accounts and Journal on the Asset Category.")

        move_vals = {
            'ref': f"Depreciation - {self.asset_id.name} ({self.date})",
            'date': self.date,
            'journal_id': category.journal_id.id,
            'line_ids': [
                (0, 0, {
                    'name': f"Depreciation - {self.asset_id.name}",
                    'account_id': category.account_depreciation_expense_id.id,
                    'debit': self.amount,
                    'credit': 0.0,
                    'analytic_distribution': {str(self.asset_id.branch_id.id): 100} if self.asset_id.branch_id else False,
                }),
                (0, 0, {
                    'name': f"Depreciation - {self.asset_id.name}",
                    'account_id': category.account_depreciation_id.id,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.move_id = move.id

    @api.depends('asset_id.original_cost', 'amount', 'date')
    def _compute_remaining_value(self):
        for line in self:
            # This is complex to calculate accurately via compute if we want history
            # For now, we'll just show a helper
            prev_lines = self.search([
                ('asset_id', '=', line.asset_id.id),
                ('date', '<=', line.date),
                ('id', '!=', line.id)
            ])
            line.remaining_value = line.asset_id.original_cost - sum(prev_lines.mapped('amount')) - line.amount
