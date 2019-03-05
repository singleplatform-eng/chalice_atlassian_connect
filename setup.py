"""
Chalice-AtlassianConnect
----------------------

This is a simple module to make creating atlassian connect based
plugins backed by AWS chalice easier

Forked from Flask-AtlassianConnect:
See https://halkeye.github.io/flask_atlassian_connect/ for docs
"""
import io
import re

from setuptools import find_packages, setup

init_py = io.open('chalice_atlassian_connect/__init__.py').read()
metadata = dict(re.findall("__([a-z]+)__ = '([^']+)'", init_py))

setup(
    name='Chalice-AtlassianConnect',
    version=metadata['version'],
    description="Atlassian Connect Helper",
    long_description=__doc__,
    author=metadata['author'],
    author_email=metadata['email'],
    url=metadata['url'],
    license=open('LICENSE.md').read(),
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    platforms='any',
    install_requires=io.open('requirements/runtime.txt').readlines(),
    setup_requires=['pytest-runner'],
    keywords=['atlassian connect', 'chalice', 'jira', 'confluence'],
    tests_require=[x for x in io.open(
        'requirements/dev.txt').readlines() if not x.startswith('-')],
    classifiers=[
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: Implementation :: PyPy",
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules'
    ]
)
