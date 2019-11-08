#!/usr/bin/env python
# -*- coding: utf-8 -*-


try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read().replace('.. :changelog:', '')

with open('requirements.txt') as requirements_file:
    requirements = requirements_file.read().splitlines()

with open('testing_requirements.txt') as requirements_file:
    testing_requirements = requirements_file.read().splitlines()


setup(
    name='netmri-bootstrap',
    version='0.0.1',
    description="Bootstrapper for interaction with NetMRI",
    long_description=readme + '\n\n' + history,
    long_description_content_type='text/x-rst',
    author="Ingmar Van Glabbeek",
    author_email='ingmar@infoblox.com',
    url='https://github.com/infobloxopen/netmri-bootstrap',
    packages=[
        'netmri-bootstrap',
    ],
    package_dir={'netmri-bootstrap':
                 'netmri-bootstrap'},
    include_package_data=True,
    install_requires=requirements,
    license="Apache",
    zip_safe=False,
    keywords='netmri-bootstrap',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    tests_require=testing_requirements
)
