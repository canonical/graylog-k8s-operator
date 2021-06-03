import json
import logging
from ops.charm import CharmEvents
from ops.framework import StoredState, EventSource, EventBase
from ops.relation import ProviderBase

logger = logging.getLogger(__name__)


class GraylogProvider(ProviderBase):
    def __init__(self, charm, name, service, version=None):
        super().__init__(charm, name, service, version)

        self.charm = charm

        self.framework.observe(
            self.charm.on[self.name].relation_joined, self._on_relation_joined
        )
        self.framework.observe(
            self.charm.on[self.name].relation_changed, self._on_relation_changed
        )
        self.framework.observe(
            self.charm.on[self.name].relation_broken, self._on_relation_broken
        )

    @property
    def unit(self):
        return self.charm.unit

    def _on_relation_joined(self, event):
        event.relation.data[self.unit].public_address = str(
            self.model.get_binding(event.relation).network.ingress_address
        )

    def set_port(self, port):
        if self.model.unit.is_leader():
            logger.debug("Notifying Consumer : %s", data)
            for rel in self.framework.model.relations[self.name]:
                rel.data[self.model.app]["graylog_port"] = port

    # def _on_relation_changed(self, event):

    # def _on_relation_broken(self, event):
