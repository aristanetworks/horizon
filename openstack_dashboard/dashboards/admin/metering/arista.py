# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from django.utils.datastructures import SortedDict
from django.utils.translation import ugettext_lazy as _

from horizon import exceptions
from horizon import tables
from openstack_dashboard.api import ceilometer

import openstack_dashboard.dashboards.admin.metering.views as ViewsBase
import logging
LOG = logging.getLogger(__name__)

class AristaDataTable(tables.DataTable):
    iface = tables.Column('iface', verbose_name=_('Interface'))
    txPackets = tables.Column('txPackets', verbose_name=_('Sent Packets'))
    rxPackets = tables.Column('rxPackets', verbose_name=_('Received Packets'))

    def get_object_id(self, datum):
        return datum['id']

    @property
    def name(self):
        return self.title

    def __unicode__(self):
        return self.title

class AristaReportView(tables.MultiTableView):
    template_name = 'admin/metering/arista.html'

    def get_tables(self):
        if self._tables:
            return self._tables
        switches = load_arista_data(self.request)
        table_instances = []
        for switch in switches:
            table = AristaDataTable(self.request,
                                    data=switches[switch])
            table.title = switch
            t = (table.title, table)
            table_instances.append(t)

        self._tables = SortedDict(table_instances)
        return self._tables

    def handle_table(self, table):
        return None

    def get_context_data(self, **kwargs):
        context = {'tables': self.get_tables().values()}
        return context

def load_arista_data(request):
    date_from, date_to = ViewsBase._calc_date_args(request.GET.get('date_from'),
                                                   request.GET.get('date_to'),
                                                   request.GET.get('date_options', 7))
    meters = ceilometer.Meters(request)
    switch_rows = {}

    query = []
    if date_from:
        query += [{'field': 'timestamp',
                   'op': 'ge',
                   'value': date_from}]
    if date_to:
        query += [{'field': 'timestamp',
                   'op': 'le',
                   'value': date_to}]

    switches = {}
    for meter in meters.list_sdn():
        samples = ceilometer.sample_list(request, meter.name, query=query)

        # Only show meters with samples
        if not samples:
            continue

        for sample in samples:
            # Ignore non-arista stuff or stuff without iface.
            if ('driver' not in sample.resource_metadata or
                sample.resource_metadata['driver'] != 'arista' or
                'iface' not in sample.resource_metadata):
                continue

            iface = sample.resource_metadata['iface']
            switch = sample.resource_id

            if switch not in switches:
                switches[switch] = {}

            if iface not in switches[switch]:
                switches[switch][iface] = {'iface': iface,
                                           'switch.port.receive.packets': 0,
                                           'switch.port.transmit.packets': 0}

            # Ugly hack until they implement sorting by dates or something. meh.
            # Select the largest sample value since all cumulative.
            if (meter.name in switches[switch][iface]
                and switches[switch][iface][meter.name] < sample.counter_volume):
                switches[switch][iface][meter.name] = sample.counter_volume
    
    # Convert to a format which DataTable can understand.
    for switch in switches:
        rows = []
        for iface in switches[switch]:
            iface_stats = switches[switch][iface]
            row = {'id': switch + iface,
                   'iface': iface,
                   'rxPackets': iface_stats['switch.port.receive.packets'],
                   'txPackets': iface_stats['switch.port.transmit.packets']}
            rows.append(row)

        switches[switch] = rows

    return switches

