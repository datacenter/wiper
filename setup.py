"""wiper setup.py."""

import os
from setuptools import setup, find_packages

with open('LICENSE.txt') as f:
    LICENSE = f.read()

__version__ = '1.0.0'
VERSION = open(os.path.join('wiper', 'version.py')).read()
print VERSION
# pylint:disable=exec-used
exec(VERSION)

PKGNAME = 'wiper'
URL = 'https://github.com/datacenter/' + PKGNAME
DOWNLOADURL = URL + '/releases/tag/' + str(__version__)


setup(
    name=PKGNAME,
    version=__version__,
    description=('Wipe the APIC config and reprovision APICs.'),
    long_description=open('README.rst').read(),
    packages=find_packages(),
    url='https://github.com/datacenter/wiper',
    download_url=DOWNLOADURL,
    license=LICENSE,
    author='Mike Timm',
    author_email='mtimm@cisco.com',
    zip_safe=False,
    install_requires=[
        'paramiko',
        'transitions',
        'paramiko-expect',
        # 'git+https://github.com/fgimian/paramiko-expect.git',
        # 'git+https://github.com/tyarkoni/transitions.git'
    ],
    dependency_links=[
        'http://github.com/fgimian/paramiko-expect/tarball/master#egg=paramiko-expect',
        'https://github.com/paramiko/paramiko/tarball/master#egg=paramiko'
    ],
    classifiers=(
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
    ),
    scripts=[os.path.join('wiper', 'wiper.py')],
    entry_points={
        "console_scripts": [
            "apic_wiper=wiper:main",
            "wiper=wiper:main",
        ],
    }
)
