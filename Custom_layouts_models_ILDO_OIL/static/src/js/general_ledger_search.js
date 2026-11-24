/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { AccountReportSearchBar } from "@account_reports/components/account_report/search_bar/search_bar";

patch(AccountReportSearchBar.prototype, {
    async search() {
        const inputText = this.searchText.el?.value?.trim() ?? "";
        const query = inputText.toLowerCase();

        // Chaque nouvelle recherche invalide les recherches precedentes.
        const generation = (this._ildoSearchGeneration || 0) + 1;
        this._ildoSearchGeneration = generation;

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

        // Attendre la disponibilite des donnees du rapport.
        // La promesse initiale peut etre deja resolue alors
        // qu'un nouveau chargement est en cours.
        const maxAttempts = 100;
        const waitMs = 100;

        let attempts = 0;

        while (
            this.controller.loadingData ||
            !Array.isArray(this.controller.data?.lines)
        ) {
            // Une nouvelle recherche rend celle-ci obsolete.
            if (
                this._ildoSearchGeneration !== generation ||
                this.searchText.el?.value?.trim() !== inputText
            ) {
                return;
            }

            if (attempts >= maxAttempts) {
                console.warn(
                    "[ILDO] Recherche non appliquee : " +
                    "donnees du rapport indisponibles."
                );
                return;
            }

            attempts++;

            await new Promise(resolve =>
                setTimeout(resolve, waitMs)
            );
        }

        // Verification finale avant toute modification
        // des filtres ou consultation des lignes.
        if (
            this._ildoSearchGeneration !== generation ||
            this.searchText.el?.value?.trim() !== inputText
        ) {
            return;
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
