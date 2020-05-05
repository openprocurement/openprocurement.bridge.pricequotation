[![Coverage Status](https://coveralls.io/repos/github/openprocurement/openprocurement.bridge.pricequotation/badge.svg)](https://coveralls.io/github/openprocurement/openprocurement.bridge.pricequotation)
[![Build Status](https://travis-ci.com/openprocurement/openprocurement.bridge.pricequotation.svg?branch=master)](https://travis-ci.com/openprocurement/openprocurement.bridge.pricequotation)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)


openprocurement.bridge.pricequotation
=====================================

Bot for Price Quotation procedure in eCatalogues which watching for tenders in `draft.publishing` and verify,
fill additional information from eCatalogues, such as:

```
- items[*].unit
- items[*].classification
- items[*].additionalClassifications
- shortlistedFirms
- criteria
- value

```

And switch tender to `active.tendering` status and switch to `draft.unsuccessful` if bot receive `HTTP 404` from eCatalogues or shortlistedFirms list will be empty.

## Development

```bash
$ git clone git@gitlab.qg:pricequotation/openprocurement.bridge.pricequotation.git
$ virtualenv -p python .venv
$ source .venv/bin/activate
$ pip install -r requirements-dev.txt
$ pip install -e .
```

## Run tests
```
$ pytest openprocurement/bridge/pricequotation/tests/ --cov=openprocurement/bridge/pricequotation
```

## How to use

```bash
$ databrige configuration.yaml
```