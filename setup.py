# -*- coding: utf-8 -*-
import ast
import re

from setuptools import setup

_version_re = re.compile(r'__version__\s+=\s+(.*)')

with open('vdir/__init__.py', 'rb') as f:
    version = str(ast.literal_eval(_version_re.search(
        f.read().decode('utf-8')).group(1)))

setup(
    name='vdir',
    version=version,
    description='Minimal interface for reading and writing from/to vdirs.',
    author='Markus Unterwaditzer',
    author_email='markus@unterwaditzer.net',
    url='https://github.com/vdirsyncer/python-vdir',
    license='MIT',
    packages=['vdir'],
    long_description=open('README.rst').read(),
    install_requires=['atomicwrites'],
    include_package_data=True,
)
