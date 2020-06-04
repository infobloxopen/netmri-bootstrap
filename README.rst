=============================================
WARNING: DO NOT USE THIS ON PRODUCTION SYSTEM
=============================================
This code is in early stage of development. I wouldn't even call it a pre-alpha in its current state. Maybe a prototype. Probably, unfinished prototype.

Nothing here is in its final form. Expect dramatic changes in program structure.

===============================
README: NetMRI Bootstrap
===============================

.. image:: https://travis-ci.org/infobloxopen/netmri-bootstrap.svg?branch=master
        :target: https://travis-ci.org/infobloxopen/netmri-bootstrap

.. image:: https://img.shields.io/pypi/v/netmri-bootstrap.svg
        :target: https://pypi.python.org/pypi/netmri-bootstrap

.. image:: https://codecov.io/github/infobloxopen/netmri-bootstrap/coverage.svg?branch=master
        :target: https://codecov.io/github/infobloxopen/netmri-bootstrap?branch=master

.. image:: https://readthedocs.org/projects/netmri-bootstrap/badge/?version=latest
        :target: http://netmri-bootstrap.readthedocs.org/en/latest/?badge=latest

Bootstrap Framework to facilitate development on NetMRI

* Free software: Apache license
* Documentation: https://netmri-bootstrap.readthedocs.org.

Intent
------------
The goal of NetMRI-bootstrap is to be a framework that allows you to easily write, maintain and run scripts
and policies on NetMRI. The workflow would be that you clone this project so it can access your NetMRI instance
and place your scripts in the relevant folder.

todo:

* netmri-bootstrap/deploy.py: deployment script
* inclusion of netmri-easy
* addition of some example scripts


Installation
------------

Once the project is in a more ready state it will be available through pip.

Install netmri-bootstrap using pip:

::

  pip install netmri-bootstrap

Usage
-----

Configure logger prior to loading netmri-bootstrap to get all debug messages in console:

.. code:: python

  import logging
  logging.basicConfig(level=logging.DEBUG)

TBD
~~~

