# graylog-operator

## Description

Graylog operator for ingesting logs.

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

Initial setup (ensure microk8s is a clean slate with `microk8s.reset` or a fresh install with `snap install microk8s --classic`:
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
juju deploy ./graylog.charm --resouce graylog-image=graylog/graylog:3.3.8-1
```


### Scale Out Usage

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
