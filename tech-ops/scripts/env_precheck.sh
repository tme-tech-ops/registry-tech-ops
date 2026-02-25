#!/bin/bash

if [[ $OFFLINE_MODE == "true" ]]; then
    echo "Offline mode detected."
    if [[ -z $OFFLINE_BINARY_URL || -z $OFFLINE_BINARY_USER || -z $OFFLINE_BINARY_PASSWORD ]]; then
        echo "OFFLINE_BINARY_URL, OFFLINE_BINARY_USER, or OFFLINE_BINARY_PASSWORD is missing."
        exit 1
    else
        echo "Downloading offline binary..."
        curl -sfLu $OFFLINE_BINARY_USER:$OFFLINE_BINARY_PASSWORD $OFFLINE_BINARY_URL -o ~/$(basename $OFFLINE_BINARY_URL)
        if [[ $? -ne 0 ]]; then 
            echo "Failed to download offline binary."
            exit 1
        fi
        echo "Extracting offline binary..."
        tar -xzf $(basename $OFFLINE_BINARY_URL) -C ~/
        if [[ $? -ne 0 ]]; then 
            echo "Failed to extract offline binary."
            exit 1
        fi
    fi
else
    echo "Online mode detected."
    if [[ -z $SCRIPT_URL ]]; then
        echo "SCRIPT_URL is missing."
        exit 1
    fi
    curl -sfL $SCRIPT_URL -o ~/$(basename $SCRIPT_URL)
    if [[ $? -ne 0 ]]; then 
        echo "Failed to download script."
        exit 1
    fi
    chmod +x ~/$(basename $SCRIPT_URL)
fi