/** @odoo-module **/

import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class AssetDashboard extends Component {
    static template = "asset_management.AssetDashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({
            isReadOnly: false,
            stats: {
                total_count: 0,
                total_value_fmt: "0",
                warehouse_count: 0,
                employee_count: 0,
                category_data: [],
                branch_data: [],
                draft_count: 0,
                running_count: 0,
                closed_count: 0,
            }
        });

        onWillStart(async () => {
            const [isViewer, isExpert, isManager] = await Promise.all([
                user.hasGroup("asset_management.group_asset_dashboard_viewer"),
                user.hasGroup("asset_management.group_asset_ffa_expert"),
                user.hasGroup("asset_management.group_asset_manager"),
            ]);
            this.state.isReadOnly = isViewer && !isExpert && !isManager;
            await this.fetchData();
        });
    }

    async fetchData() {
        const data = await this.orm.call("am.asset", "get_dashboard_data", []);
        Object.assign(this.state.stats, data);
    }

    /**
     * Generic action opener.
     * @param {string} xmlid - The action XML ID.
     * @param {Array} domain  - Optional Odoo domain to filter records.
     * @param {Object} extra  - Extra context values for the target action.
     */
    async openAction(xmlid, domain = [], extra = {}) {
        const accessContext = this.state.isReadOnly
            ? { create: false, edit: false, delete: false }
            : {};
        const action = await this.action.loadAction(xmlid, extra);
        await this.action.doAction({
            ...action,
            context: {
                ...(action.context || {}),
                ...accessContext,
                ...extra,
            },
            domain,
        });
    }

    // ─── Top KPI Cards ────────────────────────────────────────────────────────

    /** Total Assets → All Assets list */
    viewAllAssets() {
        this.openAction("asset_management.action_assets_overview", [["is_component", "=", false]]);
    }

    viewComponentAssets() {
        this.openAction("asset_management.action_assets_overview", [["is_component", "=", true]]);
    }

    /** In Warehouse → Dedicated warehouse stock view */
    viewWarehouseAssets() {
        this.openAction("asset_management.action_am_asset_warehouse_stock", [["asset_id.is_component", "=", false]]);
    }

    /** With Employees → Dedicated employee assets view */
    viewEmployeeAssets() {
        this.openAction("asset_management.action_employee_assets", [["asset_id.is_component", "=", false]]);
    }

    // ─── Lifecycle Status Cards ────────────────────────────────────────────────

    viewDraftAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "draft"], ["is_component", "=", false]]);
    }

    viewRunningAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "open"], ["is_component", "=", false]]);
    }

    viewClosedAssets() {
        this.openAction("asset_management.action_assets_overview", [["state", "=", "close"], ["is_component", "=", false]]);
    }

    // ─── Global Shortcuts ─────────────────────────────────────────────────────

    createAsset() {
        if (this.state.isReadOnly) {
            return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'am.asset',
            views: [[false, 'form']],
            target: 'current',
        });
    }
}

registry.category("actions").add("asset_dashboard_main", AssetDashboard);
