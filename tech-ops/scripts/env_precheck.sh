#!/bin/bash

if [[ ${OFFLINE_MODE,,} == "true" ]]; then
    ctx logger info "Offline mode detected."
    if [[ -z $OFFLINE_BINARY_URL || -z $OFFLINE_BINARY_USER || -z $OFFLINE_BINARY_PASSWORD ]]; then
        ctx logger info "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
        exit 1
    else
        ctx logger info "Downloading offline binary..."
        ctx logger info "curl -sfLu "$OFFLINE_BINARY_USER:$OFFLINE_BINARY_PASSWORD" $OFFLINE_BINARY_URL -o ~/$(basename $OFFLINE_BINARY_URL)"
        curl -skfLu "${OFFLINE_BINARY_USER}:${OFFLINE_BINARY_PASSWORD}" "${OFFLINE_BINARY_URL}" -o ~/$(basename $OFFLINE_BINARY_URL)
        if [[ $? -ne 0 ]]; then 
            ctx logger info "Failed to download offline binary."
            exit 1
        fi
        ctx logger info "Extracting offline binary..."
        tar -xzf $(basename $OFFLINE_BINARY_URL) -C ~/
        if [[ $? -ne 0 ]]; then 
            ctx logger info "Failed to extract offline binary."
            exit 1
        fi
        ctx logger info "Offline binary downloaded and extracted."
    fi
else
    ctx logger info "Online mode detected."
    if [[ -z $SCRIPT_URL ]]; then
        ctx logger info "SCRIPT_URL is missing."
        exit 1
    fi
    curl -skfL $SCRIPT_URL -o ~/$(basename $SCRIPT_URL)
    if [[ $? -ne 0 ]]; then 
        ctx logger info "Failed to download script."
        exit 1
    fi
    chmod +x ~/$(basename $SCRIPT_URL)
    ctx logger info "Install script downloaded and made executable."
fi