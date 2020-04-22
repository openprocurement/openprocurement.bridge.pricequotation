# -*- coding: utf-8 -*-
import logging

from openprocurement.bridge.basic.handlers import HandlerTemplate
from openprocurement.bridge.pricequotation.utils import journal_context
from retrying import retry
from tooz import coordination

from openprocurement_client.exceptions import RequestFailed, ResourceGone, ResourceNotFound, UnprocessableEntity
from openprocurement_client.resources.ecatalogues import ECataloguesClient

config = {
    "worker_type": "contracting",
    "client_inc_step_timeout": 0.1,
    "client_dec_step_timeout": 0.02,
    "drop_threshold_client_cookies": 2,
    "worker_sleep": 5,
    "retry_default_timeout": 3,
    "retries_count": 10,
    "queue_timeout": 3,
    "bulk_save_limit": 100,
    "bulk_save_interval": 3,
    "resources_api_token": "",
    "resources_api_version": "",
    "input_resources_api_server": "",
    "input_public_resources_api_server": "",
    "input_resource": "tenders",
    "output_resources_api_server": "",
    "output_public_resources_api_server": "",
    "output_resource": "agreements",
    "handler_cfaua": {
        "resources_api_token": "",
        "output_resources_api_token": "agreement_token",
        "resources_api_version": "",
        "input_resources_api_token": "tender_token",
        "input_resources_api_server": "",
        "input_public_resources_api_server": "",
        "input_resource": "tenders",
        "output_resources_api_server": "",
        "output_public_resources_api_server": "",
        "output_resource": "agreements"
    }
}

CONFIG_MAPPING = {
    "input_resources_api_token": "resources_api_token",
    "output_resources_api_token": "resources_api_token",
    "resources_api_version": "resources_api_version",
    "input_resources_api_server": "resources_api_server",
    "input_public_resources_api_server": "public_resources_api_server",
    "input_resource": "resource",
    "output_resources_api_server": "resources_api_server",
    "output_public_resources_api_server": "public_resources_api_server"
}


logger = logging.getLogger(__name__)


class PQSecondPhaseCommit(HandlerTemplate):

    def __init__(self, config, cache_db):
        logger.info("Init priceQuotation second phase commit handler.")
        self.handler_name = "handler_priceQuotationBot"
        super(PQSecondPhaseCommit, self).__init__(config, cache_db)
        coordinator_config = config.get("coordinator_config", {})
        self.coordinator = coordination.get_coordinator(coordinator_config.get("connection_url", "redis://"),
                                                        coordinator_config.get("coordinator_name", "bridge"))
        self.coordinator.start(start_heart=True)

    def initialize_clients(self):
        self.tender_client = self.create_api_client()
        self.catalogues_client = ECataloguesClient(host_url=self.handler_config.get("catalogue_api_server"),
                                                   api_version=self.handler_config.get("catalogue_api_version"),
                                                   user_agent="priceQuotationBot")

    def decline_resource(self, resource):
        status = "draft.unsuccessful"
        self.tender_client.patch_resource_item(resource["id"], {"data": {"status": status}})
        logger.info("Switch tender {} to `{}`".format(resource["id"], status),
                    extra=journal_context({"MESSAGE_ID": "tender_switched"},
                                          params={"TENDER_ID": resource["id"], "STATUS": status}))

    def process_resource(self, resource):
        status = "active.tendering"
        lock = self.coordinator.get_lock(resource["id"])
        if lock._client.exists(lock._name):
            logger.info(
                "Tender {} processing by another worker.".format(resource["id"]),
                extra=journal_context({"MESSAGE_ID": "tender_already_in_process"},
                                      params={"TENDER_ID": resource["id"]}))
            return
        with lock:
            try:
                profile = self.catalogues_client.profiles.get_profile(resource["profile"])
            except ResourceNotFound:
                logger.error("Pofile {} not found in catalouges.".format(resource["profile"]))
                self.decline_resource(resource)
                return

            try:
                suppliers = self.catalogues_client.categories.get_category_suppliers(profile.data.relatedCategory)
                if len(suppliers.data) == 0:
                    logger.error(
                        "This category {} doesn`t have qualified suppliers".format(profile.data.relatedCategory)
                    )
                    self.decline_resource(resource)
                    return
            except ResourceNotFound:
                logger.error("Category {} not found.".format(profile.data.relatedCategory))
                self.decline_resource(resource)
                return

            try:
                items = []
                for item in resource["items"]:
                    item.update({"unit": profile.data.unit,
                                 "classification": profile.data.classification,
                                 "value": profile.data.value})
                    items.append(item)
                shortlisted_firms = [sf for sf in suppliers.data if sf.status == 'active']
                data = {
                    "data": {
                        "criteria": profile.data.criteria,
                        "items": items,
                        "shortlistedFirms": shortlisted_firms,
                        "status": status
                    }
                }
                self.tender_client.patch_resource_item(resource["id"], data)
                logger.info("Successful switch tender {} to `{}`".format(resource["id"], status),
                            extra=journal_context({"MESSAGE_ID": "tender_switched"},
                                                  params={"TENDER_ID": resource["id"], "STATUS": status}))
            except ResourceNotFound:
                logger.critical("Tender {} not found".format(resource["id"]))
            except UnprocessableEntity as e:
                logger.critical("Fail patch tender {} with error: {}".format(resource["id"], e.message))
                self.tender_client.patch_resource_item(resource["id"], {"data": {"status": "draft.unsuccessful"}})
                logger.info("Switch tender {} to draft.unsuccessful".format(resource["id"]))
        self._put_resource_in_cache(resource)
