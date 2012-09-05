# -*- coding: utf-8 -*-
"""Django session table rotation tests."""
import django
import re
import datetime
from django.test import TestCase
from django.test.client import Client
from django.conf import settings
from django import db
from django.db import connection, transaction
from djsession.backends.db import SessionStore
from djsession.models import CurrentSession, PrevSession
from djsession.models import Tableversion
from djsession.settings import DJSESSION_EXPIRE_DAYS

tv = Tableversion.objects

class DJsessionTestCase(TestCase):

    def test_01_simple(self):
        """Basic tests."""
        settings.DEBUG = True
        session = SessionStore()
        self.assertFalse(session.exists('0360e53e4a8e381de3389b11455facd7'))
        django1 = db.connection.queries[0]
        # there is an issue there with the test if you have already some data...
        self.assertTrue('django_session_1' in django1['sql'])
        django0 = db.connection.queries[1]
        self.assertTrue('django_session' in django0['sql'])
        db.reset_queries()
        
        session['toto'] = 'toto'
        session.save()
        db.reset_queries()
        
        session_key = session.session_key
        session = SessionStore(session_key=session_key)
        self.assertEqual(session['toto'], 'toto')
        self.assertEqual(len(db.connection.queries), 1)

        session.delete()

        session = SessionStore(session_key=session_key)
        self.assertFalse('toto' in session)
        
        settings.DEBUG = False

    def test_02_session_migration(self):
        """Test that a session is migrated from an old table
        to the current table properly."""

        settings.DEBUG = True

        # save a session in the previous table
        session = SessionStore(
            previous=CurrentSession,
            current=PrevSession
        )
        session['tata'] = 'tata'
        session.save()
        session_key = session.session_key

        db.reset_queries()
        session = SessionStore(session_key=session_key)
        self.assertEqual(session['tata'], 'tata')
        self.assertEqual(len(db.connection.queries), 4)

        # this time, because the session is in the last table,
        # we have only one request
        db.reset_queries()
        session = SessionStore(session_key=session_key)
        self.assertEqual(session['tata'], 'tata')
        self.assertEqual(len(db.connection.queries), 1)

        settings.DEBUG = False

    def test_03_table_name(self):
        """Test that the table name is properly set up."""

        self.assertEqual(tv.get_session_table_name(),
            ('django_session', 'django_session_1'))

        Tableversion(current_version=2).save()

        self.assertEqual(tv.get_session_table_name(),
            ('django_session_1', 'django_session_2'))

        Tableversion(current_version=3).save()

        self.assertEqual(tv.get_session_table_name(),
            ('django_session_2', 'django_session_3'))
        
        settings.DEBUG = False


    def test_04_rotate_table(self):
        """Test that the rotation functions works."""
        cursor = connection.cursor()
        introspection = connection.introspection
        today = connection.ops.value_to_db_date(datetime.datetime.now())

        self.assertEqual(tv.rotate_table().current_version, 1)
        self.assertEqual(tv.rotate_table().current_version, 1)

        self.assertEqual(tv.get_session_table_name(),
            ('django_session', 'django_session_1'))

        delta = datetime.timedelta(days=DJSESSION_EXPIRE_DAYS + 1)
        lastest = tv.latest()
        lastest.latest_rotation = datetime.datetime.now() - delta
        lastest.save()

        # without data in session the rotation should be denied
        self.assertEqual(tv.rotate_table().current_version, 1)
        sql = """INSERT INTO django_session_1 VALUES ('a', 'a', %s);"""
        cursor.execute(sql, [today])
        sql = """INSERT INTO django_session VALUES ('a', 'a', %s);"""
        cursor.execute(sql, [today])

        self.assertEqual(tv.rotate_table().current_version, 2)

        self.assertEqual(tv.get_session_table_name(),
            ('django_session_1', 'django_session_2'))

        self.assertTrue("django_session_2" in introspection.table_names())
        self.assertTrue("django_session" in introspection.table_names())

        # should refuse to cleanup because django_session_2 is empty
        self.assertNotEqual(tv.cleanup_old_session_table(),
            "Success")

        # let's insert something in current table
        sql = """INSERT INTO django_session_2 VALUES ('a', 'a', %s);"""
        cursor.execute(sql, [today])
            
        self.assertEqual(tv.cleanup_old_session_table(),
            "Success")

        # django_session should have been deleted
        self.assertTrue("django_session" not in introspection.table_names())

        # then we need to put it back for other applications
        # tests that are coming
        tv.create_session_table(table_name="django_session")
        self.assertTrue("django_session" in introspection.table_names())
        
