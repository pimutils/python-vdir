import os
import sys
import errno
import uuid

from atomicwrites import atomic_write

__version__ = '0.1.0'

PY2 = sys.version_info[0] == 2


def to_unicode(x, encoding='ascii'):
    if not isinstance(x, text_type):
        return x.decode(encoding)
    return x


def to_bytes(x, encoding='ascii'):
    if not isinstance(x, bytes):
        return x.encode(encoding)
    return x

if PY2:
    text_type = unicode  # noqa
    to_native = to_bytes

else:
    text_type = str  # noqa
    to_native = to_unicode


SAFE_UID_CHARS = ('abcdefghijklmnopqrstuvwxyz'
                  'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
                  '0123456789_.-+')


def _href_safe(ident, safe=SAFE_UID_CHARS):
    return not bool(set(ident) - set(safe))


def _generate_href(ident=None, safe=SAFE_UID_CHARS):
    if not ident or not _href_safe(ident, safe):
        return to_unicode(uuid.uuid4().hex)
    else:
        return ident


class VdirError(IOError):
    pass


class NotFoundError(VdirError):
    pass


class WrongEtagError(VdirError):
    pass


class AlreadyExists(VdirError):
    pass


class Item(object):
    def __init__(self, raw):
        assert isinstance(raw, text_type)
        self.raw = raw


class Vdir(object):
    item_class = Item
    default_mode = 0o750

    def __init__(self, path, fileext, encoding='utf-8'):
        self.path = path
        self.encoding = encoding
        self.fileext = fileext

    @staticmethod
    def _get_etag_from_file(fpath):
        '''Get mtime-based etag from a filepath.'''
        stat = os.stat(fpath)
        mtime = getattr(stat, 'st_mtime_ns', None)
        if mtime is None:
            mtime = stat.st_mtime
        return '{:.9f}'.format(mtime)

    @classmethod
    def discover(cls, path, **kwargs):
        try:
            collections = os.listdir(path)
        except OSError as e:
            if e.errno != errno.ENOENT:
                raise
            return

        for collection in collections:
            collection_path = os.path.join(path, collection)
            if os.path.isdir(collection_path):
                yield cls(path=collection_path, **kwargs)

    @classmethod
    def create(cls, collection_name, **kwargs):
        kwargs = dict(kwargs)
        path = kwargs['path']

        path = os.path.join(path, collection_name)
        if not os.path.exists(path):
            os.makedirs(path, mode=cls.default_mode)
        elif not os.path.isdir(path):
            raise IOError('{} is not a directory.'.format(repr(path)))

        kwargs['path'] = path
        return kwargs

    def _get_filepath(self, href):
        return os.path.join(self.path, href)

    def _get_href(self, ident):
        return _generate_href(ident) + self.fileext

    def list(self):
        for fname in os.listdir(self.path):
            fpath = os.path.join(self.path, fname)
            if os.path.isfile(fpath) and fname.endswith(self.fileext):
                yield fname, self._get_etag_from_file(fpath)

    def get(self, href):
        fpath = self._get_filepath(href)
        try:
            with open(fpath, 'rb') as f:
                return (Item(f.read().decode(self.encoding)),
                        self._get_etag_from_file(fpath))
        except IOError as e:
            if e.errno == errno.ENOENT:
                raise NotFoundError(href)
            else:
                raise

    def upload(self, item):
        if not isinstance(item.raw, text_type):
            raise TypeError('item.raw must be a unicode string.')

        try:
            href = self._get_href(item.ident)
            fpath, etag = self._upload_impl(item, href)
        except OSError as e:
            if e.errno in (
                errno.ENAMETOOLONG,  # Unix
                errno.ENOENT  # Windows
            ):
                # random href instead of UID-based
                href = self._get_href(None)
                fpath, etag = self._upload_impl(item, href)
            else:
                raise

        if self.post_hook:
            self._run_post_hook(fpath)
        return href, etag

    def _upload_impl(self, item, href):
        fpath = self._get_filepath(href)
        try:
            with atomic_write(fpath, mode='wb', overwrite=False) as f:
                f.write(item.raw.encode(self.encoding))
                return fpath, self._get_etag_from_file(f.name)
        except OSError as e:
            if e.errno == errno.EEXIST:
                raise AlreadyExists(existing_href=href)
            else:
                raise

    def update(self, href, item, etag):
        fpath = self._get_filepath(href)
        if not os.path.exists(fpath):
            raise NotFoundError(item.uid)
        actual_etag = self._get_etag_from_file(fpath)
        if etag != actual_etag:
            raise WrongEtagError(etag, actual_etag)

        if not isinstance(item.raw, text_type):
            raise TypeError('item.raw must be a unicode string.')

        with atomic_write(fpath, mode='wb', overwrite=True) as f:
            f.write(item.raw.encode(self.encoding))
            etag = self._get_etag_from_fileobject(f)

        return etag

    def delete(self, href, etag):
        fpath = self._get_filepath(href)
        if not os.path.isfile(fpath):
            raise NotFoundError(href)
        actual_etag = self._get_etag_from_file(fpath)
        if etag != actual_etag:
            raise WrongEtagError(etag, actual_etag)
        os.remove(fpath)

    def get_meta(self, key):
        fpath = os.path.join(self.path, key)
        try:
            with open(fpath, 'rb') as f:
                return f.read().decode(self.encoding) or None
        except IOError as e:
            if e.errno == errno.ENOENT:
                return None
            else:
                raise

    def set_meta(self, key, value):
        value = value or u''
        assert isinstance(value, text_type)
        fpath = os.path.join(self.path, key)
        with atomic_write(fpath, mode='wb', overwrite=True) as f:
            f.write(value.encode(self.encoding))
