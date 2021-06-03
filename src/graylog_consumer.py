import json
import logging
from ops.charm import CharmEvents
from ops.framework import StoredState, EventSource, EventBase
from ops.relation import ConsumerBase

logger = logging.getLogger(__name__)


class GraylogConsumer(ConsumerBase):
    def __init__(self, charm, name, consumes, multi=False):
        super().__init__(charm, name, consumes, multi=False)

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

    @property
    def relation(self):
        if self._stored.relation_id:
            return self.model.get_relation(self.name, self._stored.relation_id)
        else:
            return None

    def _on_relation_joined(self, event):
        event.relation.data[self.charm.unit].public_address = str(
            self.model.get_binding(event.relation).network.ingress_address
        )

    # def _on_relation_changed(self, event):

    # def _on_relation_broken(self, event):

    def get_cluster_info(self):
        relation = self.relation
        if not relation.data[relation.app].ready:
            return None
        port = relation.data[relation.app].graylog_port

        addrs = []
        for unit in relation.units:
            if relation.data[unit].public_address:
                addrs.append(
                    "http://{}:{}/".format(relation.data[unit].public_address, port)
                )

        return addrs
