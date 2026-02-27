#!/bin/bash

OFFLINE_PACKAGE_NAME="harbor-offline-package.tar.gz"
OFFLINE_PACKAGE_GENERATED="false"
OFFLINE_PACKAGE_UPLOADED="false"
OFFLINE_PACKAGE_URL="N/A"
HARBOR_RUNNING="false"
mgmt_ip=$(hostname -I | awk '{print $1}')
health_status=$(curl -s -o /dev/null -w "%{http_code}" -u "$HARBOR_USERNAME:$HARBOR_PASSWORD" -k "https://$mgmt_ip:$HARBOR_PORT/api/v2.0/projects?page_size=1")

ctx logger info "Post install check started."

if [[ $health_status -eq 200 ]]; then
  ctx logger info "Harbor is running."
  HARBOR_RUNNING="true"
  HARBOR_IP_URL="https://$mgmt_ip:$HARBOR_PORT"
  HARBOR_FQDN_URL="https://$COMMON_NAME:$HARBOR_PORT"
else
  ctx logger info "Harbor is not running."
  HARBOR_IP_URL="N/A"
  HARBOR_FQDN_URL="N/A"
  HARBOR_USERNAME="N/A"
  HARBOR_PASSWORD="N/A"
fi

if [[ -f "~/${OFFLINE_PACKAGE_NAME}" ]]; then
  ctx logger info "Offline package found."
  OFFLINE_PACKAGE_GENERATED="true"
  if [[ $UPLOAD_OFFLINE_PACKAGE == "true" ]]; then
    ctx logger info "Uploading offline package..."
    if [[ -z $UPLOAD_BASE_URL || -z $UPLOAD_OFFLINE_PACKAGE_USER || -z $UPLOAD_OFFLINE_PACKAGE_PASSWORD ]]; then
      ctx logger info "UPLOAD_BASE_URL, UPLOAD_OFFLINE_PACKAGE_USER, or UPLOAD_OFFLINE_PACKAGE_PASSWORD is missing."
      exit 1
    else
      OFFLINE_PACKAGE_URL="${UPLOAD_BASE_URL}/${OFFLINE_PACKAGE_NAME}"
      curl -ku "${UPLOAD_OFFLINE_PACKAGE_USER}:${UPLOAD_OFFLINE_PACKAGE_PASSWORD}" \
        -X POST $OFFLINE_PACKAGE_URL \
        -F "file=@~/${OFFLINE_PACKAGE_NAME}"
      if [[ $? -ne 0 ]]; then
        ctx logger info "Failed to upload offline package."
        exit 1
      fi
    fi
    OFFLINE_PACKAGE_UPLOADED="true"
    ctx logger info "Offline package uploaded to $OFFLINE_PACKAGE_URL."
  fi
else
  ctx logger info "Offline package not found."
  OFFLINE_PACKAGE_NAME="N/A"
fi

ctx logger info "Post install check completed."
ctx instance runtime-properties capabilities.offline_package_generated "$OFFLINE_PACKAGE_GENERATED"
ctx instance runtime-properties capabilities.offline_package_name "$OFFLINE_PACKAGE_NAME"
ctx instance runtime-properties capabilities.offline_package_uploaded "$OFFLINE_PACKAGE_UPLOADED"
ctx instance runtime-properties capabilities.offline_package_url "$OFFLINE_PACKAGE_URL"
ctx instance runtime-properties capabilities.harbor_running "$HARBOR_RUNNING"
ctx instance runtime-properties capabilities.harbor_ip_url "$HARBOR_IP_URL"
ctx instance runtime-properties capabilities.harbor_fqdn_url "$HARBOR_FQDN_URL"
ctx instance runtime-properties capabilities.harbor_username "$HARBOR_USERNAME"
ctx instance runtime-properties capabilities.harbor_password "$HARBOR_PASSWORD"

