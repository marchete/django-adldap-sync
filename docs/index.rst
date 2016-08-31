.. django-adldap-sync documentation master file, created by
   sphinx-quickstart on Sun May  5 21:33:04 2013.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

django-adldap-sync documentation
==============================

django-adldap-sync provides a Django management command that synchronizes LDAP
users, groups and group memberships from Active Directory. 
It performs a one-way synchronization that creates and/or updates the local 
Django users, groups and memberships.

This synchronization is performed each time the management command is run and
can be fired manually on demand, via an automatic cron script or as a periodic
`Celery`_ task. 

It has an option to run an incremental synchronization, that reduces the sync 
time to seconds, even with large directories (+1500 users , +600 groups, +10000
group memberships).

Contents
--------

.. toctree::
   :maxdepth: 2

   installation
   settings
   changelog

Credits
-------

Forked from `jbittel/django-ldap-sync`_.

.. _Celery: http://www.celeryproject.org
.. _jbittel/django-ldap-sync: https://github.com/jbittel/django-ldap-sync
