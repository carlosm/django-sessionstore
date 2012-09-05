import base64
import cPickle as pickle

from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.contrib.sessions.models import SessionManager
from djsession.managers import TableversionManager
from django.db.models import signals
from django.core.management.color import no_style
from django.utils.hashcompat import md5_constructor
from django.conf import settings

class Tableversion(models.Model):
    """
    This model is used to keep the state of the table rotation revisions.
    The greatest current_version is the official used table.
    """
    current_version = models.IntegerField(_(u"version"), default=1)
    latest_rotation = models.DateTimeField(_(u"latest rotation"),
        auto_now_add=True)

    objects = TableversionManager()

    class Meta:
        get_latest_by = ('current_version')
        verbose_name = _("table version")
        verbose_name_plural = _(u"table versions")

    def __unicode__(self):
        return "django_session_%d" % self.current_version

# set up session table name
PREVIOUS_TABLE_NAME, CURRENT_TABLE_NAME = Tableversion.objects.get_session_table_name()

class Session(models.Model):
    """Replication of the session Model."""
    session_key = models.CharField(_('session key'), max_length=40,
                                   primary_key=True)
    session_data = models.TextField(_('session data'))
    expire_date = models.DateTimeField(_('expire date'))
    # we inherit the session manager... No sure it's
    # a good idea to rely on this code.
    objects = SessionManager()

    # SHAME, copy and paste from session model...
    # I don't remember why but I believe inheritance doesn't work
    # as I wanted so I did it this way.
    def get_decoded(self):
        encoded_data = base64.decodestring(self.session_data)
        pickled, tamper_check = encoded_data[:-32], encoded_data[-32:]
        if md5_constructor(pickled + settings.SECRET_KEY).hexdigest() != tamper_check:
            from django.core.exceptions import SuspiciousOperation
            raise SuspiciousOperation, "User tampered with session cookie."
        try:
            return pickle.loads(pickled)
        # Unpickling can cause a variety of exceptions. If something happens,
        # just return an empty dictionary (an empty session).
        except:
            return {}

    class Meta:
        abstract = True

#if ('django.contrib.sessions' in settings.INSTALLED_APPS):
#    raise ValueError("""django.contrib.sessions cannot be used with djsession.
#You have to choose.""")

class PrevSession(Session):

    class Meta:
        db_table = PREVIOUS_TABLE_NAME

class CurrentSession(Session):

    class Meta:
        db_table = CURRENT_TABLE_NAME

