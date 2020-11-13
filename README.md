# graylog-operator

## Description

Graylog operator for ingesting logs written for Juju and the Operator Framework. Graylog is a leading centralized log management solution built to open standards for capturing, storing, and enabling real-time analysis of terabytes of machine data.

## Usage

This graylog charm _must_ be deployed with Elasticsearch and MongoDB. The application will be in a blocked state if these two relations do not exist.

Install dependencies:
```bash
snap install microk8s --classic  # if microk8s is not on your system
# or
microk8s.reset  # if you already have microk8s

snap install charmcraft

snap install juju --classic
```

Initial setup (ensure microk8s is a clean slate with `microk8s.reset` or a fresh install with `snap install microk8s --classic`):
```bash
microk8s.enable dns storage registry dashboard
juju bootstrap microk8s mk8s
juju add-model lma
juju create-storage-pool operator-storage kubernetes storage-class=microk8s-hostpath
```

Deploy Graylog on its own:
```bash
git clone git@github.com:canonical/graylog-operator.git
cd graylog-operator
charmcraft build
juju deploy ./graylog.charm --config admin-password={CHOOSE_PASSWORD} --resource graylog-image=graylog/graylog:3.3.8-1
cd ..
```

Deploy the MongoDB and Elasticsearch dependencies
```bash
# mongodb
git clone git@github.com:canonical/mongodb-operator.git
cd mongodb-operator
charmcraft build
juju deploy ./mongodb.charm --resource mongodb-image=mongo:4.4.1 --num-units=3
cd ..

# elasticsearch
git clone git@github.com:canonical/elasticsearch-operator.git
cd elasticsearch-operator
charmcraft build
charmcraft build && juju deploy ./elasticsearch.charm
```

Relate Graylog to MongoDB and Elasticsearch so automatic configuration can take place
```bash
juju add-relation graylog mongodb
juju add-relation graylog elasticsearch
```

Use `watch -c juju status --color` to wait until everything has settled and is active and then visit: `{GRAYLOG_APP_IP}:9000` in your browser.

...

## Developing

Create and activate a virtualenv,
and install the development requirements,

    virtualenv -p python3 venv
    source venv/bin/activate
    pip install -r requirements-dev.txt

## Testing

Just run `run_tests`:

    ./run_tests
