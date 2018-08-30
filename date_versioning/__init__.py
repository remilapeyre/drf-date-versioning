import copy

from datetime import datetime
from rest_framework.versioning import BaseVersioning
from rest_framework import exceptions, serializers
from django.utils.translation import ugettext_lazy as _
from rest_framework.fields import empty


class DateHeaderVersioning(BaseVersioning):
    invalid_version_message = _('Invalid version in "X-Version" header.')

    def determine_version(self, request, *args, **kwargs):
        try:
            version = request.META['HTTP_X_VERSION']
        except KeyError:
            return datetime.now().strftime(r'%Y-%m-%d')

        try:
            datetime.strptime(version, r'%Y-%m-%d')
            return version
        except ValueError:
            raise exceptions.NotAcceptable(self.invalid_version_message)


class APIChange:
    """This is a no-op API change"""

    def update(self, payload):
        return payload

    def downgrade(self, fields=None, payload=None):
        return payload


class RemoveField(APIChange):
    def __init__(self, name, field, default=None):
        self.name = name
        self.default = default
        self.field = field

    def get_value(self, payload):
        return self.default

    def update(self, payload=None):
        if payload is not None:
            del payload[self.name]
        return payload

    def downgrade(self, fields=None, payload=None):
        if fields is not None:
            fields[self.name] = copy.deepcopy(self.field)
        if payload is not None:
            payload[self.name] = self.get_value(payload)
        return fields, payload


class RenameField:
    def __init__(self, from_name, to):
        self.from_name = from_name
        self.to = to

    def downgrade(self, fields=None, payload=None):
        if fields is not None:
            fields[self.from_name] = copy.deepcopy(fields[self.to])
            del fields[self.to]
        if payload is not None:
            payload[self.from_name] = payload[self.to]
            del payload[self.to]
        return fields, payload

    def update(self, payload=None):
        if payload is not None:
            payload[self.to] = payload[self.from_name]
            del payload[self.from_name]
        return payload


class AddField:
    def __init__(self, name, field, default=None):
        self.name = name
        self.field = field
        self.default = default

    def get_value(self, payload):
        return self.default

    def downgrade(self, fields=None, payload=None):
        if fields is not None:
            del fields[self.name]
        if payload is not None:
            del payload[self.name]
        return fields, payload

    def update(self, payload=None):
        if payload is not None:
            payload[self.name] = self.get_value(payload)
        return payload


class VersionedSerializer(serializers.Serializer):
    @property
    def versions(self):
        if self.version is None:
            return {}

        meta = getattr(self, 'Meta', {})
        versions = getattr(meta, 'versions', {})

        return {
            name: v for name, v in versions.items()
            if name > self.version
        }

    @property
    def version(self):
        try:
            request = self._context['request']
            return request.version
        except (KeyError, AttributeError):
            return None

    @property
    def updated_data(self):
        data = copy.deepcopy(self.data)

        for v in reversed(list(self.versions.values())):
            data = v.update(payload=data)

        return data


    @property
    def data(self):
        if hasattr(self, 'initial_data') and not hasattr(self, '_validated_data'):
            msg = (
                'When a serializer is passed a `data` keyword argument you '
                'must call `.is_valid()` before attempting to access the '
                'serialized `.data` representation.\n'
                'You should either call `.is_valid()` first, '
                'or access `.initial_data` instead.'
            )
            raise AssertionError(msg)

        if not hasattr(self, '_data'):
            if self.instance is not None and not getattr(self, '_errors', None):
                # We instanciate a serializer with the same fields but at the latest
                # version to serialize the instance and the downgrade the result
                data = self.__class__().to_representation(self.instance)
                for v in self.versions.values():
                    if type(v) is tuple:
                        for elem in v:
                            data = elem.downgrade(payload=data)[1]
                    else:
                        data = v.downgrade(payload=data)[1]
                self._data = data
            elif hasattr(self, '_validated_data') and not getattr(self, '_errors', None):
                self._data = self.to_representation(self.validated_data)
            else:
                self._data = self.get_initial()
        return self._data

    def get_fields(self):
        fields = super(VersionedSerializer, self).get_fields()

        for v in self.versions.values():
            if type(v) is tuple:
                for elem in v:
                    fields = elem.downgrade(fields=fields)[0]
            else:
                fields = v.downgrade(fields=fields)[0]

        return fields
