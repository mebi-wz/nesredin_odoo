/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class NesredinDashboard extends Component {
    static template = "nesredin_dashboard.MainDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            isLoading: true,
            activeTab: "all", // 'all', 'assets', 'sales', 'inventory', 'procurement', 'finance'
            data: {
                user_name: "",
                company_name: "",
                currency: "",
                currency_symbol: "",
                generated_at: "",
                brand: {
                    primary: "#5e4766",
                    secondary: "#010101",
                    rgb: "94, 71, 102",
                    dark: "#171119",
                    mid_dark: "#2a1f2d",
                    light: "#e6e3e8",
                    hero_gradient: "linear-gradient(135deg, #07090e 0%, #171119 45%, #5e4766 100%)",
                    accent_gradient: "linear-gradient(135deg, #5e4766 0%, #8b5cf6 100%)",
                },
                assets: {
                    total_count: 0,
                    running_count: 0,
                    draft_count: 0,
                    closed_count: 0,
                    warehouse_count: 0,
                    employee_count: 0,
                    unassigned_count: 0,
                    assignment_rate: 0,
                    component_count: 0,
                    vehicle_count: 0,
                    original_value_fmt: "0",
                    net_book_value_fmt: "0",
                    accumulated_depreciation_fmt: "0",
                    pending_handovers: 0,
                    pending_temporary: 0,
                    categories: [],
                    recent: [],
                },
                sales: {
                    month_total: 0,
                    month_total_fmt: "0",
                    month_count: 0,
                    quotations_count: 0,
                    credit_approval_count: 0,
                    top_customers: [],
                    top_products: [],
                },
                purchases: {
                    month_total: 0,
                    month_total_fmt: "0",
                    month_count: 0,
                    rfqs_count: 0,
                    local_po_count: 0,
                    foreign_po_count: 0,
                    pending_foreign_pmt_requests: 0,
                    pending_local_pmt_requests: 0,
                    margins_count: 0,
                },
                finance: {
                    overdue_invoices_count: 0,
                    overdue_invoices_amount_fmt: "0",
                    open_bills_count: 0,
                    open_bills_amount_fmt: "0",
                    bank_transactions_count: 0,
                    recent_bank_transactions: [],
                },
                inventory: {
                    total_valuation: 0,
                    total_valuation_fmt: "0",
                    total_qty: 0,
                    products_count: 0,
                    ready_deliveries: 0,
                    waiting_deliveries: 0,
                    incoming_shipments: 0,
                    top_stock_items: [],
                    low_stock_items: [],
                    low_stock_count: 0,
                },
                hr: {
                    employee_count: 0,
                },
                performance: [],
            },
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        this.state.isLoading = true;
        try {
            const result = await this.orm.call("nesredin.dashboard", "get_dashboard_data", []);
            Object.assign(this.state.data, result);
        } catch (error) {
            console.error("Failed to load dashboard data:", error);
            this.notification.add("Could not refresh dashboard metrics.", {
                type: "danger",
                title: "Dashboard Error",
            });
        } finally {
            this.state.isLoading = false;
        }
    }

    refreshDashboard() {
        return this.loadData();
    }

    setTab(tab) {
        this.state.activeTab = tab;
    }

    getGreeting() {
        const hour = new Date().getHours();
        if (hour < 12) return "Good morning";
        if (hour < 18) return "Good afternoon";
        return "Good evening";
    }

    // ── Generic Action Opener ──────────────────────────────────────────
    async openAction(xmlid, domain = [], extraContext = {}) {
        try {
            const action = await this.action.loadAction(xmlid, extraContext);
            await this.action.doAction({
                ...action,
                context: {
                    ...(action.context || {}),
                    ...extraContext,
                },
                domain: domain.length ? domain : (action.domain || []),
            });
        } catch (err) {
            console.warn(`Failed to open action ${xmlid}:`, err);
        }
    }

    // ── Form Openers ───────────────────────────────────────────────────
    openAssetForm(assetId) {
        if (!assetId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Asset",
            res_model: "am.asset",
            res_id: assetId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openPartnerForm(partnerId) {
        if (!partnerId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Customer",
            res_model: "res.partner",
            res_id: partnerId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openProductForm(productId) {
        if (!productId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Product",
            res_model: "product.product",
            res_id: productId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    openBankMoveForm(moveId) {
        if (!moveId) return;
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Journal Entry",
            res_model: "account.move",
            res_id: moveId,
            views: [[false, "form"]],
            target: "current",
        });
    }

    // ── Asset Management Actions ───────────────────────────────────────
    viewAllAssets() {
        this.openAction("asset_management.action_assets_overview", [["is_component", "=", false]]);
    }

    viewWarehouseAssets() {
        this.openAction("asset_management.action_am_asset_warehouse_stock", [["asset_id.is_component", "=", false]]);
    }

    viewEmployeeAssets() {
        this.openAction("asset_management.action_employee_assets", [["asset_id.is_component", "=", false]]);
    }

    viewUnassignedAssets() {
        this.openAction("asset_management.action_unassigned_assets", [["is_component", "=", false]]);
    }

    viewComponentAssets() {
        this.openAction("asset_management.action_assets_overview", [["is_component", "=", true]]);
    }

    viewVehicles() {
        this.openAction("asset_management.action_asset_vehicles");
    }

    viewDraftAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "draft"], ["is_component", "=", false]]);
    }

    viewRunningAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "open"], ["is_component", "=", false]]);
    }

    viewClosedAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "close"], ["is_component", "=", false]]);
    }

    viewHandoverApprovals() {
        this.openAction("asset_management.action_am_asset_handover_approval", [["state", "=", "pending"]]);
    }

    viewTemporaryApprovals() {
        this.openAction("asset_management.action_am_asset_temporary_approval", [["state", "=", "pending"]]);
    }

    // ── Sales & Credit Approvals Actions ───────────────────────────────
    viewSalesOrders() {
        this.openAction("sale.action_orders");
    }

    viewQuotations() {
        this.openAction("sale.action_quotations_with_onboarding");
    }

    viewCreditApprovals() {
        this.openAction("accounting_procurement.action_accounting_credit_sales_approval");
    }

    // ── Purchases & Procurement Actions ────────────────────────────────
    viewPurchaseOrders() {
        this.openAction("purchase.purchase_form_action");
    }

    viewLocalPOs() {
        this.openAction("accounting_procurement.action_account_local_po");
    }

    viewForeignPOs() {
        this.openAction("accounting_procurement.action_account_foreign_po");
    }

    viewRFQs() {
        this.openAction("purchase.purchase_rfq");
    }

    viewForeignPaymentRequests() {
        this.openAction("procurement_foreign_operations.action_foreign_payment_request");
    }

    viewLocalPaymentRequests() {
        this.openAction("procurement_local_purchase.action_local_payment_request");
    }

    viewBillMargins() {
        this.openAction("accounting_procurement.action_purchase_import_margin_accounting");
    }

    // ── Finance & Banking Actions ──────────────────────────────────────
    viewBankTransactions() {
        this.openAction("accounting_procurement.action_bank_transactions_journal_entries");
    }

    viewOverdueInvoices() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Overdue Invoices",
            res_model: "account.move",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["move_type", "=", "out_invoice"],
                ["state", "=", "posted"],
                ["payment_state", "not in", ["paid", "reversed"]],
                ["invoice_date_due", "<", new Date().toISOString().split("T")[0]],
            ],
            target: "current",
        });
    }

    viewOpenBills() {
        this.openAction("account.action_move_in_invoice");
    }

    // ── Inventory & Operations Actions ─────────────────────────────────
    viewInventory() {
        this.openAction("stock.action_view_quants");
    }

    viewProducts() {
        this.openAction("stock.product_template_action_product");
    }

    viewDeliveries() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Deliveries Waiting / Ready",
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain: [["picking_type_code", "=", "outgoing"], ["state", "in", ["assigned", "confirmed"]]],
            target: "current",
        });
    }

    viewReceipts() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Incoming Shipments",
            res_model: "stock.picking",
            views: [[false, "list"], [false, "form"]],
            domain: [["picking_type_code", "=", "incoming"], ["state", "in", ["assigned", "confirmed"]]],
            target: "current",
        });
    }

    viewEmployees() {
        this.openAction("hr.open_view_employee_list_my");
    }
}

registry.category("actions").add("nesredin_dashboard.main", NesredinDashboard);
