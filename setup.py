import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name='openimis-be-core',
    version='1.2.0-rc1',
    packages=find_packages(),
    include_package_data=True,
    license='GNU AGPL v3',
    description='The openIMIS Backend Core reference module.',
    # long_description=README,
    url='https://openimis.org/',
    author='Xavier Gillmann',
    author_email='xgillmann@bluesquarehub.com',
    install_requires=[
        'django',
        'django-db-signals',
        'djangorestframework',
        'cached-property',
        'nepalicalendar',
    ],   
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django',
        'Framework :: Django :: 2.1',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Affero General Public License v3',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
)