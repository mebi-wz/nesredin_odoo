from odoo import models, fields, api

class CurrentMarketAnalysis(models.Model):
    _name = 'current.market.analysis'
    _description = 'Current Market Analysis'

    name = fields.Char(default="New", readonly=True)
    product_id = fields.Many2one('product.product', required=True)
    requisition_id = fields.Many2one(
        'foreign.purchase.requisition',
        string='Requisition',
        ondelete='cascade'
    )
    requisition_line_id = fields.Many2one(
        'foreign.purchase.requisition.line',
        ondelete='cascade'
    )

    # Child lines for multiple entries
    line_ids = fields.One2many(
        'current.market.analysis.line',
        'analysis_id',
        string='Market Details'
    )

class CurrentMarketAnalysisLine(models.Model):
    _name = 'current.market.analysis.line'
    _description = 'Current Market Analysis Line'

    analysis_id = fields.Many2one('current.market.analysis', ondelete='cascade')
    importer = fields.Many2one('res.partner')
    manufacturer = fields.Many2one('res.partner', domain=[('supplier_rank', '!=', '0')])
    uom_id = fields.Many2one('uom.uom')
    available_stock = fields.Float()
    selling_unit_price = fields.Float()
    epss_stock_volume = fields.Float(string="EPSS Stock Volume")
    local_manufacturer_stock_rm_status = fields.Char(string="Local Manufacturer Stock RM Status")


class FutureMarketAnalysis(models.Model):
    _name = 'future.market.analysis'
    _description = 'Future Market Analysis'

    name = fields.Char(default="New", readonly=True)
    product_id = fields.Many2one('product.product', required=True)
    requisition_id = fields.Many2one(
        'foreign.purchase.requisition',
        string='Requisition',
        ondelete='cascade'
    )
    requisition_line_id = fields.Many2one(
        'foreign.purchase.requisition.line',
        ondelete='cascade'
    )

    line_ids = fields.One2many(
        'future.market.analysis.line',
        'analysis_id',
        string='Market Details'
    )

class FutureMarketAnalysisLine(models.Model):
    _name = 'future.market.analysis.line'
    _description = 'Future Market Analysis Line'

    analysis_id = fields.Many2one('future.market.analysis', ondelete='cascade')
    importer = fields.Many2one('res.partner')
    manufacturer = fields.Char(string="Manufacturer")
    uom_id = fields.Many2one('uom.uom')
    private_unit_price = fields.Float(string="Private Unit Price")
    private_quantity = fields.Float(string="Private Quantity")
    private_ordered_date = fields.Date(string="Private Ordered Date")
    epss_unit_price = fields.Float(string="EPSS Unit Price")
    epss_winer_manufacturer = fields.Char(string="EPSS Winner Manufacturer")
