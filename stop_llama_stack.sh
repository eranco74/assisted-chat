#!/bin/bash

#
# Stop llama-stack server script
# This script stops the llama-stack server that was started by setup.sh
#

echo "🛑 Stopping llama-stack server..."

# Check if PID file exists
if [ -f "llama_stack.pid" ]; then
    PID=$(cat llama_stack.pid)
    
    # Check if the process is running
    if ps -p $PID > /dev/null 2>&1; then
        echo "📋 Found llama-stack process with PID: $PID"
        
        # Kill the process
        kill $PID
        
        # Wait a bit and check if it's still running
        sleep 2
        if ps -p $PID > /dev/null 2>&1; then
            echo "⚠️  Process still running, force killing..."
            kill -9 $PID
        fi
        
        # Clean up PID file
        rm llama_stack.pid
        echo "✅ llama-stack server stopped successfully"
    else
        echo "⚠️  Process with PID $PID not found (may have already stopped)"
        rm llama_stack.pid
    fi
else
    echo "⚠️  No llama_stack.pid file found"
    echo "💡 Trying to find llama-stack processes..."
    
    # Try to find llama-stack processes
    PIDS=$(pgrep -f "llama stack run" || true)
    if [ -n "$PIDS" ]; then
        echo "🔍 Found llama-stack processes: $PIDS"
        echo "💀 Killing all llama-stack processes..."
        pkill -f "llama stack run"
        echo "✅ All llama-stack processes stopped"
    else
        echo "ℹ️  No llama-stack processes found"
    fi
fi

# Clean up log file if it exists
if [ -f "llama_stack.log" ]; then
    echo "🧹 Cleaning up log file..."
    rm llama_stack.log
fi

echo "🎉 Cleanup completed!" 