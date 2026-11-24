/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AccountReportSearchBar } from "@account_reports/components/account_report/search_bar/search_bar";

patch(AccountReportSearchBar.prototype, {
    async search() {
        const inputText = this.searchText.el.value.trim();
        const query = inputText.toLowerCase();

        const previousSearch = String(
            this.controller.cachedFilterOptions?.filter_search_bar ??
            this.controller.options?.filter_search_bar ??
            ""
        ).trim();

        const requiresInitial = (value) =>
            /^[45]\d*$/.test(String(value || "").trim());

        const reloadColumns =
            requiresInitial(previousSearch) !==
            requiresInitial(inputText);

        await this.controller.reportLoadingPromise;

        // Appliquer ce comportement uniquement au Grand livre général.
        const isGeneralLedger = Number(
            this.controller.options?.report_id ??
            this.controller.cachedFilterOptions?.report_id ??
            this.controller.actionReportId
        ) === 12;

        // On conserve le comportement standard ailleurs.
        if (!isGeneralLedger) {
            return super.search(...arguments);
        }

        if (!query) {
            delete this.controller.lines_searched;
            await this.controller.deleteOption("filter_search_bar", reloadColumns);
            return;
        }

        const isNumeric = /^\d+$/.test(query);
        const matchedIds = [];

        for (const line of this.controller.lines) {
            if (!line.name) {
                continue;
            }

            const lineName = line.name.trim().toLowerCase();

            const match = isNumeric
                ? lineName.startsWith(query)
                : lineName.includes(query);

            if (match) {
                matchedIds.push(line.id);
            }
        }

        this.controller.lines_searched = matchedIds;
        await this.controller.updateOption("filter_search_bar", inputText, reloadColumns);
    },
});
