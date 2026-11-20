/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AccountReportSearchBar } from "@account_reports/components/account_report/search_bar/search_bar";

const requiresInitialBalance = (value) =>
    ["4", "5"].includes(String(value || "").trim());

patch(AccountReportSearchBar.prototype, {
    async search() {
        const controller = this.controller;

        const reportId = Number(
            controller.options?.report_id ??
            controller.cachedFilterOptions?.report_id ??
            controller.actionReportId
        );

        // Ne jamais modifier le comportement des autres rapports.
        if (reportId !== 13) {
            return super.search(...arguments);
        }

        const previousSearch = String(
            controller.cachedFilterOptions?.filter_search_bar || ""
        ).trim();

        const currentSearch = String(
            this.searchText.el?.value || ""
        ).trim();

        const wasVisible = requiresInitialBalance(previousSearch);
        const shouldBeVisible = requiresInitialBalance(currentSearch);

        // Conserver le filtrage standard Odoo.
        await super.search(...arguments);

        // Eviter les rechargements inutiles et les boucles.
        if (wasVisible === shouldBeVisible) {
            return;
        }

        // Reconstruire les colonnes seulement si leur
        // visibilite doit changer.
        if (currentSearch) {
            await controller.updateOption(
                "filter_search_bar",
                currentSearch,
                true
            );
        } else {
            await controller.deleteOption(
                "filter_search_bar",
                true
            );
        }
    },
});
