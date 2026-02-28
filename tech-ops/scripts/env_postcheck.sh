#!/bin/bash

OFFLINE_PACKAGE_NAME="harbor-offline-package.tar.gz"
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

if [[ -f ~/"${OFFLINE_PACKAGE_NAME}" ]]; then
  ctx logger info "Offline package found."
  if [[ $UPLOAD_OFFLINE_PACKAGE == "true" ]]; then
    ctx logger info "Uploading offline package..."
    new_offline_package_name="$(date +%Y%m%d%H%M)-${OFFLINE_PACKAGE_NAME}"
    mv ~/"${OFFLINE_PACKAGE_NAME}" ~/"${new_offline_package_name}"
    if [[ -z $UPLOAD_BASE_URL || -z $UPLOAD_OFFLINE_PACKAGE_USER || -z $UPLOAD_OFFLINE_PACKAGE_PASSWORD ]]; then
      ctx logger info "UPLOAD_BASE_URL, UPLOAD_OFFLINE_PACKAGE_USER, or UPLOAD_OFFLINE_PACKAGE_PASSWORD is missing."
      exit 1
    else
      OFFLINE_PACKAGE_URL="${UPLOAD_BASE_URL}/${new_offline_package_name}"
      curl -ku "${UPLOAD_OFFLINE_PACKAGE_USER}:${UPLOAD_OFFLINE_PACKAGE_PASSWORD}" \
        -X POST $OFFLINE_PACKAGE_URL \
        -F "file=@$HOME/${new_offline_package_name}"
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
if [[ $UPLOAD_OFFLINE_PACKAGE == "true" ]]; then
  ctx instance runtime-properties capabilities.offline_package_name "$OFFLINE_PACKAGE_NAME"
else
  ctx instance runtime-properties capabilities.offline_package_name "$new_offline_package_name"
fi
ctx instance runtime-properties capabilities.offline_package_uploaded "$OFFLINE_PACKAGE_UPLOADED"
ctx instance runtime-properties capabilities.offline_package_url "$OFFLINE_PACKAGE_URL"
ctx instance runtime-properties capabilities.harbor_running "$HARBOR_RUNNING"
ctx instance runtime-properties capabilities.harbor_ip_url "$HARBOR_IP_URL"
ctx instance runtime-properties capabilities.harbor_fqdn_url "$HARBOR_FQDN_URL"
ctx instance runtime-properties capabilities.harbor_username "$HARBOR_USERNAME"
ctx instance runtime-properties capabilities.harbor_password "$HARBOR_PASSWORD"

