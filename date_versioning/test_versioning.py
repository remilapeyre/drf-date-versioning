import pytest
import rest_framework

from datetime import datetime
from collections import OrderedDict
from textwrap import dedent
from django.db import models
from rest_framework import serializers
from rest_framework.decorators import APIView
from rest_framework.response import Response
from . import (DateHeaderVersioning, APIChange, RemoveField, RenameField, AddField,
               VersionedSerializer)


class SimpleSerializer(serializers.Serializer):
    firstname = serializers.CharField()
    lastname = serializers.CharField()


class TestDetermineVersion:
    def test_no_versioning(self, rf):
        request = rf.get('/')
        assert DateHeaderVersioning().determine_version(request) == datetime.now().strftime(r'%Y-%m-%d')

    def test_invalid_version(self, rf):
        request = rf.get('/', **{'HTTP_X_VERSION': 'this is invalid'})
        with pytest.raises(rest_framework.exceptions.NotAcceptable):
            DateHeaderVersioning().determine_version(request)

    def test_valid_version(self, rf):
        request = rf.get('/', **{'HTTP_X_VERSION': '2018-08-03'})
        assert DateHeaderVersioning().determine_version(request) == '2018-08-03'


class TestOperations:
    chewby = {
      "name": "Chewbacca",
      "birthYear": "200BBY",
      "eyeColor": "blue",
      "gender": "male",
      "hairColor": "brown",
      "height": 228,
      "mass": 112,
      "homeworld": {
        "name": "Kashyyyk"
      }
    }

    def test_no_op(self):
        change = APIChange()
        previous_payload = change.downgrade(payload=self.chewby)
        assert previous_payload == self.chewby
        assert change.update(previous_payload) == self.chewby

    def test_remove_field(self):
        change = RemoveField('hairStyle', serializers.CharField())
        previous_payload = change.downgrade(payload=self.chewby)[1]
        assert previous_payload == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "hairStyle": None,
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }

        previous_payload['hairStyle'] = 'fluffy'
        assert change.update(payload=previous_payload) == self.chewby

        serializer = SimpleSerializer()
        fields = change.downgrade(fields=serializer._declared_fields)[0]
        assert list(fields) == ['firstname', 'lastname', 'hairStyle']

    def test_rename_field(self):
        change = RenameField('origin', 'homeworld')
        previous_payload = change.downgrade(payload=self.chewby)[1]
        assert 'homeworld' not in previous_payload
        assert previous_payload == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "height": 228,
            "mass": 112,
            "origin": {
                "name": "Kashyyyk"
            }
        }

        assert change.update(payload=previous_payload) == self.chewby

    def test_add_field(self):
        change = AddField('hairStyle', serializers.CharField())
        next_payload = change.update(payload=self.chewby)
        assert next_payload == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "hairStyle": None,
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }

        assert change.downgrade(payload=next_payload)[1] == self.chewby


instance = {
        "name": "Chewbacca",
        "birthYear": "200BBY",
        "eyeColor": "blue",
        "gender": "male",
        "hairColor": "brown",
        "height": 228,
        "mass": 112,
        "homeworld": {
            "name": "Kashyyyk"
        }
    }

class HomeworldSerializer(VersionedSerializer):
    name = serializers.CharField()


class PersonSerializer(VersionedSerializer):
    name = serializers.CharField()
    birthYear = serializers.CharField()
    eyeColor = serializers.CharField()
    gender = serializers.CharField()
    hairColor = serializers.CharField()
    height = serializers.IntegerField()
    mass = serializers.IntegerField()
    homeworld = HomeworldSerializer()

    class Meta:
        versions = {
            '2018-08-02': RemoveField('hairStyle', serializers.CharField()),
            '2018-07-29': RenameField('iColor', 'eyeColor'),
            '2018-07-27': AddField('gender', serializers.CharField(), default='male')
        }


class VersionView(APIView):
    versioning_class = DateHeaderVersioning

    def get(self, request, *args, **kwargs):
        return Response({'version': request.version})


