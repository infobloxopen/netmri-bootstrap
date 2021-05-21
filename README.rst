===============================
README: NetMRI Bootstrap
===============================

.. image:: https://img.shields.io/pypi/v/netmri-bootstrap.svg
        :target: https://pypi.python.org/pypi/netmri-bootstrap

.. image:: https://codecov.io/github/infobloxopen/netmri-bootstrap/coverage.svg?branch=master
        :target: https://codecov.io/github/infobloxopen/netmri-bootstrap?branch=master

.. image:: https://readthedocs.org/projects/netmri-bootstrap/badge/?version=latest
        :target: http://netmri-bootstrap.readthedocs.org/en/latest/?badge=latest

.. image:: https://travis-ci.org/infobloxopen/netmri-bootstrap.svg?branch=master
    :target: https://travis-ci.org/infobloxopen/netmri-bootstrap

Bootstrap Framework to facilitate development on NetMRI

* Free software: Apache license
* Documentation: https://netmri-bootstrap.readthedocs.org.

Intent
------------
The goal of NetMRI-bootstrap is to be a framework that allows you to easily write, maintain and run scripts
and policies on NetMRI. The workflow would be that you clone this project so it can access your NetMRI instance
and place your scripts in the relevant folder.



Installation
------------

Install netmri-bootstrap using pip:

::

  pip3 install netmri-bootstrap

Once installed:

::

  cd ~/.local/lib/python3.8/site-packages/netmri_bootstrap
  
  cp config.json.in config.json
  
  nano config.json


::

  {
    "host": "192.168.0.201",
    "username": "admin",
    "password": "infoblox",
    "proto": "http",
    "ssl_verify": false,
    "scripts_root": "/home/sbaksh/bootstrap",
    "bootstrap_branch": "master",
    "skip_readonly_objects": true,
    "class_paths": {
        "Script": "scripts",
        "ScriptModule": "script_modules",
        "ConfigList": "lists",
        "PolicyRule": "policy/rules",
        "Policy": "policy",
        "ConfigTemplate": "config_templates",
        "CustomIssue": "custom_issues"
    }   
  }
