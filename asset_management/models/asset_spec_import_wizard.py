from odoo import models, fields, api
from odoo.exceptions import UserError
import base64
import io
import pandas as pd  # make sure you have pandas installed

class AssetSpecImportWizard(models.TransientModel):
    _name = 'asset.spec.import.wizard'
    _description = 'Wizard to import asset specifications'

    file_data = fields.Binary(string='Excel File', required=True)
    file_name = fields.Char(string='File Name')
    asset_id = fields.Many2one('am.asset', string="Asset", required=True)

    def import_specifications(self):
        if not self.file_data:
            raise UserError("Please upload a file.")

        # Read Excel
        data = base64.b64decode(self.file_data)
        df = pd.read_excel(io.BytesIO(data))

        # Expected columns: name, value, uom
        for index, row in df.iterrows():
            self.env['am.asset.specification'].create({
                'asset_id': self.asset_id.id,
                'name': row.get('name'),
                'value': row.get('value'),
                'uom': row.get('uom'),
            })

        return {'type': 'ir.actions.act_window_close'}
