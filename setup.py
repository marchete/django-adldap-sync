#!/usr/bin/env python

from setuptools import find_packages
from setuptools import setup

from adldap_sync import __version__ as version


with open('README.md') as f:
    readme = f.read()

setup(
    name='django-adldap-sync',
    version=version,
    description='A Django application for synchronizing LDAP users, groups and group memberships',
    long_description=readme,
    license='BSD',
    author='Marchete',
    author_email='undisclosed@gmail.com',
    url='https://github.com/marchete/django-adldap-sync',
    download_url='https://github.com/marchete/django-adldap-sync',
    packages=find_packages(),
    include_package_data=True,
    install_requires=['pyldap>=2.4.25.1'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Web Environment',
        'Programming Language :: Python',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: System :: Systems Administration :: Authentication/Directory',
    ],
    keywords=['django', 'ldap', 'active directory', 'synchronize', 'sync'],
)
