#  Copyright (c) 2020 JD Williams
#
#  This file is part of Firefly, a Python SOA framework built by JD Williams. Firefly is free software; you can
#  redistribute it and/or modify it under the terms of the GNU General Public License as published by the
#  Free Software Foundation; either version 3 of the License, or (at your option) any later version.
#
#  Firefly is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#  implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
#  Public License for more details. You should have received a copy of the GNU Lesser General Public
#  License along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#  You should have received a copy of the GNU General Public License along with Firefly. If not, see
#  <http://www.gnu.org/licenses/>.

from __future__ import annotations

from datetime import datetime
from time import sleep

from mailchimp3 import MailChimp
import firefly as ff

from .mailchimp_client_factory import MailchimpClientFactory
from ... import domain as domain


class MailchimpEmailService(domain.EmailService):
    _client_factory: MailchimpClientFactory = None
    _mutex: ff.Mutex = None

    def add_contact_to_audience(self, contact: domain.Contact, audience: domain.Audience, meta: dict = None,
                                tags: list = None):
        client = self._get_client(audience)
        payload = {
            'email_address': contact.email,
            'status': 'subscribed',
        }

        if tags is not None and len(tags) > 0:
            payload['tags'] = tags

        try:
            payload['merge_fields'] = self._get_merge_fields(client, audience, meta)
            payload['skip_merge_validation'] = True
        except (TypeError, AttributeError):
            pass

        member = client.lists.members.create(audience.meta['mc_id'], payload)
        audience.get_member_by_contact(contact).meta['mc_id'] = member['id']

    def add_tag_to_audience_member(self, tag: str, audience: domain.Audience, contact: domain.Contact):
        client = self._get_client(audience)
        client.lists.members.tags.update(
            audience.meta['mc_id'],
            audience.get_member_by_contact(contact).meta['mc_id'],
            {'tags': [{'name': tag, 'status': 'active'}]}
        )

    def remove_tag_from_audience_member(self, tag: str, audience: domain.Audience, contact: domain.Contact):
        client = self._get_client(audience)
        client.lists.members.tags.update(
            audience.meta['mc_id'],
            audience.get_member_by_contact(contact).meta['mc_id'],
            {'tags': [{'name': tag, 'status': 'inactive'}]}
        )

    def _get_merge_fields(self, client: MailChimp, audience: domain.Audience, meta: dict, create: bool = True):
        merge_fields = self._get_mc_merge_fields(client, audience)

        if create is True:
            names = list(merge_fields.keys())
            for k, v in meta.items():
                if k not in names:
                    attempts = 0
                    while True:
                        try:
                            attempts += 1
                            with self._mutex(f'mailchimp-tags-{audience.id}', timeout=0):
                                merge_fields = self._get_mc_merge_fields(client, audience)
                                names = list(merge_fields.keys())
                                if k not in names:
                                    merge_fields[k] = self._create_merge_field(client, audience, k, v)
                            break
                        except TimeoutError:
                            if attempts >= 5:
                                break
                            sleep(2)

        return {v: meta[k] for k, v in merge_fields.items() if (k in meta and meta[k] is not None)}

    @staticmethod
    def _get_mc_merge_fields(client: MailChimp, audience: domain.Audience):
        return {
            x['name']: x['tag'] for x in client.lists.merge_fields.all(audience.meta['mc_id'])['merge_fields']
        }

    @staticmethod
    def _create_merge_field(client: MailChimp, audience: domain.Audience, name: str, hint: any):
        type_ = 'text'

        if isinstance(hint, (int, float)):
            type_ = 'number'

        try:
            datetime.fromisoformat(hint)
            type_ = 'date'
        except (ValueError, TypeError):
            pass

        return client.lists.merge_fields.create(audience.meta['mc_id'], {
                'default_value': '',
                'help_text': '',
                'name': name,
                'public': True,
                'required': False,
                'type': type_
        })['tag']

    def _get_client(self, audience: domain.Audience):
        return self._client_factory(audience.meta['mc_api_key'])
