import logging
from datetime import datetime

from odoo import api, fields, models
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class SecefTransaction(models.Model):
    _name = "sunsoft.secef.transaction"
    _description = "Transaction SECeF"
    _order = "create_date desc, id desc"

    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Facture",
        required=True,
        readonly=True,
        index=True,
        ondelete="restrict",
    )

    company_id = fields.Many2one(
        related="move_id.company_id",
        string="Société",
        store=True,
        readonly=True,
        index=True,
    )

    state = fields.Selection(
        selection=[
            (
                "pending",
                "En attente",
            ),
            (
                "processing",
                "En cours",
            ),
            (
                "completed",
                "Terminée",
            ),
            (
                "failed",
                "Échec",
            ),
            (
                "unknown",
                "Résultat indéterminé",
            ),
        ],
        string="État",
        default="pending",
        required=True,
        readonly=True,
        index=True,
        copy=False,
    )

    # =========================================================
    # Identifiants centraux
    # =========================================================

    request_uid = fields.Char(
        string="Identifiant de requête",
        required=True,
        readonly=True,
        copy=False,
        index=True,
    )

    central_job_uid = fields.Char(
        string="Job central SECeF",
        readonly=True,
        copy=False,
        index=True,
    )

    agent_uid = fields.Char(
        string="UID Agent SECeF",
        readonly=True,
        copy=False,
        index=True,
    )

    # =========================================================
    # Compatibilité ancienne architecture
    # =========================================================

    agent_identifier = fields.Char(
        string="Agent SECeF (legacy)",
        readonly=True,
        copy=False,
    )

    # =========================================================
    # Données de transaction
    # =========================================================

    request_payload = fields.Json(
        string="Requête",
        readonly=True,
        copy=False,
    )

    local_item_metadata = fields.Json(
        string="Metadonnees locales articles SECeF",
        readonly=True,
        copy=False,
    )


    response_payload = fields.Json(
        string="Réponse",
        readonly=True,
        copy=False,
    )

    error_message = fields.Text(
        string="Erreur",
        readonly=True,
        copy=False,
    )

    started_at = fields.Datetime(
        string="Début du traitement",
        readonly=True,
        copy=False,
    )

    completed_at = fields.Datetime(
        string="Fin du traitement",
        readonly=True,
        copy=False,
    )

    last_sync_at = fields.Datetime(
        string="Dernière synchronisation centrale",
        readonly=True,
        copy=False,
    )

    # =========================================================
    # Contraintes
    # =========================================================

    _request_uid_unique = models.Constraint(
        "UNIQUE(request_uid)",
        (
            "L'identifiant de requête SECeF "
            "doit être unique."
        ),
    )

    _central_job_uid_unique = models.Constraint(
        "UNIQUE(central_job_uid)",
        (
            "L'identifiant du Job central SECeF "
            "doit être unique."
        ),
    )

    # =========================================================
    # Réponse serveur central
    # =========================================================

    def _record_central_ack(
        self,
        response_payload,
    ):
        """
        Enregistre l'accusé de réception du serveur central.

        Cette méthode ne certifie pas la facture.
        Elle associe uniquement le Job central au request_uid
        déjà créé et persisté localement.
        """

        self.ensure_one()

        if not isinstance(
            response_payload,
            dict,
        ):
            raise UserError(
                "La réponse du serveur central SECeF "
                "est invalide."
            )

        response_request_uid = (
            response_payload.get(
                "request_uid"
            )
        )

        if (
            response_request_uid
            != self.request_uid
        ):
            raise UserError(
                "Le request_uid retourné par le "
                "serveur central est incohérent."
            )

        job_uid = (
            response_payload.get(
                "job_uid"
            )
        )

        if not job_uid:
            raise UserError(
                "Le serveur central SECeF n'a pas "
                "retourné de job_uid."
            )

        response_agent_uid = (
            response_payload.get(
                "agent_uid"
            )
        )

        if (
            self.agent_uid
            and response_agent_uid
            and response_agent_uid
            != self.agent_uid
        ):
            raise UserError(
                "L'Agent retourné par le serveur "
                "central est incohérent."
            )

        if (
            self.central_job_uid
            and self.central_job_uid
            != job_uid
        ):
            raise UserError(
                "Cette transaction SECeF est déjà "
                "rattachée à un autre Job central."
            )

        values = {
            "central_job_uid":
                job_uid,

            "response_payload":
                response_payload,

            "error_message":
                False,

            "last_sync_at":
                fields.Datetime.now(),
        }

        if (
            not self.agent_uid
            and response_agent_uid
        ):
            values[
                "agent_uid"
            ] = response_agent_uid

        self.write(
            values
        )

    def _mark_processing(
        self,
        response_payload=None,
    ):
        """
        Marque la transaction comme prise en charge
        par l'Agent via le serveur central.
        """

        self.ensure_one()

        if self.state == "completed":
            return

        values = {
            "state":
                "processing",

            "error_message":
                False,

            "last_sync_at":
                fields.Datetime.now(),
        }

        if not self.started_at:
            values[
                "started_at"
            ] = fields.Datetime.now()

        if response_payload is not None:
            values[
                "response_payload"
            ] = response_payload

        self.write(
            values
        )

        self.move_id.write({
            "secef_state":
                "processing",

            "secef_error_message":
                False,
        })

    def _apply_central_response(
        self,
        response_payload,
    ):
        """
        Applique l'état retourné par le serveur central.

        États supportés :
        - pending
        - processing
        - completed
        - failed
        - unknown
        """

        self.ensure_one()

        if not isinstance(
            response_payload,
            dict,
        ):
            raise UserError(
                "Réponse centrale SECeF invalide."
            )

        response_request_uid = (
            response_payload.get(
                "request_uid"
            )
        )

        if (
            response_request_uid
            != self.request_uid
        ):
            raise UserError(
                "Le request_uid de la réponse centrale "
                "ne correspond pas à la transaction."
            )

        response_job_uid = (
            response_payload.get(
                "job_uid"
            )
        )

        if response_job_uid:
            if (
                self.central_job_uid
                and self.central_job_uid
                != response_job_uid
            ):
                raise UserError(
                    "Le job_uid central ne correspond "
                    "pas à la transaction SECeF."
                )

            if not self.central_job_uid:
                self.write({
                    "central_job_uid":
                        response_job_uid,
                })

        central_state = (
            response_payload.get(
                "status"
            )
        )

        # -----------------------------------------------------
        # Pending
        # -----------------------------------------------------

        if central_state == "pending":
            # Ne jamais faire régresser une transaction
            # déjà passée à processing.
            if self.state == "pending":
                self.write({
                    "response_payload":
                        response_payload,

                    "error_message":
                        False,

                    "last_sync_at":
                        fields.Datetime.now(),
                })

            return

        # -----------------------------------------------------
        # Processing
        # -----------------------------------------------------

        if central_state == "processing":
            self._mark_processing(
                response_payload
            )

            return

        # -----------------------------------------------------
        # Completed
        # -----------------------------------------------------

        if central_state == "completed":
            result = (
                response_payload.get(
                    "result"
                )
            )

            if not isinstance(
                result,
                dict,
            ):
                raise UserError(
                    "Le serveur central indique une "
                    "certification terminée sans "
                    "résultat fiscal valide."
                )

            self._mark_completed(
                result
            )

            return

        error_message = (
            response_payload.get(
                "error_message"
            )
            or "Erreur SECeF non précisée."
        )

        # -----------------------------------------------------
        # Failed
        # -----------------------------------------------------

        if central_state == "failed":
            self._mark_failed(
                error_message,
                response_payload,
            )

            return

        # -----------------------------------------------------
        # Unknown
        # -----------------------------------------------------

        if central_state == "unknown":
            self._mark_unknown(
                error_message,
                response_payload,
            )

            return

        raise UserError(
            "Le serveur central SECeF a retourné "
            "un statut inconnu : %s."
            % central_state
        )

    # =========================================================
    # États fiscaux
    # =========================================================

    def _mark_completed(
        self,
        response_payload,
    ):
        """
        Enregistre définitivement une certification confirmée.
        """

        self.ensure_one()

        if self.state == "completed":
            return

        if not isinstance(
            response_payload,
            dict,
        ):
            raise UserError(
                "Le résultat fiscal SECeF "
                "est invalide."
            )

        required_fields = (
            "invoice_number",
            "mid",
            "ifu",
            "signature",
            "datetime",
            "invoice_counter",
            "total_counter",
            "qr_data",
        )

        missing_fields = [
            field_name
            for field_name in required_fields
            if response_payload.get(
                field_name
            ) in (
                None,
                "",
            )
        ]

        if missing_fields:
            raise UserError(
                "Résultat fiscal SECeF incomplet : %s."
                % ", ".join(
                    missing_fields
                )
            )

        # -----------------------------------------------------
        # Vérification numéro facture
        # -----------------------------------------------------

        if (
            response_payload[
                "invoice_number"
            ]
            != self.move_id.name
        ):
            raise UserError(
                "Le numéro de facture retourné "
                "par SECeF est incohérent."
            )

        # -----------------------------------------------------
        # Vérification date certification
        # -----------------------------------------------------

        try:
            certification_datetime = (
                datetime.strptime(
                    str(
                        response_payload[
                            "datetime"
                        ]
                    ),
                    "%Y%m%d%H%M%S",
                )
            )

        except (
            TypeError,
            ValueError,
        ) as exc:
            raise UserError(
                "La date de certification SECeF "
                "est invalide."
            ) from exc

        # -----------------------------------------------------
        # Vérification compteurs
        # -----------------------------------------------------

        for counter_name in (
            "invoice_counter",
            "total_counter",
        ):
            counter_value = (
                response_payload[
                    counter_name
                ]
            )

            if (
                isinstance(
                    counter_value,
                    bool,
                )
                or not isinstance(
                    counter_value,
                    int,
                )
                or counter_value < 0
            ):
                raise UserError(
                    "Le compteur fiscal '%s' "
                    "est invalide."
                    % counter_name
                )

        # -----------------------------------------------------
        # Vérification QR
        # -----------------------------------------------------

        expected_qr_data = ";".join([
            "BFSECEF01",
            str(
                response_payload[
                    "mid"
                ]
            ),
            str(
                response_payload[
                    "signature"
                ]
            ),
            str(
                response_payload[
                    "ifu"
                ]
            ),
            str(
                response_payload[
                    "datetime"
                ]
            ),
        ])

        if (
            response_payload[
                "qr_data"
            ]
            != expected_qr_data
        ):
            raise UserError(
                "Les données QR SECeF "
                "sont incohérentes."
            )

        now = fields.Datetime.now()

        # -----------------------------------------------------
        # Transaction
        # -----------------------------------------------------

        self.write({
            "state":
                "completed",

            "response_payload":
                response_payload,

            "error_message":
                False,

            "completed_at":
                now,

            "last_sync_at":
                now,
        })

        # -----------------------------------------------------
        # Facture
        # -----------------------------------------------------

        self.move_id.write({
            "secef_state":
                "certified",

            "secef_mid":
                response_payload[
                    "mid"
                ],

            "secef_signature":
                response_payload[
                    "signature"
                ],

            "secef_datetime":
                certification_datetime,

            "secef_qr_data":
                response_payload[
                    "qr_data"
                ],

            "secef_fiscal_counter":
                response_payload[
                    "invoice_counter"
                ],

            "secef_total_counter":
                response_payload[
                    "total_counter"
                ],

            "secef_error_message":
                False,
        })

    def _mark_failed(
        self,
        error_message,
        response_payload=None,
    ):
        """
        Enregistre un échec certain.

        Un succès déjà confirmé ne peut jamais être
        remplacé par failed.
        """

        self.ensure_one()

        if self.state == "completed":
            return

        if self.state == "failed":
            return

        now = fields.Datetime.now()

        self.write({
            "state":
                "failed",

            "response_payload":
                response_payload or {},

            "error_message":
                error_message,

            "completed_at":
                now,

            "last_sync_at":
                now,
        })

        self.move_id.write({
            "secef_state":
                "failed",

            "secef_error_message":
                error_message,
        })

    def _mark_unknown(
        self,
        error_message,
        response_payload=None,
    ):
        """
        Enregistre un résultat fiscal indéterminé.

        Cet état bloque toute nouvelle certification
        automatique ou manuelle.
        """

        self.ensure_one()

        if self.state == "completed":
            return

        if self.state == "unknown":
            return

        now = fields.Datetime.now()

        self.write({
            "state":
                "unknown",

            "response_payload":
                response_payload or {},

            "error_message":
                error_message,

            "completed_at":
                now,

            "last_sync_at":
                now,
        })

        self.move_id.write({
            "secef_state":
                "unknown",

            "secef_error_message":
                error_message,
        })

    # =========================================================
    # CRON 1 - OUTBOX
    # =========================================================

    @api.model
    def _cron_dispatch_secef_outbox(
        self,
        limit=20,
    ):
        """
        Envoie les demandes locales SECeF qui n'ont pas
        encore été confirmées par le serveur central.

        Conditions :
        - state = pending ;
        - agent_uid renseigné ;
        - central_job_uid absent.

        Le request_uid n'est jamais régénéré.
        """

        transactions = (
            self.sudo()
            .search(
                [
                    (
                        "state",
                        "=",
                        "pending",
                    ),
                    (
                        "agent_uid",
                        "!=",
                        False,
                    ),
                    (
                        "central_job_uid",
                        "=",
                        False,
                    ),
                ],
                order=(
                    "create_date asc, "
                    "id asc"
                ),
                limit=limit,
            )
        )

        selected_count = len(
            transactions
        )

        processed_count = 0

        for transaction in transactions:
            try:
                with self.env.cr.savepoint():

                    transaction = (
                        transaction
                        .sudo()
                        .exists()
                    )

                    if not transaction:
                        continue

                    # Double vérification après récupération.
                    if (
                        transaction.state
                        != "pending"
                    ):
                        continue

                    if (
                        transaction
                        .central_job_uid
                    ):
                        continue

                    if not transaction.agent_uid:
                        continue

                    move = (
                        transaction
                        .move_id
                        .sudo()
                        .with_company(
                            transaction.company_id
                        )
                    )

                    if not move:
                        _logger.error(
                            (
                                "Transaction SECeF sans facture"
                                " | transaction_id=%s"
                                " | request_uid=%s"
                            ),
                            transaction.id,
                            transaction.request_uid,
                        )

                        continue

                    _logger.info(
                        (
                            "Dispatch outbox SECeF"
                            " | transaction_id=%s"
                            " | move_id=%s"
                            " | request_uid=%s"
                            " | agent_uid=%s"
                        ),
                        transaction.id,
                        move.id,
                        transaction.request_uid,
                        transaction.agent_uid,
                    )

                    move._dispatch_secef_transaction(
                        transaction
                    )

                    processed_count += 1

            except Exception:
                # Le savepoint garantit qu'une transaction
                # défectueuse ne bloque pas le lot complet.
                _logger.exception(
                    (
                        "Erreur inattendue pendant "
                        "le cron outbox SECeF"
                        " | transaction_id=%s"
                        " | request_uid=%s"
                    ),
                    transaction.id,
                    transaction.request_uid,
                )

        _logger.info(
            (
                "Cron outbox SECeF terminé"
                " | sélectionnées=%s"
                " | traitées=%s"
            ),
            selected_count,
            processed_count,
        )

        return True

    # =========================================================
    # CRON 2 - SYNCHRONISATION
    # =========================================================

    @api.model
    def _cron_sync_secef_transactions(
        self,
        limit=50,
    ):
        """
        Synchronise les Jobs déjà connus du serveur central.

        Conditions :
        - state = pending ou processing ;
        - agent_uid renseigné ;
        - central_job_uid connu.

        Cette méthode effectue uniquement des lectures GET.
        Elle ne crée aucune nouvelle opération fiscale.
        """

        transactions = (
            self.sudo()
            .search(
                [
                    (
                        "state",
                        "in",
                        [
                            "pending",
                            "processing",
                        ],
                    ),
                    (
                        "agent_uid",
                        "!=",
                        False,
                    ),
                    (
                        "central_job_uid",
                        "!=",
                        False,
                    ),
                ],
                order=(
                    "last_sync_at asc, "
                    "create_date asc, "
                    "id asc"
                ),
                limit=limit,
            )
        )

        selected_count = len(
            transactions
        )

        processed_count = 0

        for transaction in transactions:
            try:
                with self.env.cr.savepoint():

                    transaction = (
                        transaction
                        .sudo()
                        .exists()
                    )

                    if not transaction:
                        continue

                    if transaction.state not in {
                        "pending",
                        "processing",
                    }:
                        continue

                    if not transaction.central_job_uid:
                        continue

                    move = (
                        transaction
                        .move_id
                        .sudo()
                        .with_company(
                            transaction.company_id
                        )
                    )

                    if not move:
                        _logger.error(
                            (
                                "Transaction SECeF sans facture "
                                "pendant synchronisation"
                                " | transaction_id=%s"
                                " | request_uid=%s"
                            ),
                            transaction.id,
                            transaction.request_uid,
                        )

                        continue

                    _logger.info(
                        (
                            "Synchronisation SECeF"
                            " | transaction_id=%s"
                            " | move_id=%s"
                            " | request_uid=%s"
                            " | central_job_uid=%s"
                        ),
                        transaction.id,
                        move.id,
                        transaction.request_uid,
                        transaction.central_job_uid,
                    )

                    move._sync_secef_transaction(
                        transaction
                    )

                    processed_count += 1

            except Exception:
                _logger.exception(
                    (
                        "Erreur inattendue pendant "
                        "le cron de synchronisation SECeF"
                        " | transaction_id=%s"
                        " | request_uid=%s"
                    ),
                    transaction.id,
                    transaction.request_uid,
                )

        _logger.info(
            (
                "Cron synchronisation SECeF terminé"
                " | sélectionnées=%s"
                " | traitées=%s"
            ),
            selected_count,
            processed_count,
        )

        return True

    # =========================================================
    # Compatibilité temporaire avec l'ancienne architecture
    # Odoo -> Agent
    # =========================================================

    @api.model
    def _claim_next_for_agent(
        self,
        company,
        agent_identifier,
    ):
        """
        Réserve atomiquement la prochaine transaction SECeF.

        Méthode legacy conservée temporairement jusqu'à
        suppression de controllers/secef_api.py.
        """

        self.flush_model([
            "state",
            "company_id",
            "agent_identifier",
            "started_at",
        ])

        # Verrou société afin que deux appels concurrents
        # pour le même Agent ne prennent pas deux Jobs.
        self.env.cr.execute(
            """
            SELECT id
              FROM res_company
             WHERE id = %s
             FOR UPDATE
            """,
            (
                company.id,
            ),
        )

        # Une transaction déjà processing doit toujours
        # être retournée en priorité.
        self.env.cr.execute(
            """
            SELECT id
              FROM sunsoft_secef_transaction
             WHERE state = %s
               AND company_id = %s
               AND agent_identifier = %s
             ORDER BY started_at ASC NULLS FIRST, id ASC
             LIMIT 1
            """,
            (
                "processing",
                company.id,
                agent_identifier,
            ),
        )

        row = (
            self.env.cr.fetchone()
        )

        if row:
            transaction = (
                self.browse(
                    row[0]
                )
                .exists()
            )

            return (
                transaction,
                "processing",
            )

        # Recherche d'une nouvelle transaction en attente.
        self.env.cr.execute(
            """
            SELECT id
              FROM sunsoft_secef_transaction
             WHERE state = %s
               AND company_id = %s
               AND agent_identifier = %s
             ORDER BY create_date ASC, id ASC
             FOR UPDATE SKIP LOCKED
             LIMIT 1
            """,
            (
                "pending",
                company.id,
                agent_identifier,
            ),
        )

        row = (
            self.env.cr.fetchone()
        )

        if not row:
            return (
                self.browse(),
                "none",
            )

        transaction = (
            self.browse(
                row[0]
            )
            .exists()
        )

        if not transaction:
            return (
                self.browse(),
                "none",
            )

        now = (
            fields.Datetime.now()
        )

        transaction.write({
            "state":
                "processing",

            "started_at":
                now,

            "error_message":
                False,
        })

        transaction.move_id.write({
            "secef_state":
                "processing",

            "secef_error_message":
                False,
        })

        return (
            transaction,
            "claimed",
        )

    # =========================================================
    # Wrappers legacy
    # =========================================================

    def _mark_success(
        self,
        response_payload,
    ):
        """
        Compatibilité temporaire avec
        l'ancien contrôleur Odoo -> Agent.
        """

        return self._mark_completed(
            response_payload
        )

    def _mark_error(
        self,
        error_message,
        response_payload=None,
    ):
        """
        Compatibilité temporaire avec
        l'ancien contrôleur Odoo -> Agent.
        """

        return self._mark_failed(
            error_message=error_message,
            response_payload=response_payload,
        )