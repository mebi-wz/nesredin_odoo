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
        this.notification = useService("notification");
        this.state = useState({
            isLoading: true,
            isReadOnly: false,
            canManage: false,
            lastUpdated: "",
            stats: {
                total_count: 0,
                component_count: 0,
                vehicle_count: 0,
                warehouse_count: 0,
                employee_count: 0,
                unassigned_count: 0,
                draft_count: 0,
                running_count: 0,
                closed_count: 0,
                assignment_rate: 0,
                pending_handover_count: 0,
                pending_temporary_count: 0,
                original_value_fmt: "0",
                accumulated_depreciation_fmt: "0",
                total_value_fmt: "0",
                category_data: [],
                branch_data: [],
                recent_assets: [],
            },
        });

        onWillStart(async () => {
            const [isViewer, isExpert, isManager, isPropertyManager] = await Promise.all([
                user.hasGroup("asset_management.group_asset_dashboard_viewer"),
                user.hasGroup("asset_management.group_asset_ffa_expert"),
                user.hasGroup("asset_management.group_asset_manager"),
                user.hasGroup("asset_management.group_asset_property_manager"),
            ]);
            this.state.canManage = isExpert || isManager || isPropertyManager;
            this.state.isReadOnly = isViewer && !this.state.canManage;
            await this.fetchData();
        });
    }

    async fetchData() {
        this.state.isLoading = true;
        try {
            const data = await this.orm.call("am.asset", "get_dashboard_data", []);
            Object.assign(this.state.stats, data);
            this.state.lastUpdated = new Intl.DateTimeFormat(undefined, {
                hour: "2-digit",
                minute: "2-digit",
            }).format(new Date());
        } catch (error) {
            this.notification.add("The asset dashboard could not be refreshed.", {
                title: "Dashboard unavailable",
                type: "danger",
            });
            throw error;
        } finally {
            this.state.isLoading = false;
        }
    }

    refreshDashboard() {
        return this.fetchData();
    }

    /**
     * Generic action opener.
     * @param {string} xmlid - The action XML ID.
     * @param {Array} domain  - Optional Odoo domain to filter records.
     * @param {Object} extra  - Extra context values for the target action.
     */
    async openAction(xmlid, domain = [], extraContext = {}) {
        const accessContext = this.state.isReadOnly
            ? { create: false, edit: false, delete: false }
            : {};
        const action = await this.action.loadAction(xmlid, extraContext);
        await this.action.doAction({
            ...action,
            context: {
                ...(action.context || {}),
                ...accessContext,
                ...extraContext,
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

    viewUnassignedAssets() {
        this.openAction("asset_management.action_unassigned_assets", [["is_component", "=", false]]);
    }

    viewVehicles() {
        if (this.state.isReadOnly) {
            return;
        }
        this.openAction("asset_management.action_asset_vehicles");
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

    viewHandoverApprovals() {
        if (!this.state.canManage) {
            return;
        }
        this.openAction("asset_management.action_am_asset_handover_approval", [["state", "=", "pending"]]);
    }

    viewTemporaryApprovals() {
        if (!this.state.canManage) {
            return;
        }
        this.openAction("asset_management.action_am_asset_temporary_approval", [["state", "=", "pending"]]);
    }

    viewCategory(event) {
        const categoryId = Number(event.currentTarget.dataset.categoryId);
        if (!categoryId) {
            return;
        }
        this.openAction("asset_management.action_assets_overview", [
            ["major_category_id", "=", categoryId],
            ["is_component", "=", false],
        ]);
    }

    openRecentAsset(event) {
        const assetId = Number(event.currentTarget.dataset.assetId);
        if (!assetId) {
            return;
        }
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Asset",
            res_model: "am.asset",
            res_id: assetId,
            views: [[false, "form"]],
            target: "current",
            context: this.state.isReadOnly
                ? { create: false, edit: false, delete: false }
                : {},
        });
    }

    // ─── Global Shortcuts ─────────────────────────────────────────────────────

    createAsset() {
        if (this.state.isReadOnly) {
            return;
        }
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Register Asset',
            res_model: 'am.asset',
            views: [[false, 'form']],
            target: 'current',
        });
    }
}

registry.category("actions").add("asset_dashboard_main", AssetDashboard);
