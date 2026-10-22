from odoo import models, fields, api
from odoo.exceptions import ValidationError

class AssetTransaction(models.Model):
    _name = 'am.asset.transaction'
    _description = 'Asset Transaction History'

    TRANSACTION_TYPES = [
        ('assign_employee', 'Assign Asset → Employee'),
        ('assign_warehouse', 'Assign Asset → Warehouse'),
        ('transfer_warehouse', 'Transfer: Warehouse → Warehouse'),
        ('transfer_employee', 'Transfer: Employee → Employee'),
        ('assign_temp', 'Assign (Temporary): Warehouse → Employee'),
        ('assign_perm', 'Assign (Permanent): Warehouse → Employee'),
        ('return', 'Return: Employee → Warehouse'),
        ('dispose', 'Dispose Asset')
    ]

    asset_id = fields.Many2one('am.asset', string='Asset', required=True)
    tag_number = fields.Char(related='asset_id.tag_number', string='Tag Number', readonly=True, store=True)
    transaction_type = fields.Selection(TRANSACTION_TYPES, string='Transaction Type', required=True)
    from_warehouse_id = fields.Many2one('am.asset.warehouse', string='From Warehouse')
    from_location_id = fields.Many2one('am.asset.location', string='From Location')
    to_warehouse_id = fields.Many2one('am.asset.warehouse', string='To Warehouse')
    to_location_id = fields.Many2one('am.asset.location', string='To Location')
    employee_id = fields.Many2one('hr.employee', string='Employee')
    transaction_date = fields.Datetime(string='Transaction Date', default=fields.Datetime.now)
    reference = fields.Char(string='Reference')
    performed_by = fields.Many2one('res.users', string='Performed By', default=lambda self: self.env.user)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, index=True)

    @api.model
    def create(self, vals):
        record = super().create(vals)
        record._process_transaction()
        return record

    def _process_transaction(self):
        Stock = self.env['am.asset.warehouse.stock']
        EmployeeAsset = self.env['am.employee.asset']

        for rec in self:
            # Transfer between warehouses
            if rec.transaction_type == 'transfer_warehouse':
                if not rec.from_warehouse_id or not rec.to_warehouse_id:
                    raise ValidationError("Source and destination warehouses are required.")
                stock = Stock.search([('asset_id', '=', rec.asset_id.id)], limit=1)
                if not stock or stock.warehouse_id != rec.from_warehouse_id:
                    raise ValidationError("Asset not found in source warehouse.")
                stock.warehouse_id = rec.to_warehouse_id

            # Assign asset to employee (replaces any previous active employee assignment)
            elif rec.transaction_type == 'assign_employee':
                if not rec.employee_id:
                    raise ValidationError("Target employee must be set for assignment.")
                EmployeeAsset.replace_employee_assignment(
                    rec.asset_id.id,
                    rec.employee_id.id,
                    rec.company_id.id,
                    rec.transaction_date.date(),
                )

            # Transfer between employees
            elif rec.transaction_type == 'transfer_employee':
                if not rec.employee_id:
                    raise ValidationError("Target employee must be set for transfer.")
                EmployeeAsset.replace_employee_assignment(
                    rec.asset_id.id,
                    rec.employee_id.id,
                    rec.company_id.id,
                    rec.transaction_date.date(),
                )

            # Assign from warehouse to employee
            elif rec.transaction_type in ['assign_temp', 'assign_perm']:
                if not rec.employee_id or not rec.to_warehouse_id:
                    raise ValidationError("Employee and destination warehouse are required for assignment.")
                stock = Stock.search([('asset_id', '=', rec.asset_id.id)], limit=1)
                if not stock or stock.warehouse_id != rec.to_warehouse_id:
                    raise ValidationError("Asset not found in the specified warehouse.")
                stock.unlink()  # Remove from warehouse
                EmployeeAsset.replace_employee_assignment(
                    rec.asset_id.id,
                    rec.employee_id.id,
                    rec.company_id.id,
                    rec.transaction_date.date(),
                )

            # Return asset from employee to warehouse
            elif rec.transaction_type == 'return':
                if not rec.to_warehouse_id:
                    raise ValidationError("Destination warehouse is required for return.")

                emp_asset = EmployeeAsset.search([
                    ('asset_id', '=', rec.asset_id.id),
                    ('status', '=', 'active')
                ], limit=1)
                if emp_asset:
                    emp_asset.unlink()

                stock = Stock.search([('asset_id', '=', rec.asset_id.id)], limit=1)
                if stock:
                    stock.unlink()

                Stock.create({
                    'asset_id': rec.asset_id.id,
                    'warehouse_id': rec.to_warehouse_id.id,
                    'branch_id': rec.to_warehouse_id.branch_id.id if rec.to_warehouse_id.branch_id else False,
                    'company_id': rec.company_id.id
                })

            # Dispose asset
            elif rec.transaction_type == 'dispose':
                emp_asset = EmployeeAsset.search([('asset_id', '=', rec.asset_id.id)], limit=1)
                if emp_asset:
                    emp_asset.unlink()
                stock = Stock.search([('asset_id', '=', rec.asset_id.id)], limit=1)
                if stock:
                    stock.unlink()

                # Mark asset as inactive and update status if applicable
                rec.asset_id.write({
                    'active': False,
                    'status_id': False  # or a special "Disposed" status if you have one
                })
