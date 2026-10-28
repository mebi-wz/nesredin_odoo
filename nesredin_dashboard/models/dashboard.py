# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError


class NesredinDashboard(models.AbstractModel):
    _name = "nesredin.dashboard"
    _description = "Nesredin Operational Executive Dashboard"

    @api.model
    def _safe(self, callback, default=0):
        """Keep one unavailable app from breaking the entire dashboard."""
        try:
            return callback()
        except (AccessError, KeyError, AttributeError):
            return default

    @api.model
    def _sum_field(self, model_name, domain, field_name):
        try:
            records = self.env[model_name].search(domain)
            return sum(records.mapped(field_name)) if records else 0.0
        except Exception:
            return 0.0

    @api.model
    def _sum_in_company_currency(self, model_name, domain):
        """Aggregate orders without mixing foreign-currency totals."""
        try:
            company = self.env.company
            records = self.env[model_name].search(domain)
            today = fields.Date.context_today(self)
            total = 0.0
            for r in records:
                amt = r.amount_total or 0.0
                curr = r.currency_id or company.currency_id
                if curr and curr != company.currency_id:
                    total += curr._convert(amt, company.currency_id, company, today)
                else:
                    total += amt
            return total
        except Exception:
            return 0.0

    @api.model
    def _get_brand_colors(self, company):
        primary = (getattr(company, 'primary_color', None) or "#5e4766").strip()
        secondary = (getattr(company, 'secondary_color', None) or "#010101").strip()
        if not primary.startswith("#"):
            primary = "#" + primary
        if len(primary) != 7:
            primary = "#5e4766"

        try:
            r = int(primary[1:3], 16)
            g = int(primary[3:5], 16)
            b = int(primary[5:7], 16)
        except Exception:
            r, g, b = 94, 71, 102
            primary = "#5e4766"

        rgb = f"{r}, {g}, {b}"
        dark = f"#{int(r * 0.22):02x}{int(g * 0.22):02x}{int(b * 0.22):02x}"
        mid_dark = f"#{int(r * 0.45):02x}{int(g * 0.45):02x}{int(b * 0.45):02x}"
        light = f"#{min(255, int(r + (255 - r) * 0.88)):02x}{min(255, int(g + (255 - g) * 0.88)):02x}{min(255, int(b + (255 - b) * 0.88)):02x}"
        hero_grad = f"linear-gradient(135deg, #07090e 0%, {dark} 45%, {primary} 100%)"
        accent_grad = f"linear-gradient(135deg, {primary} 0%, #8b5cf6 100%)"

        return {
            "primary": primary,
            "secondary": secondary,
            "rgb": rgb,
            "dark": dark,
            "mid_dark": mid_dark,
            "light": light,
            "hero_gradient": hero_grad,
            "accent_gradient": accent_grad,
        }

    @api.model
    def _top_customers(self, company, currency):
        """Top customers by confirmed sales volume (like Odoo spreadsheet dashboard)."""
        try:
            orders = self.env["sale.order"].search([
                ("company_id", "=", company.id),
                ("state", "in", ["sale", "done"]),
            ])
            cust_map = {}
            for o in orders:
                cid = o.partner_id.id
                if cid not in cust_map:
                    cust_map[cid] = {
                        "id": cid,
                        "name": o.partner_id.name or "Unknown",
                        "count": 0,
                        "total": 0.0,
                    }
                cust_map[cid]["count"] += 1
                cust_map[cid]["total"] += o.amount_total

            top_custs = sorted(cust_map.values(), key=lambda x: x["total"], reverse=True)[:5]
            for c in top_custs:
                c["total_fmt"] = currency.format(c["total"])
            return top_custs
        except Exception:
            return []

    @api.model
    def _top_products(self, company, currency):
        """Top selling products by revenue and units sold."""
        try:
            lines = self.env["sale.order.line"].search([
                ("company_id", "=", company.id),
                ("state", "in", ["sale", "done"]),
                ("product_id", "!=", False),
            ])
            prod_map = {}
            for l in lines:
                pid = l.product_id.id
                if pid not in prod_map:
                    prod_map[pid] = {
                        "id": pid,
                        "name": l.product_id.name or "Product",
                        "code": l.product_id.default_code or "—",
                        "qty": 0.0,
                        "revenue": 0.0,
                    }
                prod_map[pid]["qty"] += l.product_uom_qty
                prod_map[pid]["revenue"] += l.price_subtotal

            top_prods = sorted(prod_map.values(), key=lambda x: x["revenue"], reverse=True)[:5]
            for p in top_prods:
                p["qty_fmt"] = f"{p['qty']:g}"
                p["revenue_fmt"] = currency.format(p["revenue"])
            return top_prods
        except Exception:
            return []

    @api.model
    def _inventory_analytics(self, company, currency):
        """Detailed inventory valuation, top holding stock, and low stock watchlist."""
        try:
            Quant = self.env["stock.quant"]
            quants = Quant.search([
                ("company_id", "=", company.id),
                ("location_id.usage", "=", "internal"),
            ])
            total_val = sum(quants.mapped("value")) if hasattr(Quant, "value") else 0.0
            total_qty = sum(quants.mapped("quantity"))

            stock_by_prod = {}
            for q in quants:
                pid = q.product_id.id
                if pid not in stock_by_prod:
                    stock_by_prod[pid] = {
                        "id": pid,
                        "name": q.product_id.name or "Item",
                        "code": q.product_id.default_code or "—",
                        "category": q.product_id.categ_id.name if q.product_id.categ_id else "General",
                        "qty": 0.0,
                        "val": 0.0,
                    }
                stock_by_prod[pid]["qty"] += q.quantity
                stock_by_prod[pid]["val"] += getattr(q, "value", 0.0)

            top_stock_items = sorted(stock_by_prod.values(), key=lambda x: x["val"], reverse=True)[:6]
            for item in top_stock_items:
                item["qty_fmt"] = f"{item['qty']:g}"
                item["val_fmt"] = currency.format(item["val"])

            # Low stock items (stock <= 15)
            low_stock_candidates = [item for item in stock_by_prod.values() if item["qty"] <= 15]
            low_stock_items = sorted(low_stock_candidates, key=lambda x: x["qty"])[:6]
            for item in low_stock_items:
                item["qty_fmt"] = f"{item['qty']:g}"
                item["val_fmt"] = currency.format(item["val"])

            return {
                "total_valuation": total_val,
                "total_valuation_fmt": currency.format(total_val),
                "total_qty": round(total_qty, 1),
                "top_stock_items": top_stock_items,
                "low_stock_items": low_stock_items,
                "low_stock_count": len(low_stock_candidates),
            }
        except Exception:
            return {
                "total_valuation": 0.0,
                "total_valuation_fmt": currency.format(0.0),
                "total_qty": 0.0,
                "top_stock_items": [],
                "low_stock_items": [],
                "low_stock_count": 0,
            }

    @api.model
    def _monthly_performance(self, today, currency):
        result = []
        month_start = today.replace(day=1)
        for offset in range(5, -1, -1):
            start = month_start - relativedelta(months=offset)
            end = start + relativedelta(months=1)
            sale_domain = [
                ("state", "in", ["sale", "done"]),
                ("date_order", ">=", fields.Datetime.to_datetime(start)),
                ("date_order", "<", fields.Datetime.to_datetime(end)),
            ]
            purchase_domain = [
                ("state", "in", ["purchase", "done"]),
                ("date_order", ">=", fields.Datetime.to_datetime(start)),
                ("date_order", "<", fields.Datetime.to_datetime(end)),
            ]
            sales_val = self._safe(
                lambda d=sale_domain: self._sum_in_company_currency("sale.order", d),
                0.0,
            )
            purchases_val = self._safe(
                lambda d=purchase_domain: self._sum_in_company_currency("purchase.order", d),
                0.0,
            )
            result.append({
                "label": start.strftime("%b %Y"),
                "short_label": start.strftime("%b"),
                "sales": sales_val,
                "sales_fmt": currency.format(sales_val),
                "purchases": purchases_val,
                "purchases_fmt": currency.format(purchases_val),
            })

        maximum = max(
            [item[metric] for item in result for metric in ("sales", "purchases")]
            or [1.0]
        )
        maximum = maximum or 1.0
        for item in result:
            item["sales_percent"] = max(4.0, round((item["sales"] / maximum) * 100, 1)) if item["sales"] else 0.0
            item["purchases_percent"] = max(4.0, round((item["purchases"] / maximum) * 100, 1)) if item["purchases"] else 0.0
        return result

    @api.model
    def _asset_summary(self, company, currency):
        if "am.asset" not in self.env:
            return {
                "total_count": 0,
                "running_count": 0,
                "draft_count": 0,
                "closed_count": 0,
                "warehouse_count": 0,
                "employee_count": 0,
                "unassigned_count": 0,
                "assignment_rate": 0.0,
                "component_count": 0,
                "vehicle_count": 0,
                "original_value": 0.0,
                "original_value_fmt": currency.format(0.0),
                "net_book_value": 0.0,
                "net_book_value_fmt": currency.format(0.0),
                "accumulated_depreciation": 0.0,
                "accumulated_depreciation_fmt": currency.format(0.0),
                "pending_handovers": 0,
                "pending_temporary": 0,
                "categories": [],
                "recent": [],
            }

        Asset = self.env["am.asset"]
        asset_domain = [
            ("company_id", "=", company.id),
            ("is_component", "=", False),
        ]
        assets = Asset.search(asset_domain)
        total_count = len(assets)
        original_value = sum(assets.mapped("original_cost"))
        accumulated_depreciation = sum(assets.mapped("accumulated_depreciation"))
        net_book_value = sum(assets.mapped("net_book_value"))

        warehouse_count = Asset.search_count(asset_domain + [("location", "=", "warehouse")])
        employee_count = Asset.search_count(asset_domain + [("location", "=", "employee")])
        unassigned_count = Asset.search_count(asset_domain + [("location", "in", ("neither", False))])
        assigned_count = warehouse_count + employee_count
        assignment_rate = round((assigned_count / total_count) * 100, 1) if total_count else 0.0

        component_count = Asset.search_count([("company_id", "=", company.id), ("is_component", "=", True)])
        vehicle_count = Asset.search_count(asset_domain + [("is_vehicle", "=", True)])
        draft_count = Asset.search_count(asset_domain + [("state", "=", "draft")])
        running_count = Asset.search_count(asset_domain + [("state", "=", "open")])
        closed_count = Asset.search_count(asset_domain + [("state", "=", "close")])

        # Approvals
        pending_handovers = 0
        if "am.asset.handover.request" in self.env:
            pending_handovers = self._safe(
                lambda: self.env["am.asset.handover.request"].sudo().search_count([
                    ("company_id", "=", company.id),
                    ("state", "=", "pending"),
                ]),
                0,
            )
        pending_temporary = 0
        if "am.asset.temporary.request" in self.env:
            pending_temporary = self._safe(
                lambda: self.env["am.asset.temporary.request"].sudo().search_count([
                    ("company_id", "=", company.id),
                    ("state", "=", "pending"),
                ]),
                0,
            )

        # Categories breakdown
        categories = []
        if "am.asset.category" in self.env:
            cat_records = self.env["am.asset.category"].search([])
            for cat in cat_records:
                cat_assets = assets.filtered(lambda a: a.major_category_id.id == cat.id)
                if cat_assets:
                    val = sum(cat_assets.mapped("net_book_value"))
                    categories.append({
                        "id": cat.id,
                        "name": cat.name,
                        "count": len(cat_assets),
                        "val": val,
                        "value_fmt": currency.format(val),
                        "perc": round((len(cat_assets) / total_count) * 100, 1) if total_count else 0,
                    })
            categories = sorted(categories, key=lambda c: c["val"], reverse=True)[:5]

        # Recent assets
        state_labels = dict(Asset._fields["state"]._description_selection(self.env)) if "state" in Asset._fields else {}
        location_labels = dict(Asset._fields["location"]._description_selection(self.env)) if "location" in Asset._fields else {}
        recent = []
        for a in assets.sorted("create_date", reverse=True)[:6]:
            recent.append({
                "id": a.id,
                "name": a.name,
                "tag": a.tag_number or "—",
                "category": a.major_category_id.name or "General",
                "location": location_labels.get(a.location, "Unassigned"),
                "location_key": a.location or "neither",
                "state": a.state or "draft",
                "state_label": state_labels.get(a.state, a.state or "Draft"),
                "net_book_value": a.net_book_value,
                "value_fmt": currency.format(a.net_book_value),
            })

        return {
            "total_count": total_count,
            "running_count": running_count,
            "draft_count": draft_count,
            "closed_count": closed_count,
            "warehouse_count": warehouse_count,
            "employee_count": employee_count,
            "unassigned_count": unassigned_count,
            "assignment_rate": assignment_rate,
            "component_count": component_count,
            "vehicle_count": vehicle_count,
            "original_value": original_value,
            "original_value_fmt": currency.format(original_value),
            "net_book_value": net_book_value,
            "net_book_value_fmt": currency.format(net_book_value),
            "accumulated_depreciation": accumulated_depreciation,
            "accumulated_depreciation_fmt": currency.format(accumulated_depreciation),
            "pending_handovers": pending_handovers,
            "pending_temporary": pending_temporary,
            "categories": categories,
            "recent": recent,
        }

    @api.model
    def get_dashboard_data(self):
        today = fields.Date.context_today(self)
        company = self.env.company
        currency = company.currency_id
        brand = self._get_brand_colors(company)

        month_start = today.replace(day=1)
        next_month = month_start + relativedelta(months=1)
        month_datetime = fields.Datetime.to_datetime(month_start)
        next_month_datetime = fields.Datetime.to_datetime(next_month)

        # Sales Domains
        sale_month_domain = [
            ("company_id", "=", company.id),
            ("state", "in", ["sale", "done"]),
            ("date_order", ">=", month_datetime),
            ("date_order", "<", next_month_datetime),
        ]
        sales_month_total = self._safe(
            lambda: self._sum_in_company_currency("sale.order", sale_month_domain),
            0.0,
        )
        sales_month_count = self._safe(
            lambda: self.env["sale.order"].search_count(sale_month_domain),
            0,
        )
        quotations_count = self._safe(
            lambda: self.env["sale.order"].search_count([
                ("company_id", "=", company.id),
                ("state", "in", ["draft", "sent"]),
            ]),
            0,
        )
        # Customization: Credit Sales Approval
        credit_approval_count = self._safe(
            lambda: self.env["sale.order"].search_count([
                ("company_id", "=", company.id),
                ("state", "=", "finance_approval"),
            ]),
            0,
        )

        # Top Customers & Products (Odoo Spreadsheet Dashboard Analytics)
        top_customers = self._top_customers(company, currency)
        top_products = self._top_products(company, currency)

        # Purchases Domains
        purchase_month_domain = [
            ("company_id", "=", company.id),
            ("state", "in", ["purchase", "done"]),
            ("date_order", ">=", month_datetime),
            ("date_order", "<", next_month_datetime),
        ]
        purchase_month_total = self._safe(
            lambda: self._sum_in_company_currency("purchase.order", purchase_month_domain),
            0.0,
        )
        purchase_month_count = self._safe(
            lambda: self.env["purchase.order"].search_count(purchase_month_domain),
            0,
        )
        rfqs_count = self._safe(
            lambda: self.env["purchase.order"].search_count([
                ("company_id", "=", company.id),
                ("state", "in", ["draft", "sent", "to approve"]),
            ]),
            0,
        )
        # Customization: Local vs Foreign POs
        local_po_count = self._safe(
            lambda: self.env["purchase.order"].search_count([
                ("company_id", "=", company.id),
                ("request_type", "=", "local"),
            ]),
            0,
        )
        foreign_po_count = self._safe(
            lambda: self.env["purchase.order"].search_count([
                ("company_id", "=", company.id),
                ("request_type", "=", "foreign"),
            ]),
            0,
        )
        # Customization: Payment Requests (Foreign & Local)
        pending_foreign_pmt_requests = 0
        if "foreign.payment.request" in self.env:
            pending_foreign_pmt_requests = self._safe(
                lambda: self.env["foreign.payment.request"].search_count([("state", "in", ["draft", "submitted"])]),
                0,
            )
        pending_local_pmt_requests = 0
        if "local.payment.request" in self.env:
            pending_local_pmt_requests = self._safe(
                lambda: self.env["local.payment.request"].search_count([("state", "in", ["draft", "submitted"])]),
                0,
            )
        # Customization: Margins
        margins_count = 0
        if "purchase.import.margin" in self.env:
            margins_count = self._safe(
                lambda: self.env["purchase.import.margin"].search_count([]),
                0,
            )

        # Finance & Banking
        overdue_domain = [
            ("company_id", "=", company.id),
            ("move_type", "=", "out_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "not in", ["paid", "reversed"]),
            ("invoice_date_due", "<", today),
        ]
        overdue_invoices_count = self._safe(
            lambda: self.env["account.move"].search_count(overdue_domain),
            0,
        )
        overdue_invoices_amount = self._safe(
            lambda: self._sum_field("account.move", overdue_domain, "amount_residual"),
            0.0,
        )

        bills_domain = [
            ("company_id", "=", company.id),
            ("move_type", "=", "in_invoice"),
            ("state", "=", "posted"),
            ("payment_state", "not in", ["paid", "reversed"]),
        ]
        open_bills_count = self._safe(
            lambda: self.env["account.move"].search_count(bills_domain),
            0,
        )
        open_bills_amount = self._safe(
            lambda: self._sum_field("account.move", bills_domain, "amount_residual"),
            0.0,
        )

        # Customization: Bank Transactions (Journal Entries per bank journal)
        bank_moves_domain = [
            ("company_id", "=", company.id),
            ("journal_id.type", "=", "bank"),
        ]
        bank_transactions_count = self._safe(
            lambda: self.env["account.move"].search_count(bank_moves_domain),
            0,
        )
        recent_bank_entries = []
        try:
            recent_moves = self.env["account.move"].search(bank_moves_domain, order="date desc, id desc", limit=6)
            for m in recent_moves:
                val = getattr(m, "bank_amount_signed", m.amount_total_signed or m.amount_total or 0.0)
                recent_bank_entries.append({
                    "id": m.id,
                    "name": m.name or "/",
                    "ref": m.ref or "—",
                    "date": m.date.strftime("%d %b %Y") if m.date else "—",
                    "bank_name": m.journal_id.name,
                    "partner_name": m.partner_id.name or "—",
                    "amount": val,
                    "amount_fmt": currency.format(val),
                    "is_negative": val < 0,
                    "state": m.state,
                })
        except Exception:
            pass

        # Inventory Analytics & Stocks
        inventory_data = self._inventory_analytics(company, currency)
        products_count = self._safe(
            lambda: self.env["product.product"].search_count([
                ("active", "=", True),
                ("is_storable", "=", True),
            ]),
            0,
        )
        ready_deliveries = self._safe(
            lambda: self.env["stock.picking"].search_count([
                ("company_id", "=", company.id),
                ("picking_type_code", "=", "outgoing"),
                ("state", "=", "assigned"),
            ]),
            0,
        )
        waiting_deliveries = self._safe(
            lambda: self.env["stock.picking"].search_count([
                ("company_id", "=", company.id),
                ("picking_type_code", "=", "outgoing"),
                ("state", "in", ["confirmed", "waiting"]),
            ]),
            0,
        )
        incoming_shipments = self._safe(
            lambda: self.env["stock.picking"].search_count([
                ("company_id", "=", company.id),
                ("picking_type_code", "=", "incoming"),
                ("state", "in", ["assigned", "confirmed"]),
            ]),
            0,
        )

        # Merge inventory metrics
        inventory_data.update({
            "products_count": products_count,
            "ready_deliveries": ready_deliveries,
            "waiting_deliveries": waiting_deliveries,
            "incoming_shipments": incoming_shipments,
        })

        # HR / Workforce
        employee_count = self._safe(
            lambda: self.env["hr.employee"].search_count([
                ("company_id", "=", company.id),
                ("active", "=", True),
            ]),
            0,
        )

        # Asset Management
        assets = self._asset_summary(company, currency)

        return {
            "user_name": self.env.user.name,
            "company_name": company.name,
            "currency": currency.name,
            "currency_symbol": currency.symbol,
            "generated_at": datetime.now().strftime("%H:%M:%S"),
            "brand": brand,
            "assets": assets,
            "sales": {
                "month_total": sales_month_total,
                "month_total_fmt": currency.format(sales_month_total),
                "month_count": sales_month_count,
                "quotations_count": quotations_count,
                "credit_approval_count": credit_approval_count,
                "top_customers": top_customers,
                "top_products": top_products,
            },
            "purchases": {
                "month_total": purchase_month_total,
                "month_total_fmt": currency.format(purchase_month_total),
                "month_count": purchase_month_count,
                "rfqs_count": rfqs_count,
                "local_po_count": local_po_count,
                "foreign_po_count": foreign_po_count,
                "pending_foreign_pmt_requests": pending_foreign_pmt_requests,
                "pending_local_pmt_requests": pending_local_pmt_requests,
                "margins_count": margins_count,
            },
            "finance": {
                "overdue_invoices_count": overdue_invoices_count,
                "overdue_invoices_amount": overdue_invoices_amount,
                "overdue_invoices_amount_fmt": currency.format(overdue_invoices_amount),
                "open_bills_count": open_bills_count,
                "open_bills_amount": open_bills_amount,
                "open_bills_amount_fmt": currency.format(open_bills_amount),
                "bank_transactions_count": bank_transactions_count,
                "recent_bank_transactions": recent_bank_entries,
            },
            "inventory": inventory_data,
            "hr": {
                "employee_count": employee_count,
            },
            "performance": self._monthly_performance(today, currency),
        }
