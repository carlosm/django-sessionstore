from cPickle import loads, dumps

from django.contrib.sessions.backends.base import SessionBase, CreateError
from django.conf import settings

import redis

r = redis.Redis(
    host=getattr(settings, 'REDIS_SESSION_HOST', None),
    port=int(getattr(settings, 'REDIS_SESSION_PORT', None)),
    socket_timeout=int(getattr(settings, 'REDIS_SESSION_SOCKET_TIMEOUT', None)),
    db=int(getattr(settings, 'REDIS_SESSION_DB', None)))


class SessionStore(SessionBase):
    """
    A redis-based session store.
    """
    def __init__(self, session_key=None):
        self.redis = r
        # self.redis.connect()
        super(SessionStore, self).__init__(session_key)

    def load(self):
        session_data = self.redis.get(self.session_key)
        if session_data is not None:
            return loads(session_data)
        self.create()
        session_data = self.redis.get(self.session_key)
        if session_data is not None:
            return loads(session_data)

    def create(self, session_data=None):
        while True:
            self._session_key = self._get_new_session_key()
            try:
                self.save(must_create=True, session_data=session_data)
            except CreateError:
                # Would be raised if the key wasn't unique
                continue
            self.modified = True
            return

    def save(self, must_create=False, session_data=None):
        # This is needed because if not redis will save a None object
        if self.session_key is None:
            self._session_key =  self._get_new_session_key()

        if not session_data:
            session_data = self._get_session(no_load=must_create)

        # self.redis.execute_command('MULTI')
        # Removed preserve=must_create: should always be saved
        result = self.redis.set(
            self.session_key, dumps(session_data))

        if result == 0:
            raise CreateError

        if (session_data.get('_auth_user_id', False)):
            self.redis.execute_command('EXPIRE', self.session_key,
                getattr(settings, 'REDIS_AUTHENTICATED_SESSION_KEY_TTL',
                60 * 60 * 24 * 30)) # 30 days
        else:
            self.redis.execute_command('EXPIRE', self.session_key,
                getattr(settings, 'REDIS_ANONYMOUS_SESSION_KEY_TTL',
                60 * 60 * 24 * 2)) # 2 days

        #self.redis.execute_command('EXEC')

    def exists(self, session_key):
        if self.redis.exists(session_key):
            return True
        return False

    def delete(self, session_key=None):
        if session_key is None:
            if self._session_key is None:
                return
            session_key = self._session_key
        self.redis.delete(session_key)

