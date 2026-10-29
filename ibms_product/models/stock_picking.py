# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    location_transfer_id = fields.Many2one(
        'stock.location.transfer',
        string='Location Transfer Reference',
        readonly=True,
        copy=False,
        index=True
    )
    transfer_operation_type = fields.Selection([
        ('issue', 'Issue (Source)'),
        ('receive', 'Receive (Destination)'),
    ], string='Transfer Operation Type', readonly=True, copy=False)

    def _action_done(self):
        res = super()._action_done()
        for picking in self:
            if not picking.location_transfer_id:
                continue
            transfer = picking.location_transfer_id
            if picking.transfer_operation_type == 'issue' and transfer.state == 'approved':
                transfer.sudo()._create_receive_picking()
                transfer.sudo().write({
                    'state': 'in_transit',
                    'sent_by_id': self.env.user.id,
                    'sent_date': fields.Datetime.now(),
                })
                transfer.message_post(
                    body=_("📦 Issue Picking <b>%s</b> validated. Created Receive Picking <b>%s</b> for %s.") % (
                        picking.name,
                        transfer.receive_picking_id.name if transfer.receive_picking_id else '-',
                        transfer.dest_warehouse_id.name
                    )
                )
            elif picking.transfer_operation_type == 'receive' and transfer.state == 'in_transit':
                transfer.sudo().write({
                    'state': 'received',
                    'received_by_id': self.env.user.id,
                    'received_date': fields.Datetime.now(),
                })
                transfer.message_post(
                    body=_("✅ Receive Picking <b>%s</b> validated. Goods received at %s. Transfer completed.") % (
                        picking.name,
                        transfer.dest_warehouse_id.name,
                    )
                )
        return res
