from odoo import models, fields, api
from odoo.exceptions import ValidationError

class EmployeeAsset(models.Model):
    _name = 'am.employee.asset'
    _description = 'Employee Asset Assignment'

    asset_id = fields.Many2one('am.asset', string='Asset', required=True, ondelete='cascade')
    tag_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True, store=True)
    qr_code_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    quantity = fields.Integer(string='Quantity', default=1)
    asset_location = fields.Char(string='Asset Location')  # optional lookup field
    assigned_date = fields.Date(string='Assigned Date', default=fields.Date.today)
    returned_date = fields.Date(string='Returned Date')
    status = fields.Selection([
        ('active', 'Active'),
        ('returned', 'Returned'),
        ('lost', 'Lost')
    ], string='Status', default='active')
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
            raise ValidationError("Direct creation of Employee Asset Assignment is not allowed. Please use Handover/Store Requests or the Transaction Wizard.")

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
            raise ValidationError("Direct deletion of Employee Asset Assignment is not allowed. Please use Handover/Store Requests or the Transaction Wizard.")
        assets = self.mapped('asset_id')
        res = super(EmployeeAsset, self).unlink()
        assets._compute_location()
        return res

    def action_print_tag(self):
        """Print the physical Asset Tag for this assigned asset."""
        records = self
        if not records:
            active_ids = self.env.context.get('active_ids')
            if active_ids:
                records = self.browse(active_ids)
            else:
                raise UserError("Please select at least one employee assignment to print tag(s).")
        assets = records.mapped('asset_id')
        if not assets:
            raise UserError("No linked asset found for the selected record(s).")
        return assets.action_print_tag()

    @api.model
    def replace_employee_assignment(self, asset_id, employee_id, company_id=False, assigned_date=False):
        if not asset_id or not employee_id:
            raise ValidationError("Asset and employee are required for assignment.")

        asset = self.env['am.asset'].browse(asset_id)
        if not asset.exists():
            raise ValidationError("Asset not found.")

        active_assignments = self.with_context(allowed_bypass_request_check=True).search([
            ('asset_id', '=', asset_id),
            ('status', '=', 'active'),
        ])

        for assignment in active_assignments:
            if assignment.employee_id.id != employee_id:
                assignment.unlink()

        existing = self.with_context(allowed_bypass_request_check=True).search([
            ('asset_id', '=', asset_id),
            ('employee_id', '=', employee_id),
            ('status', '=', 'active'),
        ], limit=1)
        if existing:
            return existing

        return self.with_context(allowed_bypass_request_check=True).create({
            'asset_id': asset_id,
            'employee_id': employee_id,
            'status': 'active',
            'assigned_date': assigned_date or fields.Date.today(),
            'company_id': company_id or asset.company_id.id,
        })

    @api.constrains('asset_id', 'status')
    def _check_global_asset_uniqueness(self):
        for rec in self:
            if rec.status == 'active':
                # Check for other active employee assignments
                other_emp = self.search_count([
                    ('asset_id', '=', rec.asset_id.id),
                    ('status', '=', 'active'),
                    ('id', '!=', rec.id)
                ])
                if other_emp > 0:
                    raise ValidationError(f"Asset '{rec.asset_id.name}' is already assigned to an employee.")
                
                # Check for warehouse stock
                stock = self.env['am.asset.warehouse.stock'].search_count([
                    ('asset_id', '=', rec.asset_id.id)
                ])
                if stock > 0:
                    raise ValidationError(f"Asset '{rec.asset_id.name}' is currently in a warehouse. It cannot be assigned to an employee without being transferred.")
