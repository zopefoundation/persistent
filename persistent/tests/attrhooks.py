##############################################################################
#
# Copyright (c) 2004 Zope Foundation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Overriding attr methods

Examples for overriding attribute access methods.
"""

from persistent import Persistent

def _resettingJar():
    from persistent.tests.utils import ResettingJar
    return ResettingJar()

def _rememberingJar():
    from persistent.tests.utils import RememberingJar
    return RememberingJar()


class OverridesGetattr(Persistent):
    """Example of overriding __getattr__
    """
    def __getattr__(self, name):
        """Get attributes that can't be gotten the usual way
        """
        # Don't pretend we have any special attributes.
        if name.startswith("__") and name.endswrith("__"):
            raise AttributeError(name) # pragma: no cover
        return name.upper(), self._p_changed


class VeryPrivate(Persistent):
    """Example of overriding __getattribute__, __setattr__, and __delattr__
    """
    def __init__(self, **kw):
        self.__dict__['__secret__'] = kw.copy()

    def __getattribute__(self, name):
        """Get an attribute value

        See the very important note in the comment below!
        """
        #################################################################
        # IMPORTANT! READ THIS! 8->
        #
        # We *always* give Persistent a chance first.
        # Persistent handles certain special attributes, like _p_
        # attributes. In particular, the base class handles __dict__
        # and __class__.
        #
        # We call _p_getattr. If it returns True, then we have to
        # use Persistent.__getattribute__ to get the value.
        #
        #################################################################
        if Persistent._p_getattr(self, name):
            return Persistent.__getattribute__(self, name)

        # Data should be in our secret dictionary:
        secret = self.__dict__['__secret__']
        if name in secret:
            return secret[name]

        # Maybe it's a method:
        meth = getattr(self.__class__, name, None)
        if meth is None:
            raise AttributeError(name)

        return meth.__get__(self, self.__class__)


    def __setattr__(self, name, value):
        """Set an attribute value
        """
        #################################################################
        # IMPORTANT! READ THIS! 8->
        #
        # We *always* give Persistent a chance first.
        # Persistent handles certain special attributes, like _p_
        # attributes.
        #
        # We call _p_setattr. If it returns True, then we are done.
        # It has already set the attribute.
        #
        #################################################################
        if Persistent._p_setattr(self, name, value):
            return

        self.__dict__['__secret__'][name] = value

        if not name.startswith('tmp_'):
            self._p_changed = 1

    def __delattr__(self, name):
        """Delete an attribute value
        """
        #################################################################
        # IMPORTANT! READ THIS! 8->
        #
        # We *always* give Persistent a chance first.
        # Persistent handles certain special attributes, like _p_
        # attributes.
        #
        # We call _p_delattr. If it returns True, then we are done.
        # It has already deleted the attribute.
        #
        #################################################################
        if Persistent._p_delattr(self, name):
            return

        del self.__dict__['__secret__'][name]

        if not name.startswith('tmp_'):
            self._p_changed = 1
