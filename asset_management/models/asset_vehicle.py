from odoo import models, fields, api

class AssetVehicleType(models.Model):
    _name = 'am.asset.vehicle_type'
    _description = 'Vehicle Type'

    name = fields.Char(string='Vehicle Type', required=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)

class AssetModels(models.Model):
    _name = 'am.asset.model'
    _description = 'Asset Model'

    name = fields.Char(string='Model Name', required=True)
    brand_name = fields.Char(string='Brand Name')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)

class AssetVehicle(models.Model):
    _name = 'am.asset.vehicle'
    _description = 'Asset Vehicle'
    
    asset_id = fields.Many2one(
        'am.asset', string='Asset', required=True, readonly=True,
        help='Set automatically when vehicle details are created from an asset.',
    )
    tag_number = fields.Char(string='Tag Number', related='asset_id.tag_number', readonly=True, store=True)
    chassis_number = fields.Char(string='Chassis Number')
    plate_number = fields.Char(string='Plate Number')
    engine_number = fields.Char(string='Engine Number')
    vehicle_type_id = fields.Many2one('am.asset.vehicle_type', string='Vehicle Type')
    model_id = fields.Many2one('am.asset.model', string='Model')
    branch_id = fields.Many2one('account.analytic.account', string="Branch", default=lambda self: self._default_branch_id())
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company.id, index=True)

    fuel_type = fields.Selection([
        ('diesel', 'Diesel'),
        ('gasoline', 'Gasoline'),
        ('hybrid', 'Hybrid'),
        ('electric', 'Electric'),
        ('other', 'Other'),
    ], string='Fuel Type')
    color = fields.Char(string='Color')
    brand = fields.Char(string='Brand')
    tank_capacity = fields.Float(string='Tank Capacity (Liters)')
    fuel_consumption = fields.Float(string='Fuel Consumption (Km/L)')
    seats_number = fields.Integer(string='Seats Number')
    
    def _default_branch_id(self):
        asset_id = self._context.get('default_asset_id')
        if asset_id:
            asset = self.env['am.asset'].browse(asset_id)
            return asset.branch_id.id
        return False

    @api.onchange('asset_id')
    def _onchange_asset_id(self):
        if self.asset_id:
            self.branch_id = self.asset_id.branch_id
            self.company_id = self.asset_id.company_id

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        return records

    def write(self, vals):
        res = super().write(vals)
        return res

    def action_print_tag(self):
        """Print the physical Asset Tag for this vehicle's underlying asset."""
        records = self
        if not records:
            active_ids = self.env.context.get('active_ids')
            if active_ids:
                records = self.browse(active_ids)
            else:
                raise UserError("Please select at least one vehicle to print tag(s).")
        assets = records.mapped('asset_id')
        if not assets:
            raise UserError("No linked asset found for the selected vehicle(s).")
        return assets.action_print_tag()