class TestVersionedSerializer:
    def test_without_context(self):
        assert repr(PersonSerializer()) == dedent("""\
        PersonSerializer():
            name = CharField()
            birthYear = CharField()
            eyeColor = CharField()
            gender = CharField()
            hairColor = CharField()
            height = IntegerField()
            mass = IntegerField()
            homeworld = HomeworldSerializer():
                name = CharField()""")

    def test_without_version(self, rf):
        request = rf.get('/')
        assert repr(PersonSerializer(context={'request': request})) == dedent("""\
        PersonSerializer(context={'request': <WSGIRequest: GET '/'>}):
            name = CharField()
            birthYear = CharField()
            eyeColor = CharField()
            gender = CharField()
            hairColor = CharField()
            height = IntegerField()
            mass = IntegerField()
            homeworld = HomeworldSerializer():
                name = CharField()""")

        serializer_instance = PersonSerializer(instance=instance)
        serializer_data = PersonSerializer(data=instance)
        serializer_data.is_valid(raise_exception=True)
        assert serializer_instance.data == serializer_data.validated_data

    def test_with_version(self, rf):
        request = rf.get('/')
        request.version = '2018-08-01'
        assert repr(PersonSerializer(context={'request': request})) == dedent("""\
        PersonSerializer(context={'request': <WSGIRequest: GET '/'>}):
            name = CharField()
            birthYear = CharField()
            eyeColor = CharField()
            gender = CharField()
            hairColor = CharField()
            height = IntegerField()
            mass = IntegerField()
            homeworld = HomeworldSerializer():
                name = CharField()
            hairStyle = CharField()""")

    def test_with_version_and_data(self, rf):
        request = rf.get('/')
        request.version = '2018-08-01'
        data = {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "hairStyle": "fluffy",
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }
        serializer_data = PersonSerializer(
            data=data,
            context={'request': request}
        )
        serializer_data.is_valid(raise_exception=True)
        assert serializer_data.data['hairStyle'] == 'fluffy'
        assert serializer_data.updated_data == instance
        assert serializer_data.data != instance

        serializer_instance = PersonSerializer(
            instance=instance,
            context={'request': request}
        )
        assert serializer_instance.data['hairStyle'] == None

    def test_rename_field(self, rf):
        request = rf.get('/')
        request.version = '2018-07-29'
        serializer = PersonSerializer(
            data={
                "name": "Chewbacca",
                "birthYear": "200BBY",
                "eyeColor": "blue",
                "gender": "male",
                "hairColor": "brown",
                "hairStyle": "fluffy",
                "height": 228,
                "mass": 112,
                "homeworld": {
                    "name": "Kashyyyk"
                }
            },
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        assert serializer.data == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "hairStyle": "fluffy",
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }
        assert serializer.updated_data == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }

    def test_add_field(self, rf):
        request = rf.get('/')
        request.version = '2018-07-26'
        serializer = PersonSerializer(
            data={
                "name": "Chewbacca",
                "birthYear": "200BBY",
                "iColor": "blue",
                "hairColor": "brown",
                "hairStyle": "fluffy",
                "height": 228,
                "mass": 112,
                "homeworld": {
                    "name": "Kashyyyk"
                }
            },
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        assert serializer.data == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "iColor": "blue",
            "hairColor": "brown",
            "hairStyle": "fluffy",
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }
        assert serializer.updated_data == {
            "name": "Chewbacca",
            "birthYear": "200BBY",
            "eyeColor": "blue",
            "gender": "male",
            "hairColor": "brown",
            "height": 228,
            "mass": 112,
            "homeworld": {
                "name": "Kashyyyk"
            }
        }


class Homeworld(models.Model):
    name = models.CharField(max_length=20)


class Person(models.Model):
    name = models.CharField(max_length=20)
    birthYear = models.CharField(max_length=4)
    eyeColor = models.CharField(max_length=10)
    gender = models.CharField(max_length=6)
    hairColor = models.CharField(max_length=12)
    height = models.IntegerField()
    mass = models.IntegerField()
    homeworld = models.ForeignKey(Homeworld, on_delete=models.CASCADE)


class TestInstance:
    @pytest.mark.django_db
    def test_without_context(self):
        kashyyyk = Homeworld(name='Kashyyyk')
        chewby = Person(
            name="Chewbacca",
            birthYear="200BBY",
            eyeColor="blue",
            gender="male",
            hairColor="brown",
            height=228,
            mass=112,
            homeworld=kashyyyk
        )
        serializer = PersonSerializer(instance=chewby)
        assert serializer.data == {
            'name': 'Chewbacca',
            'birthYear': '200BBY',
            'eyeColor': 'blue',
            'gender': 'male',
            'hairColor': 'brown',
            'height': 228,
            'mass': 112,
            'homeworld': {
                'name': 'Kashyyyk'
            }
        }

        serializer = PersonSerializer(
            instance=chewby,
            data={
                "name": "Chewbacca",
                "birthYear": "200BBY",
                "eyeColor": "blue",
                "gender": "male",
                "hairColor": "brown",
                "height": 228,
                "mass": 112,
                "homeworld": {
                    "name": "Kashyyyk"
                }
            }
        )
        assert serializer.is_valid(raise_exception=True)

    # def test_with_context(self, rf):
    #     request = rf.get('/')
    #     request.version = '2018-07-26'

    #     kashyyyk = Homeworld(name='Kashyyyk')
    #     chewby = Person(
    #         name="Chewbacca",
    #         birthYear="200BBY",
    #         eyeColor="blue",
    #         gender="male",
    #         hairColor="brown",
    #         height=228,
    #         mass=112,
    #         homeworld=kashyyyk
    #     )
    #     serializer = PersonSerializer(
    #         instance=chewby,
    #         context={'request': request}
    #     )
    #     serializer.data == {
    #         'name': 'Chewbacca',
    #         'birthYear': '200BBY',
    #         'eyeColor': 'blue',
    #         'gender': 'male',
    #         'hairColor': 'brown',
    #         'height': 228,
    #         'mass': 112,
    #         'homeworld': {
    #             'name': 'Kashyyyk'
    #         }
    #     }
