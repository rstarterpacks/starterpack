from __future__ import print_function
#### BEGIN MOCKING REDDIT PACKAGE
import sys

try:
    import rcssmin
except ImportError:
    raise RuntimeError("rcssmin.py not downloaded from github@reddit/reddit")

class _i18n(object):
    @staticmethod
    def N_(arg):
        return str(arg)

    _ = N_

class _pylons(object):
    i18n = _i18n()

class _utils(object):
    @staticmethod
    def tup(item, ret_is_single=False): 
        if hasattr(item, '__iter__'): 
            return (item, False) if ret_is_single else item 
        return ((item,), True) if ret_is_single else (item,) 

class _contrib(object):
    rcssmin = rcssmin
    
class _lib(object):
    utils = _utils()
    contrib = _contrib()

class _r2(object):
    lib = _lib()
    
sys.modules['pylons'] = _pylons()
sys.modules['pylons.i18n'] = sys.modules['pylons'].i18n
sys.modules['r2'] = _r2()
sys.modules['r2.lib'] = sys.modules['r2'].lib
sys.modules['r2.lib.utils'] = sys.modules['r2.lib'].utils
sys.modules['r2.lib.contrib'] = sys.modules['r2.lib'].contrib

try:
    unicode
except NameError:
    unicode = str

#### END MOCK

from pylons.i18n import _
import ast
import cssfilter
import os
import praw
import rcssmin
import re
import tinycss2

IMAGE_ERROR_MESSAGES = {
    'BAD_CSS_NAME'   : _('bad image name'),
    'INVALID'        : _('Invalid image or general error'),
    'INVALID_INFO'   : _('Invalid image or general error - %(info)s'),
    'TOO_MANY'       : _('too many images (you only get %(num)d)'),
    'TOO_BIG'        : _('too big. keep it under %(num)d KiB'),
    'TOO_SMALL'      : _('%(type)s image is too small'),
}

IMAGE_CHECKS = type('Enum', (), {
    'REGEX'          : re.compile(r"\A[a-zA-Z0-9\-]{1,100}\Z"),
    'PNG_HEADER'     : praw.PNG_HEADER,
    'JPEG_HEADER'    : praw.JPEG_HEADER,
    'MIN_PNG_SIZE'   : praw.MIN_PNG_SIZE,
    'MIN_JPEG_SIZE'  : praw.MIN_JPEG_SIZE,
    'MAX_IMAGE_SIZE' : praw.MAX_IMAGE_SIZE,
})

class ImageError(cssfilter.ValidationError):
    def __init__(self, name, error_code, message_params=None):
        self.name = name
        self.error_code = error_code
        self.message_params = message_params or {}

    @property
    def message_key(self):
        return IMAGE_ERROR_MESSAGES[self.error_code]


class CSSError(object):
    def __init__(self, validation_or_image_error):
        self.error = validation_or_image_error

    @property
    def message(self):
        return _(self.error.message_key) % self.error.message_params


class CSSErrorSet(Exception):
    def __init__(self, errors):
        self.errors = errors
        self.__format_errors()

    def __str__(self):
        retstr = "List of css errors:\n    "
        return retstr + '\n    '.join(self.errors)

    def __format_errors(self):
        stringed_errors = []
        for e in self.errors:
            error = []
            if hasattr(e.error, 'line'):
                error.append('[line {0}]'.format(e.error.line))
            if isinstance(e.error, ImageError):
                error.append('[image {0}]'.format(e.error.name))
                error.append('{0}:'.format(e.error.error_code))
            error.append(e.message)
            if hasattr(e.error, "offending_line"):
                error.append(e.error.offending_line)
            stringed_errors.append(" ".join(error))
        self.errors = stringed_errors


def _force_unicode(text):
    if text is None:
        return u''

    if isinstance(text, unicode):
        return text

    try:
        text = unicode(text, 'utf-8')
    except UnicodeDecodeError:
        text = unicode(text, 'latin1')
    except TypeError:
        text = unicode(text)
    return text


def _uri_substitute(match):
    return "url(%%{0}%%)".format(
        os.path.splitext(os.path.split(match.groups()[1])[-1])[0])


def validate_images(image_dict):
    reterrors = []
    if len(image_dict) > 50:
        reterrors.append(ImageError(None, 'TOO_MANY', {'num': 50}))
    for name, path in image_dict.iteritems():
        if not IMAGE_CHECKS.REGEX.match(name):
            reterrors.append(ImageError(name, 'BAD_CSS_NAME'))
        try:
            with open(path, 'rb') as image_file:
                bytes = image_file.read()
                size = os.path.getsize(image_file.name)
                if bytes.startswith(IMAGE_CHECKS.PNG_HEADER):
                    if size < IMAGE_CHECKS.MIN_PNG_SIZE:
                        reterrors.append(ImageError(name, 'TOO_SMALL',
                                                    {'type': 'png'}))
                elif bytes.startswith(IMAGE_CHECKS.JPEG_HEADER):
                    if size < IMAGE_CHECKS.MIN_JPEG_SIZE:
                        reterrors.append(ImageError(name, 'TOO_SMALL',
                                                    {'type': 'jpeg'}))
                else:
                    reterrors.append(ImageError(name, 'INVALID_INFO',
                                                {'info': 'not jpeg or png'}))
                if size > IMAGE_CHECKS.MAX_IMAGE_SIZE:
                    reterrors.append(ImageError(name, 'TOO_BIG'))
        except (IOError, TypeError):
            reterrors.append(ImageError(name, 'INVALID'))
    return reterrors

def validate(replace_image_uris=ast.literal_eval(
                 os.getenv('replace_image_uris', 'False')),
             minify=ast.literal_eval(
                 os.getenv('minify', 'False'))):
    images = {os.path.splitext(image)[0]: os.path.join(
                  os.getenv('imgdir', 'images'), image
              ) for image in os.listdir(os.getenv('imgdir', 'images'))}
    image_errors = validate_images(images)
    with open(os.getenv('cssfile', 'stylesheet.css'), 'r+') as f:
        if replace_image_uris:
            to_write = re.sub(r"url\(('|\")(.+?)('|\")\)", _uri_substitute,
                              f.read())
            f.seek(0); f.write(to_write); f.truncate(); f.seek(0)
        data = f.read()
        parsed, errors = cssfilter.validate_css(_force_unicode(data), images)
        errors.extend(image_errors)
        errors = [CSSError(error) for error in errors]
        if errors:
            raise CSSErrorSet(errors)
        if minify:
            to_write = re.sub(
                r"url\(('|\")%%([a-zA-Z0-9\-]{1,100})%%('|\")\)",
                'url(%%\g<2>%%)',
                tinycss2.serialize(tinycss2.parse_stylesheet(data))
            )
            if minify >= 2:
                to_write = rcssmin.cssmin(to_write)
            f.seek(0); f.write(to_write); f.truncate()

if __name__ == '__main__':
    validate()