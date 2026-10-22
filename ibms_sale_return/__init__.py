# -*- coding: utf-8 -*-
from . import models
from . import wizard


def post_init_hook(env):
    """Ensure all warehouses have 'Returned from Sales' operation type configured."""
    env['stock.warehouse'].create_missing_sale_return_picking_types()
