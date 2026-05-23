# HW2-2 - Metrics
2026 NAP
lichen

## Goal
The primary objective of this lab is to establish a comprehensive monitoring ecosystem using the Cloud Native stack.
* Implement automated metric collection and storage using **Prometheus**
* Configure intelligent alerting thresholds with **Alertmanager**
* Construct high-fidelity observability dashboards through **Grafana**
* Gain hands-on experience with CRDs (Custom Resource Definitions) and Operator-based deployments in a Kubernetes environment

## Grading
* Metrics
  * Prometheus 50%
  * Alertmanager 25%
  * Grafana 25%
* Deadline
  * 2026-06-22 23:59:59

## Prerequisite
* Install `jq` and `yq` on your router

## Prometheus - Install
* Install prometheus using CRD (15%)
  * Prometheus Operator
  * Name: `prometheus`
  * Replicas: `2`
  * Namespace: `monitoring`
  * ServiceName: `prometheus-prometheus`
  * nodeport: `9090:30090`

## Prometheus - Target
* Monitor Target(15%)
  * kube-state-metrics
  * NodeExporter
  * Use service monitor to monitor Traefik

## Prometheus - Rule
* Prometheus Rule test(20%)
  * Traefik 404 5m > 100
  * alertname: `Traefik404TooHigh`

## Alertmanager - Install
* Install Alertmanger via CRD (10%)
  * Name: `alertmanager`
  * Replicas: `3`
  * Namespace: `monitoring`
  * ServiceName: `alertmanager-alertmanager`
  * nodeport: `9093:30093`

## Alertmanager - Config
* Config Alertmanager (15%)
  * `group_wait`: `1m`
  * `group_interval`: `1s`
  * `repeat_interval`: `1m`
  * `webhook_config`
    * `http://172.16.1.254:8000`

## Grafana - Install
* Install grafana (10%)
  * Name: `grafana`
  * Replicas: `1`
  * Namespace: `monitoring`
  * ServiceName: `grafana`
  * nodeport: `3000:30030`
  * `ANONYMOUS_ENABLED`
  * `ANONYMOUS_ORG_ROLE=Admin`

## Grafana - Config
* Config and Install dashboard (15%)
  * connect prometheus datasource
  * Mixin dashboard form kube-prometheus
  * traefik dashboard
    * https://grafana.com/grafana/dashboards/17347-traefik-official-kubernetes-dashboard/

## Good Luck!