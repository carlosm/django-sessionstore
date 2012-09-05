from django.db import models
import datetime
from django.conf import settings
from djsession.settings import DJSESSION_EXPIRE_DAYS
from django.db import connection, transaction

class TableversionManager(models.Manager):

    def version_table_created(self):
        """Tell if the table is available or need to be created"""
        tables = connection.introspection.table_names()
        abs_name = connection.introspection.table_name_converter(
                self.model._meta.db_table)
        if abs_name in tables:
            return True
        return False

    def get_session_table_name(self, current_version=None):
        if current_version is None:
            if self.version_table_created():
                try:
                    # try to get the latest version number
                    current_version = self.latest().current_version
                except self.model.DoesNotExist:
                    current_version = 1
            else:
                current_version = 1
        previous_version = int(current_version -1)

        # boot up the table name with the default Django table name for
        # the sessions. This will facilite a migration from the old
        # session backend to this one.
        if previous_version == 0:
            previous_table_name="django_session"
        else:
            previous_table_name="django_session_%d" % int(current_version -1)
        current_table_name="django_session_%d" % current_version
        return previous_table_name, current_table_name

    def is_rotation_necessary(self, latest_version):
        now = datetime.datetime.now()
        delta = now - latest_version.latest_rotation
        min_delta = datetime.timedelta(days=DJSESSION_EXPIRE_DAYS)
        if min_delta > delta:
            return False
        return True

    def one_sessions_table_is_empty(self):
        preserve_set = self.get_session_table_name()
        sql = """SELECT session_key FROM %s LIMIT 1;"""
        cursor = connection.cursor()
        cursor.execute(sql % preserve_set[0])
        t1 = cursor.fetchall()
        cursor.execute(sql % preserve_set[1])
        t2 = cursor.fetchall()
        if(not len(t1) or not len(t2)):
            return True
        return False

    def table_exists(self, table_name):
        return table_name in connection.introspection.table_names()

    def rotate_table(self):
        """Rotate the session table, create session tables if necessary."""
        try:
            latest_version = self.latest()
        except self.model.DoesNotExist:
            table_1, table_2 = self.get_session_table_name()
            self.create_session_table(table_1)
            self.create_session_table(table_2)
            latest_version = self.model(current_version=1)
            latest_version.save()
            return latest_version
        if self.one_sessions_table_is_empty():
            return latest_version
        if not self.is_rotation_necessary(latest_version):
            return latest_version
        incresead_version = latest_version.current_version + 1
        latest_version = self.model(current_version=incresead_version)
        latest_version.save()
        table_1, table_2 =  self.get_session_table_name()
        self.create_session_table(table_1)
        self.create_session_table(table_2)
        return latest_version

    def create_session_table(self, table_name="django_session"):
        cursor = connection.cursor()
        sql = """
        CREATE TABLE IF NOT EXISTS %s (
            session_key varchar(40) NOT NULL PRIMARY KEY,
            session_data text NOT NULL,
            expire_date datetime NOT NULL
        );
        """ % table_name
        try:
            cursor.execute(sql)
        except Exception, e:
            print e
        transaction.commit_unless_managed()
        return "Success"

    def cleanup_old_session_table(self):
        """Cleanup old session tables if necessary"""
        cursor = connection.cursor()
        preserve_set = self.get_session_table_name()

        table_empty_msg = """On of the current session table is empty.
Be sure you have restarted your servers properly and waited the
appropriate time for the old sessions to migrate."""
        # test if there is something in both of current tables
        if self.one_sessions_table_is_empty():
            return table_empty_msg
        try:
            latest_version = self.latest()
        except self.model.DoesNotExist:
            return "Nothing to cleanup"
        if latest_version.current_version < 2:
            return "Nothing to cleanup"

        for version in range(1, latest_version.current_version):
            previous, current = self.get_session_table_name(version)
            if previous not in preserve_set and self.table_exists(previous):
                sql = """TRUNCATE TABLE %s;""" % previous
                try:
                    cursor.execute(sql)
                    transaction.commit_unless_managed()
                except:
                    # for sqlite3 and tests.
                    pass
                finally:
                    sql = """DROP TABLE %s;""" % previous
                    cursor.execute(sql)
                    transaction.commit_unless_managed()
        return "Success"