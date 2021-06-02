# graylog-operator

## Description

Graylog operator for ingesting logs written for Juju and the Operator Framework. Graylog is a leading centralized log management solution built to open standards for capturing, storing, and enabling real-time analysis of terabytes of machine data.

## Usage

This graylog charm _must_ be deployed with Elasticsearch and MongoDB. The application will be in a blocked state if these two relations do not exist.

Deploy Graylog on its own:
```bash
juju deploy graylog-k8s
```

Deploy the MongoDB and Elasticsearch dependencies
```bash
# mongodb
juju deploy mongodb-k8s
juju deploy elasticsearch-k8s
```

Relate Graylog to MongoDB and Elasticsearch so automatic configuration can take place
```bash
juju add-relation graylog-k8s mongodb-k8s
juju add-relation graylog-k8s elasticsearch-k8s
```

Use `watch -c juju status --color` to wait until everything has settled and is active and then visit: `{GRAYLOG_APP_IP}:9000` in your browser.

...


## Testing

Just run `run_tests`:

    ./run_tests
