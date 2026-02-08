#!/bin/bash

echo "Restarting trading bot service..."

# Stop the service
./stop.sh

# Wait a moment
sleep 3

# Start the service
./start.sh
