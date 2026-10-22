from odoo import models, fields


class AccountAssetAsset(models.Model):
    """Extends the Accounting Asset to link back to the physical asset."""
    _inherit = 'account.asset.asset'

    physical_asset_id = fields.Many2one(
        'am.asset',
        string='Physical Asset',
        readonly=True,
        copy=False,
        help="Linked physical asset from the Asset Management module."
    )
    tag_number = fields.Char(
        related='physical_asset_id.tag_number',
        string='Tag Number',
        readonly=True,
        store=True,
        help="Tag Number from the linked physical asset."
    )

    def action_view_physical_asset(self):
        self.ensure_one()
        return {
            'name': 'Physical Asset',
            'type': 'ir.actions.act_window',
            'res_model': 'am.asset',
            'res_id': self.physical_asset_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
